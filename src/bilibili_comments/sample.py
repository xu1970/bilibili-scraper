"""Rank-based sampling of filtered search result videos."""

from __future__ import annotations

import csv
import random
from pathlib import Path
from typing import Any

from .filter_videos import is_eligible_for_sampling

MIN_VIEW_COUNT = 1000

# Rank buckets use ``eligible_rank`` (position among eligible videos in search order).
TOP_RANK_END = 50
MID_RANK_START = 51
MID_RANK_END = 350
REST_RANK_START = 351

TOP_SAMPLE_COUNT = 15  # 20% of top 50
MID_SAMPLE_RATE = 0.10  # 10% of ranks 51–350 (up to 30 when bucket is full)
MID_SAMPLE_MAX = int((MID_RANK_END - MID_RANK_START + 1) * MID_SAMPLE_RATE)  # 30
TARGET_SAMPLE_TOTAL = TOP_SAMPLE_COUNT + MID_SAMPLE_MAX + 10  # 50


def _parse_view_count(value: Any) -> int:
    if value is None or value == "":
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def load_search_csv(path: Path | str) -> list[dict[str, Any]]:
    """Load rows from a search results CSV."""
    rows: list[dict[str, Any]] = []
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            er = row.get("eligible_rank", "")
            rows.append(
                {
                    "page": int(row["page"]),
                    "rank": int(row["rank"]),
                    "bvid": row.get("bvid", ""),
                    "title": row.get("title", ""),
                    "uploader": row.get("uploader", ""),
                    "view_count": _parse_view_count(row.get("view_count")),
                    "aid": row.get("aid", ""),
                    "tags": row.get("tags", row.get("tag", "")),
                    "typename": row.get("typename", ""),
                    "danmaku": _parse_view_count(row.get("danmaku")),
                    "in_sample": row.get("in_sample", "no"),
                    "exclusion_reason": row.get("exclusion_reason", ""),
                    "search_rank": _parse_view_count(row.get("search_rank")) or "",
                    "eligible_rank": int(er) if str(er).strip().isdigit() else "",
                }
            )
    return rows


def sort_search_order(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort rows in search output order (page, then rank within page)."""
    return sorted(rows, key=lambda r: (int(r["page"]), int(r["rank"])))


def assign_search_ranks(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Assign ``search_rank`` (1-based) across all results in search order."""
    ordered = sort_search_order(rows)
    for i, row in enumerate(ordered, start=1):
        row["search_rank"] = i
    return ordered


def eligible_for_sampling(row: dict[str, Any], *, min_view_count: int) -> bool:
    """Row passes auto-filters and minimum view count."""
    if not is_eligible_for_sampling(row):
        return False
    return _parse_view_count(row.get("view_count")) >= min_view_count


def assign_eligible_ranks(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Assign ``eligible_rank`` among auto-filtered rows in search order."""
    ordered = assign_search_ranks(rows)
    rank = 0
    for row in ordered:
        if is_eligible_for_sampling(row):
            rank += 1
            row["eligible_rank"] = rank
        else:
            row["eligible_rank"] = ""
    return ordered


def _bucket_for_eligible_rank(eligible_rank: int) -> str:
    if eligible_rank <= TOP_RANK_END:
        return "top_1-50"
    if eligible_rank <= MID_RANK_END:
        return "mid_51-350"
    return "rest_351+"


def _sample_from_bucket(
    rng: random.Random,
    bucket: list[dict[str, Any]],
    n: int,
    bucket_name: str,
) -> list[dict[str, Any]]:
    if n <= 0 or not bucket:
        return []
    k = min(n, len(bucket))
    chosen = rng.sample(bucket, k)
    for row in chosen:
        row["sample_bucket"] = bucket_name
        row["review_marker"] = ""
    return chosen


def rank_based_sample_videos(
    rows: list[dict[str, Any]],
    *,
    min_view_count: int = MIN_VIEW_COUNT,
    seed: int | None = None,
) -> list[dict[str, Any]]:
    """
    Sample from the filtered list in search output order.

    - Top eligible ranks 1–50: 10 videos (20% of 50)
    - Ranks 51–350: 10% of that range (up to 30 videos)
    - Rank 351+: remainder to reach 50 total (up to 10 videos)
    """
    rng = random.Random(seed)
    ordered = assign_eligible_ranks(rows)

    eligible = [
        r
        for r in ordered
        if r.get("eligible_rank") != "" and eligible_for_sampling(r, min_view_count=min_view_count)
    ]
    top = [r for r in eligible if int(r["eligible_rank"]) <= TOP_RANK_END]
    mid = [
        r
        for r in eligible
        if MID_RANK_START <= int(r["eligible_rank"]) <= MID_RANK_END
    ]
    rest = [r for r in eligible if int(r["eligible_rank"]) >= REST_RANK_START]

    n_top = min(TOP_SAMPLE_COUNT, len(top))
    n_mid = min(MID_SAMPLE_MAX, int(len(mid) * MID_SAMPLE_RATE))
    n_rest_target = max(0, TARGET_SAMPLE_TOTAL - n_top - n_mid)

    sampled: list[dict[str, Any]] = []
    sampled.extend(_sample_from_bucket(rng, top, n_top, "top_1-50"))
    sampled.extend(_sample_from_bucket(rng, mid, n_mid, "mid_51-350"))

    sampled_aids = {str(r["aid"]) for r in sampled}
    rest_available = [r for r in rest if str(r["aid"]) not in sampled_aids]
    n_rest = min(len(rest_available), n_rest_target)
    sampled.extend(_sample_from_bucket(rng, rest_available, n_rest, "rest_351+"))
    sampled_aids = {str(r["aid"]) for r in sampled}

    shortfall = TARGET_SAMPLE_TOTAL - len(sampled)
    if shortfall > 0:
        mid_remaining = [
            r for r in mid if str(r["aid"]) not in sampled_aids
        ]
        spill = _sample_from_bucket(rng, mid_remaining, shortfall, "mid_51-350")
        sampled.extend(spill)
        sampled_aids = {str(r["aid"]) for r in sampled}
        shortfall = TARGET_SAMPLE_TOTAL - len(sampled)

    if shortfall > 0:
        top_remaining = [
            r for r in top if str(r["aid"]) not in sampled_aids
        ]
        spill = _sample_from_bucket(rng, top_remaining, shortfall, "top_1-50")
        sampled.extend(spill)

    sampled.sort(key=lambda r: int(r["eligible_rank"]))
    return sampled


def mark_rows_in_sample(
    pool: list[dict[str, Any]], sampled: list[dict[str, Any]]
) -> None:
    """Set ``in_sample=yes`` on pool rows whose aid appears in ``sampled``."""
    sampled_aids = {str(row["aid"]) for row in sampled if str(row.get("aid", ""))}
    for row in pool:
        if str(row.get("aid", "")) in sampled_aids:
            row["in_sample"] = "yes"
        elif row.get("in_sample", "no").lower() != "yes":
            row["in_sample"] = "no"
