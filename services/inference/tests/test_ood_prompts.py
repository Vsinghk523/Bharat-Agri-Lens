"""Regression tests for the OOD gate's prompt set and committed assets.

These exist because of two production failures, both of which shipped
green and were only found by a human retesting photos by hand.

1. The prompt set claimed crops the served model could not classify.
   Generated from the 20-crop baseline while production served the
   14-crop PlantVillage model, CLIP waved Wheat, Rice, Cotton, Mango and
   Brinjal through as TARGET; the classifier, having no class for any of
   them, returned the nearest label it did have. A wheat leaf-rust photo
   came back "Corn, fungal, 100%".

2. Crops described by whole-plant framings only. Wheat offered CLIP
   "wheat plants in a field" and "wheat ear close-up" but nothing about a
   leaf, while Corn had "maize leaves close-up". Since this app receives
   leaf close-ups almost exclusively, a wheat leaf matched the corn
   prompt and was diagnosed as corn. Fixing (1) alone changed nothing,
   because the wheat rows had never been in contention.

Both are invariant violations, not modelling errors, and both are
checkable without a GPU, a network call, or an image. That is what these
tests do. They are deliberately cheap so they can gate every push.

On fixtures
-----------
Image-level tests live in ``test_ood_gate_images.py`` and skip unless
fixtures are present. We do not commit wheat / rose / cat photographs:
they are third-party images with unclear licensing for redistribution in
a public repo, they add binary weight to every clone, and the tests
needing them cannot run in CI anyway without the ONNX encoder and a model
download. Structural invariants catch the class of bug; the image tests
confirm a specific instance when someone has fixtures to hand.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from app.ood_prompts import (
    CROP_PHRASINGS,
    NON_PLANT_SUBJECTS,
    NON_TARGET_PLANTS,
    RETIRED_PROMPT_LABELS,
    all_prompts,
    known_crop_labels,
    unservable_crops,
)

ASSETS = Path(__file__).resolve().parent.parent / "app" / "clip_assets"
PROMPTS_JSON = ASSETS / "clip_prompts.json"
EMBEDDINGS_NPY = ASSETS / "clip_text_embeddings.npy"

# The label set the production model actually serves, per the
# real_predictor_loaded log line (crops=14). Kept explicit rather than
# imported from a training config: the whole point of failure (1) was a
# config drifting away from what is served.
SERVED_14 = [
    "Apple", "Blueberry", "Cherry", "Corn", "Grape", "Orange", "Peach",
    "Pepper", "Potato", "Raspberry", "Soybean", "Squash", "Strawberry",
    "Tomato",
]

LEAF_WORDS = ("leaf", "leaves", "blade", "foliage")


# ---------------------------------------------------------------------
# Prompt-set invariants
# ---------------------------------------------------------------------

@pytest.mark.parametrize("crop,phrasings", CROP_PHRASINGS, ids=[c for c, _ in CROP_PHRASINGS])
def test_every_crop_describes_its_leaf(crop: str, phrasings: list[str]) -> None:
    """Each crop must offer CLIP at least one leaf-level phrasing.

    This is the invariant failure (2) violated. Users photograph a leaf,
    so a crop described only by its field, its fruit or its ear has no
    row that can win on the images this app actually receives — its
    photos land on some other crop's leaf prompt instead.
    """
    assert any(
        any(w in p.lower() for w in LEAF_WORDS) for p in phrasings
    ), (
        f"{crop} has no leaf-level phrasing: {phrasings}. Users photograph "
        f"leaves; a crop with no leaf prompt will lose its own images to "
        f"another crop's leaf prompt. Add e.g. '{crop.lower()} leaves close-up'."
    )


def test_phrasing_count_is_uniform_across_crops() -> None:
    """Every crop contributes the same number of rows.

    The gate decides on per-category probability SUMS, so a crop with
    extra rows raises its whole category's mass for every image, not just
    for its own. Uniform counts keep the comparison about similarity
    rather than about row count.
    """
    counts = {crop: len(p) for crop, p in CROP_PHRASINGS}
    distinct = set(counts.values())
    assert len(distinct) == 1, (
        f"crops have differing phrasing counts: {counts}. Category scores "
        f"are sums, so uneven counts bias whole categories."
    )


def test_no_crop_agnostic_prompts() -> None:
    """No prompt may describe a generic plant or leaf without naming it.

    A crop-agnostic row carries no information about whether the subject
    is in coverage, so wherever it is filed it only adds constant bias to
    that category. Three such rows ("a close-up of a diseased leaf" and
    friends) previously sat in TARGET and made non_target_plant
    effectively unreachable, disabling the LLM fallback.
    """
    named = {c.lower() for c in known_crop_labels()}
    generic_markers = ("crop leaf", "a plant leaf", "a diseased leaf", "a green crop")

    for record in all_prompts(served_crop_labels=SERVED_14):
        text = record["text"].lower()
        if any(marker in text for marker in generic_markers):
            assert any(n in text for n in named), (
                f"prompt {record['text']!r} describes a leaf generically without "
                f"naming a crop. Such a row biases category {record['category']} "
                f"on every image. Name the crop or drop the prompt."
            )


def test_retired_labels_are_gone_from_source() -> None:
    for crop, _ in CROP_PHRASINGS:
        assert crop not in RETIRED_PROMPT_LABELS
    for label, _ in NON_TARGET_PLANTS + NON_PLANT_SUBJECTS:
        assert label not in RETIRED_PROMPT_LABELS


# ---------------------------------------------------------------------
# TARGET derivation — failure (1)
# ---------------------------------------------------------------------

def test_target_set_equals_served_set_exactly() -> None:
    """TARGET must be precisely what the model can classify.

    A TARGET crop the model lacks is a confident-wrong diagnosis with no
    escalation. A NON_TARGET crop the model has is a needless LLM call.
    """
    prompts = all_prompts(served_crop_labels=SERVED_14)
    target = {p["label"] for p in prompts if p["category"] == "TARGET"}
    assert target == set(SERVED_14), (
        f"TARGET {sorted(target)} != served {sorted(SERVED_14)}; "
        f"extra={sorted(target - set(SERVED_14))}, "
        f"missing={sorted(set(SERVED_14) - target)}"
    )


def test_unservable_crops_are_non_target_and_keep_their_label() -> None:
    """Out-of-coverage crops route to the LLM *and* stay nameable.

    Demoting a crop must not anonymise it — "looks like wheat" is what
    makes the rejection useful to the farmer and gives the LLM its hint.
    """
    prompts = all_prompts(served_crop_labels=SERVED_14)
    for crop in unservable_crops(SERVED_14):
        cats = {p["category"] for p in prompts if p["label"] == crop}
        assert cats == {"NON_TARGET"}, f"{crop} should be NON_TARGET, got {cats}"


def test_no_served_labels_marks_everything_target() -> None:
    """The legacy behaviour is preserved but must remain explicit.

    This is the configuration that caused failure (1); it stays available
    for offline tooling with no bundle to consult, and is asserted here so
    nobody "fixes" it into something subtler.
    """
    prompts = all_prompts(served_crop_labels=None)
    target = {p["label"] for p in prompts if p["category"] == "TARGET"}
    assert target == set(known_crop_labels())


def test_served_label_matching_is_case_insensitive() -> None:
    """Label casing has drifted between training configs and exports."""
    prompts = all_prompts(served_crop_labels=["tomato", "CORN", "  Grape  "])
    target = {p["label"] for p in prompts if p["category"] == "TARGET"}
    assert target == {"Tomato", "Corn", "Grape"}


# ---------------------------------------------------------------------
# Committed artefact integrity
# ---------------------------------------------------------------------

@pytest.fixture(scope="module")
def committed() -> tuple[dict, np.ndarray]:
    meta = json.loads(PROMPTS_JSON.read_text(encoding="utf-8"))
    return meta, np.load(EMBEDDINGS_NPY)


def test_committed_rows_align_with_embeddings(committed) -> None:
    meta, emb = committed
    assert len(meta["prompts"]) == emb.shape[0], (
        "clip_prompts.json and clip_text_embeddings.npy disagree on row count. "
        "They are a matched pair — regenerate both with "
        "scripts/precompute_clip_embeddings.py."
    )


def test_committed_embeddings_are_l2_normalised(committed) -> None:
    """Runtime treats cosine similarity as a plain dot product."""
    _, emb = committed
    norms = np.linalg.norm(emb, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-4), f"norms range {norms.min()}..{norms.max()}"


def test_committed_artefact_records_its_served_labels(committed) -> None:
    """Provenance: which model's label space was this built against?"""
    meta, _ = committed
    assert meta.get("served_crop_labels"), (
        "clip_prompts.json has no served_crop_labels. Regenerate with "
        "--labels so the artefact records what it was built for."
    )


def test_committed_artefact_matches_current_source(committed) -> None:
    """The committed assets must not lag ood_prompts.py.

    Drift here is silent: the runtime guard repairs categories in memory,
    so a stale artefact degrades quietly rather than failing loudly. This
    test is the loud failure.
    """
    meta, _ = committed
    expected = all_prompts(served_crop_labels=meta["served_crop_labels"])
    committed_rows = [(p["text"], p["category"], p["label"]) for p in meta["prompts"]]
    expected_rows = [(p["text"], p["category"], p["label"]) for p in expected]
    assert committed_rows == expected_rows, (
        "committed clip assets are out of date with ood_prompts.py. "
        "Re-run: python scripts/precompute_clip_embeddings.py --labels <bundle>/labels.json"
    )


def test_committed_artefact_has_no_retired_labels(committed) -> None:
    meta, _ = committed
    present = {p["label"] for p in meta["prompts"]}
    assert not (present & RETIRED_PROMPT_LABELS), (
        f"retired labels still in committed artefact: "
        f"{sorted(present & RETIRED_PROMPT_LABELS)}"
    )
