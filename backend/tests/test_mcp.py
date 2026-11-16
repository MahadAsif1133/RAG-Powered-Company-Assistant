"""Unit tests for the standalone MCP server (tenancy scoping, read-only tools, no secret leaks)."""
from __future__ import annotations

import inspect
from unittest.mock import MagicMock

import pytest

from app import mcp_server
from app.core.config import settings
from app.services.retriever import RetrievedChunk

ORG_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
ORG_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


def test_mcp_requires_org_id(monkeypatch):
    monkeypatch.setattr(settings, "mcp_org_id", "")
    with pytest.raises(RuntimeError, match="MCP_ORG_ID"):
        mcp_server.search_knowledge_base("leave policy")
    with pytest.raises(RuntimeError, match="MCP_ORG_ID"):
        mcp_server.list_sources()


def test_search_knowledge_base_is_scoped_strictly_to_mcp_org_id(monkeypatch):
    monkeypatch.setattr(settings, "mcp_org_id", ORG_A)
    monkeypatch.setattr(settings, "supabase_service_role_key", "super-secret-service-role-key")

    calls: list[tuple[str, str]] = []

    def fake_retrieve(question: str, org_id: str):
        calls.append((question, org_id))
        return [
            RetrievedChunk(
                chunk_id="c1",
                chunk_text="Employees get 20 days of PTO.",
                similarity=0.87654,
                document_id="d1",
                chunk_index=0,
                filename="internal_storage_key.pdf",
                original_name="HR_Handbook.pdf",
            )
        ]

    monkeypatch.setattr(mcp_server, "retrieve_chunks", fake_retrieve)

    results = mcp_server.search_knowledge_base("  how much PTO? ")
    assert calls == [("how much PTO?", ORG_A)]
    assert len(results) == 1
    assert results[0]["source"] == "HR_Handbook.pdf"
    assert results[0]["text"] == "Employees get 20 days of PTO."
    # Never exposes internal storage filename or service-role key
    serialized = str(results)
    assert "super-secret-service-role-key" not in serialized
    assert "internal_storage_key.pdf" not in serialized

    # Verify the function signature does NOT accept an org_id override from clients
    sig = inspect.signature(mcp_server.search_knowledge_base)
    assert list(sig.parameters.keys()) == ["query"]


def test_list_sources_filters_by_mcp_org_id(monkeypatch):
    monkeypatch.setattr(settings, "mcp_org_id", ORG_B)

    fake_sb = MagicMock()
    query_chain = fake_sb.table.return_value.select.return_value
    eq_org = query_chain.eq.return_value
    eq_status = eq_org.eq.return_value
    ordered = eq_status.order.return_value
    ordered.execute.return_value.data = [
        {
            "id": "doc-1",
            "original_name": "Onboarding.docx",
            "file_type": "docx",
            "chunk_count": 12,
            "status": "ready",
            "uploaded_at": "2026-01-01T00:00:00Z",
        }
    ]
    monkeypatch.setattr(mcp_server, "get_supabase", lambda: fake_sb)

    sources = mcp_server.list_sources()
    query_chain.eq.assert_called_once_with("org_id", ORG_B)
    eq_org.eq.assert_called_once_with("status", "ready")
    assert sources == [
        {
            "document_id": "doc-1",
            "name": "Onboarding.docx",
            "file_type": "docx",
            "chunk_count": 12,
            "uploaded_at": "2026-01-01T00:00:00Z",
        }
    ]


def test_create_mcp_server_registers_tools(monkeypatch):
    monkeypatch.setattr(settings, "mcp_org_id", ORG_A)
    server = mcp_server.create_mcp_server()
    assert server is not None
