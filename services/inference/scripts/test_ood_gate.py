"""Smoke-test the OOD gate against a set of images.

Run after the CLIP assets are in place to confirm the gate rejects
non-target images cleanly and accepts target plant images.

Usage:
    cd services/inference
    python scripts/test_ood_gate.py path/to/image1.jpg path/to/image2.png ...
    python scripts/test_ood_gate.py --url https://example.com/leaf.jpg

    # Reproduce production exactly (recommended):
    python scripts/test_ood_gate.py --served-crops \\
        Apple,Blueberry,Cherry,Corn,Grape,Orange,Peach,Pepper,Potato,\\
Raspberry,Soybean,Squash,Strawberry,Tomato  image.jpg

``--served-crops`` (or ``--labels <labels.json>``) is what makes this
script agree with the deployed service. Without it the gate treats every
catalogued crop as TARGET, which is NOT what production does and will
happily report a pass for an image the real gate rejects. The script
warns when run that way.

Per-prompt output
-----------------
The gate's verdict alone rarely explains itself. A category can win on
one strong row or on many weak ones, and those call for different fixes.
``--top N`` prints the highest-scoring individual prompts so the winning
row is visible by name — which is how a phrasing gap gets found, e.g. a
wheat leaf close-up matching "maize leaves close-up" because no wheat
prompt describes a single blade.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.request import Request, urlopen

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import Settings  # noqa: E402
from app.ood import (  # noqa: E402
    CLIP_TEMPERATURE,
    TARGET_WIN_MARGIN,
    check_image_quality,
    get_clip_gate,
)


def _load(path_or_url: str) -> bytes:
    if path_or_url.startswith(("http://", "https://")):
        req = Request(
            path_or_url,
            headers={"User-Agent": "bal-ood-test/1.0 (admin@bharatagrilens.in)"},
        )
        with urlopen(req) as resp:  # noqa: S310
            return resp.read()
    return Path(path_or_url).read_bytes()


def _per_prompt_scores(gate, image_bytes: bytes) -> np.ndarray:
    """Re-run the gate's own scoring to expose the per-prompt softmax.

    Mirrors ``CLIPGate.gate`` up to the point where it collapses rows
    into category sums. Kept deliberately close to the original so the
    numbers printed here are the numbers the gate actually decided on.
    """
    x = gate._preprocess(image_bytes)
    outs = gate.session.run(None, {gate.input_name: x})
    image_embed = outs[0][0].astype(np.float32)
    image_embed /= np.linalg.norm(image_embed) + 1e-9
    sims = gate.text_embeddings @ image_embed
    scaled = sims * CLIP_TEMPERATURE
    probs = np.exp(scaled - scaled.max())
    probs /= probs.sum()
    return probs


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke-test the OOD gate.")
    parser.add_argument("images", nargs="*", help="Image paths or http(s) URLs.")
    parser.add_argument(
        "--served-crops",
        default=None,
        help="Comma-separated crop labels the served model can classify.",
    )
    parser.add_argument(
        "--labels",
        default=None,
        help="Path to a model bundle labels.json (alternative to --served-crops).",
    )
    parser.add_argument(
        "--top", type=int, default=8, help="How many individual prompts to print."
    )
    args = parser.parse_args()

    if not args.images:
        parser.print_help()
        sys.exit(0)

    served: list[str] | None = None
    if args.labels:
        import json

        served = list(json.loads(Path(args.labels).read_text(encoding="utf-8"))["crop_labels"])
    elif args.served_crops:
        served = [c.strip() for c in args.served_crops.split(",") if c.strip()]

    if served is None:
        print(
            "WARNING: no --served-crops/--labels given. Every catalogued crop is "
            "treated as TARGET, which is NOT what production does. This run can "
            "report a pass for an image the deployed gate rejects.\n"
        )
    else:
        print(f"served crops ({len(served)}): {sorted(served)}\n")

    settings = Settings()
    gate = get_clip_gate(settings, served_crop_labels=served)

    for arg in args.images:
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
        cat = verdict["category_probs"]
        margin = cat["TARGET"] - cat["NON_TARGET"] - cat["NON_PLANT"]

        print(f"  clip ok: {verdict['ok']}")
        print(f"  clip reason: {verdict['reason']}")
        print(f"  clip closest label: {verdict['winning_label']}")
        print("  category probs:")
        for name, p in cat.items():
            print(f"    {name:10s} {p:.4f}")
        print(
            f"  decision: TARGET - NON_TARGET - NON_PLANT = {margin:+.4f} "
            f"(needs >= {TARGET_WIN_MARGIN:+.4f} to pass)"
        )

        probs = _per_prompt_scores(gate, data)
        order = np.argsort(probs)[::-1][: args.top]
        print(f"  top {args.top} individual prompts:")
        for rank, i in enumerate(order, 1):
            p = gate.prompts[int(i)]
            print(
                f"    {rank:2d}. {probs[int(i)]:.4f}  [{p['category']:10s}] "
                f"{p['label']:18s} \"{p['text']}\""
            )


if __name__ == "__main__":
    main()
