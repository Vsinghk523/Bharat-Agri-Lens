# BharatAgriLens

[![CI](https://github.com/Vsinghk523/Bharat-Agri-Lens/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Vsinghk523/Bharat-Agri-Lens/actions/workflows/ci.yml)

AI assistant to detect plant infections, classify plants, identify infection type (insect / fungal / viral / bacterial / nutrient deficiency / abiotic stress), suggest remedies, and propose follow-up questions to the user. Supports text + voice queries in English, Hindi, and other Indian languages.

## Monorepo layout

```
.
├── apps/
│   ├── api/                 # FastAPI backend (R/W + soft + hard delete)
│   └── web/                 # React + Vite web app (built first)
├── packages/
│   ├── types/               # Shared TypeScript types
│   ├── api-client/          # Generated/wrapped API client
│   └── i18n/                # Translation keys + locale JSON
├── services/
│   ├── inference/           # Vision + LLM inference service (Railway GPU)
│   └── training/            # Vision model training pipeline (PlantViT)
└── infra/
    └── railway/             # Deployment manifests
```

The web app is built first. The mobile app (Android, then iOS) will be added later as `apps/mobile` (Expo / React Native) and will reuse `packages/*` directly.

## Prerequisites

- Node.js 20.10+ with pnpm 9+
- Python 3.13+ with `uv`
- PostgreSQL 16 (local for dev, Railway-managed for prod)
- Docker (optional, for local Postgres)

## Quick start

```bash
# 1. Install JS workspace deps
pnpm install

# 2. Bring up local Postgres + MinIO (S3-compatible object storage)
docker run --name bal-pg -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=bharat_agri_lens -p 5432:5432 -d postgres:16
docker run --name bal-minio -p 9000:9000 -p 9001:9001 \
  -e MINIO_ROOT_USER=minioadmin -e MINIO_ROOT_PASSWORD=minioadmin \
  -d minio/minio server /data --console-address ":9001"

# 3. Set up the API
cd apps/api
uv sync
cp .env.example .env   # already points S3_ENDPOINT_URL at the MinIO above
uv run alembic upgrade head
uv run uvicorn app.main:app --reload   # auto-creates the bucket at startup in dev

# 4. Set up the inference service (new shell)
cd services/inference
uv sync
cp .env.example .env
uv run uvicorn app.main:app --reload --port 8001

# 5. Set up the web app (new shell)
cd apps/web
pnpm dev
```

MinIO console: http://localhost:9001 (user: `minioadmin`, password: `minioadmin`).
API Swagger UI: http://localhost:8000/docs.

### CORS for direct browser uploads

The browser uploads images directly to object storage via a presigned PUT URL, which is cross-origin from the web app. Two regimes:

- **Local dev (MinIO):** MinIO returns permissive CORS headers by default, so the dev stack works without any extra config. You can see this in the API startup log as `startup_cors_skip`.
- **Production (real AWS S3 / Cloudflare R2):** the API automatically applies a CORS policy to the configured bucket at startup (`startup_cors_set` in the log). The policy is pulled from `CORS_ALLOWED_ORIGINS` — set this to the production web-app origin(s) (e.g. `https://app.bharatagrilens.com,https://www.bharatagrilens.com`). The policy is idempotent; setting it on every API boot is safe.

If you're targeting R2 / LocalStack / another emulator and want a single CORS rule applied via `boto3.put_bucket_cors`, just leave `S3_ENDPOINT_URL` empty in `.env` (real S3 mode); otherwise set it and rely on the server's own defaults.

## Tech stack

| Concern               | Choice                                |
| --------------------- | ------------------------------------- |
| API                   | FastAPI, SQLAlchemy 2.x async, asyncpg |
| Migrations            | Alembic                                |
| Database              | PostgreSQL 16 (+ pgvector for RAG)     |
| LLM                   | Gemma fine-tuned via unsloth + RAG     |
| Vision model          | PlantViT (LoRA fine-tune of ViT-B/16)  |
| Web                   | React 18, Vite, Tailwind, shadcn/ui    |
| Mobile (later)        | Expo / React Native (Android first)    |
| OTP                   | Resend (email) + WhatsApp Cloud API    |
| Translation / STT / TTS | Bhashini (gateway, rate-limited v1) |
| Deployment            | Railway (Nixpacks + managed Postgres + GPU) |

## Decisions

- Build own vision model: PlantViT LoRA fine-tune on PlantVillage + PlantDoc + IP102.
- OTP delivery: email (Resend) + WhatsApp Business Cloud API (free tier).
- Full R/W API with soft-delete (status=Inactive) and hard-delete (admin / DPDP "right to erasure").
- Training data: curated authoritative-source list (~100), tracked in `data_source_registry`.
- Multilingual: Bhashini gateway in v1 (rate-limited acceptable); self-host AI4Bharat in v2.
- Platform order: web → Android → iOS. Code-share via `packages/*`.

See `docs/` for the full plan (to be added).
