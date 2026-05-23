#!/usr/bin/env python3
"""Compare hot vs newest comment sort; fetch pages 1 and 2 for each."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bilibili_comments.auth import load_credential
from bilibili_comments.scrape import (
    CommentSort,
    comment_text,
    describe_sort_mode,
    extract_replies,
    fetch_two_pages,
)
from bilibili_comments.video import parse_video_ref

BVID = "BV1vVLw6KEFb"


def print_page_summary(page_num: int, page: dict, sort_info: dict) -> None:
    replies = extract_replies(page)
    count = len(replies)
    first = comment_text(replies[0]) if replies else "(none)"
    last = comment_text(replies[-1]) if replies else "(none)"

    print(f"  --- page {page_num} ---")
    print(f"  comment count:     {count}")
    print(f"  first comment:     {first[:120]}{'...' if len(first) > 120 else ''}")
    print(f"  last comment:      {last[:120]}{'...' if len(last) > 120 else ''}")


def print_sort_block(sort: CommentSort, page1: dict, page2: dict) -> None:
    info1 = describe_sort_mode(page1, sort)
    print(f"\n{'=' * 60}")
    print(f"SORT: {sort.label.upper()} (requested mode={info1['requested_mode']})")
    print(f"  API mode:       {info1['api_mode']}")
    print(f"  API mode_text:  {info1['api_mode_text']!r}")
    print(f"  API name:       {info1['api_name']!r}")
    print(f"  total comments: {info1['all_count']}")
    print(f"  page-2 cursor next index: {page1.get('cursor', {}).get('next')}")
    print_page_summary(1, page1, info1)
    print_page_summary(2, page2, describe_sort_mode(page2, sort))


async def main() -> None:
    credential = load_credential()
    ref = parse_video_ref(BVID)

    print(f"BV:  {ref.bvid}")
    print(f"aid: {ref.aid}")

    for sort in (CommentSort.HOT, CommentSort.NEWEST):
        page1, page2 = await fetch_two_pages(ref.aid, credential, sort, ps=20)
        print_sort_block(sort, page1, page2)

    print(f"\n{'=' * 60}")
    print("Browser comparison:")
    print("  热门 (hot)   → API mode 3, name often '热门评论'")
    print("  最新 (newest)→ API mode 2, name often '最新评论'")


if __name__ == "__main__":
    asyncio.run(main())
