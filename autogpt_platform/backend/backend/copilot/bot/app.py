"""CoPilot Chat Bridge — AppService that runs the configured chat-platform
adapters (Discord, Telegram, Slack) and exposes outbound message RPC for
other services to push messages into chat platforms.
"""

import asyncio
import logging
from concurrent.futures import Future

from backend.platform_linking.models import Platform
from backend.util.service import AppService, AppServiceClient, endpoint_to_async, expose
from backend.util.settings import Settings

from .adapters.base import PlatformAdapter
from .adapters.discord import config as discord_config
from .adapters.discord.adapter import DiscordAdapter
from .handler import MessageHandler
from .platform_api import PlatformAPI

logger = logging.getLogger(__name__)

# Stay up for health-checks and runtime reconfiguration when no adapter is
# configured (e.g. deployed without a Discord token).
_NO_ADAPTER_SLEEP_SECONDS = 3600


class CoPilotChatBridge(AppService):
    """Bridges AutoPilot to external chat platforms via per-platform adapters."""

    @classmethod
    def get_port(cls) -> int:
        return Settings().config.copilot_chat_bridge_port

    def run_service(self) -> None:
        future = asyncio.run_coroutine_threadsafe(
            self._run_adapters(), self.shared_event_loop
        )
        future.add_done_callback(_log_adapters_exit)
        super().run_service()

    async def _run_adapters(self) -> None:
        api = PlatformAPI()
        adapters = _build_adapters(api)

        if not adapters:
            logger.info(
                "CoPilotChatBridge: no platform adapters configured — idling. "
                "Set AUTOPILOT_BOT_DISCORD_TOKEN (or another platform token) to "
                "enable an adapter."
            )
            try:
                while True:
                    await asyncio.sleep(_NO_ADAPTER_SLEEP_SECONDS)
            finally:
                await api.close()

        handler = MessageHandler(api)
        for adapter in adapters:
            adapter.on_message(handler.handle)

        try:
            await asyncio.gather(*(a.start() for a in adapters))
        finally:
            await asyncio.gather(*(a.stop() for a in adapters), return_exceptions=True)
            await api.close()

    @expose
    async def send_message_to_channel(
        self,
        platform: Platform,
        channel_id: str,
        content: str,
    ) -> bool:
        """Deliver a message to a channel on the given platform.

        Stub — scaffolding for the inbound-RPC pattern (backend → chat
        platform). Not yet wired to a concrete adapter. Callers must not use
        ``request_retry=True`` on the client until this is implemented, since
        ``ValueError`` crosses the RPC boundary as a client-side 4xx-ish error
        rather than a transient 5xx.
        """
        raise ValueError(f"send_message_to_channel not yet wired for {platform.value}")

    @expose
    async def send_dm(
        self,
        platform: Platform,
        platform_user_id: str,
        content: str,
    ) -> bool:
        """Deliver a DM to a user on the given platform.

        Stub — scaffolding for the inbound-RPC pattern. See
        :meth:`send_message_to_channel` for the retry caveat.
        """
        raise ValueError(f"send_dm not yet wired for {platform.value}")


class CoPilotChatBridgeClient(AppServiceClient):
    @classmethod
    def get_service_type(cls):
        return CoPilotChatBridge

    send_message_to_channel = endpoint_to_async(
        CoPilotChatBridge.send_message_to_channel
    )
    send_dm = endpoint_to_async(CoPilotChatBridge.send_dm)


def _log_adapters_exit(future: "Future[None]") -> None:
    """Surface exceptions from ``_run_adapters`` — the coroutine is launched
    via ``run_coroutine_threadsafe``, which swallows them into the returned
    future otherwise.
    """
    exc = future.exception()
    if exc is not None:
        logger.error("CoPilotChatBridge adapters crashed: %r", exc, exc_info=exc)


def _build_adapters(api: PlatformAPI) -> list[PlatformAdapter]:
    """Instantiate adapters based on which platform tokens are configured."""
    adapters: list[PlatformAdapter] = []
    if discord_config.get_bot_token():
        adapters.append(DiscordAdapter(api))
        logger.info("Discord adapter enabled")
    # Future:
    # if telegram_config.get_bot_token():
    #     adapters.append(TelegramAdapter(api))
    # if slack_config.get_bot_token():
    #     adapters.append(SlackAdapter(api))
    return adapters
