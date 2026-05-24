"""Fetch Bilibili video comments."""

from __future__ import annotations

import enum
from typing import Any

from bilibili_api import comment
from bilibili_api.utils.credential import Credential
from bilibili_api.utils.network import Api
from bilibili_api.utils.utils import get_api

from .video import VideoRef, parse_video_ref

_API = get_api("common")


class CommentSort(enum.Enum):
    """
    Bilibili main comment sort modes (``mode`` query param).

    + HOT: 热门 — API mode 3
    + NEWEST: 最新 — API mode 2
    """

    HOT = 3
    NEWEST = 2

    @property
    def label(self) -> str:
        return "hot" if self is CommentSort.HOT else "newest"


def comment_text(reply: dict[str, Any]) -> str:
    """Extract plain comment text from a reply dict."""
    content = reply.get("content") or {}
    return (content.get("message") or "").replace("\n", " ")


def format_comment(reply: dict[str, Any], index: int) -> str:
    """Format a single comment dict for display."""
    member = reply.get("member") or {}
    uname = member.get("uname", "?")
    likes = reply.get("like", 0)
    rpid = reply.get("rpid", "?")
    return f"[{index}] {uname} (likes={likes}, rpid={rpid})\n    {comment_text(reply)}"


def extract_replies(page: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the replies list from a comment API page."""
    replies = page.get("replies")
    if replies is None:
        return []
    return replies


def describe_sort_mode(page: dict[str, Any], requested: CommentSort) -> dict[str, Any]:
    """Summarize sort/pagination metadata returned by the API."""
    cursor = page.get("cursor") or {}
    return {
        "requested_sort": requested.label,
        "requested_mode": requested.value,
        "api_mode": cursor.get("mode"),
        "api_mode_text": cursor.get("mode_text") or "",
        "api_name": cursor.get("name") or "",
        "all_count": cursor.get("all_count"),
        "cursor_next": cursor.get("next"),
    }


async def fetch_top_level_page(
    oid: int,
    credential: Credential,
    *,
    sort: CommentSort = CommentSort.HOT,
    next_index: int = 0,
    ps: int = 20,
) -> dict[str, Any]:
    """
    Fetch one page of top-level video comments.

    ``next_index`` is the API ``next`` parameter (0-based). For hot sort, page 2
    should use ``cursor["next"]`` from page 1, not simply ``1``.
    """
    api = _API["comment"]["reply_by_session_id"]
    params = {
        "oid": oid,
        "type": comment.CommentResourceType.VIDEO.value,
        "mode": sort.value,
        "next": next_index,
        "ps": ps,
    }
    return await Api(**api, credential=credential).update_params(**params).result


def parse_reply_row(reply: dict[str, Any], *, page: int) -> dict[str, Any]:
    """Normalize one API reply dict into a flat row for export."""
    member = reply.get("member") or {}
    ctime = reply.get("ctime", 0)
    return {
        "page": page,
        "rpid": reply.get("rpid"),
        "comment_text": comment_text(reply),
        "username": member.get("uname", ""),
        "timestamp": int(ctime) if ctime else 0,
        "like_count": reply.get("like", 0),
        "reply_count": reply.get("count", 0),
    }


async def fetch_n_pages(
    oid: int,
    credential: Credential,
    num_pages: int,
    sort: CommentSort = CommentSort.HOT,
    *,
    ps: int = 20,
) -> list[dict[str, Any]]:
    """Fetch ``num_pages`` of top-level comments, following API cursor pagination."""
    if num_pages < 1:
        return []

    pages: list[dict[str, Any]] = []
    next_index = 0

    for page_num in range(1, num_pages + 1):
        page = await fetch_top_level_page(
            oid, credential, sort=sort, next_index=next_index, ps=ps
        )
        pages.append(page)

        cursor = page.get("cursor") or {}
        if cursor.get("is_end"):
            break
        if page_num >= num_pages:
            break

        next_cursor = cursor.get("next")
        if next_cursor is None:
            break
        next_index = int(next_cursor)

    return pages


def collect_reply_rows(
    pages: list[dict[str, Any]], *, dedupe: bool = True
) -> list[dict[str, Any]]:
    """Flatten paginated API responses into export rows."""
    rows: list[dict[str, Any]] = []
    seen: set[int] = set()

    for page_num, page in enumerate(pages, start=1):
        for reply in extract_replies(page):
            rpid = reply.get("rpid")
            if dedupe and rpid is not None:
                if rpid in seen:
                    continue
                seen.add(rpid)
            rows.append(parse_reply_row(reply, page=page_num))

    return rows


async def fetch_two_pages(
    oid: int,
    credential: Credential,
    sort: CommentSort,
    *,
    ps: int = 20,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Fetch pages 1 and 2 for a given sort mode."""
    pages = await fetch_n_pages(oid, credential, 2, sort, ps=ps)
    if len(pages) < 2:
        pages.append({})
    return pages[0], pages[1]


async def fetch_comments_for_bvid(
    bvid: str,
    credential: Credential,
    *,
    sort: CommentSort = CommentSort.HOT,
    next_index: int = 0,
    ps: int = 20,
) -> tuple[VideoRef, dict[str, Any]]:
    """Resolve BV → aid and fetch one page of top-level comments."""
    ref = parse_video_ref(bvid)
    page = await fetch_top_level_page(
        ref.aid, credential, sort=sort, next_index=next_index, ps=ps
    )
    return ref, page
