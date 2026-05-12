# services/inference

FastAPI service that wraps the vision predictor + chat reply generator
behind a simple HTTP surface the API talks to over `localhost:8001`.

## Modes

| `USE_MOCK_PREDICTOR` | Vision behaviour |
|----------------------|------------------|
| `true` (default)     | `mock_predict()` — deterministic results across 7 crops, no model needed. Lets the rest of the stack develop end-to-end without GPU / dataset / training time. |
| `false`              | `RealPredictor` — loads an ONNX bundle from `VISION_MODEL_URI`, fetches the original image from object storage, runs inference. |

Chat (`POST /chat/reply`) uses keyword-matched templates regardless of
predictor mode. It's a stub for the real Gemma + RAG implementation
that will replace `app/chat.py` later.

## Run locally (mock mode)

```bash
cd services/inference
uv sync
cp .env.example .env
uv run uvicorn app.main:app --reload --port 8001
```

## Switch to the real model

1. Produce an ONNX bundle in `services/training/`:

   ```bash
   cd ../training
   uv sync
   uv run bal-train --config configs/baseline.yaml
   uv run bal-export --config configs/baseline.yaml \
     --checkpoint runs/plantvit-v0/best.pt
   ```

2. Sync the bundle to wherever the inference service can see it:

   ```bash
   # Local prod box
   cp -r runs/plantvit-v0/export /mnt/models/plantvit-v0

   # Or via S3
   aws s3 sync runs/plantvit-v0/export s3://bal-models/plantvit-v0/
   aws s3 sync s3://bal-models/plantvit-v0/ /mnt/models/plantvit-v0
   ```

3. Edit `services/inference/.env`:

   ```env
   USE_MOCK_PREDICTOR=false
   VISION_MODEL_URI=/mnt/models/plantvit-v0
   S3_BUCKET=…                  # same bucket the API writes to
   S3_REGION=…
   S3_ENDPOINT_URL=…            # if MinIO / R2
   S3_ACCESS_KEY_ID=…
   S3_SECRET_ACCESS_KEY=…
   ```

4. Install the ML extras and restart:

   ```bash
   uv sync --extra ml           # pillow + onnxruntime + numpy + boto3
   uv run uvicorn app.main:app --port 8001
   ```

Logs `real_predictor_loaded` with the active providers, label counts,
and model version on the first `/predict` call. Subsequent calls reuse
the cached session.

## Endpoints

- `GET /health` — `{status, mode, model_version}`
- `POST /predict` — `{image_id, language}` → diagnostic dict
- `POST /chat/reply` — `{message, language}` → `{reply, model_version}`
