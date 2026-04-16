"""Bot API key authentication for platform linking endpoints."""

import hmac
import logging
from functools import lru_cache

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from backend.util.settings import Settings

logger = logging.getLogger(__name__)


# APIKeyHeader lets FastAPI emit a proper X-Bot-API-Key security scheme in the
# OpenAPI spec. auto_error=False because dev-mode allows keyless requests when
# enable_auth is False — we handle the error path inline so the warning lands.
_bot_api_key_scheme = APIKeyHeader(name="X-Bot-API-Key", auto_error=False)


@lru_cache(maxsize=1)
def _auth_enabled() -> bool:
    """Cached — auth-enabled doesn't flip at runtime."""
    return Settings().config.enable_auth


async def get_bot_api_key(
    api_key: str | None = Security(_bot_api_key_scheme),
) -> str | None:
    """FastAPI dependency — validates the X-Bot-API-Key header.

    Use with ``Security(get_bot_api_key)`` on a route — any unauthorized
    request is rejected here, no per-endpoint follow-up call needed.
    """
    check_bot_api_key(api_key)
    return api_key


def check_bot_api_key(api_key: str | None) -> None:
    """Raise on invalid/missing bot API key; no-op in dev with auth disabled.

    Exposed separately so tests can exercise the validation logic directly
    without going through FastAPI's dependency machinery.
    """
    configured_key = Settings().secrets.platform_bot_api_key

    if not configured_key:
        if _auth_enabled():
            raise HTTPException(
                status_code=503,
                detail="Bot API key not configured.",
            )
        # Auth disabled (local dev) — allow without key, but warn so it's
        # never silent in staging or misconfigured production deployments.
        logger.warning(
            "PLATFORM_BOT_API_KEY is not set and auth is disabled — "
            "bot-facing platform linking endpoints are unauthenticated. "
            "Set it in your environment for any non-local deployment."
        )
        return

    if not api_key or not hmac.compare_digest(api_key, configured_key):
        raise HTTPException(status_code=401, detail="Invalid bot API key.")
