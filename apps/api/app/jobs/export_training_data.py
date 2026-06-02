"""Nightly export of reviewed diagnostics to a HuggingFace dataset.

This is the second half of the active-learning flywheel: scans get
captured, agronomists review them via /admin/labelling-queue, and
this job ships the reviewed rows out as a versioned dataset the
training pipeline can consume.

Source rows
-----------
We pick up every ``plant_diagnostics`` row with:
  - ``reviewed_at IS NOT NULL`` (a human applied authoritative labels)
  - ``reviewed_at > last_export_at`` (only new rows since last run;
    last_export_at lives in ``meta_kv``)
  - ``deleted_at IS NULL`` (skip soft-deleted)
  - an ``image_id`` that resolves to an image_uploads row (we need
    the actual bytes)

Per row we emit:
  - the raw image bytes (downloaded from S3)
  - ``correct_plant`` / ``correct_disease`` / ``correct_infection_type``
    as the gold labels
  - provenance metadata (diagnostic_id, reviewer, reviewed_at,
    original predicted_* values + the prediction_source)

The provenance lets the training pipeline filter or stratify later
(e.g. "use only rows where prediction_source='llm_fallback'" if we
want to evaluate the coverage-expansion path in isolation).

Output
------
HuggingFace Datasets format, pushed to ``HF_TRAINING_DATASET_REPO``
on the Hub. Each run produces a new revision tagged
``training-v<YYYY-MM-DD>``. The dataset is private by default; set
``HF_TOKEN`` to a write-scoped token to enable push.

Invocation
----------
Two paths, same as daily_tip:

1. HTTP (Railway cron): ``POST /admin/cron/export-training-data``
   with ``X-Cron-Secret`` header matching ``CRON_SHARED_SECRET``.
2. CLI: ``python -m app.jobs.export_training_data`` (set
   DATABASE_URL + HF_TOKEN env vars; uses prod creds via railway run).

Both paths share the same ``run_export_job`` coroutine. Safe to run
multiple times in a day — the last_export_at filter prevents
duplicate rows.
"""
from __future__ import annotations

import asyncio
import io
import json
from datetime import UTC, datetime
from typing import Any

import boto3
from botocore.client import Config as BotoConfig
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.meta_kv import get_datetime, set_datetime
from app.config import get_settings
from app.diagnostics.models import PlantDiagnostic
from app.logging import get_logger
from app.uploads.models import ImageUpload

log = get_logger(__name__)

META_KV_KEY = "training_export.last_export_at"


def _s3_client(settings: Any) -> Any:
    """Same S3 client wiring the uploads router uses — kept inline so
    the job module has no other api-internal dependencies."""
    kwargs: dict[str, Any] = {
        "region_name": settings.s3_region,
        "config": BotoConfig(
            signature_version="s3v4",
            s3={"addressing_style": "path" if settings.s3_endpoint_url else "virtual"},
        ),
    }
    if settings.s3_access_key_id and settings.s3_secret_access_key:
        kwargs["aws_access_key_id"] = settings.s3_access_key_id
        kwargs["aws_secret_access_key"] = settings.s3_secret_access_key
    if settings.s3_endpoint_url:
        kwargs["endpoint_url"] = settings.s3_endpoint_url
    return boto3.client("s3", **kwargs)


async def _fetch_image_bytes(client: Any, bucket: str, key: str) -> bytes | None:
    """Sync S3 GetObject offloaded to a thread. Returns None on miss."""
    def _go() -> bytes | None:
        try:
            resp = client.get_object(Bucket=bucket, Key=key)
            return resp["Body"].read()
        except Exception as exc:  # noqa: BLE001
            log.warning("export_image_fetch_failed", key=key, error=str(exc))
            return None

    return await asyncio.to_thread(_go)


def _build_metadata(
    diag: PlantDiagnostic, image: ImageUpload
) -> dict[str, Any]:
    """Per-row provenance shipped alongside the image + gold labels.

    Keeping the model's original prediction lets the training pipeline
    compute "agreement rate" (when did the model already get it right
    and the reviewer just confirmed?). And keeping prediction_source
    means the trainer can do source-stratified eval ("how good are
    we on plantvit-original rows vs llm_fallback-promoted rows?").
    """
    return {
        "diagnostic_id": str(diag.diagnostic_id),
        "image_id": str(diag.image_id) if diag.image_id else None,
        "image_storage_location": image.storage_location,
        # Gold labels — what the reviewer says is true.
        "label_plant": diag.correct_plant,
        "label_disease": diag.correct_disease,
        "label_infection_type": diag.correct_infection_type,
        # Model's pre-review prediction — provenance for analytics.
        "predicted_plant": diag.plant_classification,
        "predicted_disease": diag.disease_name,
        "predicted_infection_type": diag.infection_type,
        "predicted_confidence": (
            float(diag.confidence_score) if diag.confidence_score is not None else None
        ),
        "prediction_source": diag.prediction_source,
        # When + who.
        "reviewed_at": diag.reviewed_at.isoformat() if diag.reviewed_at else None,
        "reviewed_by": diag.reviewed_by,
        "user_feedback": diag.user_feedback,
        # Original scan timestamp — useful for time-based splits.
        "scanned_at": diag.add_date.isoformat() if diag.add_date else None,
    }


async def collect_export_rows(
    session: AsyncSession,
    settings: Any,
    *,
    since: datetime | None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Build the list of {"image": bytes, "metadata": dict} rows.

    Returns an in-memory list — the export volumes are bounded (a few
    hundred rows per day at our current scale). If we ever exceed
    100K rows in a single export the caller should switch to a
    streaming write to a temp Parquet file instead.
    """
    where = [PlantDiagnostic.deleted_at.is_(None), PlantDiagnostic.reviewed_at.is_not(None)]
    if since is not None:
        where.append(PlantDiagnostic.reviewed_at > since)

    stmt = (
        select(PlantDiagnostic, ImageUpload)
        .join(ImageUpload, ImageUpload.image_id == PlantDiagnostic.image_id)
        .where(*where)
        .order_by(PlantDiagnostic.reviewed_at.asc())
    )
    if limit:
        stmt = stmt.limit(limit)

    pairs = (await session.execute(stmt)).all()
    if not pairs:
        return []

    s3 = _s3_client(settings)
    out: list[dict[str, Any]] = []
    for diag, image in pairs:
        if not image.storage_location:
            continue
        data = await _fetch_image_bytes(s3, settings.s3_bucket, image.storage_location)
        if data is None:
            # Image fetch failed; skip the row rather than abort the
            # whole job. We log per-row in _fetch_image_bytes.
            continue
        out.append({"image": data, "metadata": _build_metadata(diag, image)})
    return out


def _push_to_hf_hub(
    rows: list[dict[str, Any]],
    *,
    repo_id: str,
    token: str | None,
    revision_tag: str,
) -> dict[str, Any]:
    """Build an in-memory HuggingFace dataset and push it.

    Uses the ``datasets`` library's ``Image`` feature so the bytes
    decode lazily in downstream training code. ``token`` only
    required for private repos.
    """
    # Lazy imports — only the job depends on these.
    from datasets import Dataset, Features, Image as HFImage, Value

    if not rows:
        return {"pushed": False, "reason": "no_rows", "count": 0}

    feature_schema = Features({
        "image": HFImage(),
        "label_plant": Value("string"),
        "label_disease": Value("string"),
        "label_infection_type": Value("string"),
        "predicted_plant": Value("string"),
        "predicted_disease": Value("string"),
        "predicted_infection_type": Value("string"),
        "predicted_confidence": Value("float32"),
        "prediction_source": Value("string"),
        "diagnostic_id": Value("string"),
        "image_id": Value("string"),
        "image_storage_location": Value("string"),
        "reviewed_at": Value("string"),
        "reviewed_by": Value("string"),
        "user_feedback": Value("string"),
        "scanned_at": Value("string"),
    })

    # Flatten to columnar — datasets.from_dict expects {col_name: list}.
    cols: dict[str, list[Any]] = {name: [] for name in feature_schema}
    for row in rows:
        meta = row["metadata"]
        cols["image"].append({"bytes": row["image"], "path": None})
        for k in feature_schema:
            if k == "image":
                continue
            cols[k].append(meta.get(k))

    ds = Dataset.from_dict(cols, features=feature_schema)
    log.info("export_dataset_assembled", n_rows=len(ds), repo_id=repo_id)

    # ``push_to_hub`` handles the upload + creates the repo if missing
    # (when token has write scope on the namespace). ``private=True`` is
    # the right default for farmer images.
    ds.push_to_hub(
        repo_id=repo_id,
        private=True,
        token=token or None,
        commit_message=f"Training data export {revision_tag}",
        revision="main",
    )
    return {"pushed": True, "count": len(ds), "repo_id": repo_id}


async def run_export_job(session: AsyncSession) -> dict[str, Any]:
    """Fetch reviewed rows since the last successful export, build
    an HF dataset, push to the configured repo, advance the watermark.

    Returns observability counters for the caller (admin endpoint or
    cron CLI). Best-effort: per-row image fetch failures don't abort
    the run; the HF push itself raises on credential / network errors
    so the caller learns about catastrophic failures.
    """
    settings = get_settings()

    if not settings.hf_training_dataset_repo:
        log.warning("export_skipped_no_repo_configured")
        return {"pushed": False, "reason": "no_repo_configured", "count": 0}

    since = await get_datetime(session, META_KV_KEY)
    log.info("export_run_starting", since=since.isoformat() if since else "all_time")

    rows = await collect_export_rows(session, settings, since=since)
    if not rows:
        log.info("export_no_new_rows", since=since.isoformat() if since else None)
        return {"pushed": False, "reason": "no_new_rows", "count": 0}

    revision_tag = f"training-v{datetime.now(UTC).strftime('%Y-%m-%d')}"
    result = _push_to_hf_hub(
        rows,
        repo_id=settings.hf_training_dataset_repo,
        token=settings.hf_token,
        revision_tag=revision_tag,
    )

    if result.get("pushed"):
        # Advance the watermark to the latest row's reviewed_at so the
        # next run only sees rows added after this batch.
        latest_iso = max(r["metadata"]["reviewed_at"] for r in rows)
        await set_datetime(
            session, META_KV_KEY, datetime.fromisoformat(latest_iso)
        )
        log.info(
            "export_completed",
            count=result["count"],
            repo_id=result["repo_id"],
            new_watermark=latest_iso,
        )
    return result


async def _cli_entry() -> None:
    """``python -m app.jobs.export_training_data`` entrypoint."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        result = await run_export_job(session)
        print(json.dumps(result, default=str))
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_cli_entry())
