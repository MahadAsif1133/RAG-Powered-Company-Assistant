from __future__ import annotations

import logging
import math

from app.core.config import settings

logger = logging.getLogger(__name__)

# Maximum texts per API batch call
QWEN_BATCH_SIZE = 32
VOYAGE_BATCH_SIZE = 128
OPENAI_BATCH_SIZE = 100


def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    Generate embeddings for a list of texts (for document ingestion).
    Priority:
      1. Qwen/Qwen3-Embedding-8B via Hugging Face InferenceClient (if HF_TOKEN is set)
      2. Voyage AI (if VOYAGE_API_KEY is set — also automatic fallback if Qwen quota/credits fail)
      3. OpenAI (if OPENAI_API_KEY is set)

    Returns a list of float vectors in the same order as `texts`.
    """
    if not texts:
        return []

    if settings.use_qwen:
        try:
            return _embed_qwen(texts)
        except Exception as exc:
            if settings.voyage_api_key:
                logger.warning(
                    "Qwen embedding failed (%s); falling back to Voyage AI",
                    type(exc).__name__,
                )
                return _embed_voyage(texts, input_type="document")
            if settings.openai_api_key:
                logger.warning(
                    "Qwen embedding failed (%s); falling back to OpenAI",
                    type(exc).__name__,
                )
                return _embed_openai(texts)
            raise

    if settings.use_voyage:
        return _embed_voyage(texts, input_type="document")

    if settings.use_openai:
        return _embed_openai(texts)

    raise RuntimeError(
        "No embedding API key configured. "
        "Set HF_TOKEN, VOYAGE_API_KEY, or OPENAI_API_KEY in your .env file."
    )


def embed_query(text: str) -> list[float]:
    """
    Generate an embedding for a single query string (for retrieval).
    """
    if settings.use_qwen:
        try:
            results = _embed_qwen([text])
            return results[0]
        except Exception as exc:
            if settings.voyage_api_key:
                logger.warning(
                    "Qwen query embedding failed (%s); falling back to Voyage AI",
                    type(exc).__name__,
                )
                return _embed_voyage([text], input_type="query")[0]
            if settings.openai_api_key:
                logger.warning(
                    "Qwen query embedding failed (%s); falling back to OpenAI",
                    type(exc).__name__,
                )
                return _embed_openai([text])[0]
            raise

    if settings.use_voyage:
        results = _embed_voyage([text], input_type="query")
    elif settings.use_openai:
        results = _embed_openai([text])
    else:
        raise RuntimeError(
            "No embedding API key configured. "
            "Set HF_TOKEN, VOYAGE_API_KEY, or OPENAI_API_KEY in your .env file."
        )

    return results[0]


# ── Qwen (Hugging Face InferenceClient) ─────────────────────

def _normalize_and_slice(vec: list[float], target_dim: int) -> list[float]:
    """
    Ensure the vector matches `target_dim` (e.g. 1024 for pgvector schema) using
    Matryoshka slicing + L2 renormalization when the upstream provider returns
    the full 4096-dim Qwen3-Embedding-8B vector.
    """
    floats = [float(x) for x in vec]
    if target_dim and len(floats) > target_dim:
        floats = floats[:target_dim]
    norm = math.sqrt(sum(x * x for x in floats))
    if norm > 0:
        floats = [x / norm for x in floats]
    return floats


def _to_vector_list(raw, expected_count: int, target_dim: int) -> list[list[float]]:
    """Convert InferenceClient.feature_extraction output (ndarray or nested list) to list[list[float]]."""
    data = raw.tolist() if hasattr(raw, "tolist") else raw
    if not data:
        return []
    # Single input string returns a 1D vector [f1, f2, ...]
    if isinstance(data[0], (int, float)):
        return [_normalize_and_slice(data, target_dim)]
    # 2D batch [[f1, f2, ...], ...]
    vectors: list[list[float]] = []
    for item in data:
        # Handle 3D token-level output if a provider returns [seq_len, dim]
        if item and isinstance(item[0], list):
            item = item[-1]
        vectors.append(_normalize_and_slice(item, target_dim))
    if len(vectors) != expected_count:
        raise RuntimeError(
            f"Expected {expected_count} embeddings from Qwen, got {len(vectors)}"
        )
    return vectors


def _embed_qwen(texts: list[str]) -> list[list[float]]:
    """
    Call Qwen/Qwen3-Embedding-8B via huggingface_hub.InferenceClient.
    """
    from huggingface_hub import InferenceClient

    client = InferenceClient(
        provider=settings.hf_embedding_provider,
        api_key=settings.hf_token,
    )
    target_dim = settings.embedding_dimension
    all_embeddings: list[list[float]] = []

    for i in range(0, len(texts), QWEN_BATCH_SIZE):
        batch = texts[i : i + QWEN_BATCH_SIZE]
        payload: str | list[str] = batch[0] if len(batch) == 1 else batch
        try:
            result = client.feature_extraction(
                payload,
                model=settings.hf_embedding_model,
                dimensions=target_dim,
            )
        except Exception:
            result = client.feature_extraction(
                payload,
                model=settings.hf_embedding_model,
            )
        all_embeddings.extend(_to_vector_list(result, len(batch), target_dim))

    return all_embeddings


# ── Voyage AI ────────────────────────────────────────────────

def _embed_voyage(texts: list[str], input_type: str = "document") -> list[list[float]]:
    """
    Call Voyage AI embeddings API in batches.
    Model: voyage-3-large (1024 dimensions)
    """
    import voyageai  # type: ignore

    client = voyageai.Client(api_key=settings.voyage_api_key)
    all_embeddings: list[list[float]] = []

    for i in range(0, len(texts), VOYAGE_BATCH_SIZE):
        batch = texts[i : i + VOYAGE_BATCH_SIZE]
        logger.debug(
            "Embedding Voyage batch %d/%d (%d texts)",
            i // VOYAGE_BATCH_SIZE + 1,
            -(-len(texts) // VOYAGE_BATCH_SIZE),
            len(batch),
        )
        result = client.embed(
            texts=batch,
            model="voyage-3-large",
            input_type=input_type,
        )
        all_embeddings.extend(result.embeddings)

    return all_embeddings


# ── OpenAI fallback ──────────────────────────────────────────

def _embed_openai(texts: list[str]) -> list[list[float]]:
    """
    Call OpenAI embeddings API in batches.
    Model: text-embedding-3-small (1536 dimensions)
    """
    from openai import OpenAI  # type: ignore

    client = OpenAI(api_key=settings.openai_api_key)
    all_embeddings: list[list[float]] = []

    for i in range(0, len(texts), OPENAI_BATCH_SIZE):
        batch = texts[i : i + OPENAI_BATCH_SIZE]
        logger.debug(
            "Embedding OpenAI batch %d/%d (%d texts)",
            i // OPENAI_BATCH_SIZE + 1,
            -(-len(texts) // OPENAI_BATCH_SIZE),
            len(batch),
        )
        response = client.embeddings.create(
            model="text-embedding-3-small",
            input=batch,
        )
        batch_embeddings = [item.embedding for item in response.data]
        all_embeddings.extend(batch_embeddings)

    return all_embeddings
