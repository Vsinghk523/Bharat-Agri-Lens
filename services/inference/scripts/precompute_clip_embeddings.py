"""One-shot dev script: build clip_text_embeddings.npy + clip_prompts.json.

The runtime inference service deliberately doesn't pull torch +
transformers (see services/inference/pyproject.toml). But to seed the
OOD gate we need to compute CLIP text embeddings for our prompt set
*once*. That's what this script does — runs on a developer machine
(or any environment with torch + transformers + an internet
connection), produces two static artifacts that the runtime then
loads with onnxruntime + numpy alone.

Run with:

    cd services/inference
    uv pip install transformers torch  # add to dev env, NOT to runtime deps
    uv run python scripts/precompute_clip_embeddings.py \
        --labels /path/to/model-bundle/labels.json

``--labels`` points at the ``labels.json`` of the model bundle that will
actually be served. Crops the model can classify are written as TARGET;
every other catalogued crop is written as NON_TARGET so it routes to the
LLM fallback with a usable "looks like wheat" hint.

Passing no ``--labels`` marks every catalogued crop TARGET, which is how
the prompt set previously came to claim Wheat, Rice, Cotton, Mango and
Brinjal while production served a 14-crop PlantVillage model — the gate
then waved wheat photos through to a classifier with no wheat class and
got back "Corn, fungal, 100%". The script now warns loudly in that case.
The runtime gate re-checks the same agreement on load, so a stale
artefact degrades rather than misdiagnoses, but generating it correctly
is still the fix at source.

Outputs (committed to the repo):

    services/inference/app/clip_assets/clip_text_embeddings.npy
        Shape (N_prompts, 512), L2-normalised text embeddings.
    services/inference/app/clip_assets/clip_prompts.json
        Per-row {"text", "category", "label"} matching the .npy rows.

Re-run whenever ``app/ood_prompts.py`` changes.
"""
from __future__ import annotations

import json
from pathlib import Path

# Local imports — adjust path if running outside the inference package.
import sys

THIS_FILE = Path(__file__).resolve()
INFERENCE_ROOT = THIS_FILE.parent.parent  # services/inference/
sys.path.insert(0, str(INFERENCE_ROOT))

from app.ood_prompts import all_prompts, unservable_crops  # noqa: E402

OUT_DIR = INFERENCE_ROOT / "app" / "clip_assets"
EMBEDDINGS_PATH = OUT_DIR / "clip_text_embeddings.npy"
PROMPTS_PATH = OUT_DIR / "clip_prompts.json"

CLIP_MODEL_ID = "openai/clip-vit-base-patch32"


def _load_served_crop_labels(labels_path: str | None) -> list[str] | None:
    """Read ``crop_labels`` out of a model bundle's labels.json."""
    if not labels_path:
        return None
    data = json.loads(Path(labels_path).read_text(encoding="utf-8"))
    crops = data.get("crop_labels")
    if not crops:
        raise SystemExit(f"{labels_path} has no non-empty 'crop_labels' key")
    return list(crops)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--labels",
        default=None,
        help=(
            "Path to the served model bundle's labels.json. Crops it lists "
            "become TARGET; all other catalogued crops become NON_TARGET."
        ),
    )
    args = parser.parse_args()
    served = _load_served_crop_labels(args.labels)

    if served is None:
        print(
            "WARNING: no --labels given. Every catalogued crop will be marked "
            "TARGET, which tells the gate the classifier covers crops it may "
            "have no class for. This is the configuration that produced the "
            "wheat-diagnosed-as-Corn failure. Pass --labels unless you have a "
            "specific reason not to."
        )
    else:
        unservable = unservable_crops(served)
        print(f"served crops ({len(served)}): {sorted(served)}")
        print(
            f"catalogued but not served -> NON_TARGET ({len(unservable)}): "
            f"{unservable}"
        )

    # Imports here so the script can announce its dep requirements
    # if these aren't installed.
    try:
        import numpy as np
        import torch
        from transformers import CLIPModel, CLIPTokenizer
    except ImportError as exc:
        print(f"missing dep: {exc}")
        print("install with:  uv pip install transformers torch numpy")
        raise SystemExit(1)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    prompts = all_prompts(served_crop_labels=served)
    texts = [p["text"] for p in prompts]
    print(f"computing embeddings for {len(prompts)} prompts...")

    # We only need the text encoder — sidestep CLIPProcessor (which
    # requires the image preprocessor config that some HF mirrors
    # don't ship by default in newer transformers releases).
    model = CLIPModel.from_pretrained(CLIP_MODEL_ID)
    tokenizer = CLIPTokenizer.from_pretrained(CLIP_MODEL_ID)
    model.eval()

    with torch.no_grad():
        inputs = tokenizer(texts, return_tensors="pt", padding=True, truncation=True)
        text_embeds = model.get_text_features(**inputs)
        # Newer transformers can return a ModelOutput; older versions
        # return a tensor directly. Normalise.
        if hasattr(text_embeds, "pooler_output"):
            text_embeds = text_embeds.pooler_output
        elif hasattr(text_embeds, "last_hidden_state"):
            text_embeds = text_embeds.last_hidden_state[:, 0]
        # L2-normalise so runtime cosine-sim is a plain dot product.
        text_embeds = text_embeds / text_embeds.norm(dim=-1, keepdim=True)

    arr = text_embeds.cpu().numpy().astype(np.float32)
    np.save(EMBEDDINGS_PATH, arr)
    PROMPTS_PATH.write_text(
        json.dumps(
            {
                "model": CLIP_MODEL_ID,
                # Recorded so the runtime can tell which model's label
                # space this artefact was built against, and so a human
                # reading the file can see it without guessing.
                "served_crop_labels": served,
                "prompts": prompts,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # Category counts for sanity at a glance.
    counts: dict[str, int] = {}
    for p in prompts:
        counts[p["category"]] = counts.get(p["category"], 0) + 1

    print(f"wrote {EMBEDDINGS_PATH} (shape={arr.shape})")
    print(f"wrote {PROMPTS_PATH}")
    print(f"category counts: {counts}")


if __name__ == "__main__":
    main()
