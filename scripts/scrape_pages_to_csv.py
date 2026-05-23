#!/usr/bin/env python3
"""Fetch the first N pages of top-level comments and save to CSV."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bilibili_comments.auth import load_credential
from bilibili_comments.export import write_comments_csv
from bilibili_comments.scrape import CommentSort, collect_reply_rows, fetch_n_pages
from bilibili_comments.video import parse_video_ref

DEFAULT_BVID = "BV1vVLw6KEFb"
DEFAULT_PAGES = 3
DEFAULT_SORT = CommentSort.HOT


async def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape Bilibili comments to CSV")
    parser.add_argument("--bvid", default=DEFAULT_BVID, help="Video BV id")
    parser.add_argument("--pages", type=int, default=DEFAULT_PAGES, help="Number of pages")
    parser.add_argument(
        "--sort",
        choices=("hot", "newest"),
        default=DEFAULT_SORT.label,
        help="Comment sort mode",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output CSV path (default: comments_<bvid>_<sort>_p<pages>.csv)",
    )
    args = parser.parse_args()

    sort = CommentSort.HOT if args.sort == "hot" else CommentSort.NEWEST
    credential = load_credential()
    ref = parse_video_ref(args.bvid)

    pages = await fetch_n_pages(ref.aid, credential, args.pages, sort)
    rows = collect_reply_rows(pages)

    if args.output is None:
        args.output = Path(f"comments_{ref.bvid}_{sort.label}_p{args.pages}.csv")

    out = write_comments_csv(rows, args.output)

    print(f"BV:     {ref.bvid}")
    print(f"aid:    {ref.aid}")
    print(f"sort:   {sort.label} (API mode {sort.value})")
    print(f"pages:  {len(pages)} fetched (requested {args.pages})")
    print(f"rows:   {len(rows)} comments")
    print(f"saved:  {out.resolve()}")


if __name__ == "__main__":
    asyncio.run(main())
