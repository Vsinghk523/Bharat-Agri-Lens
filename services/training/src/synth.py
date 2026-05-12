"""Procedural synthetic dataset for pipeline smoke testing.

Generates a tiny ImageFolder-shaped tree with deterministically coloured
squares per class. Lets us exercise the full train -> eval -> export
pipeline in seconds on a laptop CPU before throwing real datasets and
GPU hours at it.
"""

from __future__ import annotations

import argparse
import random
from pathlib import Path

from PIL import Image, ImageDraw

# (crop, disease, infection_type) - the class label is
# f"{crop}___{disease}" so it parses through the same code path as
# PlantVillage.
CLASSES: list[tuple[str, str, str, tuple[int, int, int]]] = [
    ("Tomato", "Late_blight", "fungal", (45, 110, 80)),
    ("Tomato", "Healthy", "unknown", (60, 170, 90)),
    ("Potato", "Early_blight", "fungal", (90, 70, 50)),
    ("Cotton", "Bollworm", "insect_pest", (180, 140, 60)),
    ("Rice", "Bacterial_blight", "bacterial", (160, 170, 70)),
    ("Wheat", "Nitrogen_deficiency", "nutrient_deficiency", (200, 200, 110)),
]


def _draw_one(rgb: tuple[int, int, int], size: int, rng: random.Random) -> Image.Image:
    """Coloured square plus a couple of noise blotches so the model has
    a non-trivial pattern to fit."""
    img = Image.new("RGB", (size, size), rgb)
    draw = ImageDraw.Draw(img)
    for _ in range(6):
        x = rng.randint(0, size - 1)
        y = rng.randint(0, size - 1)
        r = rng.randint(3, max(4, size // 8))
        jitter = tuple(max(0, min(255, c + rng.randint(-30, 30))) for c in rgb)
        draw.ellipse((x - r, y - r, x + r, y + r), fill=jitter)
    return img


def generate(out_dir: Path, per_class: int = 32, size: int = 96, seed: int = 0) -> dict[str, int]:
    """Write ``out_dir/train/<class>/*.png`` and ``out_dir/val/<class>/*.png``.

    Returns a mapping of class -> total files written, for assertions.
    """
    rng = random.Random(seed)
    counts: dict[str, int] = {}
    for split, n in (("train", per_class), ("val", max(4, per_class // 4))):
        for crop, disease, _infection, base_rgb in CLASSES:
            cls_name = f"{crop}___{disease}"
            cls_dir = out_dir / split / cls_name
            cls_dir.mkdir(parents=True, exist_ok=True)
            for i in range(n):
                img = _draw_one(base_rgb, size, rng)
                img.save(cls_dir / f"{i:04d}.png")
            counts[f"{split}/{cls_name}"] = n
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a tiny synthetic plant dataset.")
    parser.add_argument("--out", default="data/synthetic", help="Output directory")
    parser.add_argument("--per-class", type=int, default=32, help="Train samples per class")
    parser.add_argument("--size", type=int, default=96, help="Image dimension in px")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    counts = generate(Path(args.out), per_class=args.per_class, size=args.size, seed=args.seed)
    total = sum(counts.values())
    print(f"Wrote {total} files across {len(counts)} class/split combinations into {args.out}")


if __name__ == "__main__":
    main()
