# Platform bot linking API

from prisma.models import PlatformLink


async def find_server_link(
    platform: str,
    platform_server_id: str,
    platform_user_id: str | None = None,
) -> PlatformLink | None:
    """Look up the PlatformLink for a server, with DM fallback by owner user ID.

    In DM contexts there's no server. If `platform_user_id` is provided and no
    server link exists, fall back to matching an existing server link owned by
    that user — lets previously-linked owners skip re-auth in DMs.
    """
    link = await PlatformLink.prisma().find_first(
        where={"platform": platform, "platformServerId": platform_server_id}
    )
    if link is None and platform_user_id:
        link = await PlatformLink.prisma().find_first(
            where={"platform": platform, "ownerPlatformUserId": platform_user_id}
        )
    return link
