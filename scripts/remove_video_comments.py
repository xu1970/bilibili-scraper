#!/usr/bin/env python3
"""Remove scraped comments for one or more BV ids so they can be re-scraped."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bilibili_comments.remove_video_comments import (
    remove_comments_for_video,
    remove_comments_for_videos,
)

DEFAULT_OUTPUT = Path("comments_sampled_生育.csv")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Remove all comment rows for the given BV id(s) from the sampled "
            "comments CSV and clear them from the resume sidecar."
        )
    )
    parser.add_argument(
        "bvid",
        nargs="+",
        help="One or more BV ids (e.g. BV1s44y1n7aN)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Comments CSV to update",
    )
    parser.add_argument(
        "--keep-resume",
        action="store_true",
        help="Do not remove the video from the resume sidecar (only delete CSV rows)",
    )
    args = parser.parse_args()

    update_resume = not args.keep_resume

    if len(args.bvid) == 1:
        result = remove_comments_for_video(
            args.bvid[0],
            args.output,
            update_resume=update_resume,
        )
        print(f"BV:         {result['bvid']}")
        print(f"aid:        {result['aid']}")
        print(f"removed:    {result['removed']} comment rows")
        print(f"remaining:  {result['remaining']} rows in CSV")
        if update_resume:
            print(
                f"resume:     {'cleared' if result['was_in_resume'] else 'not listed (already absent)'}"
            )
        print(f"saved:      {result['comments_path']}")
        return

    results = remove_comments_for_videos(
        args.bvid,
        args.output,
        update_resume=update_resume,
    )
    total_removed = sum(r["removed"] for r in results)
    print(f"output:     {args.output.resolve()}")
    print(f"removed:    {total_removed} rows across {len(results)} video(s)")
    print(f"remaining:  {results[0]['remaining'] if results else 0} rows in CSV")
    for r in results:
        resume_note = ""
        if update_resume:
            resume_note = (
                ", resume cleared"
                if r["was_in_resume"]
                else ", not in resume"
            )
        print(f"  {r['bvid']}: {r['removed']} rows removed{resume_note}")


if __name__ == "__main__":
    main()
