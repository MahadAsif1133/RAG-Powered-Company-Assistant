"""
MCP server exposing the company knowledge base as read-only tools.

Separate entry point (`python -m app.mcp_server`) — never imported by the FastAPI app,
so a missing `mcp` package or unset `MCP_ORG_ID` never affects the main backend.

Security / tenancy guarantees:
- Every tool call is strictly scoped to `settings.mcp_org_id` (`MCP_ORG_ID` env var).
  Callers CANNOT pass or override `org_id`.
- Only read-only operations are exposed (`search_knowledge_base`, `list_sources`).
- Secrets (`SUPABASE_SERVICE_ROLE_KEY`, API keys) are never returned or logged.
"""
from __future__ import annotations

import logging
from typing import Any

from app.core.config import settings
from app.core.supabase_client import get_supabase
from app.services.retriever import retrieve_chunks

logger = logging.getLogger(__name__)


def _require_org_id() -> str:
    """Return the configured MCP_ORG_ID or raise a clear error."""
    org_id = (settings.mcp_org_id or "").strip()
    if not org_id:
        raise RuntimeError(
            "MCP_ORG_ID environment variable is required to run the MCP server. "
            "Set MCP_ORG_ID to the organization UUID this MCP server should serve."
        )
    return org_id


def search_knowledge_base(query: str) -> list[dict[str, Any]]:
    """
    Search the organization's indexed knowledge base for relevant passages.

    Scoped strictly to `MCP_ORG_ID` via the existing `retrieve_chunks` pipeline.
    """
    org_id = _require_org_id()
    cleaned = (query or "").strip()
    if not cleaned:
        raise ValueError("query cannot be empty.")
    if len(cleaned) > 2000:
        raise ValueError("query exceeds 2000 character limit.")

    chunks = retrieve_chunks(question=cleaned, org_id=org_id)
    return [
        {
            "chunk_id": c.chunk_id,
            "document_id": c.document_id,
            "source": c.original_name,
            "chunk_index": c.chunk_index,
            "similarity": round(float(c.similarity), 4),
            "text": c.chunk_text,
        }
        for c in chunks
    ]


def list_sources() -> list[dict[str, Any]]:
    """
    List ready documents in the organization's knowledge base.

    Scoped strictly to `MCP_ORG_ID`. Never exposes storage keys or credentials.
    """
    org_id = _require_org_id()
    supabase = get_supabase()
    result = (
        supabase.table("documents")
        .select("id, original_name, file_type, chunk_count, status, uploaded_at")
        .eq("org_id", org_id)
        .eq("status", "ready")
        .order("uploaded_at", desc=True)
        .execute()
    )
    rows = result.data or []
    return [
        {
            "document_id": r["id"],
            "name": r["original_name"],
            "file_type": r["file_type"],
            "chunk_count": r.get("chunk_count") or 0,
            "uploaded_at": r.get("uploaded_at"),
        }
        for r in rows
    ]


def create_mcp_server():
    """Build and return the MCP server instance registering the read-only tools."""
    _require_org_id()
    try:
        from mcp.server.mcpserver import MCPServer as ServerClass
    except ImportError:
        from mcp.server.fastmcp import FastMCP as ServerClass

    mcp = ServerClass("company-knowledge-assistant")

    @mcp.tool(
        name="search_knowledge_base",
        description="Search the organization's internal documents for passages relevant to a query.",
    )
    def _search_tool(query: str) -> list[dict[str, Any]]:
        return search_knowledge_base(query=query)

    @mcp.tool(
        name="list_sources",
        description="List all indexed (ready) documents available in the organization's knowledge base.",
    )
    def _list_sources_tool() -> list[dict[str, Any]]:
        return list_sources()

    return mcp


def main() -> None:
    """CLI entry point: run the MCP server over stdio."""
    server = create_mcp_server()
    server.run()


if __name__ == "__main__":
    main()
