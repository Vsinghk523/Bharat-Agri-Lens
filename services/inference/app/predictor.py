"""Predictor abstraction.

In production this loads the fine-tuned PlantViT model from S3 and the Gemma
LoRA adapter on a Railway GPU. For the scaffold we ship a deterministic mock
predictor that returns a realistic-looking payload so the rest of the system
can be wired and tested without GPU dependencies.
"""

from __future__ import annotations

import hashlib
from typing import Any

from app.config import Settings


def _seed_from_image(image_id: str) -> int:
    return int(hashlib.sha256(image_id.encode()).hexdigest(), 16) % 7


def mock_predict(image_id: str, language: str, settings: Settings) -> dict[str, Any]:
    """Return a deterministic prediction so flows are testable end-to-end."""
    bucket = _seed_from_image(image_id)
    catalogue = [
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
    base = catalogue[bucket]
    return {
        **base,
        "confidence_score": 0.86 + (bucket % 3) * 0.03,
        "secondary_predictions": [
            {"disease_name": alt["disease_name"], "confidence": 0.04}
            for alt in catalogue[:3]
            if alt["disease_name"] != base["disease_name"]
        ],
        "model_version": settings.vision_model_version,
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
            {"text": "What is the safe dose for my field size?", "category": "dosage", "language": language},
            {"text": "Is there an organic alternative I can use?", "category": "alternative", "language": language},
            {"text": "When is the best time of day to spray?", "category": "timing", "language": language},
            {"text": "What is the approximate cost per acre?", "category": "cost", "language": language},
            {"text": "How do I prevent this disease next season?", "category": "prevention", "language": language},
        ],
    }


async def predict(image_id: str, language: str, settings: Settings) -> dict[str, Any]:
    if settings.use_mock_predictor:
        return mock_predict(image_id, language, settings)
    # TODO: load PlantViT ONNX session, run vision inference,
    # then call Gemma RAG service for remedies + follow-ups.
    raise NotImplementedError("Real predictor not yet wired in")
