import asyncio
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth.router import router as auth_router
from app.chat.router import router as chat_router
from app.common.s3 import ensure_bucket
from app.config import get_settings
from app.diagnostics.router import router as diagnostics_router
from app.logging import configure_logging, get_logger
from app.uploads.router import router as uploads_router
from app.users.router import router as users_router


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    log = get_logger(__name__)
    log.info("startup", environment=settings.environment, app=settings.app_name)
    if settings.environment != "production":
        # ensure_bucket does blocking I/O; offload to a thread.
        ok = await asyncio.to_thread(ensure_bucket)
        log.info("startup_bucket_check", bucket=settings.s3_bucket, ok=ok)
    yield
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
    return app


app = create_app()
