from pydantic import BaseModel, Field


class TranslateRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)
    source_language: str = Field(default="en-IN", description="BCP-47, e.g. en-IN")
    target_language: str = Field(..., description="BCP-47, e.g. hi-IN")


class TranslateResponse(BaseModel):
    text: str
    source_language: str
    target_language: str
    provider: str  # 'bhashini' or 'mock'
