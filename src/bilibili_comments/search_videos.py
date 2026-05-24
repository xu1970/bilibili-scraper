"""Search Bilibili videos by keyword."""

from __future__ import annotations

import asyncio
import re
from typing import Any

from bilibili_api import search

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(text: str) -> str:
    """Remove simple HTML markup from search result titles."""
    return _HTML_TAG_RE.sub("", text or "").strip()


def extract_video_block(page_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the video result list from a ``search.search`` page response."""
    for block in page_data.get("result") or []:
        if block.get("result_type") == "video":
            data = block.get("data")
            if isinstance(data, list):
                return data
    return []


def parse_video_result(
    item: dict[str, Any], *, page: int, rank: int
) -> dict[str, Any]:
    """Normalize one search hit into a flat row for CSV export."""
    play = item.get("play")
    view_count: int | str = ""
    if play is not None and play != "":
        try:
            view_count = int(play)
        except (TypeError, ValueError):
            view_count = play

    danmaku = item.get("danmaku")
    try:
        danmaku_count = int(danmaku) if danmaku is not None and danmaku != "" else 0
    except (TypeError, ValueError):
        danmaku_count = 0

    return {
        "page": page,
        "rank": rank,
        "bvid": item.get("bvid") or "",
        "title": strip_html(item.get("title") or ""),
        "uploader": item.get("author") or item.get("uname") or "",
        "view_count": view_count,
        "aid": item.get("aid") or item.get("id") or "",
        "tags": item.get("tag") or "",
        "typename": item.get("typename") or "",
        "danmaku": danmaku_count,
        "in_sample": "no",
        "exclusion_reason": "",
    }


async def fetch_search_page(keyword: str, page: int) -> dict[str, Any]:
    """Fetch one page of web search results."""
    response = await search.search(keyword, page=page)
    return response.get("data") or response


async def search_videos(
    keyword: str,
    num_pages: int,
    *,
    delay_seconds: float = 1.0,
) -> list[dict[str, Any]]:
    """
    Search videos by keyword across ``num_pages`` (1-indexed pages).

    Uses ``bilibili_api.search.search`` (web search all/v2), extracting the
    ``video`` block from each page.
    """
    if num_pages < 1:
        return []

    rows: list[dict[str, Any]] = []
    seen_bvids: set[str] = set()

    for page in range(1, num_pages + 1):
        page_data = await fetch_search_page(keyword, page)
        videos = extract_video_block(page_data)

        for rank, item in enumerate(videos, start=1):
            row = parse_video_result(item, page=page, rank=rank)
            bvid = row["bvid"]
            if bvid and bvid in seen_bvids:
                continue
            if bvid:
                seen_bvids.add(bvid)
            rows.append(row)

        if page < num_pages and delay_seconds > 0:
            await asyncio.sleep(delay_seconds)

    return rows
