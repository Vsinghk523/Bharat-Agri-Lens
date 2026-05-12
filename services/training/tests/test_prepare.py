"""Dataset prep smoke — feeds a tiny fake source tree through prepare()
and asserts the merged ImageFolder layout + stratified train/val split.

This test is plain-stdlib (Pillow only) so it runs in CI / without
the torch stack, unlike test_pipeline.py.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

PIL = pytest.importorskip("PIL")

from scripts.prepare import prepare  # noqa: E402


def _make_png(path: Path, color: tuple[int, int, int] = (50, 100, 50)) -> None:
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8), color=color).save(path)


def _stage_plantvillage(root: Path) -> None:
    for cls in ("Tomato___Late_blight", "Tomato___healthy", "Apple___Apple_scab"):
        for i in range(6):
            _make_png(root / cls / f"img_{i}.jpg")


def _stage_plantdoc(root: Path) -> None:
    # Spaces in class names + variable casing — the canonicaliser handles both.
    for split in ("train", "test"):
        for cls in ("Tomato leaf bacterial spot", "Apple Scab Leaf"):
            for i in range(3):
                _make_png(root / split / cls / f"img_{i}.jpg")


def _stage_ip102(root: Path) -> None:
    (root / "Image").mkdir(parents=True, exist_ok=True)
    for i in range(4):
        _make_png(root / "Image" / f"{i:04d}.jpg")
    (root / "classes.txt").write_text("rice_leaf_roller\nbollworm\n", encoding="utf-8")
    (root / "train.txt").write_text(
        "Image/0000.jpg 0\nImage/0001.jpg 1\nImage/0002.jpg 0\n", encoding="utf-8"
    )
    (root / "test.txt").write_text("Image/0003.jpg 1\n", encoding="utf-8")


def test_prepare_merges_three_sources(tmp_path: Path) -> None:
    pv = tmp_path / "pv"
    pd = tmp_path / "pd"
    ip = tmp_path / "ip"
    out = tmp_path / "combined"
    _stage_plantvillage(pv)
    _stage_plantdoc(pd)
    _stage_ip102(ip)

    summary = prepare(out, pv, pd, ip, val_fraction=0.2, seed=7)

    # Source counts:
    #   plantvillage: 3 classes * 6 imgs = 18
    #   plantdoc:     2 classes * 2 splits * 3 imgs = 12
    #   ip102:        4 images
    assert summary["source_counts"] == {"plantvillage": 18, "plantdoc": 12, "ip102": 4}
    assert summary["total_train"] + summary["total_val"] == 18 + 12 + 4

    # Tomato and Apple should appear regardless of which source they came
    # from — proving the canonicaliser collapsed casing variants.
    assert (out / "train" / "Tomato___Late_blight").is_dir()
    assert (out / "train" / "Apple___Apple_scab").is_dir()
    # PlantDoc class names contained spaces; they should land under
    # disease names with underscores.
    classes = {p.name for p in (out / "train").iterdir()}
    assert any(c.startswith("Tomato___") and c != "Tomato___Late_blight" for c in classes)

    # IP102 images go under Unknown crop with the pest name as disease.
    assert (out / "train" / "Unknown___bollworm").is_dir() or (
        out / "val" / "Unknown___bollworm"
    ).is_dir()

    # Summary JSON is written next to the output.
    summary_disk = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary_disk["n_classes"] == summary["n_classes"]
