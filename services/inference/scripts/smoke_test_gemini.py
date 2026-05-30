"""Verify the Gemini key works end-to-end against a real image.

Run with:
    cd services/inference
    .\.venv\Scripts\python.exe scripts/smoke_test_gemini.py <image_path_or_url>

Prints the structured diagnosis Gemini returns. Confirms:
  - GEMINI_API_KEY is set and valid
  - google-genai SDK is importable
  - Structured-output (JSON schema) mode works
  - The schema we ship gets back a non-empty plant + disease
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.request import Request, urlopen

THIS = Path(__file__).resolve()
sys.path.insert(0, str(THIS.parent.parent))

from app.config import get_settings  # noqa: E402
from app.llm_fallback import predict_with_llm  # noqa: E402


def _load(arg: str) -> bytes:
    if arg.startswith(("http://", "https://")):
        req = Request(
            arg,
            headers={"User-Agent": "bal-gemini-smoke/1.0 (admin@bharatagrilens.in)"},
        )
        with urlopen(req) as resp:  # noqa: S310
            return resp.read()
    return Path(arg).read_bytes()


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    settings = get_settings()
    print(f"Using model: {settings.gemini_model}")
    print(f"API key configured: {bool(settings.gemini_api_key)}")
    print()

    arg = sys.argv[1]
    print(f"Loading image from: {arg}")
    img_bytes = _load(arg)
    print(f"Image bytes: {len(img_bytes)}")

    clip_hint = sys.argv[2] if len(sys.argv) > 2 else None
    if clip_hint:
        print(f"CLIP hint: {clip_hint}")

    print("\nCalling Gemini...")
    result = predict_with_llm(
        image_bytes=img_bytes,
        language="en-IN",
        settings=settings,
        clip_hint=clip_hint,
    )

    if result is None:
        print("ERROR: predict_with_llm returned None (see logs above)")
        sys.exit(1)

    print("\n=== Gemini response ===")
    print(json.dumps(
        {k: v for k, v in result.items() if k != "followup_questions"},
        indent=2,
        default=str,
    ))


if __name__ == "__main__":
    main()
