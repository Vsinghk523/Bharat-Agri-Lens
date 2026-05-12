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
            {"infection_type": self.infection_labels[int(i)], "confidence": float(infection_probs[int(i)])}
            for i in top3
            if int(i) != infection_idx
        ]

        return {
            "plant_classification": self.crop_labels[crop_idx],
            "scientific_name": None,
            "disease_name": None,
            "pathogen_name": None,
            "infection_type": self.infection_labels[infection_idx],
            "severity": _severity_from_confidence(float(infection_probs[infection_idx])),
            "confidence_score": float(infection_probs[infection_idx]),
            "secondary_predictions": secondary,
            "model_version": self.version,
            "suggested_remedies": None,
            "chemical_remedies": None,
            "organic_remedies": None,
            "preventive_measures": None,
            "followup_questions": [
                {**q, "language": language} for q in _STATIC_FOLLOWUPS
            ],
        }


def _severity_from_confidence(p: float) -> str:
    if p < 0.55:
        return "low"
    if p < 0.75:
        return "medium"
    if p < 0.9:
        return "high"
    return "critical"


# Singleton loaded lazily on first /predict call.
_predictor: RealPredictor | None = None
_image_bytes_cache: dict[str, bytes] = {}


def _get_predictor(settings: Settings) -> RealPredictor:
    global _predictor
    if _predictor is None:
        bundle = Path(settings.vision_model_uri)
        if not bundle.is_dir():
            raise FileNotFoundError(
                f"VISION_MODEL_URI must point at an export bundle directory, "
                f"got: {bundle}"
            )
        _predictor = RealPredictor(bundle)
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
