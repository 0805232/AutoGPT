"""Per-request idempotency lock for the /stream endpoint.

Blocks duplicate executor tasks from concurrent or retried POSTs (e.g. k8s
rolling-deploy retries, nginx upstream retries, rapid double-clicks).

The lock only needs to cover the brief window between the HTTP POST and the
executor acquiring the cluster-wide session lock (~1 s). The 5 s TTL is a
crash-safety fallback; the lock is always deleted explicitly on exit.
"""

import hashlib
import logging

from backend.data.redis_client import get_redis_async

logger = logging.getLogger(__name__)

_KEY_PREFIX = "chat:msg_dedup"
_TTL_SECONDS = 5


class DedupLock:
    def __init__(self, key: str, redis) -> None:
        self._key = key
        self._redis = redis

    async def release(self) -> None:
        try:
            await self._redis.delete(self._key)
        except Exception:
            pass


async def acquire_dedup_lock(
    session_id: str,
    message: str | None,
    file_ids: list[str] | None,
) -> DedupLock | None:
    """Return a DedupLock if this is a new request, or None if it is a duplicate."""
    if not message and not file_ids:
        return None

    sorted_ids = ":".join(sorted(file_ids or []))
    content_hash = hashlib.sha256(
        f"{session_id}:{message or ''}:{sorted_ids}".encode()
    ).hexdigest()[:16]
    key = f"{_KEY_PREFIX}:{session_id}:{content_hash}"

    redis = await get_redis_async()
    if not await redis.set(key, "1", ex=_TTL_SECONDS, nx=True):
        logger.warning(
            "[STREAM] Duplicate message blocked session=%s hash=%s",
            session_id,
            content_hash,
        )
        return None

    return DedupLock(key, redis)
