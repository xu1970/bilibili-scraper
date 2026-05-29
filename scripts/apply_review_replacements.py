#!/usr/bin/env python3
"""
Apply manual review markers in the sampled CSV.

Mark irrelevant rows in ``review_marker`` (e.g. ``x`` or ``irrelevant``), then run
this script. Each marked row is replaced by a random draw from the **same rank
bucket** (``top_1-50``, ``mid_51-350``, or ``rest_351+``) in the master search file.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bilibili_comments.export import (
    write_replacement_log,
    write_sampled_search_csv,
    write_search_csv,
)
from bilibili_comments.filter_videos import apply_search_filters
from bilibili_comments.paths import replacements_csv, sampled_csv, search_csv
from bilibili_comments.review import (
    IRRELEVANT_MARKERS,
    apply_review_replacements,
    is_irrelevant,
    load_sampled_csv,
)
from bilibili_comments.sample import (
    MIN_VIEW_COUNT,
    assign_eligible_ranks,
    load_search_csv,
    mark_rows_in_sample,
)

DEFAULT_KEYWORD = "生育"


def prepare_review_pool(path: Path) -> list[dict]:
    """Load master search CSV with filters and eligible_rank assigned."""
    rows = load_search_csv(path)
    apply_search_filters(rows)
    assign_eligible_ranks(rows)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Replace sampled videos marked x/irrelevant (same rank bucket)"
    )
    parser.add_argument("--keyword", default=DEFAULT_KEYWORD, help="Search keyword (used for default filenames)")
    parser.add_argument("--sampled", type=Path, default=None, help="Sampled CSV (default: search_<keyword>_sampled.csv)")
    parser.add_argument(
        "--pool",
        type=Path,
        default=None,
        help="Master search CSV (rank buckets defined by eligible_rank)",
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
        help="Only ensure review_marker column exists; do not replace",
    )
    parser.add_argument(
        "--no-sync-master",
        action="store_true",
        help="Do not update in_sample flags on the master search CSV",
    )
    args = parser.parse_args()

    if args.sampled is None:
        args.sampled = sampled_csv(args.keyword)
    if args.pool is None:
        args.pool = search_csv(args.keyword)
    if args.log is None:
        args.log = replacements_csv(args.keyword)

    sampled = load_sampled_csv(args.sampled)

    if args.init_only:
        write_sampled_search_csv(sampled, args.sampled)
        print(f"Ready for review: {args.sampled.resolve()}")
        print("Mark irrelevant rows in review_marker with one of:")
        print(f"  {', '.join(sorted(IRRELEVANT_MARKERS))}")
        print("Buckets (sample_bucket column):")
        print("  top_1-50   → redraw from eligible_rank 1–50")
        print("  mid_51-350 → redraw from eligible_rank 51–350")
        print("  rest_351+  → redraw from eligible_rank 351+")
        return

    irrelevant = [r for r in sampled if is_irrelevant(r.get("review_marker", ""))]
    if not irrelevant:
        write_sampled_search_csv(sampled, args.sampled)
        print(f"No rows marked for replacement in {args.sampled.resolve()}")
        print("Set review_marker to x (or irrelevant, exclude, etc.), then re-run.")
        return

    pool = prepare_review_pool(args.pool)
    updated, log_entries = apply_review_replacements(
        sampled,
        pool,
        min_view_count=args.min_views,
        seed=args.seed,
    )

    write_sampled_search_csv(updated, args.sampled)

    if not args.no_sync_master:
        for row in pool:
            row["in_sample"] = "no"
        mark_rows_in_sample(pool, updated)
        write_search_csv(pool, args.pool)

    write_replacement_log(log_entries, args.log, append=True)

    bucket_counts = Counter(r.get("sample_bucket") for r in updated)
    print(f"replaced:     {len(log_entries)} video(s)")
    print(f"sampled csv:  {args.sampled.resolve()}")
    if not args.no_sync_master:
        print(f"master csv:   {args.pool.resolve()} (in_sample synced)")
    print(f"log:          {args.log.resolve()} (appended)")
    print(f"sample size:  {len(updated)} by bucket: {dict(sorted(bucket_counts.items()))}")
    for entry in log_entries:
        pool_note = ""
        if entry.get("pool_bucket") and entry["pool_bucket"] != entry["sample_bucket"]:
            pool_note = f" [drawn from {entry['pool_bucket']}]"
        print(
            f"  {entry['sample_bucket']}{pool_note}: "
            f"eligible_rank {entry.get('original_eligible_rank')} "
            f"aid {entry['original_aid']} → {entry['replacement_aid']} "
            f"(new eligible_rank {entry.get('replacement_eligible_rank')})"
        )


if __name__ == "__main__":
    main()
