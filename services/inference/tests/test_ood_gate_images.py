"""End-to-end OOD gate checks against real photographs.

Skipped unless fixture images are present. They are not committed:
they are third-party photographs whose redistribution licence in a public
repo is unclear, they add binary weight to every clone, and the tests
cannot run in CI regardless — the gate needs the CLIP ONNX encoder, which
is downloaded from HF Hub on first use rather than vendored.

The structural invariants in ``test_ood_prompts.py`` are the CI gate and
catch the class of bug. This file confirms specific instances when a
developer has the images to hand, and is the check to run after any
prompt edit.

Setup
-----
Drop images into ``tests/fixtures/`` (gitignored) named for what they
are, then run pytest normally::

    tests/fixtures/
      wheat-rust.jpg      out-of-coverage crop  -> non_target_plant
      rose.jpg            ornamental            -> non_target_plant
      cat.jpg             not a plant           -> not_a_plant
      tomato.jpg          in-coverage crop      -> accepted

Only the files you provide are exercised; the rest skip. First run
downloads the CLIP encoder (~85 MB).

Why these four
--------------
They span the gate's decision surface. wheat-rust is the regression that
started this: a crop the model cannot classify, whose leaf photo was
being admitted as Corn. rose is the case the gate was built for. cat
verifies NON_PLANT still separates from NON_TARGET, since those two route
differently — NON_TARGET escalates to the LLM, NON_PLANT must not. And
tomato is the control: a fix that rejects everything would pass the first
three and be useless.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.config import Settings
from app.ood import TARGET_WIN_MARGIN, check_image_quality, get_clip_gate

FIXTURES = Path(__file__).resolve().parent / "fixtures"

SERVED_14 = [
    "Apple", "Blueberry", "Cherry", "Corn", "Grape", "Orange", "Peach",
    "Pepper", "Potato", "Raspberry", "Soybean", "Squash", "Strawberry",
    "Tomato",
]

# filename -> (expected ok, expected reason, expected label or None)
CASES = [
    ("wheat-rust.jpg", False, "non_target_plant", "Wheat"),
    ("rose.jpg", False, "non_target_plant", None),
    ("cat.jpg", False, "not_a_plant", None),
    ("tomato.jpg", True, None, None),
]


@pytest.fixture(scope="module")
def gate():
    """The gate as production builds it — served labels included.

    Passing SERVED_14 is not optional dressing. Without it every
    catalogued crop is TARGET, which is a configuration production does
    not run, and the wheat case would pass the gate and fail this test
    for the wrong reason.
    """
    pytest.importorskip("onnxruntime", reason="gate needs the ml extra")
    try:
        return get_clip_gate(Settings(), served_crop_labels=SERVED_14)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"CLIP encoder unavailable (offline?): {exc}")


@pytest.mark.parametrize("filename,expect_ok,expect_reason,expect_label", CASES)
def test_gate_verdict(gate, filename, expect_ok, expect_reason, expect_label) -> None:
    path = FIXTURES / filename
    if not path.exists():
        pytest.skip(f"no fixture at {path} — see this module's docstring")

    data = path.read_bytes()
    assert check_image_quality(data) is None, (
        f"{filename} failed the photometric layer, so this test cannot reach "
        f"the CLIP layer it is meant to exercise. Use a sharper fixture."
    )

    verdict = gate.gate(data)
    cat = verdict["category_probs"]
    margin = cat["TARGET"] - cat["NON_TARGET"] - cat["NON_PLANT"]
    detail = (
        f"{filename}: ok={verdict['ok']} reason={verdict['reason']} "
        f"label={verdict['winning_label']} margin={margin:+.4f} "
        f"(threshold {TARGET_WIN_MARGIN:+.4f}) probs={cat}"
    )

    assert verdict["ok"] is expect_ok, detail
    if expect_reason is not None:
        assert verdict["reason"] == expect_reason, detail
    if expect_label is not None:
        assert verdict["winning_label"] == expect_label, detail


def test_wheat_beats_corn_on_its_own_leaf(gate) -> None:
    """The specific regression, asserted at the row level.

    The verdict test above would also pass if wheat were rejected for
    some unrelated reason — a low overall TARGET score, say. What
    actually broke was narrower: no wheat row described a leaf, so a
    wheat leaf's best match was "maize leaves close-up" and the image was
    admitted as Corn. This asserts the row-level fact directly, so the
    test fails for the true reason if the phrasing regresses.
    """
    path = FIXTURES / "wheat-rust.jpg"
    if not path.exists():
        pytest.skip(f"no fixture at {path}")

    import numpy as np

    from app.ood import CLIP_TEMPERATURE

    x = gate._preprocess(path.read_bytes())
    embed = gate.session.run(None, {gate.input_name: x})[0][0].astype(np.float32)
    embed /= np.linalg.norm(embed) + 1e-9
    scaled = (gate.text_embeddings @ embed) * CLIP_TEMPERATURE
    probs = np.exp(scaled - scaled.max())
    probs /= probs.sum()

    best = {}
    for p, record in zip(probs, gate.prompts, strict=True):
        label = record["label"]
        if float(p) > best.get(label, (0.0, ""))[0]:
            best[label] = (float(p), record["text"])

    wheat_p, wheat_text = best.get("Wheat", (0.0, "<none>"))
    corn_p, corn_text = best.get("Corn", (0.0, "<none>"))
    assert wheat_p > corn_p, (
        f"a wheat leaf still matches Corn better than Wheat: "
        f"Corn {corn_p:.4f} ({corn_text!r}) >= Wheat {wheat_p:.4f} ({wheat_text!r}). "
        f"Check that Wheat retains a leaf-level phrasing and that the "
        f"committed clip assets were regenerated after the edit."
    )
