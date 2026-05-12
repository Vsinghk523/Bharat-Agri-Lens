"""YAML-driven training configuration.

A single dataclass mirrored to YAML so we can run ``bal-train --config
configs/baseline.yaml`` without hand-rolling argparse for every knob.
``LabelMap`` is intentionally separate because changes there have to
sync with the inference service's enum, and we want them code-reviewed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class DataConfig:
    train_dir: str  # ImageFolder-style: train_dir/<class_label>/*.jpg
    val_dir: str
    image_size: int = 224
    num_workers: int = 4
    # Class lists. We train both heads in parallel: crop ID + infection
    # type. Either list may be a single "_unused" placeholder if a
    # dataset only labels one of them — the corresponding head still
    # runs but contributes zero loss for those rows.
    crop_labels: list[str] = field(default_factory=list)
    infection_labels: list[str] = field(default_factory=list)
    # How to derive each label from the ImageFolder class string.
    # PlantVillage uses "Tomato___Late_blight"; we split on "___".
    class_separator: str = "___"
    # Map raw disease names -> our canonical infection_type enum.
    # If unmapped, falls back to "unknown".
    disease_to_infection: dict[str, str] = field(default_factory=dict)


@dataclass
class ModelConfig:
    backbone: str = "google/vit-base-patch16-224"
    lora_r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.1
    # Modules within the ViT that LoRA wraps. "query"/"value" of every
    # transformer block is the standard "ViT LoRA" footprint.
    lora_target_modules: list[str] = field(default_factory=lambda: ["query", "value"])
    dropout: float = 0.1


@dataclass
class TrainConfig:
    epochs: int = 10
    batch_size: int = 32
    learning_rate: float = 5e-4
    weight_decay: float = 0.01
    warmup_ratio: float = 0.05
    grad_accumulation_steps: int = 1
    mixed_precision: bool = True
    seed: int = 42
    save_every: int = 1  # epochs between checkpoints
    log_every: int = 50  # steps between log lines
    early_stop_patience: int = 3  # epochs of no val-F1 improvement before stop
    # Loss weight on the infection-type head relative to the crop head.
    # Both heads share the backbone; infection is the more business-critical
    # output so weight it slightly higher.
    infection_loss_weight: float = 1.5


@dataclass
class ExportConfig:
    out_dir: str = "runs/latest/export"
    quantize: bool = True
    opset: int = 17


@dataclass
class TrainingPipelineConfig:
    name: str
    data: DataConfig
    model: ModelConfig
    train: TrainConfig
    export: ExportConfig = field(default_factory=ExportConfig)


def load_config(path: str | Path) -> TrainingPipelineConfig:
    raw: dict[str, Any] = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return TrainingPipelineConfig(
        name=raw["name"],
        data=DataConfig(**raw["data"]),
        model=ModelConfig(**raw.get("model", {})),
        train=TrainConfig(**raw.get("train", {})),
        export=ExportConfig(**raw.get("export", {})),
    )
