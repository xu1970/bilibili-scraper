"""Fetch Bilibili video comments."""

from __future__ import annotations

import asyncio
import enum
import json
from collections.abc import Callable
from typing import Any

from bilibili_api import comment
from bilibili_api.exceptions import ApiException, ResponseCodeException
from bilibili_api.utils.credential import Credential
from bilibili_api.utils.network import Api
from bilibili_api.utils.utils import get_api

from .request_guard import call_with_retry
from .throttle import random_sleep
from .video import VideoRef, parse_video_ref

_API = get_api("common")

# Safety limit for primary-comment pagination loops.
_DEFAULT_MAX_REQUESTS = 500
MAX_PAGES_PER_VIDEO = 100


class PageBudget:
    """Tracks API pagination pages consumed for one video."""

    def __init__(self, limit: int = MAX_PAGES_PER_VIDEO) -> None:
        self.limit = limit
        self.pages = 0

    @property
    def exhausted(self) -> bool:
        return self.pages >= self.limit

    def record(self, n: int = 1) -> None:
        self.pages += n

    def remaining(self) -> int:
        return max(0, self.limit - self.pages)


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


def replies_is_empty(page: dict[str, Any] | None) -> bool:
    """True when the API returned no replies (``None``, missing key, or ``[]``)."""
    if not page:
        return True
    replies = page.get("replies")
    return replies is None or replies == [] or len(replies) == 0


def build_pagination_str(offset: str = "") -> str:
    """
    Build the ``pagination_str`` query value for WBI ``/x/v2/reply/wbi/main``.

    ``offset`` is usually ``cursor.pagination_reply.next_offset`` from the prior
    response; use an empty string for the first page.
    """
    escaped = offset.replace('"', r"\"")
    return '{"offset":"%s"}' % escaped


def top_rpids_from_page(page: dict[str, Any]) -> set[int]:
    """Collect pinned/top-level highlight rpids from one API page."""
    ids: set[int] = set()
    for item in page.get("top_replies") or []:
        rpid = item.get("rpid")
        if rpid is not None:
            ids.add(int(rpid))
    return ids


def pagination_next_offset(page: dict[str, Any]) -> str | None:
    """Return ``pagination_reply.next_offset`` when the API provides cursor paging."""
    cursor = page.get("cursor") or {}
    pr = cursor.get("pagination_reply")
    if isinstance(pr, dict):
        raw = pr.get("next_offset")
        if raw:
            return str(raw)
    return None


def pagination_next_index(page: dict[str, Any]) -> int | None:
    """Return legacy ``cursor.next`` page index when offset paging is unavailable."""
    cursor = page.get("cursor") or {}
    raw = cursor.get("next")
    if raw is None:
        return None
    return int(raw)


def _synthetic_offset_from_cursor(page: dict[str, Any]) -> str | None:
    """
    Build an offset token from ``session_id`` + ``cursor.next`` when
    ``pagination_reply`` is empty but the API still advertises a next page.
    """
    cursor = page.get("cursor") or {}
    session_id = cursor.get("session_id")
    next_idx = cursor.get("next")
    if not session_id or next_idx in (None, 0):
        return None
    payload = {
        "type": 1,
        "direction": 1,
        "session_id": str(session_id),
        "data": {"pn": int(next_idx)},
    }
    return json.dumps(payload, separators=(",", ":"))


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
        "next_offset": pagination_next_offset(page),
    }


async def fetch_top_level_page(
    oid: int,
    credential: Credential,
    *,
    sort: CommentSort = CommentSort.HOT,
    next_index: int = 0,
    ps: int = 20,
    pagination_offset: str | None = None,
) -> dict[str, Any]:
    """
    Fetch one page of top-level video comments.

    When ``pagination_offset`` is set (including ``""`` for the first page), the
    WBI endpoint is called with ``pagination_str`` + ``plat=1``. Otherwise the
    legacy ``next`` index is used.
    """
    api = _API["comment"]["reply_by_session_id"]
    params: dict[str, Any] = {
        "oid": oid,
        "type": comment.CommentResourceType.VIDEO.value,
        "mode": sort.value,
        "next": next_index,
        "ps": ps,
    }
    if pagination_offset is not None:
        params["pagination_str"] = build_pagination_str(pagination_offset)
        params["plat"] = 1
        params["web_location"] = "1315875"
    return await Api(**api, credential=credential).update_params(**params).result


def _advance_primary_pagination(
    *,
    use_offset_paging: bool,
    offset: str | None,
    next_index: int,
    page_num: int,
) -> tuple[bool, str | None, int]:
    """Advance cursor/page index after a failed fetch so the next iteration is not identical."""
    if use_offset_paging and offset is not None:
        return False, None, max(next_index + 1, page_num + 1)
    return use_offset_paging, offset, next_index + 1


async def fetch_all_top_level(
    oid: int,
    credential: Credential,
    *,
    sort: CommentSort = CommentSort.HOT,
    ps: int = 30,
    max_primaries: int | None = None,
    max_requests: int = _DEFAULT_MAX_REQUESTS,
    delay_seconds: float = 0.0,
    on_page_fetched: Callable[[int, int], None] | None = None,
    page_budget: PageBudget | None = None,
) -> tuple[list[dict[str, Any]], set[int]]:
    """
    Fetch all primary (top-level) comments by paginating until exhausted or capped.

    Pagination order:
    1. ``pagination_str`` / ``pagination_reply.next_offset`` (new WBI cursor)
    2. Synthetic offset from ``session_id`` + ``cursor.next`` when provided
    3. Legacy ``cursor.next`` index (older API behavior)
    """
    all_replies: list[dict[str, Any]] = []
    top_rpids: set[int] = set()
    seen_rpids: set[int] = set()

    # First request uses empty offset when WBI offset paging is available.
    offset: str | None = ""
    next_index = 0
    use_offset_paging = True
    prev_offset: str | None = None
    offset_paging_disabled = False
    page_num = 0
    consecutive_failures = 0
    request_cap = max_requests
    if page_budget is not None:
        request_cap = min(max_requests, page_budget.remaining())

    for _ in range(request_cap):
        if page_budget is not None and page_budget.exhausted:
            break

        pagination_arg: str | None
        if use_offset_paging and not offset_paging_disabled:
            pagination_arg = offset if offset is not None else ""
        else:
            pagination_arg = None

        try:
            page = await call_with_retry(
                lambda: fetch_top_level_page(
                    oid,
                    credential,
                    sort=sort,
                    next_index=next_index,
                    ps=ps,
                    pagination_offset=pagination_arg,
                ),
                label=f"primary comments oid={oid} next={next_index}",
            )
            consecutive_failures = 0
        except (ResponseCodeException, ApiException) as exc:
            consecutive_failures += 1
            print(
                f"  WARNING: primary page failed after retries ({exc}); "
                "advancing pagination token",
                flush=True,
            )
            if use_offset_paging and not offset_paging_disabled:
                offset_paging_disabled = True
                use_offset_paging = False
                offset = None
            use_offset_paging, offset, next_index = _advance_primary_pagination(
                use_offset_paging=use_offset_paging,
                offset=offset,
                next_index=next_index,
                page_num=page_num,
            )
            if consecutive_failures >= 3:
                break
            continue

        if replies_is_empty(page):
            break

        top_rpids |= top_rpids_from_page(page)
        batch = extract_replies(page)
        batch_size = len(batch)
        added_this_page = 0

        for reply in batch:
            rpid = reply.get("rpid")
            if rpid is None:
                continue
            rpid_int = int(rpid)
            if rpid_int in seen_rpids:
                continue
            seen_rpids.add(rpid_int)
            all_replies.append(reply)
            added_this_page += 1

        page_num += 1
        if page_budget is not None:
            page_budget.record(1)
        if on_page_fetched is not None:
            on_page_fetched(page_num, len(all_replies))

        if page_budget is not None and page_budget.exhausted:
            break

        if max_primaries is not None and len(all_replies) >= max_primaries:
            break

        # Empty page or API repeating the same rpids — stop paginating.
        if replies_is_empty(page) or batch_size == 0:
            break
        if added_this_page == 0:
            break

        cursor = page.get("cursor") or {}

        new_offset = pagination_next_offset(page)
        if new_offset is None:
            new_offset = _synthetic_offset_from_cursor(page)

        if new_offset and new_offset != prev_offset:
            prev_offset = offset
            offset = new_offset
            next_index = 0
            use_offset_paging = True
            if delay_seconds > 0:
                await random_sleep(delay_seconds)
            continue

        next_cursor = pagination_next_index(page)

        if cursor.get("is_end") and next_cursor in (None, 0):
            break
        if next_cursor is None:
            break

        new_next = int(next_cursor)
        if new_next == next_index:
            break

        next_index = new_next
        use_offset_paging = False
        offset = None

        if delay_seconds > 0:
            await random_sleep(delay_seconds)

    if max_primaries is not None and len(all_replies) > max_primaries:
        all_replies = all_replies[:max_primaries]

    return all_replies, top_rpids


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
    """Fetch ``num_pages`` raw API responses using the same pagination rules."""
    if num_pages < 1:
        return []

    pages: list[dict[str, Any]] = []
    offset: str | None = ""
    next_index = 0
    use_offset_paging = True
    prev_offset: str | None = None
    offset_paging_disabled = False

    for page_num in range(1, num_pages + 1):
        pagination_arg: str | None
        if use_offset_paging and not offset_paging_disabled:
            pagination_arg = offset if offset is not None else ""
        else:
            pagination_arg = None

        try:
            page = await fetch_top_level_page(
                oid,
                credential,
                sort=sort,
                next_index=next_index,
                ps=ps,
                pagination_offset=pagination_arg,
            )
        except ApiException:
            if use_offset_paging and not offset_paging_disabled:
                offset_paging_disabled = True
                use_offset_paging = False
                offset = None
                page = await fetch_top_level_page(
                    oid,
                    credential,
                    sort=sort,
                    next_index=next_index,
                    ps=ps,
                    pagination_offset=None,
                )
            else:
                raise

        pages.append(page)
        if page_num >= num_pages:
            break

        cursor = page.get("cursor") or {}
        batch_size = len(extract_replies(page))

        new_offset = pagination_next_offset(page)
        if new_offset is None:
            new_offset = _synthetic_offset_from_cursor(page)

        if new_offset and new_offset != prev_offset:
            prev_offset = offset
            offset = new_offset
            next_index = 0
            use_offset_paging = True
            continue

        next_cursor = pagination_next_index(page)
        if batch_size == 0 and (cursor.get("is_end") or next_cursor in (None, 0)):
            break
        if cursor.get("is_end") and next_cursor in (None, 0):
            break
        if next_cursor is None:
            break

        new_next = int(next_cursor)
        if new_next == next_index:
            break

        next_index = new_next
        use_offset_paging = False
        offset = None

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
    pagination_offset: str | None = None,
) -> tuple[VideoRef, dict[str, Any]]:
    """Resolve BV → aid and fetch one page of top-level comments."""
    ref = parse_video_ref(bvid)
    page = await fetch_top_level_page(
        ref.aid,
        credential,
        sort=sort,
        next_index=next_index,
        ps=ps,
        pagination_offset=pagination_offset,
    )
    return ref, page
