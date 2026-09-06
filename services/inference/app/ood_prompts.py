"""CLIP prompt definitions for the OOD gate.

This file is the *source of truth* for which prompts go into the CLIP
zero-shot category gate. Editing this file means re-running the
precompute script (``scripts/precompute_clip_embeddings.py``) which
regenerates ``clip_text_embeddings.npy`` + ``clip_prompts.json``.

Three categories
----------------
TARGET      — crops the disease classifier actually knows. Multiple
              phrasings per crop tighten the embedding cluster; CLIP
              softmax does the rest.
NON_TARGET  — plants the classifier doesn't cover. Common ornamentals,
              flowers, grass, and houseplants, PLUS any crop in
              ``CROP_PHRASINGS`` that the served model has no class
              for. A farmer who points the camera at a rose gets
              "looks like a rose" rather than a confident-wrong crop
              diagnosis; one who points it at wheat while the served
              model is PlantVillage-only gets "looks like wheat" and
              routes to the LLM fallback.
NON_PLANT   — common non-plant photo subjects. Cats / dogs / humans /
              indoor scenes / objects / food. Covers the failure mode
              where a farmer accidentally uploads any random photo
              from their gallery.

TARGET membership is derived, not declared
------------------------------------------
``CROP_PHRASINGS`` below is a phrasing *catalogue* — every crop we can
describe to CLIP — and is deliberately NOT the same thing as the set of
crops the deployed model can classify. ``all_prompts()`` takes the
served model's ``crop_labels`` and splits the catalogue: crops the model
has a class for become TARGET, every other crop becomes NON_TARGET.

This ordering exists because getting it wrong produced a real
production failure. The prompt set was previously generated from the
20-crop ``baseline.yaml`` while production served the 14-crop
``plantvillage_v0.yaml``. CLIP therefore waved Wheat, Rice, Cotton,
Mango and Brinjal through as "in coverage", the classifier had no class
for any of them, and a wheat leaf-rust photo came back as
"Corn, fungal, 100%" — a confident wrong answer, with no escalation to
the LLM fallback, which is precisely the failure the gate exists to
prevent. The gate is only as good as its agreement with the model it
guards, so that agreement is now computed rather than maintained by
hand. ``CLIPGate`` re-checks it at load time as a second line of
defence.

Adding crops
------------
Add the crop's phrasings to ``CROP_PHRASINGS`` and re-run the
precompute. Whether it lands in TARGET or NON_TARGET follows
automatically from whatever model is served. No code changes needed.
"""

from collections.abc import Collection, Iterable

# Prompt labels that have been withdrawn from the prompt set and must be
# ignored if they appear in an already-committed ``clip_prompts.json``.
#
# ``CLIPGate`` drops these rows at load time rather than re-categorising
# them, because a retired prompt is retired for being uninformative, and
# an uninformative row biases whichever category it is filed under. This
# lets a fix ship without waiting on a precompute re-run, which needs
# torch and a model download that production does not have.
RETIRED_PROMPT_LABELS: frozenset[str] = frozenset({"Crop leaf"})

# Each entry: (label, [phrasing_1, phrasing_2, ...]).
# label is what the gate returns to the UI for "looks like X" messages.
#
# NOTE: presence here does NOT mean the classifier can diagnose the
# crop — see the module docstring. It means we can describe it to CLIP
# well enough to name it in a rejection hint.

CROP_PHRASINGS: list[tuple[str, list[str]]] = [
    ("Tomato",     ["a photograph of a tomato plant", "tomato leaves close-up", "tomato fruit on the vine"]),
    ("Potato",     ["a photograph of a potato plant", "potato leaves close-up", "potato plant in a field"]),
    ("Corn",       ["a photograph of a corn plant", "maize leaves close-up", "corn cob on the stalk"]),
    ("Wheat",      ["a photograph of wheat", "wheat plants in a field", "wheat ear close-up"]),
    ("Rice",       ["a photograph of a rice paddy", "rice plants in a field", "rice grains on the plant"]),
    ("Cotton",     ["a photograph of a cotton plant", "cotton bolls on the plant", "cotton leaves close-up"]),
    ("Mango",      ["a photograph of a mango tree", "mango leaves close-up", "ripening mango fruit"]),
    ("Brinjal",    ["a photograph of an eggplant plant", "brinjal fruit on the plant", "aubergine leaves"]),
    ("Apple",      ["a photograph of an apple tree", "apple leaves close-up", "apples on the branch"]),
    ("Grape",      ["a photograph of a grapevine", "grape leaves close-up", "bunches of grapes on the vine"]),
    ("Strawberry", ["a photograph of a strawberry plant", "strawberry leaves close-up", "strawberries on the plant"]),
    ("Orange",     ["a photograph of an orange tree", "citrus leaves close-up", "oranges on the branch"]),
    ("Peach",      ["a photograph of a peach tree", "peach leaves close-up", "peach fruit on the branch"]),
    ("Cherry",     ["a photograph of a cherry tree", "cherry leaves close-up", "cherries on the branch"]),
    ("Pepper",     ["a photograph of a chilli plant", "bell pepper plant close-up", "chillies hanging on the plant"]),
    ("Soybean",    ["a photograph of a soybean plant", "soybean leaves close-up", "soybean pods"]),
    ("Squash",     ["a photograph of a squash plant", "pumpkin leaves close-up", "gourd growing on a vine"]),
    ("Raspberry",  ["a photograph of a raspberry bush", "raspberry leaves close-up", "raspberries on the bush"]),
    ("Blueberry",  ["a photograph of a blueberry bush", "blueberry leaves close-up", "blueberries on the bush"]),
]

# REMOVED — generic "Crop leaf" catch-all prompts.
#
# Three crop-agnostic phrasings used to sit in TARGET:
#     "a close-up of a green crop leaf"
#     "a close-up photograph of a plant leaf with signs of disease"
#     "a close-up of a diseased leaf"
#
# The intent was that an unfamiliar-but-clearly-agricultural leaf should
# pass rather than misroute to non_target_plant. The effect was the
# opposite of the gate's purpose: because essentially every photo this
# app receives IS a close-up of a diseased leaf, these three rows
# absorbed a large share of the softmax mass on every single request and
# TARGET won almost unconditionally. NON_TARGET could not realistically
# win, so `non_target_plant` — the highest-value escalation route into
# the LLM fallback — became unreachable, and out-of-coverage crops
# (cabbage, brassicas, anything outside the trained set) were forced
# into whichever of the trained classes sat nearest in feature space.
#
# Do not reintroduce a crop-agnostic prompt in ANY category. Such a
# prompt carries no information about whether the subject is in
# coverage, so wherever it is placed it just adds a constant bias to
# that category's sum. Unfamiliar crops are meant to lose the TARGET
# contest — that is what routes them to the LLM, which is the tier
# equipped to handle them.

NON_TARGET_PLANTS: list[tuple[str, list[str]]] = [
    ("Rose",            ["a photograph of a rose flower", "a rose in bloom", "a close-up of a rose"]),
    ("Marigold",        ["a photograph of a marigold flower", "marigolds in a garden"]),
    ("Sunflower",       ["a photograph of a sunflower", "a sunflower bloom close-up"]),
    ("Lotus",           ["a photograph of a lotus flower", "a lotus pond"]),
    ("Ornamental flower", ["a photograph of an ornamental flower", "a decorative garden plant",
                           "a flower in a pot"]),
    ("Houseplant",      ["a photograph of a houseplant", "an indoor potted plant"]),
    ("Succulent",       ["a photograph of a succulent", "a cactus close-up", "an aloe vera plant"]),
    ("Fern",            ["a photograph of a fern", "fern leaves close-up"]),
    ("Lawn grass",      ["a photograph of lawn grass", "a green grass field"]),
    ("Tree (general)",  ["a photograph of a tree trunk", "the bark of a tree", "tree branches against the sky"]),
    ("Forest scene",    ["a photograph of a forest", "trees in a forest", "a dense bush"]),
]

NON_PLANT_SUBJECTS: list[tuple[str, list[str]]] = [
    ("Cat",         ["a photograph of a cat", "a kitten on a couch", "a close-up of a cat's face"]),
    ("Dog",         ["a photograph of a dog", "a puppy in the yard", "a close-up of a dog's face"]),
    ("Cow / cattle", ["a photograph of a cow", "cattle in a field", "a buffalo"]),
    ("Bird",        ["a photograph of a bird", "a parrot perched on a branch", "a chicken"]),
    ("Person",      ["a photograph of a person", "a portrait of a face", "a selfie"]),
    ("Hand",        ["a close-up of a human hand", "fingers holding an object"]),
    ("Indoor scene", ["a photograph of a living room", "a kitchen interior", "a bedroom"]),
    ("Vehicle",     ["a photograph of a car", "a tractor in a field", "a motorcycle"]),
    ("Food on plate", ["a plate of food", "a meal served on a plate", "cooked food"]),
    ("Object",      ["a photograph of a mobile phone", "a household object on a table",
                     "a piece of furniture"]),
    ("Sky / outdoor", ["a photograph of the sky", "clouds over a city", "a sunset"]),
    ("Document",    ["a photograph of a printed document", "a screenshot of a phone screen", "a text message"]),
    ("Soil bare",   ["a photograph of bare soil", "an empty field of dry earth", "a dirt patch"]),
]


def known_crop_labels() -> list[str]:
    """Every crop this module can describe to CLIP, in catalogue order."""
    return [label for label, _ in CROP_PHRASINGS]


def all_prompts(
    served_crop_labels: Collection[str] | None = None,
) -> list[dict[str, str]]:
    """Flatten the category buckets into the per-prompt records we ship
    in ``clip_prompts.json``.

    Each record has:
      - ``text``    : the CLIP prompt to encode
      - ``category``: "TARGET" | "NON_TARGET" | "NON_PLANT"
      - ``label``   : human-friendly name shown back to the user when
                      this prompt wins (e.g. "Rose" → "looks like a rose")

    ``served_crop_labels`` is the ``crop_labels`` list from the served
    model's ``labels.json``. Crops in it become TARGET; every other crop
    in ``CROP_PHRASINGS`` becomes NON_TARGET, so it is still *named*
    back to the user ("looks like wheat") while correctly failing the
    TARGET contest and routing to the LLM fallback.

    Passing ``None`` marks every catalogued crop TARGET. That is the
    legacy behaviour and it is what caused the wheat-as-Corn failure
    described in the module docstring, so it is intended only for
    offline tooling that has no model bundle to consult. Prefer passing
    the real label set.

    Matching is case-insensitive and ignores surrounding whitespace,
    since label casing has historically drifted between the training
    configs and the export bundle.
    """
    served: set[str] | None = None
    if served_crop_labels is not None:
        served = {c.strip().casefold() for c in served_crop_labels}

    def _is_served(label: str) -> bool:
        return served is None or label.strip().casefold() in served

    out: list[dict[str, str]] = []
    for label, phrasings in CROP_PHRASINGS:
        category = "TARGET" if _is_served(label) else "NON_TARGET"
        for p in phrasings:
            out.append({"text": p, "category": category, "label": label})
    for label, phrasings in NON_TARGET_PLANTS:
        for p in phrasings:
            out.append({"text": p, "category": "NON_TARGET", "label": label})
    for label, phrasings in NON_PLANT_SUBJECTS:
        for p in phrasings:
            out.append({"text": p, "category": "NON_PLANT", "label": label})
    return out


def unservable_crops(served_crop_labels: Iterable[str]) -> list[str]:
    """Catalogued crops the served model cannot classify.

    Useful for a startup log line, so an operator can see at a glance
    which crops are being deliberately routed to the LLM fallback rather
    than silently misclassified.
    """
    served = {c.strip().casefold() for c in served_crop_labels}
    return [
        label
        for label, _ in CROP_PHRASINGS
        if label.strip().casefold() not in served
    ]
