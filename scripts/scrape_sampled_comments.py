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
from bilibili_comments.export import IncrementalCommentSink, write_sampled_comments_csv
from bilibili_comments.paths import comments_csv, sampled_csv, search_csv
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

DEFAULT_KEYWORD = "生育"


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape comments for videos in the sampled CSV"
    )
    parser.add_argument("--keyword", default=DEFAULT_KEYWORD, help="Search keyword (used for default filenames)")
    parser.add_argument("--sampled", type=Path, default=None, help="Sampled CSV (default: search_<keyword>_sampled.csv)")
    parser.add_argument("--master", type=Path, default=None, help="Master search CSV (default: search_<keyword>.csv)")
    parser.add_argument("--output", type=Path, default=None, help="Comments CSV (default: comments_sampled_<keyword>.csv)")
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

    if args.sampled is None:
        args.sampled = sampled_csv(args.keyword)
    if args.master is None:
        args.master = search_csv(args.keyword)
    if args.output is None:
        args.output = comments_csv(args.keyword)

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
        existing = load_existing_comments_csv(args.output)
        kept = [
            r
            for r in existing
            if str(r.get("video_aid", r.get("aid", ""))) != str(ref.aid)
        ]
        sink = IncrementalCommentSink.prepare_video_output(
            args.output, str(ref.aid), keep_rows=kept
        )
        row_count = await scrape_video_comments(
            video,
            credential,
            sort=sort,
            delay_seconds=args.delay,
            max_primaries=args.max_primaries,
            sink=sink,
        )
        sink.close()
        merged = load_existing_comments_csv(args.output)
        print(f"this video: {row_count} comments saved")
        print(f"csv total:  {len(merged)} rows")
        print(f"saved:      {args.output.resolve()}")
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

    levels = Counter(r.get("comment_level") for r in rows)
    print(f"comments: {len(rows)} ({dict(levels)})")
    print(f"saved:    {args.output.resolve()}")


if __name__ == "__main__":
    asyncio.run(main())
