"""Merge PlantVillage + PlantDoc + IP102 into the combined ImageFolder
layout the training pipeline expects.

Output:
    data/combined/
      train/<Crop>___<Disease>/*.jpg
      val/<Crop>___<Disease>/*.jpg

Run:
    python -m scripts.prepare \
        --plantvillage data/raw/plantvillage/PlantVillage \
        --plantdoc     data/raw/plantdoc \
        --ip102        data/raw/ip102 \
        --out          data/combined \
        --val-fraction 0.1

Any source can be omitted — the script logs how many images it took
from each and which (Crop, Disease) combinations it had to coin a new
folder for. A summary JSON is written alongside the output so the next
person can spot drift across runs.

Implementation notes:
- We default to hard links (``os.link``) instead of copying, so a 5 GB
  merge consumes ~no extra disk on filesystems that support it. Falls
  back to copying when hard-linking fails (cross-volume, FAT32, etc.).
- Train/val split is per-class (stratified) and deterministic given
  the same ``--seed`` so reruns produce the same partition.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import sys
from collections import defaultdict
from pathlib import Path

# Crop names get normalised against this canonical list so we don't end
# up with both "Apple" and "apple" folders. Extend cautiously — the
# inference labels.json reads from configs/baseline.yaml.crop_labels and
# both must agree.
CANONICAL_CROPS = {
    "apple": "Apple",
    "blueberry": "Blueberry",
    "cherry": "Cherry",
    "cherry_(including_sour)": "Cherry",
    "corn": "Corn",
    "corn_(maize)": "Corn",
    "maize": "Corn",
    "grape": "Grape",
    "orange": "Orange",
    "peach": "Peach",
    "pepper": "Pepper",
    "pepper,_bell": "Pepper",
    "bell_pepper": "Pepper",
    "potato": "Potato",
    "raspberry": "Raspberry",
    "rice": "Rice",
    "soybean": "Soybean",
    "squash": "Squash",
    "strawberry": "Strawberry",
    "tomato": "Tomato",
    "cotton": "Cotton",
    "wheat": "Wheat",
    "mango": "Mango",
    "brinjal": "Brinjal",
    "eggplant": "Brinjal",
}


def _canon_crop(raw: str) -> str:
    key = raw.strip().lower().replace(" ", "_").replace("-", "_")
    return CANONICAL_CROPS.get(key, raw.strip().replace(" ", "_"))


def _canon_disease(raw: str) -> str:
    """Disease names keep their case but normalise spaces / dashes."""
    return raw.strip().replace(" ", "_").replace("-", "_")


def _link_or_copy(src: Path, dst: Path) -> None:
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def _iter_plantvillage(root: Path):
    """PlantVillage layout: ``<root>/<Crop>___<Disease>/*.jpg``."""
    if not root.is_dir():
        return
    for cls_dir in sorted(root.iterdir()):
        if not cls_dir.is_dir():
            continue
        crop_raw, sep, disease_raw = cls_dir.name.partition("___")
        if not sep:
            print(f"  [plantvillage] skipping {cls_dir.name}: no '___' separator", file=sys.stderr)
            continue
        crop = _canon_crop(crop_raw)
        disease = _canon_disease(disease_raw)
        for img in cls_dir.iterdir():
            if img.suffix.lower() in {".jpg", ".jpeg", ".png"}:
                yield crop, disease, img


def _iter_plantdoc(root: Path):
    """PlantDoc layout: ``<root>/train|test/<Crop> <Disease>/*.jpg``.
    Names use spaces and dashes inconsistently (e.g. 'Tomato leaf
    bacterial spot'). We treat the first token as crop, the rest as
    disease, and let ``_canon_*`` normalise."""
    if not root.is_dir():
        return
    for split_name in ("train", "test", "val"):
        split = root / split_name
        if not split.is_dir():
            continue
        for cls_dir in sorted(split.iterdir()):
            if not cls_dir.is_dir():
                continue
            parts = cls_dir.name.split(" ", 1)
            if len(parts) < 2:
                print(f"  [plantdoc] skipping {cls_dir.name}: cannot split crop/disease", file=sys.stderr)
                continue
            crop = _canon_crop(parts[0])
            disease = _canon_disease(parts[1])
            for img in cls_dir.iterdir():
                if img.suffix.lower() in {".jpg", ".jpeg", ".png"}:
                    yield crop, disease, img


def _iter_ip102(root: Path):
    """IP102 layout: ``<root>/Image/<idx>.jpg`` + ``classes.txt`` +
    ``train.txt`` / ``test.txt`` listing ``<rel_path> <class_idx>``.

    All IP102 images describe insect pests on various crops; we collapse
    them under crop='Unknown' (or per-pest crop when classes.txt names
    one) and disease=<pest_name>, infection_type=insect_pest."""
    if not root.is_dir():
        return
    classes_file = root / "classes.txt"
    if not classes_file.exists():
        # Some distributions ship 'species_list.txt' or numeric only.
        classes_file = root / "species_list.txt"
        if not classes_file.exists():
            print(f"  [ip102] no classes/species file in {root}", file=sys.stderr)
            return
    class_names = [line.strip() for line in classes_file.read_text(encoding="utf-8").splitlines() if line.strip()]

    for split_name, fname in (("train", "train.txt"), ("test", "test.txt"), ("val", "val.txt")):
        manifest = root / fname
        if not manifest.exists():
            continue
        for line in manifest.read_text(encoding="utf-8").splitlines():
            parts = line.strip().split()
            if len(parts) < 2:
                continue
            rel, idx_s = parts[0], parts[1]
            try:
                idx = int(idx_s)
            except ValueError:
                continue
            if not (0 <= idx < len(class_names)):
                continue
            pest = class_names[idx]
            crop = "Unknown"
            disease = _canon_disease(pest)
            img_path = root / rel
            if img_path.exists():
                yield crop, disease, img_path


def prepare(
    out_dir: Path,
    plantvillage: Path | None,
    plantdoc: Path | None,
    ip102: Path | None,
    val_fraction: float,
    seed: int,
) -> dict[str, int]:
    rng = random.Random(seed)
    # bucket key -> list of source Paths
    buckets: dict[tuple[str, str], list[Path]] = defaultdict(list)
    counts: dict[str, int] = {"plantvillage": 0, "plantdoc": 0, "ip102": 0}

    for tag, it in (
        ("plantvillage", _iter_plantvillage(plantvillage) if plantvillage else iter([])),
        ("plantdoc", _iter_plantdoc(plantdoc) if plantdoc else iter([])),
        ("ip102", _iter_ip102(ip102) if ip102 else iter([])),
    ):
        for crop, disease, img in it:
            buckets[(crop, disease)].append(img)
            counts[tag] += 1

    train_root = out_dir / "train"
    val_root = out_dir / "val"
    train_root.mkdir(parents=True, exist_ok=True)
    val_root.mkdir(parents=True, exist_ok=True)

    train_counts: dict[str, int] = {}
    val_counts: dict[str, int] = {}
    for (crop, disease), images in buckets.items():
        cls_name = f"{crop}___{disease}"
        # Stratified split: shuffle within class, take val_fraction off
        # the top. min 1 in val if the class has ≥ 2 samples.
        rng.shuffle(images)
        n_val = max(1, int(len(images) * val_fraction)) if len(images) >= 2 else 0
        val_images = images[:n_val]
        train_images = images[n_val:]

        (train_root / cls_name).mkdir(parents=True, exist_ok=True)
        (val_root / cls_name).mkdir(parents=True, exist_ok=True)

        for i, src in enumerate(train_images):
            dst = train_root / cls_name / f"{i:06d}{src.suffix.lower()}"
            _link_or_copy(src, dst)
        for i, src in enumerate(val_images):
            dst = val_root / cls_name / f"{i:06d}{src.suffix.lower()}"
            _link_or_copy(src, dst)

        train_counts[cls_name] = len(train_images)
        val_counts[cls_name] = len(val_images)

    summary = {
        "source_counts": counts,
        "train_per_class": train_counts,
        "val_per_class": val_counts,
        "total_train": sum(train_counts.values()),
        "total_val": sum(val_counts.values()),
        "n_classes": len(buckets),
        "val_fraction": val_fraction,
        "seed": seed,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plantvillage", type=Path, default=None)
    parser.add_argument("--plantdoc", type=Path, default=None)
    parser.add_argument("--ip102", type=Path, default=None)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--val-fraction", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    if not any((args.plantvillage, args.plantdoc, args.ip102)):
        parser.error("at least one of --plantvillage / --plantdoc / --ip102 is required")

    summary = prepare(
        args.out, args.plantvillage, args.plantdoc, args.ip102,
        val_fraction=args.val_fraction, seed=args.seed,
    )
    print(json.dumps(summary, indent=2))
    print(
        f"\nReady: {summary['total_train']:,} train + {summary['total_val']:,} val "
        f"across {summary['n_classes']} classes in {args.out}"
    )


if __name__ == "__main__":
    main()
