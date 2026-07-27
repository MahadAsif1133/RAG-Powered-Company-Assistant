from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from pathlib import Path
from typing import List

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile, File, status
from pydantic import BaseModel

from app.api.deps import AdminDep, UserDep
from app.core.supabase_client import get_supabase
from app.services.chunker import chunk_text
from app.services.embedder import embed_texts
from app.services.parser import parse_document, SUPPORTED_TYPES

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/documents", tags=["Documents"])

MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB


# ── Response models ──────────────────────────────────────────

class DocumentResponse(BaseModel):
    id: str
    filename: str
    original_name: str
    file_type: str
    file_size: int | None
    status: str
    chunk_count: int | None
    error_msg: str | None
    uploaded_at: str
    updated_at: str


class UploadResponse(BaseModel):
    document_id: str
    message: str


# ── Upload endpoint ──────────────────────────────────────────

@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    background_tasks: BackgroundTasks,
    current_user: AdminDep,
    file: UploadFile = File(...),
) -> UploadResponse:
    """
    Admin-only: Upload a document for indexing.
    - Validates file type and size
    - Creates a `documents` row with status='processing'
    - Kicks off background ingestion task (parse → chunk → embed → store)
    - Returns immediately with document_id for status polling
    """
    # Validate file type
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in SUPPORTED_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{suffix}'. Allowed: {', '.join(SUPPORTED_TYPES)}",
        )

    # Read file content
    content = await file.read()

    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum size of {MAX_FILE_SIZE_BYTES // (1024*1024)} MB.",
        )

    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")

    # Sanitize filename for storage
    safe_filename = _sanitize_filename(file.filename or "document")
    unique_filename = f"{uuid.uuid4().hex}_{safe_filename}"

    supabase = get_supabase()

    # Create document record (status=processing)
    doc_result = (
        supabase.table("documents")
        .insert(
            {
                "org_id": current_user.org_id,
                "filename": unique_filename,
                "original_name": file.filename,
                "file_type": suffix.lstrip("."),
                "file_size": len(content),
                "uploaded_by": current_user.user_id,
                "status": "processing",
            }
        )
        .execute()
    )

    if not doc_result.data:
        raise HTTPException(status_code=500, detail="Failed to create document record.")

    document_id = doc_result.data[0]["id"]
    logger.info("Created document %s for org %s — starting ingestion", document_id, current_user.org_id)

    # Kick off background ingestion
    background_tasks.add_task(
        _ingest_document,
        document_id=document_id,
        org_id=current_user.org_id,
        content=content,
        filename=file.filename or safe_filename,
        original_name=file.filename or safe_filename,
    )

    return UploadResponse(
        document_id=document_id,
        message="Document uploaded. Ingestion started — poll /status for progress.",
    )


# ── List documents ───────────────────────────────────────────

@router.get("", response_model=List[DocumentResponse])
async def list_documents(current_user: AdminDep) -> List[DocumentResponse]:
    """Admin-only: List all documents for the organization."""
    supabase = get_supabase()
    result = (
        supabase.table("documents")
        .select("*")
        .eq("org_id", current_user.org_id)
        .order("uploaded_at", desc=True)
        .execute()
    )
    return [DocumentResponse(**row) for row in (result.data or [])]


# ── Document status ──────────────────────────────────────────

@router.get("/{document_id}/status")
async def get_document_status(document_id: str, current_user: AdminDep) -> dict:
    """Admin-only: Poll ingestion status for a specific document."""
    supabase = get_supabase()
    result = (
        supabase.table("documents")
        .select("id, status, chunk_count, error_msg, updated_at")
        .eq("id", document_id)
        .eq("org_id", current_user.org_id)
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Document not found.")
    return result.data


# ── Delete document ──────────────────────────────────────────

@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(document_id: str, current_user: AdminDep) -> None:
    """
    Admin-only: Delete a document and all its chunks.
    Cascade delete is handled by the FK constraint in schema.sql.
    """
    supabase = get_supabase()

    # Verify document belongs to this org
    check = (
        supabase.table("documents")
        .select("id")
        .eq("id", document_id)
        .eq("org_id", current_user.org_id)
        .single()
        .execute()
    )
    if not check.data:
        raise HTTPException(status_code=404, detail="Document not found.")

    supabase.table("documents").delete().eq("id", document_id).execute()
    logger.info("Deleted document %s (org=%s)", document_id, current_user.org_id)


# ── Background ingestion task ────────────────────────────────

async def _ingest_document(
    document_id: str,
    org_id: str,
    content: bytes,
    filename: str,
    original_name: str,
) -> None:
    """
    Background task: parse → chunk → embed → store to document_chunks.
    Updates document status to 'ready' on success or 'failed' on error.
    """
    supabase = get_supabase()

    try:
        logger.info("[Ingest %s] Parsing document", document_id)
        text = parse_document(content, filename)

        if not text or len(text.strip()) < 10:
            raise ValueError("Parsed document produced no usable text.")

        logger.info("[Ingest %s] Chunking (%d chars)", document_id, len(text))
        chunks = chunk_text(text)

        if not chunks:
            raise ValueError("Chunker produced no chunks.")

        logger.info("[Ingest %s] Generating embeddings for %d chunks", document_id, len(chunks))
        # Run embedding in thread pool to avoid blocking event loop
        embeddings = await asyncio.get_event_loop().run_in_executor(None, embed_texts, chunks)

        logger.info("[Ingest %s] Storing %d chunks to DB", document_id, len(chunks))
        chunk_rows = [
            {
                "document_id": document_id,
                "org_id": org_id,
                "chunk_index": i,
                "chunk_text": chunk,
                "embedding": embedding,
                "token_count": len(chunk) // 4,  # rough approximation
            }
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings))
        ]

        # Insert in batches of 50 to avoid request size limits
        for batch_start in range(0, len(chunk_rows), 50):
            batch = chunk_rows[batch_start : batch_start + 50]
            supabase.table("document_chunks").insert(batch).execute()

        # Update document status → ready
        supabase.table("documents").update(
            {"status": "ready", "chunk_count": len(chunks)}
        ).eq("id", document_id).execute()

        logger.info("[Ingest %s] Complete — %d chunks indexed", document_id, len(chunks))

    except Exception as exc:
        logger.error("[Ingest %s] FAILED: %s", document_id, exc, exc_info=True)
        supabase.table("documents").update(
            {"status": "failed", "error_msg": str(exc)[:500]}
        ).eq("id", document_id).execute()


# ── Helpers ──────────────────────────────────────────────────

def _sanitize_filename(filename: str) -> str:
    """Remove unsafe characters from filenames before using as storage key."""
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    safe_stem = re.sub(r"[^\w\-.]", "_", stem)[:100]
    return f"{safe_stem}{suffix}"
