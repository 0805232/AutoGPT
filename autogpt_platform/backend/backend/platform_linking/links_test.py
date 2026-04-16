"""Unit tests for platform_linking link helpers."""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.util.exceptions import (
    LinkAlreadyExistsError,
    LinkFlowMismatchError,
    LinkTokenExpiredError,
    NotAuthorizedError,
    NotFoundError,
)

from .links import (
    confirm_server_link,
    confirm_user_link,
    create_server_link_token,
    create_user_link_token,
    delete_server_link,
    delete_user_link,
    get_link_token_info,
    get_link_token_status,
    resolve_server_link,
    resolve_user_link,
)
from .models import (
    CreateLinkTokenRequest,
    CreateUserLinkTokenRequest,
    LinkType,
    Platform,
)


@asynccontextmanager
async def _fake_transaction():
    # Avoids Prisma's tx binding asyncio primitives to the wrong loop in tests.
    yield MagicMock()


# ── Resolve ──────────────────────────────────────────────────────────


class TestResolve:
    @pytest.mark.asyncio
    async def test_server_linked(self):
        with patch(
            "backend.platform_linking.links.find_server_link",
            new=AsyncMock(return_value=MagicMock(userId="autogpt-user-123")),
        ):
            result = await resolve_server_link("DISCORD", "guild_123")
        assert result.linked is True

    @pytest.mark.asyncio
    async def test_server_unlinked(self):
        with patch(
            "backend.platform_linking.links.find_server_link",
            new=AsyncMock(return_value=None),
        ):
            result = await resolve_server_link("DISCORD", "guild_unknown")
        assert result.linked is False

    @pytest.mark.asyncio
    async def test_user_linked(self):
        with patch(
            "backend.platform_linking.links.find_user_link",
            new=AsyncMock(return_value=MagicMock(userId="autogpt-user-xyz")),
        ):
            result = await resolve_user_link("DISCORD", "user_456")
        assert result.linked is True

    @pytest.mark.asyncio
    async def test_user_unlinked(self):
        with patch(
            "backend.platform_linking.links.find_user_link",
            new=AsyncMock(return_value=None),
        ):
            result = await resolve_user_link("DISCORD", "user_unknown")
        assert result.linked is False


# ── Token creation ───────────────────────────────────────────────────


class TestCreateServerLinkToken:
    @pytest.mark.asyncio
    async def test_creates_token_for_unlinked_server(self):
        with (
            patch(
                "backend.platform_linking.links.find_server_link",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "backend.platform_linking.links.transaction",
                new=_fake_transaction,
            ),
            patch(
                "backend.platform_linking.links.PlatformLinkToken"
            ) as mock_token_model,
        ):
            mock_token_model.prisma.return_value.update_many = AsyncMock(return_value=0)
            mock_token_model.prisma.return_value.create = AsyncMock(
                return_value=MagicMock()
            )

            result = await create_server_link_token(
                CreateLinkTokenRequest(
                    platform=Platform.DISCORD,
                    platform_server_id="guild_123",
                    platform_user_id="user_456",
                    server_name="Test Server",
                ),
            )

        assert result.token
        assert "guild_123" not in result.token  # token is random
        assert result.token in result.link_url
        assert "?platform=DISCORD" in result.link_url

    @pytest.mark.asyncio
    async def test_rejects_when_already_linked(self):
        with patch(
            "backend.platform_linking.links.find_server_link",
            new=AsyncMock(return_value=MagicMock()),
        ):
            with pytest.raises(LinkAlreadyExistsError):
                await create_server_link_token(
                    CreateLinkTokenRequest(
                        platform=Platform.DISCORD,
                        platform_server_id="guild_already_linked",
                        platform_user_id="user_456",
                    ),
                )


class TestCreateUserLinkToken:
    @pytest.mark.asyncio
    async def test_creates_token_for_unlinked_user(self):
        with (
            patch(
                "backend.platform_linking.links.find_user_link",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "backend.platform_linking.links.transaction",
                new=_fake_transaction,
            ),
            patch(
                "backend.platform_linking.links.PlatformLinkToken"
            ) as mock_token_model,
        ):
            mock_token_model.prisma.return_value.update_many = AsyncMock(return_value=0)
            mock_token_model.prisma.return_value.create = AsyncMock(
                return_value=MagicMock()
            )

            result = await create_user_link_token(
                CreateUserLinkTokenRequest(
                    platform=Platform.DISCORD,
                    platform_user_id="user_456",
                    platform_username="Bently",
                ),
            )

        assert result.token
        assert result.token in result.link_url
        assert "?platform=DISCORD" in result.link_url

    @pytest.mark.asyncio
    async def test_rejects_when_already_linked(self):
        with patch(
            "backend.platform_linking.links.find_user_link",
            new=AsyncMock(return_value=MagicMock()),
        ):
            with pytest.raises(LinkAlreadyExistsError):
                await create_user_link_token(
                    CreateUserLinkTokenRequest(
                        platform=Platform.DISCORD,
                        platform_user_id="user_already_linked",
                    ),
                )


# ── Token status / info ───────────────────────────────────────────────


class TestGetLinkTokenStatus:
    @pytest.mark.asyncio
    async def test_not_found(self):
        with patch("backend.platform_linking.links.PlatformLinkToken") as mock_model:
            mock_model.prisma.return_value.find_unique = AsyncMock(return_value=None)
            with pytest.raises(NotFoundError):
                await get_link_token_status("abc123")

    @pytest.mark.asyncio
    async def test_pending(self):
        future = datetime.now(timezone.utc) + timedelta(minutes=10)
        fake_token = MagicMock(usedAt=None, expiresAt=future)
        with patch("backend.platform_linking.links.PlatformLinkToken") as mock_model:
            mock_model.prisma.return_value.find_unique = AsyncMock(
                return_value=fake_token
            )
            result = await get_link_token_status("abc123")
        assert result.status == "pending"

    @pytest.mark.asyncio
    async def test_expired_by_time(self):
        past = datetime.now(timezone.utc) - timedelta(minutes=10)
        fake_token = MagicMock(usedAt=None, expiresAt=past)
        with patch("backend.platform_linking.links.PlatformLinkToken") as mock_model:
            mock_model.prisma.return_value.find_unique = AsyncMock(
                return_value=fake_token
            )
            result = await get_link_token_status("abc123")
        assert result.status == "expired"

    @pytest.mark.asyncio
    async def test_used_with_user_link_reports_linked(self):
        fake_token = MagicMock(
            usedAt=datetime.now(timezone.utc),
            linkType=LinkType.USER.value,
            platform="DISCORD",
            platformUserId="user_456",
        )
        with (
            patch("backend.platform_linking.links.PlatformLinkToken") as mock_model,
            patch(
                "backend.platform_linking.links.find_user_link",
                new=AsyncMock(return_value=MagicMock()),
            ),
        ):
            mock_model.prisma.return_value.find_unique = AsyncMock(
                return_value=fake_token
            )
            result = await get_link_token_status("abc123")
        assert result.status == "linked"

    @pytest.mark.asyncio
    async def test_used_without_link_reports_expired(self):
        # Superseded token: usedAt set, but no backing link row.
        fake_token = MagicMock(
            usedAt=datetime.now(timezone.utc),
            linkType=LinkType.SERVER.value,
            platform="DISCORD",
            platformServerId="guild_123",
        )
        with (
            patch("backend.platform_linking.links.PlatformLinkToken") as mock_model,
            patch(
                "backend.platform_linking.links.find_server_link",
                new=AsyncMock(return_value=None),
            ),
        ):
            mock_model.prisma.return_value.find_unique = AsyncMock(
                return_value=fake_token
            )
            result = await get_link_token_status("abc123")
        assert result.status == "expired"


class TestGetLinkTokenInfo:
    @pytest.mark.asyncio
    async def test_not_found(self):
        with patch("backend.platform_linking.links.PlatformLinkToken") as mock_model:
            mock_model.prisma.return_value.find_unique = AsyncMock(return_value=None)
            with pytest.raises(NotFoundError):
                await get_link_token_info("abc123")

    @pytest.mark.asyncio
    async def test_used_returns_not_found(self):
        fake_token = MagicMock(usedAt=datetime.now(timezone.utc))
        with patch("backend.platform_linking.links.PlatformLinkToken") as mock_model:
            mock_model.prisma.return_value.find_unique = AsyncMock(
                return_value=fake_token
            )
            with pytest.raises(NotFoundError):
                await get_link_token_info("abc123")

    @pytest.mark.asyncio
    async def test_expired_raises_expired(self):
        past = datetime.now(timezone.utc) - timedelta(minutes=5)
        fake_token = MagicMock(usedAt=None, expiresAt=past)
        with patch("backend.platform_linking.links.PlatformLinkToken") as mock_model:
            mock_model.prisma.return_value.find_unique = AsyncMock(
                return_value=fake_token
            )
            with pytest.raises(LinkTokenExpiredError):
                await get_link_token_info("abc123")

    @pytest.mark.asyncio
    async def test_success_returns_display_info(self):
        future = datetime.now(timezone.utc) + timedelta(minutes=10)
        fake_token = MagicMock(
            usedAt=None,
            expiresAt=future,
            platform="DISCORD",
            linkType=LinkType.SERVER.value,
            serverName="My Server",
        )
        with patch("backend.platform_linking.links.PlatformLinkToken") as mock_model:
            mock_model.prisma.return_value.find_unique = AsyncMock(
                return_value=fake_token
            )
            result = await get_link_token_info("abc123")
        assert result.platform == "DISCORD"
        assert result.link_type == LinkType.SERVER
        assert result.server_name == "My Server"


# ── Confirmation ─────────────────────────────────────────────────────


class TestConfirmServerLink:
    @pytest.mark.asyncio
    async def test_not_found(self):
        with patch("backend.platform_linking.links.PlatformLinkToken") as mock_model:
            mock_model.prisma.return_value.find_unique = AsyncMock(return_value=None)
            with pytest.raises(NotFoundError):
                await confirm_server_link("abc", "user-1")

    @pytest.mark.asyncio
    async def test_wrong_link_type_rejected(self):
        fake_token = MagicMock(linkType=LinkType.USER.value)
        with patch("backend.platform_linking.links.PlatformLinkToken") as mock_model:
            mock_model.prisma.return_value.find_unique = AsyncMock(
                return_value=fake_token
            )
            with pytest.raises(LinkFlowMismatchError):
                await confirm_server_link("abc", "user-1")

    @pytest.mark.asyncio
    async def test_already_used(self):
        fake_token = MagicMock(
            linkType=LinkType.SERVER.value, usedAt=datetime.now(timezone.utc)
        )
        with patch("backend.platform_linking.links.PlatformLinkToken") as mock_model:
            mock_model.prisma.return_value.find_unique = AsyncMock(
                return_value=fake_token
            )
            with pytest.raises(LinkTokenExpiredError):
                await confirm_server_link("abc", "user-1")

    @pytest.mark.asyncio
    async def test_expired_by_time(self):
        fake_token = MagicMock(
            linkType=LinkType.SERVER.value,
            usedAt=None,
            expiresAt=datetime.now(timezone.utc) - timedelta(minutes=5),
        )
        with patch("backend.platform_linking.links.PlatformLinkToken") as mock_model:
            mock_model.prisma.return_value.find_unique = AsyncMock(
                return_value=fake_token
            )
            with pytest.raises(LinkTokenExpiredError):
                await confirm_server_link("abc", "user-1")

    @pytest.mark.asyncio
    async def test_already_linked_to_same_user(self):
        fake_token = MagicMock(
            linkType=LinkType.SERVER.value,
            usedAt=None,
            expiresAt=datetime.now(timezone.utc) + timedelta(minutes=10),
            platform="DISCORD",
            platformServerId="guild_123",
        )
        existing = MagicMock(userId="user-1")
        with (
            patch("backend.platform_linking.links.PlatformLinkToken") as mock_model,
            patch(
                "backend.platform_linking.links.find_server_link",
                new=AsyncMock(return_value=existing),
            ),
        ):
            mock_model.prisma.return_value.find_unique = AsyncMock(
                return_value=fake_token
            )
            with pytest.raises(LinkAlreadyExistsError) as exc_info:
                await confirm_server_link("abc", "user-1")
        assert "your account" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_already_linked_to_other_user(self):
        fake_token = MagicMock(
            linkType=LinkType.SERVER.value,
            usedAt=None,
            expiresAt=datetime.now(timezone.utc) + timedelta(minutes=10),
            platform="DISCORD",
            platformServerId="guild_123",
        )
        existing = MagicMock(userId="other-user")
        with (
            patch("backend.platform_linking.links.PlatformLinkToken") as mock_model,
            patch(
                "backend.platform_linking.links.find_server_link",
                new=AsyncMock(return_value=existing),
            ),
        ):
            mock_model.prisma.return_value.find_unique = AsyncMock(
                return_value=fake_token
            )
            with pytest.raises(LinkAlreadyExistsError) as exc_info:
                await confirm_server_link("abc", "user-1")
        assert "another" in str(exc_info.value)


class TestConfirmUserLink:
    @pytest.mark.asyncio
    async def test_not_found(self):
        with patch("backend.platform_linking.links.PlatformLinkToken") as mock_model:
            mock_model.prisma.return_value.find_unique = AsyncMock(return_value=None)
            with pytest.raises(NotFoundError):
                await confirm_user_link("abc", "user-1")

    @pytest.mark.asyncio
    async def test_wrong_link_type_rejected(self):
        fake_token = MagicMock(linkType=LinkType.SERVER.value)
        with patch("backend.platform_linking.links.PlatformLinkToken") as mock_model:
            mock_model.prisma.return_value.find_unique = AsyncMock(
                return_value=fake_token
            )
            with pytest.raises(LinkFlowMismatchError):
                await confirm_user_link("abc", "user-1")

    @pytest.mark.asyncio
    async def test_expired_by_time(self):
        fake_token = MagicMock(
            linkType=LinkType.USER.value,
            usedAt=None,
            expiresAt=datetime.now(timezone.utc) - timedelta(minutes=5),
        )
        with patch("backend.platform_linking.links.PlatformLinkToken") as mock_model:
            mock_model.prisma.return_value.find_unique = AsyncMock(
                return_value=fake_token
            )
            with pytest.raises(LinkTokenExpiredError):
                await confirm_user_link("abc", "user-1")

    @pytest.mark.asyncio
    async def test_already_linked_to_other_user(self):
        fake_token = MagicMock(
            linkType=LinkType.USER.value,
            usedAt=None,
            expiresAt=datetime.now(timezone.utc) + timedelta(minutes=10),
            platform="DISCORD",
            platformUserId="user_456",
        )
        existing = MagicMock(userId="other-user")
        with (
            patch("backend.platform_linking.links.PlatformLinkToken") as mock_model,
            patch(
                "backend.platform_linking.links.find_user_link",
                new=AsyncMock(return_value=existing),
            ),
        ):
            mock_model.prisma.return_value.find_unique = AsyncMock(
                return_value=fake_token
            )
            with pytest.raises(LinkAlreadyExistsError):
                await confirm_user_link("abc", "user-1")


# ── Delete (user-facing, authz checks) ───────────────────────────────


class TestDeleteLinks:
    @pytest.mark.asyncio
    async def test_delete_server_link_not_found(self):
        with patch("backend.platform_linking.links.PlatformLink") as mock_model:
            mock_model.prisma.return_value.find_unique = AsyncMock(return_value=None)
            with pytest.raises(NotFoundError):
                await delete_server_link("link-1", "user-1")

    @pytest.mark.asyncio
    async def test_delete_server_link_not_owned(self):
        link = MagicMock(userId="owner-A", platform="DISCORD", platformServerId="g1")
        with patch("backend.platform_linking.links.PlatformLink") as mock_model:
            mock_model.prisma.return_value.find_unique = AsyncMock(return_value=link)
            with pytest.raises(NotAuthorizedError):
                await delete_server_link("link-1", "user-B")

    @pytest.mark.asyncio
    async def test_delete_user_link_not_found(self):
        with patch("backend.platform_linking.links.PlatformUserLink") as mock_model:
            mock_model.prisma.return_value.find_unique = AsyncMock(return_value=None)
            with pytest.raises(NotFoundError):
                await delete_user_link("link-1", "user-1")

    @pytest.mark.asyncio
    async def test_delete_user_link_not_owned(self):
        link = MagicMock(userId="owner-A", platform="DISCORD")
        with patch("backend.platform_linking.links.PlatformUserLink") as mock_model:
            mock_model.prisma.return_value.find_unique = AsyncMock(return_value=link)
            with pytest.raises(NotAuthorizedError):
                await delete_user_link("link-1", "user-B")
