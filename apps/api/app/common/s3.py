"""S3 / S3-compatible object storage client.

Designed to work against any S3-compatible endpoint (real AWS S3,
Cloudflare R2, MinIO, LocalStack). For local development the
``S3_ENDPOINT_URL`` env var points at MinIO; for production it's
unset and boto3 picks the real AWS endpoint.

Presigned-URL generation is purely cryptographic — boto3 signs the
URL locally and does not make a network call — so it is safe to
invoke from async code without a thread offload. Actual network ops
(``ensure_bucket``, ``head_object``) ARE blocking and should be run
through ``asyncio.to_thread`` if called from async handlers.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import boto3
from botocore.client import BaseClient, Config
from botocore.exceptions import ClientError

from app.config import get_settings
from app.logging import get_logger

log = get_logger(__name__)


@lru_cache
def get_s3_client() -> BaseClient:
    """Return a singleton boto3 S3 client configured from settings."""
    s = get_settings()
    kwargs: dict[str, Any] = {
        "region_name": s.s3_region,
        "config": Config(
            signature_version="s3v4",
            s3={"addressing_style": "path" if s.s3_endpoint_url else "virtual"},
            retries={"max_attempts": 3, "mode": "standard"},
        ),
    }
    if s.s3_access_key_id and s.s3_secret_access_key:
        kwargs["aws_access_key_id"] = s.s3_access_key_id
        kwargs["aws_secret_access_key"] = s.s3_secret_access_key
    if s.s3_endpoint_url:
        kwargs["endpoint_url"] = s.s3_endpoint_url
    return boto3.client("s3", **kwargs)


def generate_put_url(key: str, mime_type: str, expires: int) -> str:
    """Presigned URL for the client to PUT an object directly.

    The client MUST send the ``Content-Type`` header set to the same
    ``mime_type`` used here, otherwise the signature will not match.
    """
    s = get_settings()
    return get_s3_client().generate_presigned_url(
        ClientMethod="put_object",
        Params={
            "Bucket": s.s3_bucket,
            "Key": key,
            "ContentType": mime_type,
        },
        ExpiresIn=expires,
        HttpMethod="PUT",
    )


def generate_get_url(key: str, expires: int) -> str:
    """Presigned URL for the client to GET / display the object."""
    s = get_settings()
    return get_s3_client().generate_presigned_url(
        ClientMethod="get_object",
        Params={"Bucket": s.s3_bucket, "Key": key},
        ExpiresIn=expires,
    )


def ensure_bucket() -> bool:
    """Create the configured bucket if it doesn't exist (dev only).

    Returns True if the bucket exists or was created, False otherwise.
    Intended to run at API startup against a local MinIO. In production
    the bucket is provisioned by infrastructure-as-code and this
    function should not be called.
    """
    s = get_settings()
    client = get_s3_client()
    try:
        client.head_bucket(Bucket=s.s3_bucket)
        log.info("bucket_exists", bucket=s.s3_bucket)
        return True
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "")
        if error_code not in {"404", "NoSuchBucket", "NotFound"}:
            log.warning("bucket_check_failed", bucket=s.s3_bucket, code=error_code)
            return False

    try:
        # MinIO + many S3 emulators reject the LocationConstraint header for
        # us-east-1; only set it for non-default regions.
        create_kwargs: dict[str, Any] = {"Bucket": s.s3_bucket}
        if s.s3_region and s.s3_region != "us-east-1" and not s.s3_endpoint_url:
            create_kwargs["CreateBucketConfiguration"] = {
                "LocationConstraint": s.s3_region
            }
        client.create_bucket(**create_kwargs)
        log.info("bucket_created", bucket=s.s3_bucket)
        return True
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in {"BucketAlreadyOwnedByYou", "BucketAlreadyExists"}:
            return True
        log.warning("bucket_create_failed", bucket=s.s3_bucket, code=code, error=str(exc))
        return False


def object_key_for_upload(user_id: str, image_id: str, image_name: str) -> str:
    """Canonical S3 key layout: tenant-scoped, image-scoped."""
    # Strip any path separators that might come from the client to prevent
    # writing outside the intended prefix.
    safe_name = image_name.replace("/", "_").replace("\\", "_")
    return f"uploads/{user_id}/{image_id}/{safe_name}"
