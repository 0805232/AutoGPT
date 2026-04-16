"""Shared configuration — platform-agnostic only.

Platform-specific config (tokens, limits) lives in adapters/<platform>/config.py.
"""

import logging
import os

logger = logging.getLogger(__name__)

PLATFORM_BOT_API_KEY: str = os.getenv("PLATFORM_BOT_API_KEY", "")
AUTOGPT_API_URL: str = os.getenv("AUTOGPT_API_URL", "http://localhost:8006")
AUTOGPT_FRONTEND_URL: str = os.getenv(
    "AUTOGPT_FRONTEND_URL", "https://platform.agpt.co"
)

# Max seconds between SSE events from the backend before we consider the
# connection dead. Resets on every chunk or keepalive.
SSE_IDLE_TIMEOUT = 90

# Cache TTL for AutoPilot session IDs (per channel/thread)
SESSION_TTL = 86400  # 24 hours


def validate_shared_config() -> None:
    """Validate platform-agnostic config. Each adapter validates its own."""
    if not PLATFORM_BOT_API_KEY:
        env = os.getenv("APP_ENV", "local")
        if env in ("prod", "production"):
            raise RuntimeError("PLATFORM_BOT_API_KEY is required in production")
        logger.warning("PLATFORM_BOT_API_KEY is not set — bot API calls will fail")
