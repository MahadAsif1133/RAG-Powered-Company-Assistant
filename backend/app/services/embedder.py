from __future__ import annotations

import logging
from typing import List

from app.core.config import settings

logger = logging.getLogger(__name__)

# Maximum texts per API batch call
VOYAGE_BATCH_SIZE = 128
OPENAI_BATCH_SIZE = 100


def embed_texts(texts: List[str]) -> List[List[float]]:
    """
    Generate embeddings for a list of texts (for document ingestion).
    Uses Voyage AI if VOYAGE_API_KEY is set, otherwise falls back to OpenAI.

    Returns a list of float vectors in the same order as `texts`.
    """
    if not texts:
        return []

    if settings.use_voyage:
        return _embed_voyage(texts, input_type="document")

    if settings.use_openai:
        return _embed_openai(texts)

    raise RuntimeError(
        "No embedding API key configured. "
        "Set VOYAGE_API_KEY or OPENAI_API_KEY in your .env file."
    )


def embed_query(text: str) -> List[float]:
    """
    Generate an embedding for a single query string (for retrieval).
    Voyage AI has a separate input_type='query' for query-side embeddings,
    which improves retrieval quality.
    """
    if settings.use_voyage:
        results = _embed_voyage([text], input_type="query")
    elif settings.use_openai:
        results = _embed_openai([text])
    else:
        raise RuntimeError(
            "No embedding API key configured. "
            "Set VOYAGE_API_KEY or OPENAI_API_KEY in your .env file."
        )

    return results[0]


# ── Voyage AI ────────────────────────────────────────────────

def _embed_voyage(texts: List[str], input_type: str = "document") -> List[List[float]]:
    """
    Call Voyage AI embeddings API in batches.
    Model: voyage-3-large (1024 dimensions)
    """
    import voyageai  # type: ignore

    client = voyageai.Client(api_key=settings.voyage_api_key)
    all_embeddings: List[List[float]] = []

    for i in range(0, len(texts), VOYAGE_BATCH_SIZE):
        batch = texts[i : i + VOYAGE_BATCH_SIZE]
        logger.debug("Embedding Voyage batch %d/%d (%d texts)", i // VOYAGE_BATCH_SIZE + 1,
                     -(-len(texts) // VOYAGE_BATCH_SIZE), len(batch))
        result = client.embed(
            texts=batch,
            model="voyage-3-large",
            input_type=input_type,
        )
        all_embeddings.extend(result.embeddings)

    return all_embeddings


# ── OpenAI fallback ──────────────────────────────────────────

def _embed_openai(texts: List[str]) -> List[List[float]]:
    """
    Call OpenAI embeddings API in batches.
    Model: text-embedding-3-small (1536 dimensions)

    NOTE: If switching to OpenAI, update EMBEDDING_DIMENSION=1536
    in your .env and change vector(1024) → vector(1536) in schema.sql.
    """
    from openai import OpenAI  # type: ignore

    client = OpenAI(api_key=settings.openai_api_key)
    all_embeddings: List[List[float]] = []

    for i in range(0, len(texts), OPENAI_BATCH_SIZE):
        batch = texts[i : i + OPENAI_BATCH_SIZE]
        logger.debug("Embedding OpenAI batch %d/%d (%d texts)", i // OPENAI_BATCH_SIZE + 1,
                     -(-len(texts) // OPENAI_BATCH_SIZE), len(batch))
        response = client.embeddings.create(
            model="text-embedding-3-small",
            input=batch,
        )
        batch_embeddings = [item.embedding for item in response.data]
        all_embeddings.extend(batch_embeddings)

    return all_embeddings
