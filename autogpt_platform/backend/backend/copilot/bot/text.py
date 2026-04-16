"""Text formatting helpers — message batching and chunk splitting."""


def format_batch(batch: list[tuple[str, str, str]], platform: str) -> str:
    """Format one or more pending messages into a single prompt for AutoPilot.

    Each batch entry is (username, user_id, text). When multiple messages are
    batched together (because they arrived while the bot was streaming a prior
    response), they're labelled individually so the LLM can address each.
    """
    platform_display = platform.capitalize()
    if len(batch) == 1:
        username, user_id, text = batch[0]
        return (
            f"[Message sent by {username} ({platform_display} user ID: {user_id})]\n"
            f"{text}"
        )

    lines = ["[Multiple messages — please address them together]"]
    for username, user_id, text in batch:
        lines.append(
            f"\n[From {username} ({platform_display} user ID: {user_id})]\n{text}"
        )
    return "\n".join(lines)


def split_at_boundary(text: str, flush_at: int) -> tuple[str, str]:
    """Split text at a natural boundary to fit within a length limit.

    Returns (postable_chunk, remaining_text).
    Prefers: paragraph > newline > sentence end > space > hard cut.
    Used for chunking long responses across any platform's message limit.
    """
    if len(text) <= flush_at:
        return text, ""

    search_start = max(0, flush_at - 200)
    search_region = text[search_start:flush_at]

    for sep in ("\n\n", "\n"):
        idx = search_region.rfind(sep)
        if idx != -1:
            cut = search_start + idx
            return text[:cut].rstrip(), text[cut:].lstrip("\n")

    for sep in (". ", "! ", "? "):
        idx = search_region.rfind(sep)
        if idx != -1:
            cut = search_start + idx + len(sep)
            return text[:cut], text[cut:]

    idx = search_region.rfind(" ")
    if idx != -1:
        cut = search_start + idx
        return text[:cut], text[cut:].lstrip()

    return text[:flush_at], text[flush_at:]
