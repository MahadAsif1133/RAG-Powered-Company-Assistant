"""Redis cache + per-org rate limit tests, using an in-memory fake Redis (no server needed)."""
from __future__ import annotations

import pytest

from app.core.config import settings
from app.services import cache, ratelimit, redis_client

ORG_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
ORG_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


class FakeRedis:
    def __init__(self):
        self.data: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    def get(self, k):
        return self.data.get(k)

    def set(self, k, v, ex=None):
        self.data[k] = v
        if ex:
            self.ttls[k] = ex

    def incr(self, k):
        self.data[k] = str(int(self.data.get(k, "0")) + 1)
        return int(self.data[k])

    def expire(self, k, s):
        self.ttls[k] = s


class BrokenRedis:
    def __getattr__(self, name):
        def fail(*a, **k):
            raise ConnectionError("down")

        return fail


@pytest.fixture
def fake(monkeypatch):
    r = FakeRedis()
    monkeypatch.setattr(redis_client, "get_redis", lambda: r)
    monkeypatch.setattr(settings, "cache_ttl_seconds", 123)
    return r


def test_cache_roundtrip_and_normalization(fake):
    cache.set_cached_answer(ORG_A, "What is  the Leave policy?", "20 days", [{"document_id": "d"}], True)
    hit = cache.get_cached_answer(ORG_A, "  what is the leave POLICY? ")
    assert hit["answer"] == "20 days" and hit["was_confident"] is True
    assert cache.get_cached_answer(ORG_A, "something else") is None


def test_ttl_is_set(fake):
    cache.set_cached_answer(ORG_A, "q", "a", [], True)
    assert list(fake.ttls.values()) == [123]


def test_two_orgs_never_share_cache_entries(fake):
    cache.set_cached_answer(ORG_A, "What is the leave policy?", "ORG A SECRET", [], True)

    # Same question, other org: miss
    assert cache.get_cached_answer(ORG_B, "What is the leave policy?") is None

    cache.set_cached_answer(ORG_B, "What is the leave policy?", "org b answer", [], True)
    assert cache.get_cached_answer(ORG_A, "What is the leave policy?")["answer"] == "ORG A SECRET"
    assert cache.get_cached_answer(ORG_B, "What is the leave policy?")["answer"] == "org b answer"

    # Every key is namespaced by its own org_id and none leaks the other org's id.
    for key in fake.data:
        assert key.startswith(f"rag:{ORG_A}:") or key.startswith(f"rag:{ORG_B}:")
    for key, value in fake.data.items():
        other = ORG_B if ORG_A in key else ORG_A
        assert other not in key and other not in value


def test_invalidation_affects_only_that_org(fake):
    cache.set_cached_answer(ORG_A, "q", "a1", [], True)
    cache.set_cached_answer(ORG_B, "q", "b1", [], True)
    cache.invalidate_org_cache(ORG_A)
    assert cache.get_cached_answer(ORG_A, "q") is None
    assert cache.get_cached_answer(ORG_B, "q")["answer"] == "b1"
    # New answers after invalidation are cached under the new version
    cache.set_cached_answer(ORG_A, "q", "a2", [], True)
    assert cache.get_cached_answer(ORG_A, "q")["answer"] == "a2"


def test_org_mismatch_payload_is_rejected(fake):
    cache.set_cached_answer(ORG_A, "q", "a", [], True)
    key = next(k for k in fake.data if ":q:" in k)
    fake.data[key] = fake.data[key].replace(ORG_A, ORG_B)
    assert cache.get_cached_answer(ORG_A, "q") is None


def test_no_redis_url_means_no_cache_and_no_limit(monkeypatch):
    monkeypatch.setattr(settings, "redis_url", "")
    redis_client.reset_redis_client()
    assert redis_client.get_redis() is None
    cache.set_cached_answer(ORG_A, "q", "a", [], True)  # no error
    assert cache.get_cached_answer(ORG_A, "q") is None
    cache.invalidate_org_cache(ORG_A)  # no error
    assert ratelimit.check_org_rate_limit(ORG_A) == (True, 0)


def test_redis_errors_fail_safe(monkeypatch):
    monkeypatch.setattr(redis_client, "get_redis", lambda: BrokenRedis())
    assert cache.get_cached_answer(ORG_A, "q") is None
    cache.set_cached_answer(ORG_A, "q", "a", [], True)
    cache.invalidate_org_cache(ORG_A)
    assert ratelimit.check_org_rate_limit(ORG_A) == (True, 0)


def test_unreachable_redis_url_does_not_raise(monkeypatch):
    monkeypatch.setattr(settings, "redis_url", "redis://127.0.0.1:1/0")
    redis_client.reset_redis_client()
    assert redis_client.get_redis() is None
    redis_client.reset_redis_client()


def test_parse_rate_limit():
    assert ratelimit.parse_rate_limit("10/minute") == (10, 60)
    assert ratelimit.parse_rate_limit("100/hour") == (100, 3600)
    assert ratelimit.parse_rate_limit("5/2minutes") == (5, 120)
    assert ratelimit.parse_rate_limit("garbage") == (10, 60)


def test_rate_limit_is_per_org(fake, monkeypatch):
    monkeypatch.setattr(settings, "query_rate_limit", "3/minute")
    results_a = [ratelimit.check_org_rate_limit(ORG_A)[0] for _ in range(5)]
    assert results_a == [True, True, True, False, False]
    # Org B is unaffected by org A exhausting its budget
    assert ratelimit.check_org_rate_limit(ORG_B)[0] is True
    allowed, retry = ratelimit.check_org_rate_limit(ORG_A)
    assert allowed is False and 1 <= retry <= 60
