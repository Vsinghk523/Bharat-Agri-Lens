"""Export a trained checkpoint to ONNX (+ optional int8 dynamic quant).

Output layout:
    out_dir/
      plantvit.onnx              # fp32, ~350 MB for ViT-B
      plantvit-int8.onnx         # dynamic quant, ~90 MB (when --quantize)
      labels.json                # crop_labels + infection_labels arrays
      provenance.json            # backbone, lora_r, training metrics

The inference service consumes whatever path is set in
``services/inference/.env``'s ``VISION_MODEL_URI``. Either ONNX is fine;
the int8 variant is the prod default for cost.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch

from src.config import TrainingPipelineConfig, load_config
from src.model import build_model


def export_to_onnx(
    cfg: TrainingPipelineConfig,
    checkpoint_path: str | Path,
    out_dir: str | Path,
    *,
    smoke: bool = False,
    quantize: bool = True,
    opset: int = 17,
) -> dict[str, str]:
    out_dir_p = Path(out_dir)
    out_dir_p.mkdir(parents=True, exist_ok=True)
    device = torch.device("cpu")  # ONNX export is always CPU
    model = build_model(
        cfg.model,
        num_crop_labels=len(cfg.data.crop_labels),
        num_infection_labels=len(cfg.data.infection_labels),
        from_scratch_for_smoke=smoke,
    ).to(device)
    state = torch.load(checkpoint_path, map_location=device, weights_only=False)
    model.load_state_dict(state["model_state"])
    model.eval()

    dummy = torch.randn(1, 3, cfg.data.image_size, cfg.data.image_size, dtype=torch.float32)
    fp32_path = out_dir_p / "plantvit.onnx"
    torch.onnx.export(
        model,
        (dummy,),
        str(fp32_path),
        input_names=["pixel_values"],
        output_names=["crop_logits", "infection_logits"],
        dynamic_axes={
            "pixel_values": {0: "batch"},
            "crop_logits": {0: "batch"},
            "infection_logits": {0: "batch"},
        },
        opset_version=opset,
        do_constant_folding=True,
    )
    print(f"[export] wrote {fp32_path} ({fp32_path.stat().st_size / 1e6:.1f} MB)")

    int8_path: Path | None = None
    if quantize:
        from onnxruntime.quantization import QuantType, quantize_dynamic

        int8_path = out_dir_p / "plantvit-int8.onnx"
        quantize_dynamic(
            model_input=str(fp32_path),
            model_output=str(int8_path),
            weight_type=QuantType.QInt8,
        )
        print(f"[export] wrote {int8_path} ({int8_path.stat().st_size / 1e6:.1f} MB)")

    labels_path = out_dir_p / "labels.json"
    labels_path.write_text(
        json.dumps(
            {
                "crop_labels": cfg.data.crop_labels,
                "infection_labels": cfg.data.infection_labels,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    prov_path = out_dir_p / "provenance.json"
    prov_path.write_text(
        json.dumps(
            {
                "name": cfg.name,
                "backbone": cfg.model.backbone,
                "lora_r": cfg.model.lora_r,
                "image_size": cfg.data.image_size,
                "training_metrics": state.get("metrics"),
                "training_epoch": state.get("epoch"),
                "opset": opset,
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    return {
        "onnx_fp32": str(fp32_path),
        "onnx_int8": str(int8_path) if int8_path else "",
        "labels": str(labels_path),
        "provenance": str(prov_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--out", default=None, help="Defaults to cfg.export.out_dir")
    parser.add_argument("--no-quantize", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()

    cfg = load_config(args.config)
    out = args.out or cfg.export.out_dir
    paths = export_to_onnx(
        cfg,
        args.checkpoint,
        out,
        smoke=args.smoke,
        quantize=not args.no_quantize and cfg.export.quantize,
        opset=cfg.export.opset,
    )
    print("Exported:")
    for k, v in paths.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
