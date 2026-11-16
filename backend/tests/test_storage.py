"""Unit tests for the optional S3 storage backend (per-org prefixes, default Supabase no-op)."""
from __future__ import annotations

from unittest.mock import MagicMock

import boto3
import pytest

from app.core.config import settings
from app.services import storage

ORG_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
ORG_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


def test_default_storage_backend_is_noop(monkeypatch):
    monkeypatch.setattr(settings, "storage_backend", "supabase")
    mock_boto = MagicMock()
    monkeypatch.setattr(boto3, "client", mock_boto)

    assert storage.store_document_file(ORG_A, "doc.pdf", b"hello") is None
    assert storage.delete_document_file(ORG_A, "doc.pdf") is False
    mock_boto.assert_not_called()


def test_build_s3_key_scopes_by_org_id_and_blocks_traversal():
    key_a = storage.build_s3_key(ORG_A, "123_policy.pdf")
    key_b = storage.build_s3_key(ORG_B, "123_policy.pdf")

    assert key_a == f"organizations/{ORG_A}/123_policy.pdf"
    assert key_b == f"organizations/{ORG_B}/123_policy.pdf"
    assert key_a != key_b
    assert ORG_B not in key_a and ORG_A not in key_b

    with pytest.raises(ValueError):
        storage.build_s3_key("../other", "file.pdf")
    with pytest.raises(ValueError):
        storage.build_s3_key(ORG_A, "../secret.pdf")
    with pytest.raises(ValueError):
        storage.build_s3_key("org/evil", "file.pdf")


def test_s3_upload_and_delete_use_org_prefix(monkeypatch):
    monkeypatch.setattr(settings, "storage_backend", "s3")
    monkeypatch.setattr(settings, "s3_bucket_name", "company-rag-bucket")
    monkeypatch.setattr(settings, "aws_region", "us-east-1")

    fake_s3 = MagicMock()
    monkeypatch.setattr(boto3, "client", MagicMock(return_value=fake_s3))

    key_a = storage.store_document_file(ORG_A, "abc_handbook.pdf", b"%PDF-1.4")
    key_b = storage.store_document_file(ORG_B, "abc_handbook.pdf", b"%PDF-1.4")

    assert key_a == f"organizations/{ORG_A}/abc_handbook.pdf"
    assert key_b == f"organizations/{ORG_B}/abc_handbook.pdf"

    put_calls = fake_s3.put_object.call_args_list
    assert len(put_calls) == 2
    assert put_calls[0].kwargs["Bucket"] == "company-rag-bucket"
    assert put_calls[0].kwargs["Key"] == f"organizations/{ORG_A}/abc_handbook.pdf"
    assert put_calls[1].kwargs["Key"] == f"organizations/{ORG_B}/abc_handbook.pdf"

    assert storage.delete_document_file(ORG_A, "abc_handbook.pdf") is True
    fake_s3.delete_object.assert_called_once_with(
        Bucket="company-rag-bucket",
        Key=f"organizations/{ORG_A}/abc_handbook.pdf",
    )


def test_s3_error_fails_safe(monkeypatch):
    monkeypatch.setattr(settings, "storage_backend", "s3")
    monkeypatch.setattr(settings, "s3_bucket_name", "company-rag-bucket")

    fake_s3 = MagicMock()
    fake_s3.put_object.side_effect = RuntimeError("S3 unreachable")
    monkeypatch.setattr(boto3, "client", MagicMock(return_value=fake_s3))

    # Must not raise so ingestion into pgvector still succeeds
    assert storage.store_document_file(ORG_A, "abc_handbook.pdf", b"data") is None
