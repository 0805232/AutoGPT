"""
Platform Bot Linking API routes.

Two independent linking flows:

  * SERVER links (PlatformLink) — claimed via `/tokens` flow. When anyone in
    the server messages the bot, the response is billed to the server owner.
  * USER links (PlatformUserLink) — claimed via `/user-tokens` flow. DMs
    between the bot and that individual are billed to their own account.

The two are fully independent. A user who owns a linked server must still
link their DMs separately.
"""

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated

from autogpt_libs import auth
from fastapi import APIRouter, HTTPException, Path, Security
from prisma.models import PlatformLink, PlatformLinkToken, PlatformUserLink

from backend.data.db import transaction
from backend.util.settings import Settings

from . import find_server_link, find_user_link
from .auth import get_bot_api_key
from .models import (
    ConfirmLinkResponse,
    ConfirmUserLinkResponse,
    CreateLinkTokenRequest,
    CreateUserLinkTokenRequest,
    DeleteLinkResponse,
    LinkTokenInfoResponse,
    LinkTokenResponse,
    LinkTokenStatusResponse,
    LinkType,
    PlatformLinkInfo,
    PlatformUserLinkInfo,
    ResolveResponse,
    ResolveServerRequest,
    ResolveUserRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter()

LINK_TOKEN_EXPIRY_MINUTES = 30

TokenPath = Annotated[
    str,
    Path(max_length=64, pattern=r"^[A-Za-z0-9_-]+$"),
]


def _link_base_url() -> str:
    return Settings().config.platform_link_base_url


# ── Bot-facing endpoints (API key auth) ───────────────────────────────


@router.post(
    "/tokens",
    response_model=LinkTokenResponse,
    dependencies=[Security(get_bot_api_key)],
    summary="Create a SERVER link token for an unlinked server",
)
async def create_link_token(
    request: CreateLinkTokenRequest,
) -> LinkTokenResponse:
    """Bot creates a token to claim a server. First user to confirm becomes owner."""

    platform = request.platform.value

    existing = await find_server_link(platform, request.platform_server_id)
    if existing:
        raise HTTPException(
            status_code=409,
            detail="This server is already linked to an AutoGPT account.",
        )

    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=LINK_TOKEN_EXPIRY_MINUTES
    )

    # Atomically invalidate pending tokens and create new one to prevent TOCTOU races
    async with transaction() as tx:
        await PlatformLinkToken.prisma(tx).update_many(
            where={
                "platform": platform,
                "linkType": LinkType.SERVER.value,
                "platformServerId": request.platform_server_id,
                "usedAt": None,
            },
            data={"usedAt": datetime.now(timezone.utc)},
        )

        await PlatformLinkToken.prisma(tx).create(
            data={
                "token": token,
                "platform": platform,
                "linkType": LinkType.SERVER.value,
                "platformServerId": request.platform_server_id,
                "platformUserId": request.platform_user_id,
                "platformUsername": request.platform_username,
                "serverName": request.server_name,
                "channelId": request.channel_id,
                "expiresAt": expires_at,
            }
        )

    logger.info(
        "Created SERVER link token for %s server %s (expires %s)",
        platform,
        request.platform_server_id,
        expires_at.isoformat(),
    )

    return LinkTokenResponse(
        token=token,
        expires_at=expires_at,
        link_url=f"{_link_base_url()}/{token}?platform={platform}",
    )


@router.post(
    "/user-tokens",
    response_model=LinkTokenResponse,
    dependencies=[Security(get_bot_api_key)],
    summary="Create a USER link token for an unlinked DM user",
)
async def create_user_link_token(
    request: CreateUserLinkTokenRequest,
) -> LinkTokenResponse:
    """Bot creates a token for an individual to link their DMs with the bot."""

    platform = request.platform.value

    existing = await find_user_link(platform, request.platform_user_id)
    if existing:
        raise HTTPException(
            status_code=409,
            detail="Your DMs with the bot are already linked to an AutoGPT account.",
        )

    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=LINK_TOKEN_EXPIRY_MINUTES
    )

    # Atomically invalidate pending tokens and create new one to prevent TOCTOU races
    async with transaction() as tx:
        await PlatformLinkToken.prisma(tx).update_many(
            where={
                "platform": platform,
                "linkType": LinkType.USER.value,
                "platformUserId": request.platform_user_id,
                "usedAt": None,
            },
            data={"usedAt": datetime.now(timezone.utc)},
        )

        await PlatformLinkToken.prisma(tx).create(
            data={
                "token": token,
                "platform": platform,
                "linkType": LinkType.USER.value,
                "platformUserId": request.platform_user_id,
                "platformUsername": request.platform_username,
                "expiresAt": expires_at,
            }
        )

    logger.info(
        "Created USER link token for %s (expires %s)",
        platform,
        expires_at.isoformat(),
    )

    return LinkTokenResponse(
        token=token,
        expires_at=expires_at,
        link_url=f"{_link_base_url()}/{token}?platform={platform}",
    )


@router.get(
    "/tokens/{token}/status",
    response_model=LinkTokenStatusResponse,
    dependencies=[Security(get_bot_api_key)],
    summary="Check if a link token has been consumed",
)
async def get_link_token_status(
    token: TokenPath,
) -> LinkTokenStatusResponse:
    """Bot polls to check if the user has completed linking."""

    link_token = await PlatformLinkToken.prisma().find_unique(where={"token": token})

    if not link_token:
        raise HTTPException(status_code=404, detail="Token not found.")

    if link_token.usedAt is not None:
        # Only report "linked" if the corresponding link actually exists — a
        # superseded token (invalidated by create_*_token) has usedAt set
        # without a link row.
        if link_token.linkType == LinkType.USER.value:
            actual = await find_user_link(
                link_token.platform, link_token.platformUserId
            )
        else:
            actual = (
                await find_server_link(link_token.platform, link_token.platformServerId)
                if link_token.platformServerId
                else None
            )
        return LinkTokenStatusResponse(status="linked" if actual else "expired")

    if link_token.expiresAt.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        return LinkTokenStatusResponse(status="expired")

    return LinkTokenStatusResponse(status="pending")


@router.get(
    "/tokens/{token}/info",
    response_model=LinkTokenInfoResponse,
    dependencies=[Security(auth.requires_user)],
    summary="Get display info for a link token",
)
async def get_link_token_info(token: TokenPath) -> LinkTokenInfoResponse:
    """Display info for the frontend link page (platform, link type, server
    name). JWT-authed so only logged-in users can probe token state."""
    link_token = await PlatformLinkToken.prisma().find_unique(where={"token": token})

    if not link_token or link_token.usedAt is not None:
        raise HTTPException(status_code=404, detail="Token not found.")

    if link_token.expiresAt.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Token expired.")

    return LinkTokenInfoResponse(
        platform=link_token.platform,
        link_type=LinkType(link_token.linkType),
        server_name=link_token.serverName,
    )


@router.post(
    "/resolve",
    response_model=ResolveResponse,
    dependencies=[Security(get_bot_api_key)],
    summary="Check whether a platform server is linked",
)
async def resolve_platform_server(
    request: ResolveServerRequest,
) -> ResolveResponse:
    """Called by the bot for every message in a server/group channel."""

    link = await find_server_link(request.platform.value, request.platform_server_id)
    return ResolveResponse(linked=link is not None)


@router.post(
    "/resolve-user",
    response_model=ResolveResponse,
    dependencies=[Security(get_bot_api_key)],
    summary="Check whether an individual's DMs are linked",
)
async def resolve_platform_user(
    request: ResolveUserRequest,
) -> ResolveResponse:
    """Called by the bot for every DM with an individual."""

    link = await find_user_link(request.platform.value, request.platform_user_id)
    return ResolveResponse(linked=link is not None)


# ── User-facing endpoints (JWT auth) ──────────────────────────────────


@router.post(
    "/tokens/{token}/confirm",
    response_model=ConfirmLinkResponse,
    dependencies=[Security(auth.requires_user)],
    summary="Confirm a SERVER link token (user must be authenticated)",
)
async def confirm_link_token(
    token: TokenPath,
    user_id: Annotated[str, Security(auth.get_user_id)],
) -> ConfirmLinkResponse:
    """Frontend calls this after the user logs in and clicks 'Connect'."""
    link_token = await PlatformLinkToken.prisma().find_unique(where={"token": token})

    if not link_token:
        raise HTTPException(status_code=404, detail="Token not found.")

    if link_token.linkType != LinkType.SERVER.value:
        raise HTTPException(
            status_code=400,
            detail="This link is for a different linking flow.",
        )

    if link_token.usedAt is not None:
        raise HTTPException(status_code=410, detail="This link has already been used.")

    if link_token.expiresAt.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="This link has expired.")

    if not link_token.platformServerId:
        # Should be impossible given linkType=SERVER but satisfy the type system.
        raise HTTPException(status_code=500, detail="Server token missing server ID.")

    existing = await find_server_link(link_token.platform, link_token.platformServerId)
    if existing:
        detail = (
            "This server is already linked to your account."
            if existing.userId == user_id
            else "This server is already linked to another AutoGPT account."
        )
        raise HTTPException(status_code=409, detail=detail)

    # Atomically consume token and create link to prevent token burning on create failures
    now = datetime.now(timezone.utc)
    try:
        async with transaction() as tx:
            updated = await PlatformLinkToken.prisma(tx).update_many(
                where={"token": token, "usedAt": None, "expiresAt": {"gt": now}},
                data={"usedAt": now},
            )
            if updated == 0:
                raise HTTPException(
                    status_code=410, detail="This link has already been used."
                )

            await PlatformLink.prisma(tx).create(
                data={
                    "userId": user_id,
                    "platform": link_token.platform,
                    "platformServerId": link_token.platformServerId,
                    "ownerPlatformUserId": link_token.platformUserId,
                    "serverName": link_token.serverName,
                }
            )
    except HTTPException:
        raise
    except Exception as exc:
        if "unique" in str(exc).lower():
            raise HTTPException(
                status_code=409,
                detail="This server was just linked by another request.",
            ) from exc
        raise

    logger.info(
        "Linked %s server %s to user ...%s",
        link_token.platform,
        link_token.platformServerId,
        user_id[-8:],
    )

    return ConfirmLinkResponse(
        success=True,
        platform=link_token.platform,
        platform_server_id=link_token.platformServerId,
        server_name=link_token.serverName,
    )


@router.post(
    "/user-tokens/{token}/confirm",
    response_model=ConfirmUserLinkResponse,
    dependencies=[Security(auth.requires_user)],
    summary="Confirm a USER link token (user must be authenticated)",
)
async def confirm_user_link_token(
    token: TokenPath,
    user_id: Annotated[str, Security(auth.get_user_id)],
) -> ConfirmUserLinkResponse:
    """Frontend calls this after the user logs in and clicks 'Connect' on a DM link."""
    link_token = await PlatformLinkToken.prisma().find_unique(where={"token": token})

    if not link_token:
        raise HTTPException(status_code=404, detail="Token not found.")

    if link_token.linkType != LinkType.USER.value:
        raise HTTPException(
            status_code=400,
            detail="This link is for a different linking flow.",
        )

    if link_token.usedAt is not None:
        raise HTTPException(status_code=410, detail="This link has already been used.")

    if link_token.expiresAt.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="This link has expired.")

    existing = await find_user_link(link_token.platform, link_token.platformUserId)
    if existing:
        detail = (
            "Your DMs are already linked to your account."
            if existing.userId == user_id
            else "This platform user is already linked to another AutoGPT account."
        )
        raise HTTPException(status_code=409, detail=detail)

    # Atomically consume token and create link to prevent token burning on create failures
    now = datetime.now(timezone.utc)
    try:
        async with transaction() as tx:
            updated = await PlatformLinkToken.prisma(tx).update_many(
                where={"token": token, "usedAt": None, "expiresAt": {"gt": now}},
                data={"usedAt": now},
            )
            if updated == 0:
                raise HTTPException(
                    status_code=410, detail="This link has already been used."
                )

            await PlatformUserLink.prisma(tx).create(
                data={
                    "userId": user_id,
                    "platform": link_token.platform,
                    "platformUserId": link_token.platformUserId,
                    "platformUsername": link_token.platformUsername,
                }
            )
    except HTTPException:
        raise
    except Exception as exc:
        if "unique" in str(exc).lower():
            raise HTTPException(
                status_code=409,
                detail="Your DMs were just linked by another request.",
            ) from exc
        raise

    logger.info(
        "Linked %s DMs to AutoGPT user ...%s",
        link_token.platform,
        user_id[-8:],
    )

    return ConfirmUserLinkResponse(
        success=True,
        platform=link_token.platform,
        platform_user_id=link_token.platformUserId,
    )


@router.get(
    "/links",
    response_model=list[PlatformLinkInfo],
    dependencies=[Security(auth.requires_user)],
    summary="List all platform servers linked to the authenticated user",
)
async def list_my_links(
    user_id: Annotated[str, Security(auth.get_user_id)],
) -> list[PlatformLinkInfo]:
    links = await PlatformLink.prisma().find_many(
        where={"userId": user_id},
        order={"linkedAt": "desc"},
    )
    return [
        PlatformLinkInfo(
            id=link.id,
            platform=link.platform,
            platform_server_id=link.platformServerId,
            owner_platform_user_id=link.ownerPlatformUserId,
            server_name=link.serverName,
            linked_at=link.linkedAt,
        )
        for link in links
    ]


@router.get(
    "/user-links",
    response_model=list[PlatformUserLinkInfo],
    dependencies=[Security(auth.requires_user)],
    summary="List all DM links for the authenticated user",
)
async def list_my_user_links(
    user_id: Annotated[str, Security(auth.get_user_id)],
) -> list[PlatformUserLinkInfo]:
    links = await PlatformUserLink.prisma().find_many(
        where={"userId": user_id},
        order={"linkedAt": "desc"},
    )
    return [
        PlatformUserLinkInfo(
            id=link.id,
            platform=link.platform,
            platform_user_id=link.platformUserId,
            platform_username=link.platformUsername,
            linked_at=link.linkedAt,
        )
        for link in links
    ]


@router.delete(
    "/links/{link_id}",
    response_model=DeleteLinkResponse,
    dependencies=[Security(auth.requires_user)],
    summary="Unlink a platform server",
)
async def delete_link(
    link_id: str,
    user_id: Annotated[str, Security(auth.get_user_id)],
) -> DeleteLinkResponse:
    link = await PlatformLink.prisma().find_unique(where={"id": link_id})
    if not link:
        raise HTTPException(status_code=404, detail="Link not found.")
    if link.userId != user_id:
        raise HTTPException(status_code=403, detail="Not your link.")

    await PlatformLink.prisma().delete(where={"id": link_id})
    logger.info(
        "Unlinked %s server %s from user ...%s",
        link.platform,
        link.platformServerId,
        user_id[-8:],
    )
    return DeleteLinkResponse(success=True)


@router.delete(
    "/user-links/{link_id}",
    response_model=DeleteLinkResponse,
    dependencies=[Security(auth.requires_user)],
    summary="Unlink a DM / user link",
)
async def delete_user_link(
    link_id: str,
    user_id: Annotated[str, Security(auth.get_user_id)],
) -> DeleteLinkResponse:
    link = await PlatformUserLink.prisma().find_unique(where={"id": link_id})
    if not link:
        raise HTTPException(status_code=404, detail="Link not found.")
    if link.userId != user_id:
        raise HTTPException(status_code=403, detail="Not your link.")

    await PlatformUserLink.prisma().delete(where={"id": link_id})
    logger.info(
        "Unlinked %s DMs from AutoGPT user ...%s",
        link.platform,
        user_id[-8:],
    )
    return DeleteLinkResponse(success=True)
