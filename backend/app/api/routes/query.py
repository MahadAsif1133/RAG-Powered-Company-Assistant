from __future__ import annotations

import logging
import time
from typing import List

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.api.deps import UserDep
from app.core.config import settings
from app.core.supabase_client import get_supabase
from app.services.llm import generate_answer
from app.services.retriever import retrieve_chunks

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/query", tags=["Query"])

# Rate limiter — keyed by remote IP (upgrade to user_id key with Redis for prod)
# TODO: For multi-instance production deployments, move state to Redis:
#   from slowapi import Limiter
#   limiter = Limiter(key_func=get_user_id_key, storage_uri="redis://...")
limiter = Limiter(key_func=get_remote_address)


# ── Request / Response models ────────────────────────────────

class QueryRequest(BaseModel):
    question: str

    class Config:
        json_schema_extra = {
            "example": {"question": "What is the remote work policy?"}
        }


class SourceDocument(BaseModel):
    original_name: str
    filename: str
    document_id: str


class QueryResponse(BaseModel):
    answer: str
    sources: List[SourceDocument]
    was_answered_confidently: bool
    latency_ms: int


# ── Query endpoint ───────────────────────────────────────────

@router.post("", response_model=QueryResponse)
@limiter.limit(settings.query_rate_limit)
async def query(
    request: Request,
    body: QueryRequest,
    current_user: UserDep,
) -> QueryResponse:
    """
    RAG query pipeline:
    1. Embed the question
    2. Vector similarity search (top-k chunks for this org)
    3. Build Claude prompt with retrieved context
    4. Generate answer (grounded, citation-aware)
    5. Log to query_logs
    6. Return answer + source documents

    Rate-limited to 10 requests/minute per IP.
    """
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Question cannot be empty.")

    if len(question) > 2000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Question exceeds 2000 character limit.",
        )

    start_ms = int(time.time() * 1000)

    # Step 1 & 2: Retrieve relevant chunks
    logger.info("RAG query from user=%s org=%s", current_user.user_id, current_user.org_id)
    chunks = retrieve_chunks(question=question, org_id=current_user.org_id)

    # Step 3 & 4: Generate answer
    answer, was_confident = generate_answer(question=question, chunks=chunks)

    latency_ms = int(time.time() * 1000) - start_ms

    # Step 5: Log to query_logs (fire-and-forget — don't fail the request if logging fails)
    chunk_ids = [c.chunk_id for c in chunks]
    _log_query(
        org_id=current_user.org_id,
        user_id=current_user.user_id,
        question=question,
        answer=answer,
        chunk_ids=chunk_ids,
        was_confident=was_confident,
        latency_ms=latency_ms,
    )

    # Step 6: Build unique source document list
    seen_docs: dict[str, SourceDocument] = {}
    for chunk in chunks:
        if chunk.document_id not in seen_docs:
            seen_docs[chunk.document_id] = SourceDocument(
                original_name=chunk.original_name,
                filename=chunk.filename,
                document_id=chunk.document_id,
            )

    return QueryResponse(
        answer=answer,
        sources=list(seen_docs.values()),
        was_answered_confidently=was_confident,
        latency_ms=latency_ms,
    )


# ── Analytics endpoints ──────────────────────────────────────

@router.get("/analytics/summary", tags=["Analytics"])
async def analytics_summary(current_user: UserDep) -> dict:
    """
    Return aggregate analytics for the admin dashboard:
    - Total queries
    - Confident vs. punted counts
    - Recent questions (last 50)
    """
    supabase = get_supabase()
    result = (
        supabase.table("query_logs")
        .select("id, question, was_answered_confidently, created_at, latency_ms")
        .eq("org_id", current_user.org_id)
        .order("created_at", desc=True)
        .limit(200)
        .execute()
    )
    rows = result.data or []

    total = len(rows)
    confident = sum(1 for r in rows if r["was_answered_confidently"])
    punted = total - confident

    return {
        "total_queries": total,
        "confident_count": confident,
        "punted_count": punted,
        "confident_pct": round(confident / total * 100, 1) if total else 0,
        "recent_questions": [
            {
                "question": r["question"],
                "was_answered_confidently": r["was_answered_confidently"],
                "created_at": r["created_at"],
                "latency_ms": r["latency_ms"],
            }
            for r in rows[:50]
        ],
    }


# ── Internal helpers ─────────────────────────────────────────

def _log_query(
    org_id: str,
    user_id: str,
    question: str,
    answer: str,
    chunk_ids: list[str],
    was_confident: bool,
    latency_ms: int,
) -> None:
    """Log a query to query_logs. Swallows errors to not affect response."""
    try:
        supabase = get_supabase()
        supabase.table("query_logs").insert(
            {
                "org_id": org_id,
                "user_id": user_id,
                "question": question,
                "retrieved_chunk_ids": chunk_ids,
                "answer": answer,
                "was_answered_confidently": was_confident,
                "latency_ms": latency_ms,
            }
        ).execute()
    except Exception as exc:
        logger.warning("Failed to log query to query_logs: %s", exc)
