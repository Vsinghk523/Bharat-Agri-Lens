"""List which Gemini models the configured API key has access to."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402

settings = get_settings()
print(f"API key configured: {bool(settings.gemini_api_key)}\n")

from google import genai  # noqa: E402

client = genai.Client(api_key=settings.gemini_api_key)
print(f"{'Model name':<50}  {'Methods':<30}  Input limit")
print("-" * 100)
for m in client.models.list():
    methods = ",".join(m.supported_actions or [])
    in_lim = getattr(m, "input_token_limit", None)
    print(f"{m.name:<50}  {methods:<30}  {in_lim}")
