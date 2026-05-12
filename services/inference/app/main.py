from fastapi import FastAPI
from pydantic import BaseModel, Field

from app.chat import generate_reply
from app.config import get_settings
from app.predictor import predict


class PredictIn(BaseModel):
    image_id: str
    language: str = "en-IN"


class ChatReplyIn(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    language: str = "en"


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

    @app.post("/chat/reply")
    async def chat_reply_endpoint(payload: ChatReplyIn) -> dict[str, str]:
        return generate_reply(payload.message, payload.language)

    return app


app = create_app()
