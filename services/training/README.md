# services/training — PlantViT training pipeline

LoRA fine-tune of `google/vit-base-patch16-224` with two parallel
classification heads — one for crop, one for infection type. Output is
an ONNX bundle the inference service drops into via `VISION_MODEL_URI`.

## Why LoRA?

The full ViT-B has ~86M parameters. With LoRA rank=16 on `query` +
`value` projections of every transformer block we train ~600K
parameters — roughly 0.7% of the full model. That trains in 3–4 hours
on a single A100 against the full PlantVillage + PlantDoc + IP102
merge, instead of 30+ hours for a full fine-tune. Accuracy gap on this
domain is < 1% per published benchmarks.

## Repo shape

```
services/training/
├── pyproject.toml          uv project, Python 3.11/3.12
├── README.md               this file
├── configs/
│   ├── synthetic.yaml      smoke config — runs in seconds on CPU
│   └── baseline.yaml       production config — PlantVillage + extras
├── src/
│   ├── config.py           YAML -> dataclasses
│   ├── synth.py            procedural synthetic dataset (smoke)
│   ├── datasets.py         dual-label ImageFolder dataset
│   ├── augment.py          Albumentations train / val pipelines
│   ├── model.py            ViT + LoRA + dual heads (PlantViT)
│   ├── train.py            CLI: bal-train
│   ├── eval.py             CLI: bal-eval (per-class P/R/F1 + confusion)
│   └── export.py           CLI: bal-export (ONNX + int8 quant)
└── tests/
    └── test_pipeline.py    synth -> train -> export -> load assertions
```

## Quick start — synthetic smoke (CPU, ~30 seconds)

```bash
cd services/training
uv sync                                                # ~5 min first time (torch)
uv run bal-synth --out data/synthetic --per-class 16
uv run bal-train --config configs/synthetic.yaml --smoke
uv run bal-export --config configs/synthetic.yaml \
  --checkpoint runs/synthetic-smoke-*/best.pt --smoke
ls runs/synthetic/export                              # plantvit.onnx + labels.json + provenance.json
uv run pytest -v                                       # green
```

The `--smoke` flag swaps the pretrained ViT-B backbone for a freshly
initialised 2-layer toy ViT so the test doesn't pull 300 MB from
HuggingFace. It validates wiring, not accuracy.

## Production training — PlantVillage + PlantDoc + IP102

### 1. Data

```bash
# PlantVillage (~54k images, ~1.5 GB)
huggingface-cli download nateraw/plantvillage \
  --repo-type dataset --local-dir data/raw/plantvillage

# PlantDoc (~2.5k field images)
git clone https://github.com/pratikkayal/PlantDoc-Dataset data/raw/plantdoc

# IP102 (~75k insect pest images)
# Manual download — fill the form at
# https://github.com/xpwu95/IP102 then unzip into data/raw/ip102
```

Then merge the three sources into the `data/combined/{train,val}/<Crop>___<Disease>/*.jpg`
layout the training pipeline expects:

```bash
uv run python -m scripts.prepare \
    --plantvillage data/raw/plantvillage/PlantVillage \
    --plantdoc     data/raw/plantdoc \
    --ip102        data/raw/ip102 \
    --out          data/combined \
    --val-fraction 0.1
```

The script:
- normalises crop names (`Apple_scab` vs `apple` vs `Apple Scab`) against
  a single canonical list (extend in `scripts/prepare.py:CANONICAL_CROPS`),
- splits per class deterministically (same `--seed`, same partition),
- hard-links instead of copying when the filesystem supports it (so a
  5 GB merge consumes ~no extra disk),
- writes `data/combined/summary.json` with per-class train/val counts
  for the next person to diff.

Run `pytest tests/test_prepare.py` (Pillow only, no torch) for the
mini end-to-end on a fake source tree.

### 2. Train

```bash
uv run bal-train --config configs/baseline.yaml \
  --run-dir runs/plantvit-v0
```

GPU box (single A100 40 GB recommended): 30 epochs, 3–4 hours, ~$8 on
spot instances. Reduce `batch_size` to 16 if you only have a T4.

Monitor:
- stdout: per-step loss + per-epoch validation accuracy
- `runs/<name>/best.pt` is updated whenever val infection-F1 improves
- early stop after `train.early_stop_patience` epochs without
  improvement

### 3. Evaluate

```bash
uv run bal-eval --config configs/baseline.yaml \
  --checkpoint runs/plantvit-v0/best.pt \
  --out runs/plantvit-v0/metrics.json
```

Produces per-class precision/recall/F1 + confusion matrix for both heads.

### 4. Export

```bash
uv run bal-export --config configs/baseline.yaml \
  --checkpoint runs/plantvit-v0/best.pt
```

Writes `runs/plantvit-v0/export/`:
- `plantvit.onnx`           fp32, ~350 MB
- `plantvit-int8.onnx`      dynamic-quantised, ~90 MB (prod default)
- `labels.json`             {crop_labels, infection_labels}
- `provenance.json`         backbone, lora_r, training metrics, opset

### 5. Deploy

Upload the export directory to S3, then point the inference service at it:

```bash
aws s3 sync runs/plantvit-v0/export s3://bal-models/plantvit-v0/
# In services/inference/.env:
USE_MOCK_PREDICTOR=false
VISION_MODEL_URI=/mnt/models/plantvit-v0       # or a local sync of the s3 dir
```

The inference service prefers `plantvit-int8.onnx` when present, falls
back to `plantvit.onnx`. CUDA execution provider is auto-detected.

## Adding a new disease label

1. Add the raw folder-name mapping to `configs/baseline.yaml`
   under `data.disease_to_infection`. Unmapped diseases fall through
   to `unknown` rather than crash.
2. Re-train.
3. The exported `labels.json` will pick up the new mapping; the
   inference service reads it on next startup.

## Why isn't this in CI?

Installing torch + transformers + peft is 1.5–2 GB and slow on every
push, and the synthetic smoke needs ~5 minutes of CPU even with the
toy ViT. The training code changes infrequently relative to the API
and the synthetic smoke is the run-before-PR check, not the merge
gate. CI runs the API + workspace typecheck (see `.github/workflows/ci.yml`).

## Known TODOs

- W&B integration — basic stdout logging only for now.
- Active-learning hook that pulls `feedback_events` rows from the
  production database into a "needs-labels" review queue.
- Real ingest of PlantViT classes into the `model_registry` table on
  upload so the API can render "model_version" properly.
