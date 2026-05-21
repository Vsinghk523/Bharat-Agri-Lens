---
title: BAL PlantViT Trainer
emoji: 🌱
colorFrom: green
colorTo: yellow
sdk: docker
app_port: 7860
suggested_hardware: a100-large
suggested_storage: medium
secrets:
  - HF_TOKEN
  - HF_DATASET_REPO
  - HF_MODEL_REPO
---

# BAL PlantViT Trainer

Fine-tunes a ViT-base backbone (with LoRA) for plant disease
classification on the PlantVillage dataset, exports the result to ONNX
(fp32 + int8 quantized), and uploads the bundle to a HuggingFace model
repo. Used to produce the model the BharatAgriLens inference service
consumes in production.

## Inputs and outputs

| | Repo | Type |
|---|---|---|
| Reads | `viveksk523/bal-plantvit-data` | dataset |
| Writes | `viveksk523/bal-plantvit-v0` | model |

The dataset repo must contain `train/` and `val/` folders in
ImageFolder layout (`<root>/<split>/<Crop>___<Disease>/*.jpg`). Run
`services/training/scripts/prepare.py` from the main repo to produce
that layout.

The output bundle contains:
- `plantvit.onnx` — fp32 (~350 MB)
- `plantvit-int8.onnx` — dynamic-int8 quantized (~90 MB; production default)
- `labels.json` — crop_labels + infection_labels arrays
- `provenance.json` — backbone, lora_r, best-epoch metrics, training timestamp

## Run order

### 1. Configure secrets

Space → **Settings** → **Variables and secrets** → add:

| Name | Value |
|---|---|
| `HF_TOKEN` | A Write-scoped HuggingFace token (https://huggingface.co/settings/tokens) |
| `HF_DATASET_REPO` | `viveksk523/bal-plantvit-data` |
| `HF_MODEL_REPO` | `viveksk523/bal-plantvit-v0` |

### 2. Pick hardware

Space → **Settings** → **Hardware** → upgrade to **A100-large**
(\$2.50/hr). Cheaper tiers work but take longer:

| Hardware | Cost/hr | Full 30-epoch run |
|---|---|---|
| A100-large | \$2.50 | ~3-4h (~\$10 total) |
| L4 single | \$0.80 | ~6-8h (~\$5-6 total) |
| T4-small | \$0.40 | ~12-15h (~\$5-6 total; reduce `batch_size` to 16 in the config) |

### 3. Restart and watch

Save settings → the Space restarts on the new hardware → Gradio UI
streams the live training log. The 5 pipeline stages run in order:

1. Download dataset from HF Hub
2. Train (the long stage)
3. Export the best checkpoint to ONNX
4. Upload the export bundle to the model repo
5. Auto-pause the Space (billing stops)

When you see `✅ Training pipeline complete.` followed by
`paused. ✅`, the run is done. Check
`https://huggingface.co/viveksk523/bal-plantvit-v0/tree/main` for the
artifacts.

## Optional knobs

| Variable | Purpose |
|---|---|
| `EPOCHS` | Override the config's epoch count. Set `EPOCHS=2` for a smoke test before paying for a full run. |
| `TRAINING_CONFIG` | Path under `services/training/` to a different YAML (e.g. `configs/baseline.yaml` once we add PlantDoc/IP102 support in v0.1). |

## Re-running

To re-train (after dataset changes, config tweaks, or to bump a model
version): un-pause the Space — it restarts, sees a fresh container,
and runs the pipeline again from scratch. The dataset download is
re-snapshotted (HF Hub deduplicates content-addressed blobs so this is
fast on the second run).

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `Missing required secrets: HF_TOKEN, ...` | Secrets not set or Space not restarted after adding them | Set, restart |
| `RuntimeError: CUDA out of memory` | Hardware tier too small for the configured `batch_size` | Drop `batch_size` (in the yaml) or pick a bigger GPU |
| Pipeline finishes but model repo is empty | Token doesn't have Write scope for the target repo | Regenerate with Write scope, update the secret |
| Logs show 0 train samples after download | `HF_DATASET_REPO` is wrong, or the dataset doesn't have `train/`/`val/` at the root | Verify the dataset repo URL + structure |
