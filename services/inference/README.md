# services/inference — Inference service

FastAPI service that wraps the fine-tuned **PlantViT** vision model and the **Gemma** LLM (with RAG over the curated authoritative-source corpus). Designed to run on Railway's GPU infrastructure.

For now it ships a **mock predictor** so `apps/api` and `apps/web` can be developed end-to-end without GPU dependencies. Flip `USE_MOCK_PREDICTOR=false` once real artifacts are available.

## Run locally

```bash
uv sync
cp .env.example .env
uv run uvicorn app.main:app --reload --port 8001
```

## Endpoints

- `GET /health` — service status + active model version
- `POST /predict` — `{ image_id, language }` → diagnostic payload

## Production wiring (TODO)

1. Pull the latest tagged ONNX from S3 (`VISION_MODEL_URI`).
2. Load the Gemma + LoRA adapter (`LLM_ADAPTER_URI`) on the GPU at startup.
3. Replace `mock_predict` with the real two-stage pipeline:
   - vision → `(plant, disease, infection_type, confidence, top-N)`
   - RAG over `pesticide_catalog` + curated corpus → remedies + follow-ups
4. Set `USE_MOCK_PREDICTOR=false`.
