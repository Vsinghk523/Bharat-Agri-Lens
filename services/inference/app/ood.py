"""Out-of-distribution defense for the plant-disease classifier.

Why this exists
---------------
The PlantViT v0 model is a closed-world classifier: its output is a
softmax over ~19 crop classes. Architecturally, it MUST pick one — there
is no "I don't know" head. Result: it confidently labels a rose photo as
"Strawberry, 98.4%" and a cat photo as "Tomato, 37.2% bacterial".

This module is the gate that sits in front of the classifier. It runs
three independent checks; any one of them tripping turns the diagnosis
into an explanatory rejection instead of a confident-wrong answer.

Layer 1 — Image quality
    Pillow-based: minimum resolution, blur detection (Laplacian
    variance), exposure histogram. Catches "you uploaded a thumbnail",
    "you took the photo at night with no flash", "out of focus".

Layer 2 — CLIP zero-shot category gate
    Encode the image with CLIP ViT-B/32 (ONNX, ~87 MB image encoder).
    Cosine-similarity against pre-computed text embeddings for three
    categories of prompts:
        - TARGET    : our 19 trained crops, multiple phrasings each
        - NON_TARGET: roses, marigolds, succulents, houseplants,
                      ferns, ornamental flowers, grass
        - NON_PLANT : cats, dogs, humans, indoor scenes, vehicles,
                      food on a plate, hands, the sky
    Sum the softmaxed similarities by category and pick the winner.
    If TARGET doesn't win with a comfortable margin, reject — explaining
    the closest non-target match so the farmer learns what to retake.

Layer 3 — Plant-classifier confidence
    After the disease classifier runs, check (a) is the top-1 confidence
    above CONFIDENCE_THRESHOLD, and (b) is the gap between top-1 and
    top-2 above MARGIN_THRESHOLD. Either failing means the model is
    genuinely uncertain — better to say so than to assert.

Why ONNX CLIP and not transformers+torch
----------------------------------------
The existing inference service deliberately avoids torch and
transformers (see pyproject.toml comment). They add ~1.5 GB to the
container and ~15 s to cold start, which is wasteful when we only need
CLIP's image encoder at runtime. Instead:
    1. Use ``Xenova/clip-vit-base-patch32`` ONNX exports from HF Hub
       (image encoder only; we don't run text at runtime).
    2. Pre-compute text embeddings ONCE on the dev machine
       (``services/inference/scripts/precompute_clip_embeddings.py``)
       and commit them as ``clip_text_embeddings.npy`` plus the
       per-prompt category labels in ``clip_prompts.json``.
    3. At runtime: load the image encoder via the same ``snapshot_download``
       mechanism the plant model uses, run one forward pass per request,
       cosine-similarity against the static text matrix.

Per-request cost: ~80-150 ms on CPU, negligible memory beyond the
already-loaded 87 MB image encoder.

Rejection reasons (matches the public response schema)
------------------------------------------------------
    too_blurry          : image quality (Laplacian variance below floor)
    too_dark            : image quality (mean luminance too low)
    too_small           : image quality (below MIN_DIMENSION)
    not_a_plant         : CLIP top category is NON_PLANT
    non_target_plant    : CLIP top category is NON_TARGET (includes
                          which species/category looked closest, so
                          the UI can say "looks like a rose")
    low_confidence      : classifier top-1 below CONFIDENCE_THRESHOLD
    ambiguous           : top-1 and top-2 within MARGIN_THRESHOLD of
                          each other (model can't decide)

The downstream API stores the rejection_reason on the diagnostic row;
the web UI renders an explanatory message for each.
"""
from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime as ort
from PIL import Image, ImageFilter

from app.config import Settings
from app.logging import get_logger

# CLIP ONNX source. The Xenova export bundles fp32 / int8 / int4
# variants; we use the int8 ``quantized`` build for production
# (~85 MB, ~3x faster on CPU, accuracy delta is negligible for
# zero-shot category gating).
CLIP_HF_REPO = "Xenova/clip-vit-base-patch32"
CLIP_VISION_ONNX_FILENAME = "onnx/vision_model_quantized.onnx"

log = get_logger(__name__)

# ------------------------------------------------------------------
# Tuning constants
# ------------------------------------------------------------------

# Layer 1 — image quality
MIN_DIMENSION = 200             # px; reject if either width or height below
MIN_LAPLACIAN_VAR = 30.0        # blur floor; below = out of focus
MIN_MEAN_LUMA = 25.0            # exposure floor on 0-255 scale; below = too dark
MAX_MEAN_LUMA = 240.0           # exposure ceiling; above = blown out / white

# Layer 2 — CLIP gate
CLIP_INPUT_SIZE = 224
# CLIP uses a different normalisation from ImageNet — these are the
# canonical values openai/clip-vit-base-patch32 was trained with.
CLIP_MEAN = np.array([0.48145466, 0.4578275, 0.40821073], dtype=np.float32).reshape(1, 3, 1, 1)
CLIP_STD = np.array([0.26862954, 0.26130258, 0.27577711], dtype=np.float32).reshape(1, 3, 1, 1)
# Sharpness of the softmax that turns cosine similarities into a
# distribution over prompts. CLIP's pretrained temperature is exp(4.6) ≈ 100;
# we use the same so our results agree with the canonical zero-shot recipe.
CLIP_TEMPERATURE = 100.0
# How much the TARGET category needs to dominate the others, summed.
# 0.50 means TARGET prob >= NON_TARGET prob + NON_PLANT prob.
TARGET_WIN_MARGIN = 0.05

# Layer 3 — classifier confidence
CONFIDENCE_THRESHOLD = 0.60     # top-1 must clear this
MARGIN_THRESHOLD = 0.05         # top-1 must beat top-2 by this much


# ------------------------------------------------------------------
# Layer 1 — image quality
# ------------------------------------------------------------------

def check_image_quality(image_bytes: bytes) -> str | None:
    """Return a rejection reason if the image fails any quality bar.

    None means "image is good enough to run further inference on".
    Cheap (single Pillow open + a couple of stats) so we run it first.
    """
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except (OSError, Image.DecompressionBombError) as exc:
        log.warning("ood_image_unreadable", error=str(exc))
        return "too_small"  # closest user-facing bucket — "send a real photo"

    w, h = img.size
    if w < MIN_DIMENSION or h < MIN_DIMENSION:
        log.info("ood_image_too_small", width=w, height=h)
        return "too_small"

    # Mean luma (BT.601 weights) for exposure check.
    luma = np.asarray(img.convert("L"), dtype=np.float32)
    mean_luma = float(luma.mean())
    if mean_luma < MIN_MEAN_LUMA:
        log.info("ood_image_too_dark", mean_luma=mean_luma)
        return "too_dark"
    if mean_luma > MAX_MEAN_LUMA:
        # Treat blown-out white the same as too dark from the user's
        # perspective ("retake with better light"). Same bucket.
        log.info("ood_image_overexposed", mean_luma=mean_luma)
        return "too_dark"

    # Blur via Laplacian variance. Run on a downsized image to keep
    # this cheap regardless of input size.
    small = img.resize((256, 256), Image.BILINEAR)
    lap = np.asarray(small.filter(ImageFilter.FIND_EDGES).convert("L"), dtype=np.float32)
    lap_var = float(lap.var())
    if lap_var < MIN_LAPLACIAN_VAR:
        log.info("ood_image_too_blurry", lap_var=lap_var)
        return "too_blurry"

    return None


# ------------------------------------------------------------------
# Layer 2 — CLIP gate
# ------------------------------------------------------------------

# Per-prompt rows in the embedding matrix map to (category, label).
# Categories: TARGET, NON_TARGET, NON_PLANT.
# The label is what we show in the rejection message when a NON_TARGET
# row wins (e.g. "looks like a rose").

class CLIPGate:
    """Stateful holder for the ONNX image encoder + precomputed text matrix.

    Constructed once per process (singleton via ``get_clip_gate``).
    Loading the ONNX session + the .npy matrix takes ~2-3 s; per-request
    cost is one ONNX forward pass + a (N×512) matmul.
    """

    def __init__(
        self,
        vision_onnx_path: Path,
        text_embeddings_path: Path,
        prompts_meta_path: Path,
    ) -> None:
        # Vision encoder.
        providers = [p for p in ("CUDAExecutionProvider", "CPUExecutionProvider")
                     if p in ort.get_available_providers()]
        self.session = ort.InferenceSession(str(vision_onnx_path), providers=providers)
        self.input_name = self.session.get_inputs()[0].name

        # Pre-computed unit-norm text embeddings: (N_prompts, 512).
        self.text_embeddings: np.ndarray = np.load(text_embeddings_path)

        # Per-row category + label so we can attribute a winning row.
        meta = json.loads(prompts_meta_path.read_text(encoding="utf-8"))
        self.prompts: list[dict[str, str]] = meta["prompts"]
        if len(self.prompts) != self.text_embeddings.shape[0]:
            raise ValueError(
                f"text_embeddings rows ({self.text_embeddings.shape[0]}) does not "
                f"match prompts count ({len(self.prompts)})"
            )

        log.info(
            "clip_gate_loaded",
            vision_onnx=str(vision_onnx_path),
            prompts=len(self.prompts),
            providers=providers,
        )

    def _preprocess(self, image_bytes: bytes) -> np.ndarray:
        img = (
            Image.open(io.BytesIO(image_bytes))
            .convert("RGB")
            .resize((CLIP_INPUT_SIZE, CLIP_INPUT_SIZE), Image.BICUBIC)
        )
        arr = np.asarray(img, dtype=np.float32) / 255.0
        arr = arr.transpose(2, 0, 1)[None, ...]  # 1x3xHxW
        arr = (arr - CLIP_MEAN) / CLIP_STD
        return arr.astype(np.float32)

    def gate(self, image_bytes: bytes) -> dict[str, Any]:
        """Return a verdict dict:

        {
          "ok": bool,                  # True iff TARGET wins with margin
          "reason": str | None,        # "not_a_plant" | "non_target_plant" | None
          "winning_label": str | None, # what the model thinks it sees (UI hint)
          "category_probs": {"TARGET": float, "NON_TARGET": float, "NON_PLANT": float},
        }
        """
        x = self._preprocess(image_bytes)
        outs = self.session.run(None, {self.input_name: x})
        # ONNX CLIP vision returns image_embeds at index 0.
        image_embed = outs[0][0].astype(np.float32)
        # L2-normalise so the cosine similarity is just a dot product.
        image_embed /= np.linalg.norm(image_embed) + 1e-9

        # (N_prompts,) similarity vector.
        sims = self.text_embeddings @ image_embed
        # Softmax with CLIP's temperature.
        scaled = sims * CLIP_TEMPERATURE
        probs = np.exp(scaled - scaled.max())
        probs /= probs.sum()

        # Sum probabilities by category.
        cat_probs: dict[str, float] = {"TARGET": 0.0, "NON_TARGET": 0.0, "NON_PLANT": 0.0}
        for prob, prompt in zip(probs, self.prompts, strict=True):
            cat_probs[prompt["category"]] += float(prob)

        # Identify the single highest-probability prompt for the UI hint.
        top_idx = int(np.argmax(probs))
        top_prompt = self.prompts[top_idx]

        # Decision rule: TARGET must beat the sum of the other two
        # categories by at least TARGET_WIN_MARGIN. This is stricter than
        # "TARGET is the largest category" because it forces the model to
        # be actively confident the image is in scope, not just slightly
        # more likely than alternatives.
        target_minus_rest = cat_probs["TARGET"] - cat_probs["NON_TARGET"] - cat_probs["NON_PLANT"]
        if target_minus_rest >= TARGET_WIN_MARGIN:
            return {
                "ok": True,
                "reason": None,
                "winning_label": top_prompt["label"],
                "category_probs": cat_probs,
            }

        # TARGET lost. Distinguish "not a plant at all" from "plant but
        # not one we cover" so the rejection message is informative.
        if cat_probs["NON_PLANT"] > cat_probs["NON_TARGET"]:
            reason = "not_a_plant"
        else:
            reason = "non_target_plant"
        return {
            "ok": False,
            "reason": reason,
            "winning_label": top_prompt["label"],
            "category_probs": cat_probs,
        }


_clip_gate: CLIPGate | None = None


def _clip_assets_dir() -> Path:
    """Where the static text-embedding artifacts live in the repo."""
    return Path(__file__).resolve().parent / "clip_assets"


def _download_clip_vision_model(settings: Settings) -> Path:
    """Pull the quantized vision-encoder ONNX from HF Hub.

    Same pattern as the plant model in real_predictor.py: cache in
    ``settings.hf_model_cache_dir`` so re-deploys with persistent disk
    skip the re-download. Without a persistent disk the file is
    fetched once on cold start (~5 s on a fast link).
    """
    from huggingface_hub import hf_hub_download  # lazy

    log.info("downloading_clip_vision_from_hf", repo=CLIP_HF_REPO)
    local_path = hf_hub_download(
        repo_id=CLIP_HF_REPO,
        filename=CLIP_VISION_ONNX_FILENAME,
        local_dir=settings.hf_model_cache_dir,
        token=settings.hf_token or None,
    )
    return Path(local_path)


def get_clip_gate(settings: Settings) -> CLIPGate:
    """Process-wide singleton.

    Vision encoder downloaded from HF Hub on first call (cached in
    ``settings.hf_model_cache_dir``). Text embeddings + prompts ship
    with the repo (``app/clip_assets/``) — they're the contract
    between the precompute script and the runtime gate.
    """
    global _clip_gate
    if _clip_gate is None:
        assets = _clip_assets_dir()
        _clip_gate = CLIPGate(
            vision_onnx_path=_download_clip_vision_model(settings),
            text_embeddings_path=assets / "clip_text_embeddings.npy",
            prompts_meta_path=assets / "clip_prompts.json",
        )
    return _clip_gate


# ------------------------------------------------------------------
# Layer 3 — classifier confidence
# ------------------------------------------------------------------

def check_classifier_confidence(probs: np.ndarray) -> str | None:
    """Decide if the disease classifier's prediction is trustworthy.

    Returns a rejection reason or None.

    - ``low_confidence`` if the argmax probability is below
      ``CONFIDENCE_THRESHOLD``. The model is just guessing.
    - ``ambiguous`` if top-1 and top-2 are within ``MARGIN_THRESHOLD``.
      The model genuinely can't decide between two diagnoses; better to
      say so than to assert one.
    """
    sorted_probs = np.sort(probs)[::-1]
    top1 = float(sorted_probs[0])
    if top1 < CONFIDENCE_THRESHOLD:
        return "low_confidence"
    if len(sorted_probs) >= 2:
        top2 = float(sorted_probs[1])
        if (top1 - top2) < MARGIN_THRESHOLD:
            return "ambiguous"
    return None
