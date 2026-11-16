"""Unit tests for the LLM provider layer. The Groq client is mocked: no network, no keys."""
from __future__ import annotations

from unittest.mock import MagicMock

import groq
import httpx
import pytest

from app.core.config import settings
from app.services import llm
from app.services.retriever import RetrievedChunk


def _chunk(text: str = "Employees get 20 days of leave.", name: str = "HR Policy.pdf") -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id="c1", chunk_text=text, similarity=0.9, document_id="d1",
        chunk_index=0, filename="abc_HR_Policy.pdf", original_name=name,
    )


def _completion(text: str) -> MagicMock:
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = text
    return resp


def _rate_limit_error() -> groq.RateLimitError:
    request = httpx.Request("POST", "https://api.groq.com/x")
    response = httpx.Response(429, request=request, headers={"retry-after": "2"})
    return groq.RateLimitError("rate limited", response=response, body=None)


@pytest.fixture(autouse=True)
def groq_settings(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "groq")
    monkeypatch.setattr(settings, "groq_api_key", "test-key")
    monkeypatch.setattr(settings, "groq_model", "test-model")
    monkeypatch.setattr(settings, "llm_max_retries", 2)
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)


@pytest.fixture
def groq_client(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr(groq, "Groq", MagicMock(return_value=client))
    return client


def test_groq_message_format_and_answer(groq_client):
    groq_client.chat.completions.create.return_value = _completion("20 days.\nSource: [HR Policy.pdf]")
    answer, confident = llm.generate_answer("How many leave days?", [_chunk()])

    assert confident is True
    assert answer.startswith("20 days.")
    kwargs = groq_client.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == "test-model"  # comes from settings, not code
    assert kwargs["messages"][0] == {"role": "system", "content": llm.SYSTEM_PROMPT}
    assert kwargs["messages"][1]["role"] == "user"
    assert "How many leave days?" in kwargs["messages"][1]["content"]
    assert "HR Policy.pdf" in kwargs["messages"][1]["content"]
    assert "contact HR/IT" in llm.SYSTEM_PROMPT


def test_punt_is_not_confident(groq_client):
    groq_client.chat.completions.create.return_value = _completion(
        "I don't have information about that in the uploaded documents — please contact HR/IT directly."
    )
    _, confident = llm.generate_answer("What is the CEO's salary?", [_chunk()])
    assert confident is False


def test_no_chunks_skips_llm(groq_client):
    answer, confident = llm.generate_answer("anything", [])
    assert confident is False
    assert "contact HR/IT" in answer
    groq_client.chat.completions.create.assert_not_called()


def test_rate_limit_then_success(groq_client):
    groq_client.chat.completions.create.side_effect = [_rate_limit_error(), _completion("ok")]
    answer, _ = llm.generate_answer("q", [_chunk()])
    assert answer == "ok"
    assert groq_client.chat.completions.create.call_count == 2


def test_rate_limit_exhausted_gives_clear_error(groq_client):
    groq_client.chat.completions.create.side_effect = _rate_limit_error()
    with pytest.raises(llm.LLMRateLimitError) as exc:
        llm.generate_answer("q", [_chunk()])
    assert "too many requests" in str(exc.value)
    assert groq_client.chat.completions.create.call_count == 3  # 1 try + 2 retries


def test_missing_model_is_clear_error(groq_client, monkeypatch):
    monkeypatch.setattr(settings, "groq_model", "")
    with pytest.raises(RuntimeError, match="GROQ_MODEL"):
        llm.generate_answer("q", [_chunk()])


def test_unknown_provider(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "nope")
    with pytest.raises(RuntimeError, match="LLM_PROVIDER"):
        llm.generate_answer("q", [_chunk()])
