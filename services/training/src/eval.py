"""Standalone evaluation of a saved checkpoint.

Produces per-class precision / recall / F1 + a confusion-matrix tally
that gets dumped to ``metrics.json`` alongside the checkpoint. Useful
for comparing two runs without re-training.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch
from sklearn.metrics import classification_report, confusion_matrix
from torch.utils.data import DataLoader
from tqdm import tqdm

from src.augment import val_transform
from src.config import load_config
from src.datasets import PlantViTDataset
from src.model import build_model


@torch.no_grad()
def evaluate(checkpoint_path: str | Path, config_path: str | Path, *, smoke: bool = False) -> dict:
    cfg = load_config(config_path)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = build_model(
        cfg.model,
        num_crop_labels=len(cfg.data.crop_labels),
        num_infection_labels=len(cfg.data.infection_labels),
        from_scratch_for_smoke=smoke,
    ).to(device)
    state = torch.load(checkpoint_path, map_location=device, weights_only=False)
    model.load_state_dict(state["model_state"])
    model.eval()

    ds = PlantViTDataset(
        root=cfg.data.val_dir,
        crop_labels=cfg.data.crop_labels,
        infection_labels=cfg.data.infection_labels,
        disease_to_infection=cfg.data.disease_to_infection,
        transform=val_transform(cfg.data.image_size),
        class_separator=cfg.data.class_separator,
    )
    dl = DataLoader(ds, batch_size=cfg.train.batch_size, shuffle=False, num_workers=0)

    crop_pred: list[int] = []
    crop_true: list[int] = []
    inf_pred: list[int] = []
    inf_true: list[int] = []
    for x, crop_y, infection_y in tqdm(dl, desc="eval"):
        x = x.to(device, non_blocking=True)
        crop_logits, infection_logits = model(x)
        crop_pred.extend(crop_logits.argmax(-1).cpu().tolist())
        crop_true.extend(crop_y.tolist())
        inf_pred.extend(infection_logits.argmax(-1).cpu().tolist())
        inf_true.extend(infection_y.tolist())

    report = {
        "crop": {
            "report": classification_report(
                crop_true, crop_pred, target_names=cfg.data.crop_labels, zero_division=0, output_dict=True
            ),
            "confusion_matrix": confusion_matrix(crop_true, crop_pred).tolist(),
        },
        "infection": {
            "report": classification_report(
                inf_true,
                inf_pred,
                target_names=cfg.data.infection_labels,
                zero_division=0,
                output_dict=True,
            ),
            "confusion_matrix": confusion_matrix(inf_true, inf_pred).tolist(),
        },
        "n_samples": int(len(crop_true)),
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--out", default=None, help="Write metrics.json (default: alongside checkpoint)")
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()

    metrics = evaluate(args.checkpoint, args.config, smoke=args.smoke)
    out = Path(args.out or (Path(args.checkpoint).parent / "metrics.json"))
    out.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(f"Wrote {out}")
    print(
        f"crop macro F1:       {metrics['crop']['report']['macro avg']['f1-score']:.4f}\n"
        f"infection macro F1:  {metrics['infection']['report']['macro avg']['f1-score']:.4f}"
    )


if __name__ == "__main__":
    main()
