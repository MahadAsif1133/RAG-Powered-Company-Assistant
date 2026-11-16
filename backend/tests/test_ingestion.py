"""Before/after test: legacy parser+chunker vs the LlamaIndex ingestion pipeline."""
from __future__ import annotations

import io
import re

import docx
import pytest

from app.core.config import settings
from app.services import ingestion
from app.services.chunker import DEFAULT_CHUNK_SIZE, chunk_text
from app.services.ingestion import ingest_chunks, legacy_chunks, llamaindex_chunks

ORG = "11111111-1111-1111-1111-111111111111"
DOC = "22222222-2222-2222-2222-222222222222"


def _sample_text() -> str:
    paras = []
    for i in range(1, 15):
        paras.append(
            f"Section {i}. Leave policy. Full-time employees accrue {i + 10} days of paid leave "
            "per year. Requests must be submitted to the line manager at least two weeks in "
            "advance. Unused leave may be carried over for up to three months. Sick leave "
            "requires a doctor's note after three consecutive days. Contact HR for exceptions. "
            "Managers approve or decline requests within five working days. " * 2
        )
    return "\n\n".join(paras)


def _words(text: str) -> set[str]:
    return set(re.findall(r"[A-Za-z0-9']+", text))


@pytest.fixture
def sample_txt() -> bytes:
    return _sample_text().encode()


def test_before_after_txt(sample_txt):
    source = sample_txt.decode()
    before = [c.text for c in legacy_chunks(sample_txt, "policy.txt", ORG, DOC)]
    after_chunks = llamaindex_chunks(sample_txt, "policy.txt", ORG, DOC)
    after = [c.text for c in after_chunks]

    print(f"\nlegacy: {len(before)} chunks, max {max(map(len, before))} chars")
    print(f"llamaindex: {len(after)} chunks, max {max(map(len, after))} chars")

    assert before and after
    # Similar granularity: same order of magnitude of chunk count.
    assert 0.5 <= len(after) / len(before) <= 2.0
    # No text lost: every word in the source appears in the new chunks, as with legacy.
    assert _words(source) <= _words(" ".join(after))
    assert _words(source) <= _words(" ".join(before))
    # Chunks respect the target size (small slack for sentence boundaries).
    assert max(map(len, after)) <= DEFAULT_CHUNK_SIZE * 1.15
    assert all(t.strip() and t == t.strip() for t in after)
    # Stored text is plain text: metadata is NOT mixed into chunk_text.
    assert not any(ORG in t or DOC in t for t in after)


def test_metadata_attached_to_every_node(sample_txt):
    chunks = llamaindex_chunks(sample_txt, "policy.txt", ORG, DOC)
    for c in chunks:
        assert c.metadata["org_id"] == ORG
        assert c.metadata["document_id"] == DOC
        assert c.metadata["filename"] == "policy.txt"


def test_docx_reader_path():
    d = docx.Document()
    for para in _sample_text().split("\n\n")[:4]:
        d.add_paragraph(para)
    buf = io.BytesIO()
    d.save(buf)

    chunks = llamaindex_chunks(buf.getvalue(), "policy.docx", ORG, DOC)
    assert chunks
    assert "Leave policy" in " ".join(c.text for c in chunks)


def test_row_format_compatible_with_existing_insert(sample_txt):
    """ingest_chunks output maps 1:1 onto the document_chunks columns the retriever expects."""
    chunks = ingest_chunks(sample_txt, "policy.txt", ORG, DOC)
    rows = [
        {
            "document_id": DOC,
            "org_id": ORG,
            "chunk_index": i,
            "chunk_text": c.text,
            "embedding": [0.0],
            "token_count": len(c.text) // 4,
        }
        for i, c in enumerate(chunks)
    ]
    assert set(rows[0]) == {
        "document_id", "org_id", "chunk_index", "chunk_text", "embedding", "token_count"
    }
    assert all(isinstance(r["chunk_text"], str) and r["chunk_text"] for r in rows)


def test_fallback_to_legacy_when_llamaindex_fails(sample_txt, monkeypatch):
    def boom(*a, **k):
        raise ImportError("llama-index missing")

    monkeypatch.setattr(settings, "ingestion_pipeline", "llamaindex")
    monkeypatch.setattr(ingestion, "llamaindex_chunks", boom)
    chunks = ingest_chunks(sample_txt, "policy.txt", ORG, DOC)
    assert [c.text for c in chunks] == chunk_text(_sample_text())  # exact legacy output


def test_legacy_mode_skips_llamaindex(sample_txt, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("must not be called")

    monkeypatch.setattr(settings, "ingestion_pipeline", "legacy")
    monkeypatch.setattr(ingestion, "llamaindex_chunks", boom)
    assert ingest_chunks(sample_txt, "policy.txt", ORG, DOC)
