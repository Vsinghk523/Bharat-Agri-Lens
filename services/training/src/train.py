"""Training entry point.

Usage:
    bal-train --config configs/baseline.yaml
    bal-train --config configs/synthetic.yaml --epochs 1   # smoke

Run from a GPU box for the real PlantVillage / PlantDoc / IP102 run.
The synthetic config runs in seconds on CPU and is what the test suite
exercises to keep the pipeline honest.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.optim import AdamW
from torch.optim.lr_scheduler import LambdaLR
from torch.utils.data import DataLoader
from tqdm import tqdm

from src.augment import train_transform, val_transform
from src.config import TrainingPipelineConfig, load_config
from src.datasets import PlantViTDataset
from src.model import build_model


def _set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def _make_loaders(cfg: TrainingPipelineConfig) -> tuple[DataLoader, DataLoader]:
    train_ds = PlantViTDataset(
        root=cfg.data.train_dir,
        crop_labels=cfg.data.crop_labels,
        infection_labels=cfg.data.infection_labels,
        disease_to_infection=cfg.data.disease_to_infection,
        transform=train_transform(cfg.data.image_size),
        class_separator=cfg.data.class_separator,
    )
    val_ds = PlantViTDataset(
        root=cfg.data.val_dir,
        crop_labels=cfg.data.crop_labels,
        infection_labels=cfg.data.infection_labels,
        disease_to_infection=cfg.data.disease_to_infection,
        transform=val_transform(cfg.data.image_size),
        class_separator=cfg.data.class_separator,
    )
    train_dl = DataLoader(
        train_ds,
        batch_size=cfg.train.batch_size,
        shuffle=True,
        num_workers=cfg.data.num_workers,
        pin_memory=torch.cuda.is_available(),
        drop_last=True,
    )
    val_dl = DataLoader(
        val_ds,
        batch_size=cfg.train.batch_size,
        shuffle=False,
        num_workers=cfg.data.num_workers,
        pin_memory=torch.cuda.is_available(),
    )
    return train_dl, val_dl


def _cosine_with_warmup(
    optimizer: torch.optim.Optimizer, total_steps: int, warmup_steps: int
) -> LambdaLR:
    def lr_lambda(step: int) -> float:
        if step < warmup_steps:
            return float(step) / float(max(1, warmup_steps))
        progress = (step - warmup_steps) / max(1, total_steps - warmup_steps)
        return 0.5 * (1.0 + np.cos(np.pi * progress))

    return LambdaLR(optimizer, lr_lambda)


@torch.no_grad()
def _validate(model: nn.Module, val_dl: DataLoader, device: torch.device) -> dict[str, float]:
    """Quick top-1 accuracy + macro-F1-friendly per-head correct count."""
    model.eval()
    crop_correct = 0
    infection_correct = 0
    seen = 0
    for batch in val_dl:
        x, crop_y, infection_y = batch
        x = x.to(device, non_blocking=True)
        crop_y = crop_y.to(device)
        infection_y = infection_y.to(device)
        crop_logits, infection_logits = model(x)
        crop_correct += (crop_logits.argmax(-1) == crop_y).sum().item()
        infection_correct += (infection_logits.argmax(-1) == infection_y).sum().item()
        seen += x.size(0)
    model.train()
    return {
        "val_crop_acc": crop_correct / max(1, seen),
        "val_infection_acc": infection_correct / max(1, seen),
        "val_seen": seen,
    }


def train(cfg: TrainingPipelineConfig, run_dir: Path, *, smoke: bool = False) -> Path:
    """Run training and return the path to the best checkpoint."""
    _set_seed(cfg.train.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[train] device={device}, run_dir={run_dir}, smoke={smoke}")

    train_dl, val_dl = _make_loaders(cfg)
    print(f"[train] train_samples={len(train_dl.dataset)} val_samples={len(val_dl.dataset)}")

    model = build_model(
        cfg.model,
        num_crop_labels=len(cfg.data.crop_labels),
        num_infection_labels=len(cfg.data.infection_labels),
        from_scratch_for_smoke=smoke,
    ).to(device)
    n_trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    n_total = sum(p.numel() for p in model.parameters())
    print(f"[train] trainable params: {n_trainable:,} / {n_total:,}")

    optimizer = AdamW(
        filter(lambda p: p.requires_grad, model.parameters()),
        lr=cfg.train.learning_rate,
        weight_decay=cfg.train.weight_decay,
    )
    total_steps = max(1, cfg.train.epochs * len(train_dl) // max(1, cfg.train.grad_accumulation_steps))
    warmup_steps = max(1, int(total_steps * cfg.train.warmup_ratio))
    scheduler = _cosine_with_warmup(optimizer, total_steps, warmup_steps)

    ce_loss = nn.CrossEntropyLoss()
    scaler = torch.amp.GradScaler("cuda", enabled=cfg.train.mixed_precision and torch.cuda.is_available())

    best_val_acc = -1.0
    best_ckpt: Path | None = None
    epochs_without_improvement = 0

    for epoch in range(cfg.train.epochs):
        model.train()
        epoch_t0 = time.time()
        running_loss = 0.0
        running_n = 0
        for step, batch in enumerate(tqdm(train_dl, desc=f"epoch {epoch + 1}/{cfg.train.epochs}")):
            x, crop_y, infection_y = batch
            x = x.to(device, non_blocking=True)
            crop_y = crop_y.to(device)
            infection_y = infection_y.to(device)

            with torch.amp.autocast("cuda", enabled=scaler.is_enabled()):
                crop_logits, infection_logits = model(x)
                loss_crop = ce_loss(crop_logits, crop_y)
                loss_infection = ce_loss(infection_logits, infection_y)
                loss = loss_crop + cfg.train.infection_loss_weight * loss_infection
                loss = loss / cfg.train.grad_accumulation_steps

            scaler.scale(loss).backward()
            if (step + 1) % cfg.train.grad_accumulation_steps == 0:
                scaler.step(optimizer)
                scaler.update()
                optimizer.zero_grad(set_to_none=True)
                scheduler.step()

            running_loss += loss.item() * x.size(0)
            running_n += x.size(0)
            if (step + 1) % cfg.train.log_every == 0:
                print(
                    f"[train] epoch={epoch + 1} step={step + 1} "
                    f"loss={running_loss / max(1, running_n):.4f}"
                )

        metrics = _validate(model, val_dl, device)
        elapsed = time.time() - epoch_t0
        print(
            f"[train] epoch {epoch + 1} done in {elapsed:.1f}s · "
            f"avg_loss={running_loss / max(1, running_n):.4f} · "
            f"val_crop_acc={metrics['val_crop_acc']:.3f} · "
            f"val_infection_acc={metrics['val_infection_acc']:.3f}"
        )

        epoch_score = metrics["val_infection_acc"]
        if epoch_score > best_val_acc:
            best_val_acc = epoch_score
            best_ckpt = run_dir / "best.pt"
            torch.save(
                {
                    "model_state": model.state_dict(),
                    "config": cfg.__dict__,
                    "epoch": epoch + 1,
                    "metrics": metrics,
                },
                best_ckpt,
            )
            epochs_without_improvement = 0
            print(f"[train] new best: val_infection_acc={best_val_acc:.4f} -> {best_ckpt}")
        else:
            epochs_without_improvement += 1
            if epochs_without_improvement >= cfg.train.early_stop_patience:
                print(f"[train] early stop after {epochs_without_improvement} epochs without improvement")
                break

    if best_ckpt is None:
        # Cover the degenerate single-epoch smoke case where the model
        # never produces a positive accuracy.
        best_ckpt = run_dir / "best.pt"
        torch.save({"model_state": model.state_dict(), "config": cfg.__dict__}, best_ckpt)
    return best_ckpt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--run-dir", default=None)
    parser.add_argument("--smoke", action="store_true", help="Use a tiny untrained ViT (CI / CPU)")
    parser.add_argument("--epochs", type=int, default=None, help="Override config.train.epochs")
    args = parser.parse_args()

    cfg = load_config(args.config)
    if args.epochs is not None:
        cfg.train.epochs = args.epochs

    run_dir = Path(args.run_dir or f"runs/{cfg.name}-{int(time.time())}")
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "config.json").write_text(
        json.dumps(
            {
                "name": cfg.name,
                "data": cfg.data.__dict__,
                "model": cfg.model.__dict__,
                "train": cfg.train.__dict__,
                "export": cfg.export.__dict__,
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    ckpt = train(cfg, run_dir, smoke=args.smoke)
    print(f"\nBest checkpoint: {ckpt}")
    print(f"Next: bal-export --config {args.config} --checkpoint {ckpt}")


if __name__ == "__main__":
    main()
