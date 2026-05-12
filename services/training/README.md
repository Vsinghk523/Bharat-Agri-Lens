# services/training — Vision model training pipeline

Trains the **own** plant-disease vision model used by `services/inference`.

## Approach

- **Backbone:** ViT-Base/16 pretrained on ImageNet-21k.
- **Method:** LoRA fine-tune via `peft` for fast iteration (trains in hours on a single A100, weights ~50 MB).
- **Heads:** dual-head — (a) crop classification, (b) infection type (insect_pest, fungal, viral, bacterial, nematode, nutrient_deficiency, abiotic_stress, weed_competition, unknown).
- **Output:** ONNX export + int8 quantized variant, uploaded to S3 with a model registry row.

## Datasets (initial)

| Dataset      | Size  | License            | Notes                              |
|--------------|-------|--------------------|------------------------------------|
| PlantVillage | ~54k  | CC0 / public domain| Lab images, 38 disease classes     |
| PlantDoc     | ~2.5k | CC BY 4.0          | Real-field photos, 27 classes      |
| IP102        | ~75k  | research use       | 102 insect-pest categories         |
| Curated 100  | TBD   | varies             | Tracked in `data_source_registry`  |

## Pipeline layout (planned)

```
services/training/
├── data/                # DVC-tracked datasets (gitignored)
├── notebooks/           # Exploration only
├── src/
│   ├── ingest.py        # Pull + verify each labeled dataset
│   ├── label.py         # Merge taxonomies, handle class imbalance
│   ├── augment.py       # Albumentations (CLAHE, mixup, cutmix)
│   ├── train.py         # ViT + LoRA, 80/10/10 split
│   ├── eval.py          # Per-class precision, recall, F1, confusion matrix
│   └── export.py        # ONNX + int8 quant + push to S3
├── configs/             # YAML hyperparameter sweeps
├── dvc.yaml             # Reproducible stages
└── runs/                # mlflow / W&B run artifacts (gitignored)
```

## First steps

1. Add `dvc init` and configure remote (S3-compatible).
2. Pull PlantVillage + PlantDoc as the v0 dataset.
3. Train baseline ViT-B/16 LoRA (5 epochs) — record metrics in `model_registry` table.
4. Iterate with active learning: pull `feedback_events` from production weekly.

## Why not "from scratch"?

Training a vision model from scratch needs millions of labeled images and weeks of GPU time. LoRA fine-tuning a pretrained backbone gives you a model **whose weights you own and version** at a fraction of the cost — that is what "build own AI model" means in practice. The `model_registry` table makes every checkpoint reproducible (training data hash + eval metrics).
