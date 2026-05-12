"""Dump the active-learning labelling queue to CSV for offline review.

Run from the repo root:

    cd apps/api
    uv run python -m scripts.export_labelling_queue \
        --out ../../runs/labels-2026-05-13.csv \
        --batch 500

CSV columns:
    diagnostic_id, image_id, image_url, predicted_plant,
    predicted_disease, predicted_infection_type, confidence_score,
    user_feedback, language_used, modify_date

Each ``image_url`` is a presigned GET that's valid for the configured
S3 TTL (default 5 minutes). Re-run if links expire — re-running is
idempotent because the script only reads the database.

This is the operational tool for the active-learning loop: hand the
CSV to a domain reviewer, they tag the correct labels in a new
column, you slot the corrected rows into the next training run.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from pathlib import Path

from sqlalchemy import func, select

from app.common.s3 import generate_get_url
from app.config import get_settings
from app.db import AsyncSessionLocal
from app.diagnostics.models import PlantDiagnostic
from app.uploads.models import ImageUpload

_FLAGGED_VERDICTS = ("incorrect", "partial")
_HEADERS = [
    "diagnostic_id",
    "image_id",
    "image_url",
    "predicted_plant",
    "predicted_disease",
    "predicted_infection_type",
    "confidence_score",
    "user_feedback",
    "language_used",
    "modify_date",
]


async def export(out_path: Path, batch_size: int) -> int:
    settings = get_settings()
    rows_written = 0
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(_HEADERS)

        async with AsyncSessionLocal() as session:
            total = int(
                (
                    await session.execute(
                        select(func.count())
                        .select_from(PlantDiagnostic)
                        .where(
                            PlantDiagnostic.deleted_at.is_(None),
                            PlantDiagnostic.user_feedback.in_(_FLAGGED_VERDICTS),
                        )
                    )
                ).scalar_one()
            )
            print(f"Flagged diagnostics in queue: {total}", file=sys.stderr)

            offset = 0
            while offset < total:
                stmt = (
                    select(PlantDiagnostic, ImageUpload)
                    .outerjoin(ImageUpload, ImageUpload.image_id == PlantDiagnostic.image_id)
                    .where(
                        PlantDiagnostic.deleted_at.is_(None),
                        PlantDiagnostic.user_feedback.in_(_FLAGGED_VERDICTS),
                    )
                    .order_by(PlantDiagnostic.modify_date.desc())
                    .limit(batch_size)
                    .offset(offset)
                )
                for diag, image in (await session.execute(stmt)).all():
                    url = ""
                    if image is not None and image.storage_location:
                        try:
                            url = generate_get_url(
                                image.storage_location, settings.s3_presign_ttl_seconds
                            )
                        except Exception as exc:  # noqa: BLE001
                            print(
                                f"  warn: presign failed for {image.image_id}: {exc}",
                                file=sys.stderr,
                            )
                    writer.writerow(
                        [
                            str(diag.diagnostic_id),
                            str(diag.image_id) if diag.image_id else "",
                            url,
                            diag.plant_classification or "",
                            diag.disease_name or "",
                            diag.infection_type or "",
                            diag.confidence_score if diag.confidence_score is not None else "",
                            diag.user_feedback or "",
                            diag.language_used or "",
                            diag.modify_date.isoformat() if diag.modify_date else "",
                        ]
                    )
                    rows_written += 1
                offset += batch_size

    print(f"Wrote {rows_written} rows to {out_path}", file=sys.stderr)
    return rows_written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--batch", type=int, default=500, help="DB pagination size")
    args = parser.parse_args()
    asyncio.run(export(args.out, args.batch))


if __name__ == "__main__":
    main()
