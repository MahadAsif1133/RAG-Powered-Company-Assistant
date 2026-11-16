"""
Per-organization query-answer cache (Redis, optional).

Key layout (EVERY key starts with the org_id, so tenants can never collide):
    rag:{org_id}:docver                      -> integer "document version" for the org
    rag:{org_id}:v{docver}:q:{sha256(question)} -> JSON {org_id, answer, sources, was_confident}

Invalidation: whenever the org's documents change (ingestion finished/failed, delete) the
org's docver is incremented, so all older entries become unreachable immediately and
expire on their own via the TTL. Other orgs are untouched.

No Redis / any Redis error  ->  behaves as a cache miss. Never raises.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re

from app.core.config import settings
from app.services import redis_client

logger = logging.getLogger(__name__)


def normalize_question(question: str) -> str:
    """Lowercase + collapse whitespace so trivially different spellings share an entry."""
    return re.sub(r"\s+", " ", question.strip().lower())


def question_hash(question: str) -> str:
    return hashlib.sha256(normalize_question(question).encode("utf-8")).hexdigest()


def _version_key(org_id: str) -> str:
    return f"rag:{org_id}:docver"


def _answer_key(org_id: str, version: str, question: str) -> str:
    return f"rag:{org_id}:v{version}:q:{question_hash(question)}"


def _current_version(r, org_id: str) -> str:
    return r.get(_version_key(org_id)) or "0"


def get_cached_answer(org_id: str, question: str) -> dict | None:
    """Return {"answer", "sources", "was_confident"} or None."""
    r = redis_client.get_redis()
    if r is None:
        return None
    try:
        raw = r.get(_answer_key(org_id, _current_version(r, org_id), question))
        if not raw:
            return None
        data = json.loads(raw)
        if data.get("org_id") != org_id:  # defense in depth; should be impossible
            logger.error("Cache entry org mismatch - ignoring")
            return None
        return data
    except Exception as exc:
        logger.warning("Cache read failed (%s); treating as miss", type(exc).__name__)
        return None


def set_cached_answer(
    org_id: str, question: str, answer: str, sources: list[dict], was_confident: bool
) -> None:
    r = redis_client.get_redis()
    if r is None:
        return
    try:
        payload = json.dumps(
            {
                "org_id": org_id,
                "answer": answer,
                "sources": sources,
                "was_confident": was_confident,
            }
        )
        key = _answer_key(org_id, _current_version(r, org_id), question)
        r.set(key, payload, ex=settings.cache_ttl_seconds)
    except Exception as exc:
        logger.warning("Cache write failed (%s); continuing", type(exc).__name__)


def invalidate_org_cache(org_id: str) -> None:
    """Call when this org's documents change. Only affects this org."""
    r = redis_client.get_redis()
    if r is None:
        return
    try:
        r.incr(_version_key(org_id))
    except Exception as exc:
        logger.warning("Cache invalidation failed (%s)", type(exc).__name__)
