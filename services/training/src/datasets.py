"""Dual-label image dataset.

Builds on torchvision's ``ImageFolder`` discovery semantics — point it
at ``train_dir`` and it walks ``train_dir/<class>/*.jpg``. Each class
folder name is split into ``(crop, disease)`` via the configured
separator, and each ``disease`` is mapped through
``disease_to_infection`` to one of our canonical infection-type
labels. Returns ``(image_tensor, crop_idx, infection_idx)`` per sample.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
from torch.utils.data import Dataset


def _list_images(class_dir: Path) -> list[Path]:
    exts = {".jpg", ".jpeg", ".png", ".webp"}
    return sorted(p for p in class_dir.iterdir() if p.suffix.lower() in exts)


class PlantViTDataset(Dataset):
    """ImageFolder-style dataset with two parallel labels per sample."""

    def __init__(
        self,
        root: str | Path,
        crop_labels: list[str],
        infection_labels: list[str],
        disease_to_infection: dict[str, str],
        transform: Any | None = None,
        class_separator: str = "___",
    ) -> None:
        self.root = Path(root)
        if not self.root.is_dir():
            raise FileNotFoundError(f"dataset root does not exist: {self.root}")
        self.transform = transform
        self.class_sep = class_separator
        self.crop_to_idx = {label: i for i, label in enumerate(crop_labels)}
        self.infection_to_idx = {label: i for i, label in enumerate(infection_labels)}
        self.disease_to_infection = disease_to_infection

        # Build the sample list once at construction so __len__ / __getitem__
        # are cheap. Each entry: (path, crop_idx, infection_idx).
        unknown_infection_idx = self.infection_to_idx.get("unknown", 0)
        self.samples: list[tuple[Path, int, int]] = []
        for cls_dir in sorted(self.root.iterdir()):
            if not cls_dir.is_dir():
                continue
            crop, _, disease = cls_dir.name.partition(self.class_sep)
            crop_idx = self.crop_to_idx.get(crop, 0)
            infection_label = self.disease_to_infection.get(disease, "unknown")
            infection_idx = self.infection_to_idx.get(
                infection_label, unknown_infection_idx
            )
            for img_path in _list_images(cls_dir):
                self.samples.append((img_path, crop_idx, infection_idx))

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> tuple[Any, int, int]:
        path, crop_idx, infection_idx = self.samples[idx]
        img = Image.open(path).convert("RGB")
        if self.transform is not None:
            # Albumentations transforms expect a numpy array and return
            # a dict; torchvision transforms take the PIL image directly.
            arr = np.array(img)
            out = self.transform(image=arr)
            tensor = out["image"]
        else:
            tensor = np.array(img)
        return tensor, crop_idx, infection_idx
