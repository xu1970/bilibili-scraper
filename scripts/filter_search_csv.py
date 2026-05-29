#!/usr/bin/env python3
"""Apply automatic exclusion filters to a search results CSV."""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bilibili_comments.export import write_search_csv
from bilibili_comments.filter_videos import apply_search_filters, filter_summary, is_eligible_for_sampling
from bilibili_comments.exclude_sampled import apply_exclude_aids, collect_sampled_aids
from bilibili_comments.paths import search_csv
from bilibili_comments.sample import assign_eligible_ranks, load_search_csv

DEFAULT_KEYWORD = "生育"


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply auto-filters to search results CSV")
    parser.add_argument("--keyword", default=DEFAULT_KEYWORD, help="Search keyword (used for default filenames)")
    parser.add_argument("--input", type=Path, default=None, help="Search CSV (default: search_<keyword>.csv)")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output path (default: overwrite --input)",
    )
    parser.add_argument(
        "--exclude-sampled",
        type=Path,
        action="append",
        default=[],
        help="A sampled CSV to exclude (can be repeated). Example: search_生育_sampled.csv",
    )
    parser.add_argument(
        "--exclude-sampled-glob",
        default="search_*_sampled*.csv",
        help="Glob (relative to current directory) for sampled CSVs to exclude",
    )
    args = parser.parse_args()

    if args.input is None:
        args.input = search_csv(args.keyword)

    rows = load_search_csv(args.input)
    if not rows:
        print("No rows found.")
        return

    # Require metadata from a fresh search export
    if "danmaku" not in rows[0] and rows[0].get("danmaku", "") == "":
        missing = sum(1 for r in rows if not str(r.get("tags", "")))
        if missing == len(rows):
            print(
                "Warning: CSV may lack tags/danmaku. Re-run search_to_csv.py first for accurate filters."
            )

    # Exclude previously sampled aids (across other keywords).
    sampled_paths: list[Path] = list(args.exclude_sampled)
    if args.exclude_sampled_glob:
        sampled_paths.extend(sorted(Path(".").glob(args.exclude_sampled_glob)))
    sampled_paths = [p for p in sampled_paths if p.is_file() and p.resolve() != args.input.resolve()]
    excluded_aids = collect_sampled_aids(sampled_paths)
    if excluded_aids:
        apply_exclude_aids(rows, excluded_aids, reason="already_sampled")

    apply_search_filters(rows)
    assign_eligible_ranks(rows)
    out_path = args.output or args.input
    write_search_csv(rows, out_path)

    summary = filter_summary(rows)
    reasons = Counter(
        r["exclusion_reason"].split("; ")[0]
        for r in rows
        if r.get("exclusion_reason")
    )

    print(f"saved:    {out_path.resolve()}")
    print(f"total:    {summary['total']}")
    print(f"eligible: {summary['eligible']}")
    print(f"excluded: {summary['excluded']}")
    print(f"in_sample:{summary['in_sample']}")
    if excluded_aids:
        print(f"excluded (already_sampled): {sum(1 for r in rows if 'already_sampled' in str(r.get('exclusion_reason','')))}")
    print("top exclusion reasons:")
    for reason, count in reasons.most_common(10):
        print(f"  {reason}: {count}")


if __name__ == "__main__":
    main()
