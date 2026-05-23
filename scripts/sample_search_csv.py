#!/usr/bin/env python3
"""Stratified sample from a search results CSV."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bilibili_comments.export import write_sampled_search_csv, write_search_csv
from bilibili_comments.filter_videos import apply_search_filters, filter_summary
from bilibili_comments.sample import (
    MIN_VIEW_COUNT,
    load_search_csv,
    mark_rows_in_sample,
    stratified_sample_videos,
)

DEFAULT_INPUT = Path("search_生育_p20.csv")


def main() -> None:
    parser = argparse.ArgumentParser(description="Stratified sample search results")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Search CSV")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output CSV (default: <input stem>_sampled.csv)",
    )
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

    rows = load_search_csv(args.input)
    apply_search_filters(rows)

    # Reset sample flags before drawing a new sample
    for row in rows:
        row["in_sample"] = "no"

    sampled = stratified_sample_videos(
        rows, min_view_count=args.min_views, seed=args.seed
    )
    mark_rows_in_sample(rows, sampled)

    if args.output is None:
        args.output = args.input.with_name(f"{args.input.stem}_sampled.csv")

    write_search_csv(rows, args.input)
    out = write_sampled_search_csv(sampled, args.output)
    summary = filter_summary(rows)

    # Summary by page
    from collections import Counter

    counts = Counter(int(r["page"]) for r in sampled)
    print(f"input:     {args.input.resolve()} (in_sample flags updated)")
    print(f"eligible:  {summary['eligible']} videos passed auto-filter")
    print(f"min views: {args.min_views}")
    print(f"seed:      {args.seed}")
    print(f"sampled:   {len(sampled)} videos")
    print(f"saved:     {out.resolve()}")
    print("per page:", dict(sorted(counts.items())))


if __name__ == "__main__":
    main()
