"""
Pluggable file storage layer (optional S3, default Supabase behavior).

Key layout for S3 (`STORAGE_BACKEND=s3`):
    organizations/{org_id}/{unique_filename}

Guarantees:
- Every S3 object key begins with `organizations/{org_id}/` so two organizations
  can never overwrite or read each other's files.
- Uses the standard boto3 AWS credential chain (`boto3.client("s3", region_name=...)`)
  — no AWS access keys are stored in code or Settings.
- Default (`STORAGE_BACKEND=supabase` or unset) leaves existing upload/delete behavior
  completely unchanged so missing S3 configuration never stops ingestion.
"""
from __future__ import annotations

import logging
import mimetypes

from app.core.config import settings

logger = logging.getLogger(__name__)


def build_s3_key(org_id: str, filename: str) -> str:
    """Build a tenant-isolated S3 object key: `organizations/{org_id}/{filename}`."""
    clean_org = (org_id or "").strip().strip("/")
    clean_file = (filename or "").strip().lstrip("/")
    if not clean_org or ".." in clean_org or "/" in clean_org:
        raise ValueError("Invalid org_id for storage path.")
    if not clean_file or ".." in clean_file:
        raise ValueError("Invalid filename for storage path.")
    return f"organizations/{clean_org}/{clean_file}"


def is_s3_enabled() -> bool:
    return (settings.storage_backend or "supabase").strip().lower() == "s3"


def _get_s3_client():
    import boto3

    region = (settings.aws_region or "").strip() or None
    return boto3.client("s3", region_name=region)


def store_document_file(org_id: str, filename: str, content: bytes) -> str | None:
    """
    Store raw uploaded document bytes when `STORAGE_BACKEND=s3`.
    Returns the S3 object key (`organizations/{org_id}/{filename}`) or `None` when S3 is not enabled.
    Fails safe on S3 errors so document ingestion in Postgres/pgvector is not blocked.
    """
    if not is_s3_enabled():
        return None

    bucket = (settings.s3_bucket_name or "").strip()
    if not bucket:
        logger.warning("STORAGE_BACKEND=s3 but S3_BUCKET_NAME is empty; skipping S3 upload")
        return None

    key = build_s3_key(org_id, filename)
    content_type, _ = mimetypes.guess_type(filename)
    try:
        client = _get_s3_client()
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=content,
            ContentType=content_type or "application/octet-stream",
            ServerSideEncryption="AES256",
        )
        logger.info("Stored document in S3 bucket=%s key=%s", bucket, key)
        return key
    except Exception as exc:
        logger.warning("S3 upload failed for key=%s (%s); continuing ingestion", key, type(exc).__name__)
        return None


def delete_document_file(org_id: str, filename: str) -> bool:
    """
    Delete the raw document object from S3 when `STORAGE_BACKEND=s3`.
    Scoped to `organizations/{org_id}/{filename}` so an org can only delete its own prefix.
    """
    if not is_s3_enabled():
        return False

    bucket = (settings.s3_bucket_name or "").strip()
    if not bucket:
        return False

    key = build_s3_key(org_id, filename)
    try:
        client = _get_s3_client()
        client.delete_object(Bucket=bucket, Key=key)
        logger.info("Deleted document from S3 bucket=%s key=%s", bucket, key)
        return True
    except Exception as exc:
        logger.warning("S3 delete failed for key=%s (%s)", key, type(exc).__name__)
        return False
