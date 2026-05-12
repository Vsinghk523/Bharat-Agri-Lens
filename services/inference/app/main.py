from fastapi import FastAPI
from pydantic import BaseModel

from app.config import get_settings
from app.predictor import predict


class PredictIn(BaseModel):
    image_id: str
    language: str = "en-IN"


def create_app() -> FastAPI:
    app = FastAPI(title="BharatAgriLens Inference", version="0.1.0")
    settings = get_settings()

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {
            "status": "ok",
            "mode": "mock" if settings.use_mock_predictor else "real",
            "model_version": settings.vision_model_version,
        }

    @app.post("/predict")
    async def predict_endpoint(payload: PredictIn) -> dict:
        return await predict(payload.image_id, payload.language, settings)

    return app


app = create_app()
