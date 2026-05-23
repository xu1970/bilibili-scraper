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
from bilibili_comments.sample import load_search_csv

DEFAULT_INPUT = Path("search_生育_p20.csv")


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply auto-filters to search results CSV")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output path (default: overwrite --input)",
    )
    args = parser.parse_args()

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

    apply_search_filters(rows)
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
    print("top exclusion reasons:")
    for reason, count in reasons.most_common(10):
        print(f"  {reason}: {count}")


if __name__ == "__main__":
    main()
