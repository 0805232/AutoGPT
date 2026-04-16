import json
import logging
from dataclasses import dataclass
from typing import AsyncGenerator, Callable, Optional

import aiohttp

from .config import AUTOGPT_API_URL, PLATFORM_BOT_API_KEY, SSE_IDLE_TIMEOUT

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=30)


class PlatformAPIError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        super().__init__(f"Platform API error {status}: {message}")


@dataclass
class ResolveResult:
    linked: bool


@dataclass
class LinkTokenResult:
    token: str
    link_url: str
    expires_at: str


class PlatformAPI:
    def __init__(
        self,
        base_url: str = AUTOGPT_API_URL,
        api_key: str = PLATFORM_BOT_API_KEY,
    ):
        self._base_url = base_url.rstrip("/")
        self._headers = {
            "Content-Type": "application/json",
            "X-Bot-API-Key": api_key,
        }
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers=self._headers, timeout=DEFAULT_TIMEOUT
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def _request(
        self, method: str, path: str, json: Optional[dict] = None
    ) -> dict:
        session = await self._get_session()
        url = f"{self._base_url}{path}"
        async with session.request(method, url, json=json) as resp:
            if resp.status >= 400:
                body = await resp.text()
                raise PlatformAPIError(resp.status, body)
            return await resp.json()

    async def resolve_server(
        self, platform: str, platform_server_id: str
    ) -> ResolveResult:
        data = await self._request(
            "POST",
            "/api/platform-linking/resolve",
            json={
                "platform": platform.upper(),
                "platform_server_id": platform_server_id,
            },
        )
        return ResolveResult(linked=data.get("linked", False))

    async def resolve_user(self, platform: str, platform_user_id: str) -> ResolveResult:
        data = await self._request(
            "POST",
            "/api/platform-linking/resolve-user",
            json={
                "platform": platform.upper(),
                "platform_user_id": platform_user_id,
            },
        )
        return ResolveResult(linked=data.get("linked", False))

    async def create_link_token(
        self,
        platform: str,
        platform_server_id: str,
        platform_user_id: str,
        platform_username: str,
        server_name: str,
        channel_id: str = "",
    ) -> LinkTokenResult:
        data = await self._request(
            "POST",
            "/api/platform-linking/tokens",
            json={
                "platform": platform.upper(),
                "platform_server_id": platform_server_id,
                "platform_user_id": platform_user_id,
                "platform_username": platform_username,
                "server_name": server_name,
                "channel_id": channel_id,
            },
        )
        return LinkTokenResult(
            token=data["token"],
            link_url=data["link_url"],
            expires_at=data["expires_at"],
        )

    async def create_user_link_token(
        self,
        platform: str,
        platform_user_id: str,
        platform_username: str,
    ) -> LinkTokenResult:
        data = await self._request(
            "POST",
            "/api/platform-linking/user-tokens",
            json={
                "platform": platform.upper(),
                "platform_user_id": platform_user_id,
                "platform_username": platform_username,
            },
        )
        return LinkTokenResult(
            token=data["token"],
            link_url=data["link_url"],
            expires_at=data["expires_at"],
        )

    async def stream_chat(
        self,
        platform: str,
        platform_user_id: str,
        message: str,
        session_id: Optional[str] = None,
        platform_server_id: Optional[str] = None,
        on_session_id: Optional[Callable[[str], None]] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream a chat response. If session_id is None, the backend creates one
        and returns it via the X-Session-Id response header — on_session_id() is
        called with that value so the caller can cache it for subsequent messages.
        """
        session = await self._get_session()
        url = f"{self._base_url}/api/platform-linking/chat/stream"
        body: dict = {
            "platform": platform.upper(),
            "platform_user_id": platform_user_id,
            "message": message,
        }
        if session_id:
            body["session_id"] = session_id
        if platform_server_id:
            body["platform_server_id"] = platform_server_id

        timeout = aiohttp.ClientTimeout(total=0, sock_read=SSE_IDLE_TIMEOUT)
        async with session.post(url, json=body, timeout=timeout) as resp:
            if resp.status >= 400:
                error_body = await resp.text()
                raise PlatformAPIError(resp.status, error_body)

            # Backend returns the (possibly new) session ID in this header
            returned_session_id = resp.headers.get("X-Session-Id")
            if returned_session_id and on_session_id:
                on_session_id(returned_session_id)

            async for raw_line in resp.content:
                line = raw_line.decode("utf-8", errors="replace").rstrip("\n\r")

                if not line or line.startswith(":"):
                    continue

                if not line.startswith("data: "):
                    continue

                payload = line[6:]
                if payload == "[DONE]":
                    return

                try:
                    event = json.loads(payload)
                except (json.JSONDecodeError, ValueError):
                    continue

                event_type = event.get("type", "")
                if event_type == "text-delta":
                    delta = event.get("delta", "")
                    if delta:
                        yield delta
                elif event_type == "error":
                    error_msg = event.get("content", "Unknown error")
                    logger.error(f"SSE error from backend: {error_msg}")
                    yield f"\n[Error: {error_msg}]"
                    return
