#!/usr/bin/env python3
"""Search Bilibili videos by keyword and save metadata to CSV."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bilibili_comments.export import write_search_csv
from bilibili_comments.filter_videos import apply_search_filters, filter_summary
from bilibili_comments.search_videos import search_videos

DEFAULT_KEYWORD = "生育"
DEFAULT_PAGES = 20


async def main() -> None:
    parser = argparse.ArgumentParser(description="Search Bilibili videos and export CSV")
    parser.add_argument("--keyword", default=DEFAULT_KEYWORD, help="Search keyword")
    parser.add_argument("--pages", type=int, default=DEFAULT_PAGES, help="Number of pages")
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Seconds to wait between page requests",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output CSV path",
    )
    args = parser.parse_args()

    rows = await search_videos(args.keyword, args.pages, delay_seconds=args.delay)
    apply_search_filters(rows)

    if args.output is None:
        safe_kw = args.keyword.replace("/", "_")
        args.output = Path(f"search_{safe_kw}_p{args.pages}.csv")

    out = write_search_csv(rows, args.output)

    summary = filter_summary(rows)
    print(f"keyword:  {args.keyword}")
    print(f"pages:    {args.pages}")
    print(f"rows:     {len(rows)} videos")
    print(f"eligible: {summary['eligible']} (after auto-filter)")
    print(f"excluded: {summary['excluded']}")
    print(f"saved:    {out.resolve()}")


if __name__ == "__main__":
    asyncio.run(main())
