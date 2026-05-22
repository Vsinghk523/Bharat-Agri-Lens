"""ONNX-backed vision predictor.

Loads a PlantViT bundle produced by ``services/training/src/export.py``:

    <bundle_dir>/
      plantvit.onnx           (or plantvit-int8.onnx)
      labels.json             {"crop_labels": [...], "infection_labels": [...]}
      provenance.json         (informational; backbone name, training metrics)

Inference path:
    1. Fetch the image bytes from object storage via boto3.
    2. ImageNet-normalise + resize to the configured input size.
    3. Run a single onnxruntime session (CPU-only is fine for ViT-B int8;
       prod can switch to CUDA EP without code changes).
    4. Argmax + softmax both heads -> crop label, infection label, confidence.
    5. Shape the result to the same dict the mock predictor emits so the
       upstream API doesn't need to branch on which mode it ran in.

This module is imported lazily — only when the real predictor mode is
actually selected — so the mock-mode dev experience doesn't pay the
onnxruntime / numpy import cost.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import boto3
import numpy as np
from botocore.client import Config as BotoConfig
import onnxruntime as ort
from PIL import Image

from app.config import Settings
from app.logging import get_logger

log = get_logger(__name__)

IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32).reshape(1, 3, 1, 1)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32).reshape(1, 3, 1, 1)

# Static followups the model itself doesn't predict. Once the LLM
# integration generates these per-diagnosis they move out of here.
_STATIC_FOLLOWUPS = [
    {"text": "What is the safe dose for my field size?", "category": "dosage"},
    {"text": "Is there an organic alternative I can use?", "category": "alternative"},
    {"text": "When is the best time of day to spray?", "category": "timing"},
    {"text": "What is the approximate cost per acre?", "category": "cost"},
    {"text": "How do I prevent this disease next season?", "category": "prevention"},
]

# ---------------------------------------------------------------------------
# Static content used to enrich raw model output.
#
# The v0 vision model only predicts two heads (crop + infection_type), so
# the response dict would otherwise have None for scientific_name,
# disease_name, suggested_remedies, preventive_measures. Empty cards on
# the result page are a worse UX than honest generic guidance, so we fill
# them with safe, infection-type-keyed defaults below.
#
# IMPORTANT: this is not medical or agronomic advice. The remedy text
# below is generic best practice; the app already shows a disclaimer
# nudging users to confirm with a local agronomist / KVK officer. When
# we add a curated knowledge base or an LLM-generated remedy step in
# v0.1, these defaults retire.
# ---------------------------------------------------------------------------

_SCIENTIFIC_NAMES: dict[str, str] = {
    "Apple": "Malus domestica",
    "Blueberry": "Vaccinium corymbosum",
    "Cherry": "Prunus avium",
    "Corn": "Zea mays",
    "Grape": "Vitis vinifera",
    "Orange": "Citrus sinensis",
    "Peach": "Prunus persica",
    "Pepper": "Capsicum annuum",
    "Potato": "Solanum tuberosum",
    "Raspberry": "Rubus idaeus",
    "Soybean": "Glycine max",
    "Squash": "Cucurbita pepo",
    "Strawberry": "Fragaria × ananassa",
    "Tomato": "Solanum lycopersicum",
    "Rice": "Oryza sativa",
    "Cotton": "Gossypium hirsutum",
    "Wheat": "Triticum aestivum",
    "Mango": "Mangifera indica",
    "Brinjal": "Solanum melongena",
}

# Display label for the diagnosed condition when the model only knows
# the broad infection category. Lower-case the type for natural English
# (``Suspected fungal infection`` reads better than ``Suspected FUNGAL``).
_INFECTION_DISPLAY: dict[str, str] = {
    "fungal": "Suspected fungal infection",
    "bacterial": "Suspected bacterial infection",
    "viral": "Suspected viral infection",
    "insect_pest": "Suspected insect / pest damage",
    "nematode": "Suspected nematode infestation",
    "nutrient_deficiency": "Suspected nutrient deficiency",
    "abiotic_stress": "Suspected abiotic stress (water / heat / chemical)",
    "weed_competition": "Suspected weed competition",
    "unknown": "Condition unclear",
}

_REMEDIES_BY_INFECTION: dict[str, str] = {
    "fungal": (
        "1. Remove and destroy affected leaves, fruits, and crop residue.\n"
        "2. Apply a CIBRC-recommended fungicide at label dose (e.g. Mancozeb "
        "75% WP, 2 g / litre water).\n"
        "3. Improve airflow around plants and avoid overhead irrigation; "
        "water at the base early in the day."
    ),
    "bacterial": (
        "1. Prune and destroy infected branches / leaves; bag and dispose "
        "off-field.\n"
        "2. Spray a copper-based bactericide (e.g. copper oxychloride 50% WP, "
        "3 g / litre) as per label dose.\n"
        "3. Sterilise pruning tools between plants and avoid field work when "
        "foliage is wet."
    ),
    "viral": (
        "1. Rogue out and destroy infected plants — viral diseases have no "
        "chemical cure.\n"
        "2. Control insect vectors (aphids, whiteflies, thrips) that spread "
        "the virus, using an IPM approach.\n"
        "3. Use certified virus-free seedlings or resistant varieties for the "
        "next season."
    ),
    "insect_pest": (
        "1. Scout fields weekly with sticky / pheromone traps to confirm pest "
        "and assess threshold counts.\n"
        "2. Apply an IPM-approved insecticide only when economic threshold is "
        "exceeded; rotate modes of action to delay resistance.\n"
        "3. Encourage natural predators (ladybugs, parasitoid wasps) with "
        "refuge strips and avoid broad-spectrum sprays."
    ),
    "nematode": (
        "1. Rotate with non-host crops (e.g. maize, marigold) for 2-3 "
        "seasons to break the cycle.\n"
        "2. Apply nematicide only if soil sampling confirms heavy infestation "
        "— follow CIBRC label.\n"
        "3. Use resistant varieties where available and avoid moving infested "
        "soil on tools or footwear."
    ),
    "nutrient_deficiency": (
        "1. Soil-test and apply the missing nutrient at the recommended dose "
        "for your crop and region.\n"
        "2. Foliar spray for quick correction (e.g. 1% urea for nitrogen, "
        "0.5% MOP for potassium).\n"
        "3. Add compost or farmyard manure to build long-term soil organic "
        "matter and micronutrient supply."
    ),
    "abiotic_stress": (
        "1. Irrigate during dry spells; mulch with straw or crop residue to "
        "conserve soil moisture.\n"
        "2. Shade-net or whitewash trunks to protect from heat; provide "
        "windbreaks against hot dry winds.\n"
        "3. Re-test soil for salinity / pH and adjust fertilisation if "
        "chemical stress is suspected."
    ),
    "weed_competition": (
        "1. Hand-weed or hoe early — first 20-25 days after emergence are "
        "critical.\n"
        "2. Use a stale-seedbed approach before sowing, or apply a selective "
        "herbicide labelled for your crop.\n"
        "3. Mulch with crop residue to suppress further weed germination."
    ),
    "unknown": (
        "Diagnosis is uncertain. Take a clearer photo in daylight (whole "
        "plant + close-up of symptoms), and consult a local agronomist or "
        "KVK officer before applying any treatment."
    ),
}

_PREVENTION_BY_INFECTION: dict[str, str] = {
    "fungal": (
        "Rotate crops on a 3-4 year cycle; use certified disease-free seed; "
        "maintain plant spacing for airflow; scout weekly in humid weather; "
        "destroy crop residue after harvest."
    ),
    "bacterial": (
        "Use certified pathogen-free planting material; sterilise pruning "
        "tools between plants; avoid overhead irrigation; remove and burn "
        "infected debris promptly."
    ),
    "viral": (
        "Plant only certified virus-free seedlings; control insect vectors "
        "year-round; remove volunteer plants and weed hosts; choose "
        "resistant varieties where available."
    ),
    "insect_pest": (
        "Weekly scouting with pheromone or sticky traps; intercrop with "
        "trap or repellent crops; rotate insecticide modes of action; "
        "preserve refuge strips for natural enemies."
    ),
    "nematode": (
        "Crop rotation with non-host species; resistant varieties; soil "
        "solarisation between seasons; avoid carrying infested soil on "
        "tools or footwear."
    ),
    "nutrient_deficiency": (
        "Annual soil testing; balanced NPK + micronutrients sized to crop "
        "demand; add organic matter (FYM / compost); maintain soil pH near "
        "the crop's optimum range."
    ),
    "abiotic_stress": (
        "Mulch to conserve moisture; provide windbreaks; irrigate at "
        "critical growth stages; choose locally adapted varieties; "
        "schedule chemical sprays for cooler hours."
    ),
    "weed_competition": (
        "Stale seedbed before sowing; clean seed; mulch with crop residue; "
        "timely first hoeing within 20-25 days; close crop canopy to "
        "smother late weed flushes."
    ),
    "unknown": (
        "General good practice: certified seed, balanced nutrition, timely "
        "irrigation, weekly scouting, and consultation with a local expert "
        "for specific recommendations."
    ),
}


def _severity_from_confidence(p: float) -> str:
    if p < 0.55:
        return "low"
    if p < 0.75:
        return "medium"
    if p < 0.9:
        return "high"
    return "critical"


def _softmax(x: np.ndarray) -> np.ndarray:
    """Numerically-stable softmax over the last axis."""
    e = np.exp(x - x.max(axis=-1, keepdims=True))
    return e / e.sum(axis=-1, keepdims=True)


def _preprocess(image_bytes: bytes, size: int) -> np.ndarray:
    """Bytes -> 1x3xHxW float32 tensor, ImageNet-normalised."""
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB").resize((size, size), Image.BILINEAR)
    arr = np.asarray(img, dtype=np.float32) / 255.0  # HxWx3
    arr = arr.transpose(2, 0, 1)[None, ...]  # 1x3xHxW
    arr = (arr - IMAGENET_MEAN) / IMAGENET_STD
    return arr.astype(np.float32)


class RealPredictor:
    """Process-wide singleton holding the loaded ONNX session + labels."""

    def __init__(self, bundle_dir: Path, image_size: int = 224) -> None:
        self.bundle_dir = bundle_dir
        self.image_size = image_size

        labels = json.loads((bundle_dir / "labels.json").read_text(encoding="utf-8"))
        self.crop_labels: list[str] = labels["crop_labels"]
        self.infection_labels: list[str] = labels["infection_labels"]

        # Prefer the int8 build when present — same accuracy ±0.5%,
        # ~4x smaller + faster on CPU.
        int8_path = bundle_dir / "plantvit-int8.onnx"
        fp32_path = bundle_dir / "plantvit.onnx"
        if int8_path.exists():
            model_path = int8_path
        elif fp32_path.exists():
            model_path = fp32_path
        else:
            raise FileNotFoundError(
                f"no plantvit.onnx or plantvit-int8.onnx in {bundle_dir}"
            )

        providers = ort.get_available_providers()
        # CUDAExecutionProvider first when available; CPU fallback always
        # last.
        order = [p for p in ("CUDAExecutionProvider", "CPUExecutionProvider") if p in providers]
        self.session = ort.InferenceSession(str(model_path), providers=order)
        self.input_name = self.session.get_inputs()[0].name

        prov_path = bundle_dir / "provenance.json"
        self.version = "plantvit-unknown"
        if prov_path.exists():
            prov = json.loads(prov_path.read_text(encoding="utf-8"))
            self.version = f"{prov.get('name', 'plantvit')}-{prov.get('backbone', 'unknown').replace('/', '_')}"

        log.info(
            "real_predictor_loaded",
            model=str(model_path),
            providers=order,
            crops=len(self.crop_labels),
            infections=len(self.infection_labels),
            version=self.version,
        )

    def predict(self, image_bytes: bytes, language: str) -> dict[str, Any]:
        x = _preprocess(image_bytes, self.image_size)
        outs = self.session.run(None, {self.input_name: x})
        # Export pin: output_names=["crop_logits", "infection_logits"].
        crop_logits, infection_logits = outs[0][0], outs[1][0]
        crop_probs = _softmax(crop_logits)
        infection_probs = _softmax(infection_logits)
        crop_idx = int(crop_probs.argmax())
        infection_idx = int(infection_probs.argmax())
        # Secondary picks for "explore other diagnoses".
        top3 = infection_probs.argsort()[-3:][::-1]
        secondary = [
            {
                "infection_type": self.infection_labels[int(i)],
                # Mirror the chosen-prediction's display string so the
                # web UI can render "Suspected fungal infection" instead
                # of an unfriendly raw enum value.
                "disease_name": _INFECTION_DISPLAY.get(
                    self.infection_labels[int(i)],
                    self.infection_labels[int(i)],
                ),
                "confidence": float(infection_probs[int(i)]),
            }
            for i in top3
            if int(i) != infection_idx
        ]

        crop = self.crop_labels[crop_idx]
        infection = self.infection_labels[infection_idx]

        return {
            "plant_classification": crop,
            # v0 has no scientific-name head — look it up from a small
            # static table keyed by crop label. Unknown crops fall back
            # to None so the UI hides the field rather than displaying
            # something misleading.
            "scientific_name": _SCIENTIFIC_NAMES.get(crop),
            # No disease-name head in v0 either; show a clear
            # "Suspected {infection_type} infection" placeholder so the
            # result card reads naturally instead of "None".
            "disease_name": _INFECTION_DISPLAY.get(infection, infection),
            "pathogen_name": None,
            "infection_type": infection,
            "severity": _severity_from_confidence(float(infection_probs[infection_idx])),
            "confidence_score": float(infection_probs[infection_idx]),
            "secondary_predictions": secondary,
            "model_version": self.version,
            # Generic best-practice remedy + prevention text per infection
            # type. Not a substitute for an agronomist's diagnosis (the
            # app's disclaimer already says so) — just better than empty
            # cards for v0. v0.1 wires curated content / LLM output here.
            "suggested_remedies": _REMEDIES_BY_INFECTION.get(infection),
            "chemical_remedies": None,
            "organic_remedies": None,
            "preventive_measures": _PREVENTION_BY_INFECTION.get(infection),
            "followup_questions": [
                {**q, "language": language} for q in _STATIC_FOLLOWUPS
            ],
        }


# Singleton loaded lazily on first /predict call.
_predictor: RealPredictor | None = None
_image_bytes_cache: dict[str, bytes] = {}


def _resolve_bundle_dir(settings: Settings) -> Path:
    """Return a local directory containing plantvit.onnx + labels.json.

    Two supported sources:
    - ``hf_model_repo`` set → snapshot_download from the HuggingFace Hub
      into ``hf_model_cache_dir``. Subsequent calls in the same process
      hit the local cache (snapshot_download itself is idempotent).
    - ``hf_model_repo`` unset → treat ``vision_model_uri`` as a local
      filesystem path (back-compat with the original deployment).
    """
    if settings.hf_model_repo:
        # Import lazily so deployments not using HF Hub don't pay the
        # huggingface_hub import cost (and don't need the dep installed).
        from huggingface_hub import snapshot_download

        log.info(
            "downloading_model_from_hf_hub",
            repo=settings.hf_model_repo,
            cache_dir=settings.hf_model_cache_dir,
        )
        local_dir = snapshot_download(
            repo_id=settings.hf_model_repo,
            repo_type="model",
            local_dir=settings.hf_model_cache_dir,
            token=settings.hf_token or None,
            # Only fetch the files we actually need — skip large training
            # artifacts if the repo accidentally accumulated any.
            allow_patterns=[
                "plantvit.onnx",
                "plantvit-int8.onnx",
                "labels.json",
                "provenance.json",
            ],
        )
        return Path(local_dir)

    bundle = Path(settings.vision_model_uri)
    if not bundle.is_dir():
        raise FileNotFoundError(
            f"VISION_MODEL_URI must point at an export bundle directory "
            f"(or set HF_MODEL_REPO to pull from the Hub), got: {bundle}"
        )
    return bundle


def _get_predictor(settings: Settings) -> RealPredictor:
    global _predictor
    if _predictor is None:
        _predictor = RealPredictor(_resolve_bundle_dir(settings))
    return _predictor


def _fetch_image_bytes(image_id: str, settings: Settings) -> bytes:
    """Download the original image from object storage.

    The S3 key layout matches what the API's presign endpoint writes:
    ``uploads/<user_id>/<image_id>/<filename>``. We don't know the
    filename or user_id here, so we list-with-prefix on
    ``uploads/`` and pick the first object whose key contains the
    image_id. Cheap because the bucket prefix is shallow.
    """
    if image_id in _image_bytes_cache:
        return _image_bytes_cache[image_id]

    kwargs: dict[str, Any] = {
        "region_name": settings.s3_region,
        "config": BotoConfig(
            signature_version="s3v4",
            s3={"addressing_style": "path" if settings.s3_endpoint_url else "virtual"},
        ),
    }
    if settings.s3_access_key_id and settings.s3_secret_access_key:
        kwargs["aws_access_key_id"] = settings.s3_access_key_id
        kwargs["aws_secret_access_key"] = settings.s3_secret_access_key
    if settings.s3_endpoint_url:
        kwargs["endpoint_url"] = settings.s3_endpoint_url
    client = boto3.client("s3", **kwargs)

    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=settings.s3_bucket, Prefix="uploads/"):
        for obj in page.get("Contents", []) or []:
            key: str = obj["Key"]
            if image_id in key and not key.endswith(".thumb.jpg"):
                resp = client.get_object(Bucket=settings.s3_bucket, Key=key)
                data: bytes = resp["Body"].read()
                _image_bytes_cache[image_id] = data
                return data

    raise FileNotFoundError(f"no object found for image_id={image_id}")


async def real_predict(image_id: str, language: str, settings: Settings) -> dict[str, Any]:
    """Async wrapper. Both _fetch_image_bytes and session.run are
    synchronous + CPU-bound; offload to a thread so the event loop
    keeps moving."""
    import asyncio

    predictor = _get_predictor(settings)
    img_bytes = await asyncio.to_thread(_fetch_image_bytes, image_id, settings)
    return await asyncio.to_thread(predictor.predict, img_bytes, language)
