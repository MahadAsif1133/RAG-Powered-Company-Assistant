"""Unit tests for Qwen (Hugging Face InferenceClient) embeddings and dimension normalization."""
from __future__ import annotations

import math
from unittest.mock import MagicMock

import huggingface_hub

from app.core.config import settings
from app.services import embedder


def test_qwen_embedding_uses_inference_client_and_slices_to_target_dim(monkeypatch):
    monkeypatch.setattr(settings, "hf_token", "hf_test_token")
    monkeypatch.setattr(settings, "hf_embedding_provider", "deepinfra")
    monkeypatch.setattr(settings, "hf_embedding_model", "Qwen/Qwen3-Embedding-8B")
    monkeypatch.setattr(settings, "embedding_dimension", 1024)

    fake_client = MagicMock()
    # Simulate DeepInfra returning a full 4096-d vector for a single query
    fake_client.feature_extraction.return_value = [1.0] * 4096
    mock_cls = MagicMock(return_value=fake_client)
    monkeypatch.setattr(huggingface_hub, "InferenceClient", mock_cls)

    vec = embedder.embed_query("Today is a sunny day and I will get some ice cream.")
    mock_cls.assert_called_once_with(provider="deepinfra", api_key="hf_test_token")
    assert len(vec) == 1024
    # L2 normalized
    assert math.isclose(math.sqrt(sum(x * x for x in vec)), 1.0, rel_tol=1e-5)


def test_qwen_batch_embed_texts(monkeypatch):
    monkeypatch.setattr(settings, "hf_token", "hf_test_token")
    monkeypatch.setattr(settings, "embedding_dimension", 1024)

    fake_client = MagicMock()
    fake_client.feature_extraction.return_value = [[2.0] * 1024, [3.0] * 1024]
    monkeypatch.setattr(huggingface_hub, "InferenceClient", MagicMock(return_value=fake_client))

    vecs = embedder.embed_texts(["first chunk", "second chunk"])
    assert len(vecs) == 2
    assert all(len(v) == 1024 for v in vecs)
