"""Gemini-backed fallback predictor for OOD plant images.

When the PlantViT classifier's OOD gate rejects an image with one of
{non_target_plant, low_confidence, ambiguous}, the API is asked to
defer to a general multimodal LLM rather than show the rejection to
the farmer. The LLM (Gemini 1.5 Flash by default) gets the same image
plus the CLIP gate's best-guess label as a hint, and is asked to
return a structured diagnosis matching our existing schema.

Architectural choices
---------------------

**Why Gemini Flash, not Gemini Pro:**
Flash is ~10x cheaper, 3x faster, and the accuracy gap is small for
this task ("identify the plant in this photo and any disease you can
see"). We can promote to Pro later if a specific failure pattern
emerges.

**Why structured output (JSON schema), not free-form text + parse:**
Gemini Flash supports a `response_mime_type='application/json'` mode
that constrains the output to a JSON schema. We pin the schema to
match our DiagnosticRead row shape, so the LLM output drops directly
into the same code path that handles our own predictor's output. No
prompt engineering for output format, no regex parsing, no
"sometimes the model wraps it in markdown code fences" headache.

**Why we only call this for specific rejection reasons:**
- ``non_target_plant``: a real plant, just not one our model knows.
  This is the highest-value fallback — turns "we can't help" into
  "here's a best-effort diagnosis".
- ``low_confidence``: our model isn't sure. LLM may have a stronger
  prior from internet-scale training.
- ``ambiguous``: top-1 and top-2 are tied. LLM acts as a tiebreaker.
- ``not_a_plant``: CLIP is confident this is a cat/object — don't
  ask the LLM to hallucinate a diagnosis for a couch. Skipped.
- Quality issues (too_blurry, too_dark, too_small): the LLM can't
  fix a bad photo either. Skipped.

**Fail-open behaviour:**
If Gemini is unreachable, returns invalid JSON, or hits a quota, we
fall back to the original rejection from the PlantViT layer. The
farmer sees "couldn't diagnose" with our usual explanatory card —
worse than a real diagnosis but not worse than no fallback layer at
all. All failures are logged loudly.

**Provenance:**
Every LLM-sourced row is tagged ``prediction_source='llm_fallback'``
so the result UI can show a "Diagnosed via general AI" badge and so
the labelling-queue + analytics can aggregate these separately. The
top crops that consistently route through LLM are the natural
candidates for the next training-set expansion.
"""
from __future__ import annotations

import base64
import json
from typing import Any

from app.config import Settings
from app.logging import get_logger

log = get_logger(__name__)

# Rejection reasons for which we attempt LLM fallback. The API can
# override per-request (e.g. when a user has hit their daily quota).
FALLBACK_REASONS = frozenset({"non_target_plant", "low_confidence", "ambiguous"})


# JSON schema returned by Gemini. Mirrors the shape the rest of the
# pipeline expects so the LLM output is a drop-in for the PlantViT
# output. Fields we don't ask the LLM to produce (confidence_score,
# secondary_predictions, model_version) are filled in by the caller.
_GEMINI_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "plant_classification": {
            "type": "string",
            "description": (
                "Common name of the plant in the photo. If you can't identify "
                "a plant at all (image is not a plant), return null in this "
                "field via 'is_plant': false."
            ),
        },
        "scientific_name": {
            "type": "string",
            "description": "Scientific binomial (e.g. 'Rosa indica'). Empty string if unknown.",
        },
        "is_plant": {
            "type": "boolean",
            "description": (
                "True if you can identify a real plant in the image. "
                "False for animals, objects, indoor scenes, etc. — in which "
                "case we will discard your diagnosis."
            ),
        },
        "disease_name": {
            "type": "string",
            "description": (
                "Name of the disease, pest, or condition visible on the plant. "
                "Use 'Healthy' if no visible issues. Use 'Diagnosis uncertain' "
                "if you can see the plant but can't read its condition."
            ),
        },
        "pathogen_name": {
            "type": "string",
            "description": (
                "Specific pathogen / organism causing the disease, when known "
                "(e.g. 'Phytophthora infestans'). Empty string for healthy "
                "plants or unknown pathogens."
            ),
        },
        "infection_type": {
            "type": "string",
            "enum": [
                "fungal",
                "bacterial",
                "viral",
                "insect_pest",
                "nematode",
                "nutrient_deficiency",
                "abiotic_stress",
                "weed_competition",
                "unknown",
            ],
            "description": (
                "Coarse category of the condition. 'unknown' is allowed if "
                "the plant looks healthy or you can't determine the cause."
            ),
        },
        "severity": {
            "type": "string",
            "enum": ["low", "medium", "high", "critical"],
            "description": (
                "How urgent intervention is. 'low' for healthy plants or "
                "minor cosmetic issues; 'critical' only for diseases that "
                "will kill the plant within days without action."
            ),
        },
        "suggested_remedies": {
            "type": "string",
            "description": (
                "Treatment plan as a numbered list (e.g. '1. Remove infected "
                "leaves.\\n2. Apply copper-based fungicide.\\n3. Improve "
                "drainage.'). Tailored to Indian smallholder context — "
                "prefer locally-available chemicals (Mancozeb, copper "
                "oxychloride, neem oil, Bordeaux mixture) over speciality "
                "products. Always reference CIBRC-approved doses where "
                "applicable. If the plant looks healthy, give one-line "
                "maintenance advice instead."
            ),
        },
        "preventive_measures": {
            "type": "string",
            "description": (
                "How to prevent recurrence next season. 2-3 short sentences. "
                "Focus on cultural practices (rotation, sanitation, resistant "
                "varieties) over chemicals."
            ),
        },
    },
    "required": [
        "is_plant",
        "plant_classification",
        "disease_name",
        "infection_type",
        "severity",
        "suggested_remedies",
        "preventive_measures",
    ],
}


def _build_prompt(clip_hint: str | None) -> str:
    """The text part of the multimodal request.

    We thread in CLIP's best guess as a hint, but explicitly tell the
    model to override it if the image disagrees — CLIP can be wrong on
    the long-tail plants we'd be asking it about, and we'd rather the
    LLM follow what it actually sees.
    """
    hint_block = ""
    if clip_hint:
        hint_block = (
            f"\n\nA preliminary classifier suggested this image might be "
            f"a {clip_hint}, but it isn't sure. Use this as a starting "
            f"point if it matches what you see, otherwise ignore it and "
            f"trust the image."
        )

    return (
        "You are an experienced agronomist diagnosing plant diseases for "
        "Indian smallholder farmers. Look at this image and identify:\n\n"
        "  - The plant species (common and scientific names)\n"
        "  - Whether it appears healthy or has a visible disease / pest / "
        "stress\n"
        "  - The likely cause (infection type and pathogen if known)\n"
        "  - A practical treatment plan using inputs commonly available "
        "in Indian agri-input shops\n"
        "  - How to prevent the same issue next season\n\n"
        "Important: be honest about uncertainty. If the image is too "
        "blurry, dark, or doesn't actually contain a plant (e.g. a cat, "
        "an indoor scene, an object), set is_plant=false and use "
        "'Diagnosis uncertain' as the disease_name. Do not make up "
        "diagnoses for non-plant images."
        + hint_block
    )


# Lazy module-level cache. We can't ``@lru_cache`` on a function that
# takes Settings (pydantic-settings instances aren't hashable). One
# client per process is plenty — genai.Client is thread-safe and
# multiplexes HTTP/2 internally.
_client_cache: dict[str, Any] = {}


def _get_client(settings: Settings) -> Any:
    """Lazy Gemini client, cached per api key.

    Imported inside the function so the inference service can boot
    without google-genai installed (e.g. in mock-only deployments
    where the LLM fallback is never invoked).
    """
    from google import genai  # lazy import

    if not settings.gemini_api_key:
        raise RuntimeError(
            "gemini_api_key is empty — LLM fallback can't run. "
            "Set GEMINI_API_KEY on the inference service."
        )
    key = settings.gemini_api_key
    cached = _client_cache.get(key)
    if cached is None:
        cached = genai.Client(api_key=key)
        _client_cache[key] = cached
    return cached


def predict_with_llm(
    image_bytes: bytes,
    language: str,
    settings: Settings,
    clip_hint: str | None = None,
) -> dict[str, Any] | None:
    """Run a Gemini multimodal call. Returns a normalised prediction
    dict on success, or ``None`` if anything goes wrong.

    The caller treats ``None`` as "fallback failed — return the original
    rejection to the user".
    """
    if not settings.gemini_api_key:
        log.warning("llm_fallback_skipped_no_api_key")
        return None

    try:
        # Lazy imports so a deployment without google-genai installed
        # can still serve mock + plantvit predictions.
        from google.genai import types  # lazy

        client = _get_client(settings)
    except ImportError as exc:
        log.error("llm_fallback_import_failed", error=str(exc))
        return None

    prompt = _build_prompt(clip_hint)

    # Gemini SDK takes the image bytes plus an inline mime type. We
    # accept whatever bytes the caller hands us; JPEG and PNG are
    # both fine. We do NOT re-encode (saves CPU) — the model
    # auto-detects from the magic bytes.
    image_part = types.Part.from_bytes(
        data=image_bytes,
        mime_type="image/jpeg" if image_bytes[:3] == b"\xff\xd8\xff" else "image/png",
    )

    try:
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=[image_part, prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_GEMINI_RESPONSE_SCHEMA,
                temperature=0.2,  # low — we want repeatability, not creativity
                max_output_tokens=1024,
            ),
        )
    except Exception as exc:  # noqa: BLE001 — broad catch on purpose
        # Network errors, quota errors, 5xx — anything Gemini throws we
        # treat as "fallback unavailable". The caller surfaces the
        # original rejection instead.
        log.warning(
            "llm_fallback_api_call_failed",
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return None

    raw = response.text  # response_mime_type=json makes this a JSON string
    if not raw:
        log.warning("llm_fallback_empty_response")
        return None

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        log.warning("llm_fallback_invalid_json", error=str(exc), raw_preview=raw[:200])
        return None

    # Defensive: did the model decide there isn't actually a plant in
    # the image after all? CLIP shouldn't have routed us here in that
    # case (it filtered non_target_plant, not not_a_plant), but the
    # model is allowed to disagree. If so, don't return a diagnosis.
    if not parsed.get("is_plant", True):
        log.info("llm_fallback_declined_not_a_plant", model_response=parsed)
        return None

    plant = (parsed.get("plant_classification") or "").strip()
    disease = (parsed.get("disease_name") or "").strip()
    infection = parsed.get("infection_type") or "unknown"
    severity = parsed.get("severity") or "low"

    # Build the same shape the PlantViT path returns so the API doesn't
    # need to branch on source. confidence_score is omitted for LLM
    # rows (LLMs don't expose calibrated probabilities); the UI hides
    # the chip when null.
    return {
        "rejection_reason": None,
        "rejection_hint": None,
        "prediction_source": "llm_fallback",
        "plant_classification": plant or None,
        "scientific_name": (parsed.get("scientific_name") or "").strip() or None,
        "disease_name": disease or None,
        "pathogen_name": (parsed.get("pathogen_name") or "").strip() or None,
        "infection_type": infection,
        "severity": severity,
        "confidence_score": None,
        "secondary_predictions": [],
        # gemini_model already includes the "gemini-" prefix from
        # config.py, so we don't double it.
        "model_version": settings.gemini_model,
        "suggested_remedies": parsed.get("suggested_remedies") or None,
        "chemical_remedies": None,
        "organic_remedies": None,
        "preventive_measures": parsed.get("preventive_measures") or None,
        "followup_questions": _DEFAULT_FOLLOWUPS_FOR_LANGUAGE(language),
    }


def _DEFAULT_FOLLOWUPS_FOR_LANGUAGE(language: str) -> list[dict[str, str]]:
    """Same static followup-question set we use for PlantViT rows. The
    LLM could generate per-diagnosis questions but the cost / latency
    isn't worth it for v1 — same five canned questions work for any
    crop."""
    return [
        {"text": "What is the safe dose for my field size?", "category": "dosage", "language": language},
        {"text": "Is there an organic alternative I can use?", "category": "alternative", "language": language},
        {"text": "When is the best time of day to spray?", "category": "timing", "language": language},
        {"text": "What is the approximate cost per acre?", "category": "cost", "language": language},
        {"text": "How do I prevent this disease next season?", "category": "prevention", "language": language},
    ]


# Re-export so callers don't have to import base64 themselves to log
# debug payloads if they need to.
__all__ = ["FALLBACK_REASONS", "predict_with_llm"]

# Silence unused-import warning for base64; it's intentionally exported
# above for debugging convenience.
_ = base64
