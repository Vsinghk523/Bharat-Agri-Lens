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
NON_TARGET  — plants the classifier doesn't cover. We list common
              ornamentals, flowers, grass, and houseplants so a
              farmer who points the camera at a rose gets "looks like
              a rose, we don't cover ornamental plants yet" instead
              of a confident-wrong crop diagnosis.
NON_PLANT   — common non-plant photo subjects. Cats / dogs / humans /
              indoor scenes / objects / food. Covers the failure mode
              where a farmer accidentally uploads any random photo
              from their gallery.

Adding crops
------------
When the trained crop set expands (e.g. we add Bell pepper, Cucumber,
etc.), add them under TARGET with the same multi-phrasing pattern and
re-run the precompute. No code changes elsewhere are needed.
"""

# Each entry: (label, [phrasing_1, phrasing_2, ...]).
# label is what the gate returns to the UI for "looks like X" messages.

TARGET_CROPS: list[tuple[str, list[str]]] = [
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
    # Generic catch-alls so a clear leaf photo of an unfamiliar variety
    # still passes the gate rather than misrouting to non_target_plant.
    # The disease classifier itself will then either give a useful
    # crop guess or be filtered out by the confidence layer.
    ("Crop leaf",  ["a close-up of a green crop leaf", "a close-up photograph of a plant leaf with signs of disease",
                    "a close-up of a diseased leaf"]),
]

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


def all_prompts() -> list[dict[str, str]]:
    """Flatten the three category buckets into the per-prompt records
    we ship in ``clip_prompts.json``.

    Each record has:
      - ``text``    : the CLIP prompt to encode
      - ``category``: "TARGET" | "NON_TARGET" | "NON_PLANT"
      - ``label``   : human-friendly name shown back to the user when
                      this prompt wins (e.g. "Rose" → "looks like a rose")
    """
    out: list[dict[str, str]] = []
    for label, phrasings in TARGET_CROPS:
        for p in phrasings:
            out.append({"text": p, "category": "TARGET", "label": label})
    for label, phrasings in NON_TARGET_PLANTS:
        for p in phrasings:
            out.append({"text": p, "category": "NON_TARGET", "label": label})
    for label, phrasings in NON_PLANT_SUBJECTS:
        for p in phrasings:
            out.append({"text": p, "category": "NON_PLANT", "label": label})
    return out
