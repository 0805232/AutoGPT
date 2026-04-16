"""CoPilot Bot process entry point.

Constructs the enabled platform adapters (Discord, Telegram, Slack) based on
which env vars are set, wires them to the shared MessageHandler, and runs
them all concurrently.
"""

import asyncio
import logging

from backend.util.process import AppProcess

from .adapters.base import PlatformAdapter
from .adapters.discord import config as discord_config
from .adapters.discord.adapter import DiscordAdapter
from .config import validate_shared_config
from .handler import MessageHandler
from .platform_api import PlatformAPI

logger = logging.getLogger(__name__)


class CoPilotBot(AppProcess):
    """Runs chat platform adapters and routes messages to AutoPilot."""

    @property
    def service_name(self) -> str:
        return "CoPilotBot"

    def run(self) -> None:
        validate_shared_config()
        asyncio.run(self._run_async())

    async def _run_async(self) -> None:
        api = PlatformAPI()
        adapters = _build_adapters(api)

        if not adapters:
            raise RuntimeError(
                "No platform adapters configured. Set AUTOPILOT_BOT_DISCORD_TOKEN "
                "(or another platform token) to enable at least one adapter."
            )

        handler = MessageHandler(api)
        for adapter in adapters:
            adapter.on_message(handler.handle)

        try:
            await asyncio.gather(*(a.start() for a in adapters))
        finally:
            await asyncio.gather(
                *(a.stop() for a in adapters), return_exceptions=True
            )
            await api.close()


def _build_adapters(api: PlatformAPI) -> list[PlatformAdapter]:
    """Instantiate adapters based on which platform tokens are configured."""
    adapters: list[PlatformAdapter] = []
    if discord_config.BOT_TOKEN:
        adapters.append(DiscordAdapter(api))
        logger.info("Discord adapter enabled")
    # Future:
    # if telegram_config.BOT_TOKEN:
    #     adapters.append(TelegramAdapter(api))
    # if slack_config.BOT_TOKEN:
    #     adapters.append(SlackAdapter(api))
    return adapters
