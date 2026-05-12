"""Synthetic-data end-to-end smoke for the training pipeline.

Generates a tiny dataset, trains a freshly-initialised micro-ViT for
one epoch on CPU, exports it to ONNX, and verifies the ONNX file loads
cleanly with the right input / output names. Total runtime: ~20s on a
modest laptop.

Not part of the API's pytest run — this test needs the (heavy)
training dependencies installed via ``uv sync`` from
``services/training/``. CI ignores it; humans run it before any
non-trivial change to ``services/training/src/``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# Skip the entire module if torch / transformers / peft / onnxruntime
# aren't installed — pytest emits a clear skip reason rather than an
# import error.
torch = pytest.importorskip("torch")
pytest.importorskip("transformers")
pytest.importorskip("peft")
ort = pytest.importorskip("onnxruntime")

from src.config import load_config  # noqa: E402
from src.export import export_to_onnx  # noqa: E402
from src.synth import generate  # noqa: E402
from src.train import train  # noqa: E402


def test_pipeline_synth_train_export(tmp_path: Path) -> None:
    # Stage a synthetic dataset under tmp_path/data.
    data_dir = tmp_path / "data"
    generate(data_dir, per_class=8, size=96, seed=0)

    # Load the synthetic config, then point its dataset paths at our
    # tmp dir so the test doesn't write outside.
    cfg = load_config(Path(__file__).resolve().parents[1] / "configs" / "synthetic.yaml")
    cfg.data.train_dir = str(data_dir / "train")
    cfg.data.val_dir = str(data_dir / "val")
    cfg.train.epochs = 1
    cfg.train.batch_size = 4
    cfg.train.num_workers = 0
    cfg.data.num_workers = 0

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    ckpt = train(cfg, run_dir, smoke=True)
    assert ckpt.exists(), "training did not produce a checkpoint"

    # Export and verify the ONNX is loadable.
    out_dir = tmp_path / "export"
    paths = export_to_onnx(cfg, ckpt, out_dir, smoke=True, quantize=False)
    onnx_path = paths["onnx_fp32"]
    assert Path(onnx_path).exists()

    sess = ort.InferenceSession(onnx_path, providers=["CPUExecutionProvider"])
    in_name = sess.get_inputs()[0].name
    out_names = [o.name for o in sess.get_outputs()]
    assert in_name == "pixel_values"
    assert out_names == ["crop_logits", "infection_logits"]

    # Quick sanity inference on a zero tensor.
    import numpy as np

    x = np.zeros((1, 3, cfg.data.image_size, cfg.data.image_size), dtype=np.float32)
    outs = sess.run(None, {in_name: x})
    assert outs[0].shape == (1, len(cfg.data.crop_labels))
    assert outs[1].shape == (1, len(cfg.data.infection_labels))

    # Labels round-trip.
    labels = json.loads(Path(paths["labels"]).read_text(encoding="utf-8"))
    assert labels["crop_labels"] == cfg.data.crop_labels
    assert labels["infection_labels"] == cfg.data.infection_labels
