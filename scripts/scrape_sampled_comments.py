#!/usr/bin/env python3
"""Scrape primary + secondary comments for sampled videos."""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bilibili_comments.auth import load_credential
from bilibili_comments.request_guard import configure_http_timeouts
from bilibili_comments.export import write_sampled_comments_csv
from bilibili_comments.scrape import CommentSort
from bilibili_comments.scrape_sampled import (
    completed_aid_set,
    load_existing_comments_csv,
    load_sampled_videos,
    merge_comments_for_video,
    resume_state_path,
    scrape_sampled_videos,
    scrape_video_comments,
)
from bilibili_comments.video import parse_video_ref

DEFAULT_SAMPLED = Path("search_生育_p20_sampled.csv")
DEFAULT_MASTER = Path("search_生育_p20.csv")
DEFAULT_OUTPUT = Path("comments_sampled_生育.csv")


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape comments for videos in the sampled CSV"
    )
    parser.add_argument("--sampled", type=Path, default=DEFAULT_SAMPLED)
    parser.add_argument("--master", type=Path, default=DEFAULT_MASTER)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--bvid",
        default=None,
        help="Scrape only this BV id (for testing); merges into existing output CSV",
    )
    parser.add_argument(
        "--sort",
        choices=("hot", "newest"),
        default="hot",
        help="Comment sort mode",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Base seconds between requests (actual pause is random in [0.5×, 1.5×] this value)",
    )
    parser.add_argument(
        "--max-primaries",
        type=int,
        default=None,
        metavar="N",
        help="Stop after N primary comments per video (default: no limit)",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Re-scrape all videos even if already present in the output file",
    )
    args = parser.parse_args()

    configure_http_timeouts()
    credential = load_credential()
    sort = CommentSort.HOT if args.sort == "hot" else CommentSort.NEWEST
    resume = not args.no_resume

    if args.bvid:
        ref = parse_video_ref(args.bvid)
        videos = load_sampled_videos(args.sampled, master_path=args.master)
        match = next((v for v in videos if str(v.get("aid")) == str(ref.aid)), None)
        video = match or {
            "aid": str(ref.aid),
            "bvid": ref.bvid,
            "title": "",
            "sample_bucket": "",
            "eligible_rank": "",
        }
        print(f"test bvid: {ref.bvid} (aid {ref.aid})")
        print(f"primary:   ALL top-level comments")
        print(f"sort:      {sort.label}")
        new_rows = await scrape_video_comments(
            video,
            credential,
            sort=sort,
            delay_seconds=args.delay,
            max_primaries=args.max_primaries,
        )
        existing = load_existing_comments_csv(args.output)
        merged = merge_comments_for_video(existing, new_rows, str(ref.aid))
        out = write_sampled_comments_csv(merged, args.output)
        levels = Counter(r.get("comment_level") for r in new_rows)
        print(f"this video: {len(new_rows)} comments ({dict(levels)})")
        print(f"csv total:  {len(merged)} rows")
        print(f"saved:      {out.resolve()}")
        return

    videos = load_sampled_videos(args.sampled, master_path=args.master)
    if not videos:
        print("No videos to scrape (check sampled CSV / review_marker).")
        return

    print(f"videos:   {len(videos)}")
    print(f"primary:  ALL top-level comments")
    print(f"sort:     {sort.label}")
    print(f"delay:    {args.delay}s (randomized)")
    print(f"output:   {args.output.resolve()}")
    print(f"resume:   {resume} ({resume_state_path(args.output).name})")

    rows = await scrape_sampled_videos(
        videos,
        credential,
        sort=sort,
        delay_seconds=args.delay,
        max_primaries=args.max_primaries,
        output_path=args.output,
        resume=resume,
    )

    out = write_sampled_comments_csv(rows, args.output)
    levels = Counter(r.get("comment_level") for r in rows)

    print(f"comments: {len(rows)} ({dict(levels)})")
    print(f"saved:    {out.resolve()}")


if __name__ == "__main__":
    asyncio.run(main())
