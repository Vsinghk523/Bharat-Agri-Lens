import asyncio
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.admin.router import router as admin_router
from app.auth.router import router as auth_router
from app.chat.router import router as chat_router
from app.common.s3 import ensure_bucket, ensure_cors
from app.config import get_settings
from app.diagnostics.router import router as diagnostics_router
from app.logging import configure_logging, get_logger
from app.translations.router import router as translations_router
from app.uploads.router import router as uploads_router
from app.users.router import router as users_router
from app.voice.router import router as voice_router


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    log = get_logger(__name__)
    log.info("startup", environment=settings.environment, app=settings.app_name)
    # Bucket auto-create: dev convenience. Production buckets are
    # provisioned by infrastructure-as-code, not at app startup.
    if settings.environment != "production":
        bucket_ok = await asyncio.to_thread(ensure_bucket)
        log.info("startup_bucket_check", bucket=settings.s3_bucket, ok=bucket_ok)

    # CORS: real AWS S3 rejects cross-origin uploads by default and
    # needs an explicit bucket policy. MinIO + most other emulators
    # are permissive out of the box, AND they reject S3's PutBucketCors
    # API with NotImplemented when boto3 sends modern checksum headers.
    # So we apply the policy only when no custom endpoint is set
    # (i.e., targeting real S3), regardless of environment.
    if not settings.s3_endpoint_url:
        cors_ok = await asyncio.to_thread(ensure_cors)
        log.info("startup_cors_check", bucket=settings.s3_bucket, ok=cors_ok)
    else:
        log.info(
            "startup_cors_skip",
            endpoint=settings.s3_endpoint_url,
            note="S3-compatible server uses its own default CORS",
        )

    # Background moderation / thumbnail worker. We launch a single
    # task per API replica; coordination across replicas is handled
    # by SELECT ... FOR UPDATE SKIP LOCKED inside the worker.
    moderation_stop = asyncio.Event()
    moderation_task: asyncio.Task[None] | None = None
    if settings.moderation_enabled and settings.environment != "test":
        from app.jobs.moderation import moderation_loop

        moderation_task = asyncio.create_task(
            moderation_loop(moderation_stop), name="moderation_worker"
        )
        log.info("moderation_worker_started")
    else:
        log.info(
            "moderation_worker_skipped",
            enabled=settings.moderation_enabled,
            env=settings.environment,
        )

    try:
        yield
    finally:
        if moderation_task is not None:
            moderation_stop.set()
            try:
                await asyncio.wait_for(moderation_task, timeout=15)
            except asyncio.TimeoutError:
                moderation_task.cancel()
                log.warning("moderation_worker_force_cancelled")
            log.info("moderation_worker_stopped")
        log.info("shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="BharatAgriLens API",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": settings.app_name}

    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(uploads_router)
    app.include_router(diagnostics_router)
    app.include_router(chat_router)
    app.include_router(translations_router)
    app.include_router(voice_router)
    app.include_router(admin_router)
    return app


app = create_app()
