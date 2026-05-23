#!/usr/bin/env python3
"""Minimal test: load credentials, fetch first comment page, print 3 comments."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Allow imports from src/ without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bilibili_comments.auth import load_credential
from bilibili_comments.scrape import extract_replies, fetch_comments_for_bvid, format_comment

BVID = "BV1vVLw6KEFb"


async def main() -> None:
    credential = load_credential()
    ref, page = await fetch_comments_for_bvid(BVID, credential, pn=1, ps=20)

    print(f"BV:  {ref.bvid}")
    print(f"aid: {ref.aid}")

    replies = extract_replies(page)
    print(f"page 1: {len(replies)} comments returned\n")

    for i, reply in enumerate(replies[:3], start=1):
        print(format_comment(reply, i))
        print()


if __name__ == "__main__":
    asyncio.run(main())
