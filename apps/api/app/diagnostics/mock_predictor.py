"""Inline mock predictor for the diagnostics flow.

Mirrors ``services/inference/app/predictor.py``'s ``mock_predict`` so the
api can return a realistic-looking diagnostic even when the inference
service hasn't been deployed yet. Gated behind
``INFERENCE_FALLBACK_TO_MOCK`` so it never accidentally fires in real
production deployments.

Determinism by ``image_id`` is important — refreshing the result page
must return the same prediction, not a new random one each call.
"""

from __future__ import annotations

import hashlib
from typing import Any

_CATALOGUE: list[dict[str, Any]] = [
    {
        "plant_classification": "Tomato",
        "scientific_name": "Solanum lycopersicum",
        "disease_name": "Late blight",
        "pathogen_name": "Phytophthora infestans",
        "infection_type": "fungal",
        "severity": "high",
    },
    {
        "plant_classification": "Potato",
        "scientific_name": "Solanum tuberosum",
        "disease_name": "Early blight",
        "pathogen_name": "Alternaria solani",
        "infection_type": "fungal",
        "severity": "medium",
    },
    {
        "plant_classification": "Cotton",
        "scientific_name": "Gossypium hirsutum",
        "disease_name": "Bollworm infestation",
        "pathogen_name": "Helicoverpa armigera",
        "infection_type": "insect_pest",
        "severity": "high",
    },
    {
        "plant_classification": "Rice",
        "scientific_name": "Oryza sativa",
        "disease_name": "Bacterial leaf blight",
        "pathogen_name": "Xanthomonas oryzae pv. oryzae",
        "infection_type": "bacterial",
        "severity": "medium",
    },
    {
        "plant_classification": "Brinjal",
        "scientific_name": "Solanum melongena",
        "disease_name": "Tomato yellow leaf curl virus",
        "pathogen_name": "TYLCV (Begomovirus)",
        "infection_type": "viral",
        "severity": "high",
    },
    {
        "plant_classification": "Wheat",
        "scientific_name": "Triticum aestivum",
        "disease_name": "Nitrogen deficiency",
        "pathogen_name": None,
        "infection_type": "nutrient_deficiency",
        "severity": "low",
    },
    {
        "plant_classification": "Mango",
        "scientific_name": "Mangifera indica",
        "disease_name": "Powdery mildew",
        "pathogen_name": "Oidium mangiferae",
        "infection_type": "fungal",
        "severity": "medium",
    },
]


def _seed_from_image(image_id: str) -> int:
    return int(hashlib.sha256(image_id.encode()).hexdigest(), 16) % len(_CATALOGUE)


def mock_predict(image_id: str, language: str) -> dict[str, Any]:
    """Return a deterministic prediction so the UI is testable end-to-end."""
    bucket = _seed_from_image(image_id)
    base = _CATALOGUE[bucket]
    return {
        **base,
        "confidence_score": 0.86 + (bucket % 3) * 0.03,
        "secondary_predictions": [
            {"disease_name": alt["disease_name"], "confidence": 0.04}
            for alt in _CATALOGUE[:3]
            if alt["disease_name"] != base["disease_name"]
        ],
        "model_version": "api-inline-mock-0.1",
        "suggested_remedies": (
            "1. Remove and destroy affected plant parts.\n"
            "2. Apply a recommended fungicide / pesticide per CIBRC label dose.\n"
            "3. Improve airflow and avoid overhead irrigation."
        ),
        "chemical_remedies": [
            {
                "name": "Mancozeb 75% WP",
                "dose": "2.0 g / litre water",
                "interval_days": 7,
                "phi_days": 14,
            }
        ],
        "organic_remedies": [
            {
                "name": "Neem oil 3%",
                "dose": "5 ml / litre water",
                "interval_days": 7,
            }
        ],
        "preventive_measures": (
            "Rotate crops, use certified seed, maintain plant spacing, "
            "and scout fields weekly during humid conditions."
        ),
        "followup_questions": [
            {
                "text": "What is the safe dose for my field size?",
                "category": "dosage",
                "language": language,
            },
            {
                "text": "Is there an organic alternative I can use?",
                "category": "alternative",
                "language": language,
            },
            {
                "text": "When is the best time of day to spray?",
                "category": "timing",
                "language": language,
            },
            {
                "text": "What is the approximate cost per acre?",
                "category": "cost",
                "language": language,
            },
            {
                "text": "How do I prevent this disease next season?",
                "category": "prevention",
                "language": language,
            },
        ],
    }
