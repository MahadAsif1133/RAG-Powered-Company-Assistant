"""
LlamaIndex ingestion pipeline (ingestion ONLY).

LlamaIndex is used for: document readers, node parsing / chunking, and per-node
metadata (org_id, document_id, source filename). Embeddings (Voyage), storage
(Supabase pgvector) and retrieval are unchanged and do not use LlamaIndex.

Safe by design: if LlamaIndex is missing, errors, or produces nothing, the caller
falls back to the legacy parser + chunker, so ingestion never breaks because of it.
"""
from __future__ import annotations

import logging
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings
from app.services.chunker import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    chunk_text,
)
from app.services.parser import parse_document

logger = logging.getLogger(__name__)

# The legacy chunker works in characters (2000 chars / 200 overlap ~ 500 / 50 tokens).
# LlamaIndex counts "tokens" with whatever tokenizer we give it. We pass a cheap
# chars/4 approximation (no tiktoken download, works offline) so chunk sizes match the
# legacy ones: 500 "tokens" ~ 2000 chars, 50 ~ 200 chars.
_CHARS_PER_TOKEN = 4
CHUNK_SIZE_TOKENS = DEFAULT_CHUNK_SIZE // _CHARS_PER_TOKEN
CHUNK_OVERLAP_TOKENS = DEFAULT_CHUNK_OVERLAP // _CHARS_PER_TOKEN

_METADATA_KEYS = ["org_id", "document_id", "filename"]


@dataclass
class IngestedChunk:
    """One chunk ready for embedding. `text` is stored in document_chunks.chunk_text."""

    text: str
    metadata: dict


def _approx_tokenizer(text: str) -> list[int]:
    return [0] * max(1, len(text) // _CHARS_PER_TOKEN)


# ── LlamaIndex pipeline ──────────────────────────────────────

def _read_documents(content: bytes, filename: str):
    """Use LlamaIndex readers; return a list of llama_index Documents (maybe empty)."""
    from llama_index.core import Document

    suffix = Path(filename).suffix.lower()

    if suffix == ".txt":
        return [Document(text=content.decode("utf-8", errors="replace").strip())]

    if suffix == ".pdf":
        from llama_index.readers.file import PDFReader

        reader = PDFReader()
    elif suffix == ".docx":
        from llama_index.readers.file import DocxReader

        reader = DocxReader()
    else:  # .doc etc. - no LlamaIndex reader; caller falls back to the legacy parser
        return []

    # The readers want a file path, so spill to a temp file (deleted right after).
    fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(content)
        return reader.load_data(Path(tmp_path))
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _legacy_text_documents(content: bytes, filename: str):
    """Reader fallback: legacy parser output wrapped as a LlamaIndex Document."""
    from llama_index.core import Document

    text = parse_document(content, filename)
    return [Document(text=text)] if text and text.strip() else []


def llamaindex_chunks(
    content: bytes, filename: str, org_id: str, document_id: str
) -> list[IngestedChunk]:
    """Read -> attach metadata -> split into nodes with a LlamaIndex IngestionPipeline."""
    from llama_index.core.ingestion import IngestionPipeline
    from llama_index.core.node_parser import SentenceSplitter

    documents = [d for d in _read_documents(content, filename) if d.text and d.text.strip()]
    if sum(len(d.text.strip()) for d in documents) < 10:
        logger.info("LlamaIndex reader gave no usable text for '%s'; using legacy parser", filename)
        documents = _legacy_text_documents(content, filename)

    for doc in documents:
        doc.metadata = {"org_id": org_id, "document_id": document_id, "filename": filename}
        # Keep metadata out of the text that is chunked/embedded, so stored chunk_text is
        # plain document text exactly like the legacy format.
        doc.excluded_embed_metadata_keys = list(_METADATA_KEYS)
        doc.excluded_llm_metadata_keys = list(_METADATA_KEYS)

    pipeline = IngestionPipeline(
        transformations=[
            SentenceSplitter(
                chunk_size=CHUNK_SIZE_TOKENS,
                chunk_overlap=CHUNK_OVERLAP_TOKENS,
                tokenizer=_approx_tokenizer,
                chunking_tokenizer_fn=lambda text: re.split(r"(?<=[.!?])\s+", text),
            )
        ]
    )
    nodes = pipeline.run(documents=documents, show_progress=False)

    chunks = []
    for node in nodes:
        text = node.get_content().strip()  # MetadataMode.NONE: plain text only
        if text:
            chunks.append(IngestedChunk(text=text, metadata=dict(node.metadata)))
    return chunks


# ── Public entry point ───────────────────────────────────────

def ingest_chunks(
    content: bytes, filename: str, org_id: str, document_id: str
) -> list[IngestedChunk]:
    """
    Turn an uploaded file into chunks. INGESTION_PIPELINE=llamaindex (default) uses
    LlamaIndex; any failure falls back to the legacy parser + chunker. "legacy" skips it.
    """
    if (settings.ingestion_pipeline or "llamaindex").strip().lower() == "llamaindex":
        try:
            chunks = llamaindex_chunks(content, filename, org_id, document_id)
            if chunks:
                return chunks
            logger.warning("LlamaIndex pipeline produced no chunks for '%s'; falling back", filename)
        except Exception as exc:  # ImportError, reader errors, ...
            logger.warning("LlamaIndex pipeline failed for '%s' (%s); falling back", filename, exc)

    return legacy_chunks(content, filename, org_id, document_id)


def legacy_chunks(
    content: bytes, filename: str, org_id: str, document_id: str
) -> list[IngestedChunk]:
    """The original parse_document + chunk_text path (unchanged logic)."""
    text = parse_document(content, filename)
    if not text or len(text.strip()) < 10:
        raise ValueError("Parsed document produced no usable text.")
    meta = {"org_id": org_id, "document_id": document_id, "filename": filename}
    return [IngestedChunk(text=c, metadata=dict(meta)) for c in chunk_text(text)]
