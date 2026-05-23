#!/usr/bin/env python3
"""
Apply manual review markers in a sampled CSV.

Mark irrelevant videos in the ``review_marker`` column (e.g. ``irrelevant``),
then run this script to swap them for new random videos from the same search page.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bilibili_comments.export import write_replacement_log, write_sampled_search_csv
from bilibili_comments.review import (
    IRRELEVANT_MARKERS,
    apply_review_replacements,
    is_irrelevant,
    load_sampled_csv,
)
from bilibili_comments.sample import MIN_VIEW_COUNT, load_search_csv

DEFAULT_SAMPLED = Path("search_生育_p20_sampled.csv")
DEFAULT_POOL = Path("search_生育_p20.csv")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Replace sampled videos marked irrelevant in review_marker column"
    )
    parser.add_argument("--sampled", type=Path, default=DEFAULT_SAMPLED)
    parser.add_argument(
        "--pool",
        type=Path,
        default=DEFAULT_POOL,
        help="Full search results CSV to draw replacements from",
    )
    parser.add_argument(
        "--log",
        type=Path,
        default=None,
        help="Replacement log CSV (default: <sampled stem>_replacements.csv)",
    )
    parser.add_argument("--min-views", type=int, default=MIN_VIEW_COUNT)
    parser.add_argument("--seed", type=int, default=42, help="Random seed for redraws")
    parser.add_argument(
        "--init-only",
        action="store_true",
        help="Only add empty review_marker column; do not replace",
    )
    args = parser.parse_args()

    sampled = load_sampled_csv(args.sampled)
    has_marker_col = "review_marker" in sampled[0] if sampled else True

    if args.init_only:
        write_sampled_search_csv(sampled, args.sampled)
        print(f"Added review_marker column to {args.sampled.resolve()}")
        print(f"Mark irrelevant rows with one of: {', '.join(sorted(IRRELEVANT_MARKERS))}")
        return

    irrelevant = [r for r in sampled if is_irrelevant(r.get("review_marker", ""))]
    if not irrelevant:
        # Ensure column exists for manual editing
        write_sampled_search_csv(sampled, args.sampled)
        print(f"No rows marked irrelevant in {args.sampled.resolve()}")
        print(f"Edit review_marker column, then re-run. Accepted values:")
        print(f"  {', '.join(sorted(IRRELEVANT_MARKERS))}")
        if not has_marker_col:
            print("(Added empty review_marker column.)")
        return

    pool = load_search_csv(args.pool)
    updated, log_entries = apply_review_replacements(
        sampled,
        pool,
        min_view_count=args.min_views,
        seed=args.seed,
    )

    write_sampled_search_csv(updated, args.sampled)

    if args.log is None:
        args.log = args.sampled.with_name(f"{args.sampled.stem}_replacements.csv")

    write_replacement_log(log_entries, args.log, append=True)

    counts = Counter(int(r["page"]) for r in updated)
    print(f"replaced:  {len(log_entries)} video(s)")
    print(f"sampled:   {args.sampled.resolve()} (updated)")
    print(f"log:       {args.log.resolve()} (appended)")
    print(f"per page:  {dict(sorted(counts.items()))}")
    for entry in log_entries:
        print(
            f"  page {entry['page']}: "
            f"aid {entry['original_aid']} -> {entry['replacement_aid']}"
        )


if __name__ == "__main__":
    main()
