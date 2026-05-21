"""PlantViT: a ViT-B/16 with LoRA adapters and two classification heads.

We start from an ImageNet-21k-pretrained ViT and add:

* LoRA wraps around the ``query`` and ``value`` projections of every
  transformer block. PEFT handles the wiring; the backbone weights
  are frozen, only the rank-r adapters train.
* Two linear heads on the pooled CLS token output:
    - ``crop_head``      -> num_crop_labels classes  (e.g. Tomato, Rice…)
    - ``infection_head`` -> num_infection_labels classes (insect_pest, fungal…)

Both heads share the encoder. They train jointly via a weighted sum of
cross-entropy losses (see ``TrainConfig.infection_loss_weight``).

The forward signature returns both logits sets unconditionally — at
inference time the caller picks which it wants. Same model exports
cleanly to ONNX with a tuple output.
"""

from __future__ import annotations

import torch
import torch.nn as nn
from peft import LoraConfig, get_peft_model
from transformers import ViTConfig, ViTModel

from src.config import ModelConfig


def _resolve_lora_targets(
    backbone: nn.Module,
    configured: list[str],
) -> list[str]:
    """Pick LoRA target module names that actually exist in this backbone.

    Different transformers releases name the attention projections
    differently:

    - ``query`` / ``key`` / ``value``  — classic ViTSelfAttention
    - ``q_proj`` / ``k_proj`` / ``v_proj`` — newer HuggingFace standard
      used by many SDPA-backed implementations and the canonical naming
      PEFT 0.13+ documentation recommends

    PEFT requires every configured target_modules entry to match at least
    one nn.Module in the backbone, so a stale config name breaks the
    whole adapter injection with `Target modules {...} not found`. Auto-
    detect what's there and fall back to the modern naming when the
    configured one isn't present — keeps existing configs working across
    version bumps without manual yaml surgery.
    """
    suffixes = {name.split(".")[-1] for name, _ in backbone.named_modules() if name}
    if configured and all(t in suffixes for t in configured):
        return list(configured)

    print(
        f"[model] configured LoRA targets {configured} not all present; "
        f"available attention-like suffixes: "
        f"{sorted(s for s in suffixes if any(k in s.lower() for k in ('query', 'key', 'value', 'proj', 'attn')))}"
    )
    for fallback in (["q_proj", "v_proj"], ["query", "value"]):
        if all(t in suffixes for t in fallback):
            print(f"[model] falling back to LoRA targets: {fallback}")
            return fallback
    raise RuntimeError(
        f"Cannot find any usable LoRA target modules. Configured "
        f"({configured}) and known fallbacks all missing. "
        f"All module suffixes in backbone: {sorted(suffixes)}"
    )


class PlantViT(nn.Module):
    def __init__(
        self,
        model_cfg: ModelConfig,
        num_crop_labels: int,
        num_infection_labels: int,
    ) -> None:
        super().__init__()
        self.num_crop_labels = num_crop_labels
        self.num_infection_labels = num_infection_labels

        backbone = ViTModel.from_pretrained(model_cfg.backbone, add_pooling_layer=True)
        # Freeze all backbone weights; only LoRA adapters and the two
        # heads we add below will actually train.
        for p in backbone.parameters():
            p.requires_grad = False

        targets = _resolve_lora_targets(backbone, model_cfg.lora_target_modules)
        lora_cfg = LoraConfig(
            r=model_cfg.lora_r,
            lora_alpha=model_cfg.lora_alpha,
            target_modules=targets,
            lora_dropout=model_cfg.lora_dropout,
            bias="none",
        )
        self.backbone = get_peft_model(backbone, lora_cfg)

        hidden_size = backbone.config.hidden_size
        self.dropout = nn.Dropout(model_cfg.dropout)
        self.crop_head = nn.Linear(hidden_size, num_crop_labels)
        self.infection_head = nn.Linear(hidden_size, num_infection_labels)

    def forward(self, pixel_values: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        out = self.backbone(pixel_values=pixel_values)
        # ViTModel returns last_hidden_state + pooler_output; the pooler
        # is a tanh-projected CLS token, which is what we want.
        pooled = out.pooler_output
        pooled = self.dropout(pooled)
        return self.crop_head(pooled), self.infection_head(pooled)


def build_model(
    model_cfg: ModelConfig,
    num_crop_labels: int,
    num_infection_labels: int,
    *,
    from_scratch_for_smoke: bool = False,
) -> PlantViT:
    """Construct the model.

    ``from_scratch_for_smoke=True`` skips downloading pretrained weights
    and uses ``ViTModel(ViTConfig(...))`` instead. This is what the
    pytest smoke test uses so CI / tiny CPU runs don't pull 300 MB from
    HuggingFace.
    """
    if from_scratch_for_smoke:
        # Build a tiny untrained ViT — enough to verify shapes flow.
        # Production code path doesn't take this branch.
        cfg = ViTConfig(
            hidden_size=128,
            num_hidden_layers=2,
            num_attention_heads=4,
            intermediate_size=256,
            image_size=96,
            patch_size=16,
        )
        backbone = ViTModel(cfg, add_pooling_layer=True)
        for p in backbone.parameters():
            p.requires_grad = False
        # PEFT requires the LoRA target modules to exist — they do on
        # ViTModel's attention modules, but the naming has drifted
        # across transformers releases. _resolve_lora_targets picks
        # whichever convention is actually present.
        targets = _resolve_lora_targets(backbone, model_cfg.lora_target_modules)
        lora_cfg = LoraConfig(
            r=model_cfg.lora_r,
            lora_alpha=model_cfg.lora_alpha,
            target_modules=targets,
            lora_dropout=model_cfg.lora_dropout,
            bias="none",
        )
        peft_backbone = get_peft_model(backbone, lora_cfg)

        m = PlantViT.__new__(PlantViT)
        nn.Module.__init__(m)
        m.num_crop_labels = num_crop_labels
        m.num_infection_labels = num_infection_labels
        m.backbone = peft_backbone
        hidden_size = cfg.hidden_size
        m.dropout = nn.Dropout(model_cfg.dropout)
        m.crop_head = nn.Linear(hidden_size, num_crop_labels)
        m.infection_head = nn.Linear(hidden_size, num_infection_labels)
        return m

    return PlantViT(model_cfg, num_crop_labels, num_infection_labels)
