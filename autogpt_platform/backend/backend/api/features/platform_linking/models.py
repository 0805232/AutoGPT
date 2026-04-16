"""Pydantic models for the platform bot linking API."""

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class Platform(str, Enum):
    """Supported platform types (mirrors Prisma PlatformType)."""

    DISCORD = "DISCORD"
    TELEGRAM = "TELEGRAM"
    SLACK = "SLACK"
    TEAMS = "TEAMS"
    WHATSAPP = "WHATSAPP"
    GITHUB = "GITHUB"
    LINEAR = "LINEAR"


class LinkType(str, Enum):
    """Whether a token/link targets a server (group chat) or a user (DM)."""

    SERVER = "SERVER"
    USER = "USER"


# ── Request Models ─────────────────────────────────────────────────────


class CreateLinkTokenRequest(BaseModel):
    """
    Request from the bot service to create a linking token for a server.

    Called when no PlatformLink exists for the given server. The bot sends
    the resulting link URL to the user who triggered the interaction — they
    become the server owner when they complete the link.
    """

    platform: Platform = Field(description="Platform name")
    platform_server_id: str = Field(
        description="Server/guild/group ID on the platform",
        min_length=1,
        max_length=255,
    )
    platform_user_id: str = Field(
        description="Platform user ID of the person claiming ownership",
        min_length=1,
        max_length=255,
    )
    platform_username: str | None = Field(
        default=None,
        description="Display name of the person claiming ownership",
        max_length=255,
    )
    server_name: str | None = Field(
        default=None,
        description="Display name of the server/group",
        max_length=255,
    )
    channel_id: str | None = Field(
        default=None,
        description="Channel ID so the bot can send a confirmation message",
        max_length=255,
    )


class CreateUserLinkTokenRequest(BaseModel):
    """Request from the bot service to create a DM (user-level) linking token."""

    platform: Platform
    platform_user_id: str = Field(
        description="Platform user ID of the person linking their DMs",
        min_length=1,
        max_length=255,
    )
    platform_username: str | None = Field(
        default=None,
        description="Their display name (best-effort for audit)",
        max_length=255,
    )


class ResolveServerRequest(BaseModel):
    """Check whether a platform server is linked to an AutoGPT owner account."""

    platform: Platform
    platform_server_id: str = Field(
        description="Server/guild/group ID to look up",
        min_length=1,
        max_length=255,
    )


class ResolveUserRequest(BaseModel):
    """Check whether an individual platform user has linked their DMs."""

    platform: Platform
    platform_user_id: str = Field(
        description="Platform user ID to look up",
        min_length=1,
        max_length=255,
    )


class BotChatRequest(BaseModel):
    """
    Request from the bot to send a message on behalf of a platform user.

    Exactly one of (platform_server_id) or () must resolve via context:
      - SERVER context: both platform_server_id and platform_user_id set.
        Billed to the server owner; per-user sessions.
      - DM context: platform_server_id is null, platform_user_id set.
        Billed to that user's own account.
    """

    platform: Platform
    platform_server_id: str | None = Field(
        default=None,
        description="Server/guild/group ID — null for DM context",
        # min_length only applies when value is a string; null stays valid.
        min_length=1,
        max_length=255,
    )
    platform_user_id: str = Field(
        description="Platform user ID of the person who sent the message",
        min_length=1,
        max_length=255,
    )
    message: str = Field(
        description="The user's message", min_length=1, max_length=32000
    )
    session_id: str | None = Field(
        default=None,
        description="Existing CoPilot session ID. If omitted, a new session is created.",
    )


# ── Response Models ────────────────────────────────────────────────────


class LinkTokenResponse(BaseModel):
    token: str
    expires_at: datetime
    link_url: str


class LinkTokenStatusResponse(BaseModel):
    status: Literal["pending", "linked", "expired"]


class LinkTokenInfoResponse(BaseModel):
    """Non-sensitive display info for the frontend link page."""

    platform: str
    link_type: LinkType
    server_name: str | None = None


class ResolveResponse(BaseModel):
    linked: bool


class PlatformLinkInfo(BaseModel):
    id: str
    platform: str
    platform_server_id: str
    owner_platform_user_id: str
    server_name: str | None
    linked_at: datetime


class PlatformUserLinkInfo(BaseModel):
    id: str
    platform: str
    platform_user_id: str
    platform_username: str | None
    linked_at: datetime


class ConfirmLinkResponse(BaseModel):
    """Server-link confirmation result. link_type is always SERVER here."""

    success: bool
    link_type: LinkType = LinkType.SERVER
    platform: str
    platform_server_id: str
    server_name: str | None


class ConfirmUserLinkResponse(BaseModel):
    """User-link (DM) confirmation result."""

    success: bool
    link_type: LinkType = LinkType.USER
    platform: str
    platform_user_id: str


class DeleteLinkResponse(BaseModel):
    success: bool


class BotChatSessionResponse(BaseModel):
    """Returned when creating a new session via the bot proxy."""

    session_id: str
