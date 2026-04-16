"""Discord-specific configuration."""

import os

BOT_TOKEN: str = os.getenv("AUTOPILOT_BOT_DISCORD_TOKEN", "")

# Discord message content limit (hard platform cap)
MAX_MESSAGE_LENGTH = 2000

# Flush the streaming buffer at 1900 — leaves 100-char headroom under the
# 2000 cap so the boundary-splitter has room to reach a natural break point.
CHUNK_FLUSH_AT = 1900
