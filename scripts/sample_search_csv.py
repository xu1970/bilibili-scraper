#!/usr/bin/env python3
"""Rank-based sample from filtered search results."""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bilibili_comments.export import write_sampled_search_csv, write_search_csv
from bilibili_comments.filter_videos import apply_search_filters, filter_summary
from bilibili_comments.paths import sampled_csv, search_csv
from bilibili_comments.sample import (
    ADAPTIVE_SAMPLE_ELIGIBLE_THRESHOLD,
    MID_SAMPLE_MAX,
    MIN_VIEW_COUNT,
    TAKE_ALL_ELIGIBLE_THRESHOLD,
    TARGET_SAMPLE_TOTAL,
    TOP_SAMPLE_COUNT,
    assign_eligible_ranks,
    eligible_for_sampling,
    load_search_csv,
    mark_rows_in_sample,
    rank_based_sample_videos,
)

DEFAULT_KEYWORD = "生育"


def main() -> None:
    parser = argparse.ArgumentParser(description="Rank-based sample of search results")
    parser.add_argument("--keyword", default=DEFAULT_KEYWORD, help="Search keyword (used for default filenames)")
    parser.add_argument("--input", type=Path, default=None, help="Search CSV (default: search_<keyword>.csv)")
    parser.add_argument("--output", type=Path, default=None, help="Sampled CSV (default: search_<keyword>_sampled.csv)")
    parser.add_argument(
        "--min-views",
        type=int,
        default=MIN_VIEW_COUNT,
        help="Minimum view_count to include",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducible sampling",
    )
    args = parser.parse_args()

    if args.input is None:
        args.input = search_csv(args.keyword)
    if args.output is None:
        args.output = sampled_csv(args.keyword)

    rows = load_search_csv(args.input)
    apply_search_filters(rows)
    assign_eligible_ranks(rows)

    for row in rows:
        row["in_sample"] = "no"

    sampled = rank_based_sample_videos(
        rows, min_view_count=args.min_views, seed=args.seed
    )
    mark_rows_in_sample(rows, sampled)

    write_search_csv(rows, args.input)
    out = write_sampled_search_csv(sampled, args.output)
    summary = filter_summary(rows)

    eligible_count = sum(
        1
        for r in rows
        if r.get("eligible_rank") != ""
        and eligible_for_sampling(r, min_view_count=args.min_views)
    )

    buckets = Counter(r.get("sample_bucket") for r in sampled)
    print(f"input:      {args.input.resolve()} (ranks + in_sample updated)")
    print(f"eligible:   {summary['eligible']} videos passed auto-filter")
    print(f"in pool:    {eligible_count} videos (auto-filter + min-views {args.min_views})")
    if eligible_count < TAKE_ALL_ELIGIBLE_THRESHOLD:
        mode = f"take-all (pool < {TAKE_ALL_ELIGIBLE_THRESHOLD}, no sampling)"
        print(f"plan:       {mode}, total={len(sampled)}")
    else:
        mode = (
            "adaptive tiers"
            if eligible_count < ADAPTIVE_SAMPLE_ELIGIBLE_THRESHOLD
            else f"top={TOP_SAMPLE_COUNT}, mid<={MID_SAMPLE_MAX}"
        )
        print(f"plan:       {mode}, total={TARGET_SAMPLE_TOTAL}")
    print(f"seed:       {args.seed}")
    print(f"sampled:    {len(sampled)} videos")
    print(f"by bucket:  {dict(sorted(buckets.items()))}")
    print(f"saved:      {out.resolve()}")


if __name__ == "__main__":
    main()
