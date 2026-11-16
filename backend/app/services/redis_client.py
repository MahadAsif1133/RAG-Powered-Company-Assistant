"""
Optional Redis connection. If REDIS_URL is unset (or Redis is unreachable) callers get
`None` and must behave as if Redis does not exist. This module never raises.
"""
from __future__ import annotations

import logging
import time

from app.core.config import settings

logger = logging.getLogger(__name__)

_client = None
_retry_after = 0.0  # monotonic time before which we don't try to (re)connect
_RETRY_SECONDS = 30.0


def redis_enabled() -> bool:
    return bool(settings.redis_url)


def get_redis():
    """Return a redis client, or None when Redis is not configured / currently unreachable."""
    global _client, _retry_after
    if not settings.redis_url:
        return None
    if _client is not None:
        return _client
    if time.monotonic() < _retry_after:
        return None
    try:
        import redis

        client = redis.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        client.ping()
        _client = client
        logger.info("Redis connected (caching + rate limiting enabled)")
        return _client
    except Exception as exc:
        _retry_after = time.monotonic() + _RETRY_SECONDS
        logger.warning("Redis unavailable (%s); running without it", type(exc).__name__)
        return None


def reset_redis_client() -> None:
    """Drop the cached client (used on errors and in tests)."""
    global _client, _retry_after
    _client = None
    _retry_after = 0.0
