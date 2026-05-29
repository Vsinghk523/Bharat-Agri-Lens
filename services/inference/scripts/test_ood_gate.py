"""Smoke-test the OOD gate against a set of images.

Run after the CLIP assets are in place to confirm the gate rejects
non-target images cleanly and accepts target plant images.

Usage:
    cd services/inference
    python scripts/test_ood_gate.py path/to/image1.jpg path/to/image2.png ...
    python scripts/test_ood_gate.py --url https://example.com/leaf.jpg
"""
from __future__ import annotations

import sys
from pathlib import Path
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import Settings  # noqa: E402
from app.ood import check_image_quality, get_clip_gate  # noqa: E402


def _load(path_or_url: str) -> bytes:
    if path_or_url.startswith(("http://", "https://")):
        req = Request(
            path_or_url,
            headers={"User-Agent": "bal-ood-test/1.0 (admin@bharatagrilens.in)"},
        )
        with urlopen(req) as resp:  # noqa: S310
            return resp.read()
    return Path(path_or_url).read_bytes()


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    settings = Settings()
    gate = get_clip_gate(settings)

    for arg in sys.argv[1:]:
        if arg.startswith("--url"):
            continue
        try:
            data = _load(arg)
        except Exception as exc:  # noqa: BLE001
            print(f"{arg}: failed to load — {exc}")
            continue

        print(f"\n=== {arg} ({len(data)} bytes) ===")

        q = check_image_quality(data)
        if q:
            print(f"  QUALITY REJECT: {q}")
            continue
        print("  quality: OK")

        verdict = gate.gate(data)
        print(f"  clip ok: {verdict['ok']}")
        print(f"  clip reason: {verdict['reason']}")
        print(f"  clip closest label: {verdict['winning_label']}")
        print("  category probs:")
        for cat, p in verdict["category_probs"].items():
            print(f"    {cat:10s} {p:.4f}")


if __name__ == "__main__":
    main()
