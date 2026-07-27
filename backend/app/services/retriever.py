from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List

from app.core.config import settings
from app.core.supabase_client import get_supabase
from app.services.embedder import embed_query

logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    """A single retrieved document chunk with its metadata."""
    chunk_id: str
    chunk_text: str
    similarity: float
    document_id: str
    chunk_index: int
    filename: str
    original_name: str


def retrieve_chunks(question: str, org_id: str) -> List[RetrievedChunk]:
    """
    Full retrieval pipeline:
    1. Embed the question using the configured embedder
    2. Call the `match_document_chunks` Postgres function via Supabase RPC
    3. Return top-k chunks ordered by cosine similarity

    Args:
        question: The user's natural language question
        org_id:   The organization UUID (for multi-tenant isolation)

    Returns:
        List of RetrievedChunk objects (up to MAX_RETRIEVED_CHUNKS)
    """
    # Step 1: Embed the query
    logger.info("Embedding query for org %s", org_id)
    query_embedding = embed_query(question)

    # Step 2: Vector similarity search via pgvector
    supabase = get_supabase()
    logger.info(
        "Running vector search: org=%s, top_k=%d, threshold=%.2f",
        org_id,
        settings.max_retrieved_chunks,
        settings.similarity_threshold,
    )

    response = supabase.rpc(
        "match_document_chunks",
        {
            "query_embedding": query_embedding,
            "p_org_id": org_id,
            "match_count": settings.max_retrieved_chunks,
            "similarity_threshold": settings.similarity_threshold,
        },
    ).execute()

    if not response.data:
        logger.info("No chunks matched (org=%s, threshold=%.2f)", org_id, settings.similarity_threshold)
        return []

    # Step 3: Map to dataclass
    chunks = [
        RetrievedChunk(
            chunk_id=row["id"],
            chunk_text=row["chunk_text"],
            similarity=row["similarity"],
            document_id=row["document_id"],
            chunk_index=row["chunk_index"],
            filename=row["filename"],
            original_name=row["original_name"],
        )
        for row in response.data
    ]

    logger.info("Retrieved %d chunks for query (top similarity=%.3f)", len(chunks),
                chunks[0].similarity if chunks else 0)
    return chunks
