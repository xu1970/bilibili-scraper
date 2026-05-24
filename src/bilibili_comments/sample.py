"""Stratified sampling of search result videos."""

from __future__ import annotations

import csv
import random
from pathlib import Path
from typing import Any

from .filter_videos import is_eligible_for_sampling

# Samples per page by page range: (first_page, last_page, count).
DEFAULT_STRATA: tuple[tuple[int, int, int], ...] = (
    (1, 5, 5),
    (6, 10, 3),
    (11, 20, 1),
)

MIN_VIEW_COUNT = 1000


def _sample_size_for_page(page: int, strata: tuple[tuple[int, int, int], ...]) -> int:
    for start, end, count in strata:
        if start <= page <= end:
            return count
    return 0


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
                }
            )
    return rows


def eligible_for_stratified_sample(row: dict[str, Any], *, min_view_count: int) -> bool:
    """Row passes auto-filters and minimum view count."""
    if not is_eligible_for_sampling(row):
        return False
    return _parse_view_count(row.get("view_count")) >= min_view_count


def stratified_sample_videos(
    rows: list[dict[str, Any]],
    *,
    strata: tuple[tuple[int, int, int], ...] = DEFAULT_STRATA,
    min_view_count: int = MIN_VIEW_COUNT,
    seed: int | None = None,
) -> list[dict[str, Any]]:
    """
    Stratified random sample by search page.

    For each page, keep videos with ``view_count >= min_view_count``, then randomly
    draw up to the configured number of videos for that page's stratum.
    """
    rng = random.Random(seed)

    by_page: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        page = int(row["page"])
        by_page.setdefault(page, []).append(row)

    sampled: list[dict[str, Any]] = []
    for page in sorted(by_page):
        n = _sample_size_for_page(page, strata)
        if n <= 0:
            continue

        eligible = [
            r for r in by_page[page] if eligible_for_stratified_sample(r, min_view_count=min_view_count)
        ]
        if not eligible:
            continue

        k = min(n, len(eligible))
        chosen = rng.sample(eligible, k)
        chosen.sort(key=lambda r: int(r["rank"]))
        for row in chosen:
            row["review_marker"] = ""
        sampled.extend(chosen)

    return sampled


def mark_rows_in_sample(
    pool: list[dict[str, Any]], sampled: list[dict[str, Any]]
) -> None:
    """Set ``in_sample=yes`` on pool rows whose aid appears in ``sampled``."""
    sampled_aids = {str(row["aid"]) for row in sampled if str(row.get("aid", ""))}
    for row in pool:
        if str(row.get("aid", "")) in sampled_aids:
            row["in_sample"] = "yes"
