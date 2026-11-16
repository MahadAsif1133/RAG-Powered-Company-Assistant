"""
Per-organization rate limiting backed by Redis (fixed window), optional.

Uses the existing QUERY_RATE_LIMIT setting ("10/minute", "100/hour", ...).
Without REDIS_URL (or if Redis is down) this returns "allowed"; the existing in-memory
per-IP slowapi limiter keeps working unchanged in the route either way.
"""
from __future__ import annotations

import logging
import re
import time

from app.core.config import settings
from app.services import redis_client

logger = logging.getLogger(__name__)

_UNITS = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}


def parse_rate_limit(spec: str) -> tuple[int, int]:
    """'10/minute' -> (10, 60). Falls back to 10/minute on a malformed value."""
    m = re.fullmatch(r"\s*(\d+)\s*(?:/|per)\s*(\d*)\s*(second|minute|hour|day)s?\s*", spec or "")
    if not m:
        logger.warning("Unparseable QUERY_RATE_LIMIT '%s'; using 10/minute", spec)
        return 10, 60
    return int(m.group(1)), int(m.group(2) or 1) * _UNITS[m.group(3)]


def check_org_rate_limit(org_id: str) -> tuple[bool, int]:
    """
    Count one request for this org. Returns (allowed, retry_after_seconds).
    Key is scoped by org_id, so each organization has its own budget.
    """
    r = redis_client.get_redis()
    if r is None:
        return True, 0
    limit, window = parse_rate_limit(settings.query_rate_limit)
    bucket = int(time.time()) // window
    key = f"rl:{org_id}:{window}:{bucket}"
    try:
        count = r.incr(key)
        if count == 1:
            r.expire(key, window + 1)
        if count > limit:
            return False, window - (int(time.time()) % window)
        return True, 0
    except Exception as exc:
        logger.warning("Redis rate limit check failed (%s); allowing request", type(exc).__name__)
        return True, 0
