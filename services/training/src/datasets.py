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


class ActiveLearningDataset(Dataset):
    """Loader for the HF Dataset that ``apps/api/app/jobs/export_training_data.py``
    pushes nightly to ``HF_TRAINING_DATASET_REPO``.

    Differences from PlantViTDataset:
    - Source is an HF Dataset (single Parquet shard, not folder tree).
    - Labels come straight from ``label_plant`` / ``label_infection_type``
      columns (the agronomist's authoritative re-labels), not from
      directory names.
    - Each row carries provenance (``prediction_source``,
      ``user_feedback``, ``reviewed_by``, etc.) that the trainer can
      use for stratification or filtering.

    Why a separate class instead of a unified loader: the two data
    sources have legitimately different shapes (folder tree vs
    columnar dataset) and different label semantics (filename split vs
    explicit columns). Forcing a single class would need adapters
    everywhere; two narrow classes + ``ConcatDataset`` is cleaner.

    Combining with PlantVillage:

        from torch.utils.data import ConcatDataset
        pv = PlantViTDataset(root="data/plantvillage", ...)
        al = ActiveLearningDataset.from_hub(
            "viveksk523/bal-training-data",
            crop_labels=pv.crop_to_idx,  # reuse the same vocabulary
            infection_labels=pv.infection_to_idx,
            transform=train_transform,
        )
        combined = ConcatDataset([pv, al])
    """

    def __init__(
        self,
        dataset: Any,
        crop_to_idx: dict[str, int],
        infection_to_idx: dict[str, int],
        transform: Any | None = None,
        require_gold_labels: bool = True,
    ) -> None:
        # ``dataset`` is an ``hf datasets.Dataset`` instance. Stored
        # by reference — no copy. The class does not require the
        # ``datasets`` library at module-import time; it's a runtime
        # dependency you bring in via ``from_hub`` or by passing your
        # own.
        self.ds = dataset
        self.transform = transform
        self.crop_to_idx = crop_to_idx
        self.infection_to_idx = infection_to_idx
        self.unknown_infection_idx = infection_to_idx.get("unknown", 0)

        # Filter at construction time so __len__ matches what we'll
        # actually yield. ``require_gold_labels=True`` (default) keeps
        # only rows where the agronomist provided a label_plant.
        if require_gold_labels:
            kept_indices = [
                i for i, row in enumerate(self.ds)
                if row.get("label_plant")
            ]
            if len(kept_indices) != len(self.ds):
                self.ds = self.ds.select(kept_indices)

    @classmethod
    def from_hub(
        cls,
        repo_id: str,
        crop_to_idx: dict[str, int],
        infection_to_idx: dict[str, int],
        token: str | None = None,
        split: str = "train",
        transform: Any | None = None,
        require_gold_labels: bool = True,
    ) -> "ActiveLearningDataset":
        """Convenience: load from HF Hub by repo_id."""
        from datasets import load_dataset  # lazy

        ds = load_dataset(repo_id, split=split, token=token)
        return cls(
            ds,
            crop_to_idx=crop_to_idx,
            infection_to_idx=infection_to_idx,
            transform=transform,
            require_gold_labels=require_gold_labels,
        )

    def __len__(self) -> int:
        return len(self.ds)

    def __getitem__(self, idx: int) -> tuple[Any, int, int]:
        row = self.ds[idx]
        # ``image`` column is HF's ``Image`` feature which decodes
        # bytes lazily to a PIL.Image when accessed.
        img = row["image"].convert("RGB")
        crop_idx = self.crop_to_idx.get(row.get("label_plant", ""), 0)
        infection_idx = self.infection_to_idx.get(
            row.get("label_infection_type") or "unknown",
            self.unknown_infection_idx,
        )
        if self.transform is not None:
            arr = np.array(img)
            out = self.transform(image=arr)
            tensor = out["image"]
        else:
            tensor = np.array(img)
        return tensor, crop_idx, infection_idx
