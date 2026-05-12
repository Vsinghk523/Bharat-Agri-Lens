# apps/api — BharatAgriLens API

FastAPI + SQLAlchemy 2.x async + asyncpg + Alembic.

## Run locally

```bash
uv sync
cp .env.example .env
# edit .env, especially DATABASE_URL, JWT_SECRET, CPA_FERNET_KEY
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

Open http://localhost:8000/docs for Swagger UI.

## Endpoints

- `POST /auth/otp/request` — request OTP via `email` or `whatsapp` channel
- `POST /auth/otp/verify` — exchange OTP for JWT pair
- `GET|PATCH|DELETE /users/{user_id}` — user CRUD + soft-delete
- `DELETE /users/{user_id}/purge` — hard delete (DPDP right to erasure)
- `POST /uploads/presign` — get S3 presigned PUT URL
- `GET|DELETE /uploads/{image_id}`, `GET /uploads`
- `POST /diagnostics` — trigger inference and persist
- `GET|PATCH|DELETE /diagnostics/{id}`
- `GET /diagnostics/{id}/followups`
- `POST /diagnostics/followups`, `POST /diagnostics/followups/{id}/click`
- `POST /diagnostics/{id}/feedback`
- `GET|POST /chat/sessions`, `GET /chat/sessions/{id}/messages`, `POST /chat/messages`

## Migrations

```bash
uv run alembic revision --autogenerate -m "describe change"
uv run alembic upgrade head
uv run alembic downgrade -1
```

## Generating secrets

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"           # JWT_SECRET
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"  # CPA_FERNET_KEY
```
