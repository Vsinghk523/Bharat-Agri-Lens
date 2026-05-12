import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class LabellingQueueItem(BaseModel):
    diagnostic_id: uuid.UUID
    image_id: uuid.UUID | None
    image_url: str | None
    storage_location: str | None
    predicted_plant: str | None
    predicted_disease: str | None
    predicted_infection_type: str | None
    confidence_score: Decimal | None
    user_feedback: str
    language_used: str | None
    add_date: datetime
    modify_date: datetime


class LabellingQueueResponse(BaseModel):
    items: list[LabellingQueueItem]
    total: int
    limit: int
    offset: int
