"""Manual review and replacement of rank-based samples."""

from __future__ import annotations

import csv
import random
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .filter_videos import is_eligible_for_sampling
from .sample import (
    BLOCK_SIZE,
    MID_RANK_END,
    MID_RANK_START,
    MIN_VIEW_COUNT,
    REST_RANK_START,
    TOP_RANK_END,
    _block_bucket_name,
    _parse_view_count,
    load_search_csv,
)

# Values in ``review_marker`` that mean "replace this row".
IRRELEVANT_MARKERS = frozenset(
    {
        "irrelevant",
        "exclude",
        "no",
        "x",
        "0",
        "false",
        "reject",
        "skip",
    }
)

REVIEW_MARKER_OK = ""


def is_irrelevant(marker: Any) -> bool:
    """Return True if the review marker means the video should be replaced."""
    if marker is None:
        return False
    text = str(marker).strip().lower()
    if not text:
        return False
    return text in IRRELEVANT_MARKERS


def load_sampled_csv(path: Path | str) -> list[dict[str, Any]]:
    """Load a sampled videos CSV (with optional ``review_marker`` column)."""
    rows: list[dict[str, Any]] = []
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            er = row.get("eligible_rank", "")
            rows.append(
                {
                    "page": int(row["page"]),
                    "rank": int(row["rank"]),
                    "title": row.get("title", ""),
                    "view_count": _parse_view_count(row.get("view_count")),
                    "aid": str(row.get("aid", "")),
                    "eligible_rank": int(er) if str(er).strip().isdigit() else "",
                    "sample_bucket": row.get("sample_bucket", ""),
                    "review_marker": row.get("review_marker", "").strip(),
                }
            )
    return rows


def _bucket_name_for_row(row: dict[str, Any]) -> str:
    bucket = row.get("sample_bucket") or ""
    if bucket:
        return bucket
    er = row.get("eligible_rank")
    if er == "" or er is None:
        return ""
    er = int(er)
    if er <= TOP_RANK_END:
        return "top_1-50"
    if er <= MID_RANK_END:
        return "mid_51-350"
    return "rest_351+"


def _tier_block_bounds(bucket_name: str) -> tuple[int, int] | None:
    """Parse ``tier_{k}_rank{start}-{end}`` adaptive bucket names."""
    if not bucket_name.startswith("tier_"):
        return None
    try:
        block_index = int(bucket_name.split("_", 2)[1])
    except (IndexError, ValueError):
        return None
    start = block_index * BLOCK_SIZE + 1
    end = (block_index + 1) * BLOCK_SIZE
    return start, end


def _eligible_rank_in_bucket(eligible_rank: int, bucket_name: str) -> bool:
    tier_bounds = _tier_block_bounds(bucket_name)
    if tier_bounds is not None:
        start, end = tier_bounds
        return start <= eligible_rank <= end
    if bucket_name == "top_1-50":
        return eligible_rank <= TOP_RANK_END
    if bucket_name == "mid_51-350":
        return MID_RANK_START <= eligible_rank <= MID_RANK_END
    if bucket_name == "rest_351+":
        return eligible_rank >= REST_RANK_START
    return False


def _pool_candidates_for_bucket(
    pool: list[dict[str, Any]],
    bucket_name: str,
    *,
    min_view_count: int,
    reserved_aids: set[str],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for candidate in pool:
        er = candidate.get("eligible_rank")
        if er == "" or er is None:
            continue
        if not _eligible_rank_in_bucket(int(er), bucket_name):
            continue
        if not is_eligible_for_sampling(candidate):
            continue
        if _parse_view_count(candidate.get("view_count")) < min_view_count:
            continue
        aid = str(candidate.get("aid", ""))
        if not aid or aid in reserved_aids:
            continue
        candidates.append(candidate)
    return candidates


def _bucket_fallback_chain(bucket_name: str) -> tuple[str, ...]:
    """If a bucket is exhausted, try earlier rank tiers, then legacy buckets."""
    tier_bounds = _tier_block_bounds(bucket_name)
    if tier_bounds is not None:
        block_index = int(bucket_name.split("_", 2)[1])
        fallbacks = [_block_bucket_name(i) for i in range(block_index - 1, -1, -1)]
        return tuple(fallbacks)
    return _LEGACY_BUCKET_FALLBACK.get(bucket_name, ())


# If a rank bucket has no spare videos, try the next broader bucket.
_LEGACY_BUCKET_FALLBACK: dict[str, tuple[str, ...]] = {
    "rest_351+": ("mid_51-350", "top_1-50"),
    "mid_51-350": ("top_1-50",),
}


def find_replacement_candidate(
    pool: list[dict[str, Any]],
    bucket_name: str,
    rng: random.Random,
    *,
    min_view_count: int,
    reserved_aids: set[str],
) -> tuple[dict[str, Any], str]:
    """
    Pick a replacement from the same rank bucket (with fallback if exhausted).

    Returns (candidate row, pool bucket actually drawn from).
    """
    buckets_to_try = (bucket_name, *_bucket_fallback_chain(bucket_name))
    for try_bucket in buckets_to_try:
        eligible = _pool_candidates_for_bucket(
            pool,
            try_bucket,
            min_view_count=min_view_count,
            reserved_aids=reserved_aids,
        )
        if eligible:
            return rng.choice(eligible), try_bucket

    raise RuntimeError(
        f"No replacement available for sample bucket {bucket_name!r} "
        f"(including fallbacks {buckets_to_try[1:]!r}). "
        f"All eligible videos in those rank ranges are already in the sample."
    )


def _row_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "page": row.get("page"),
        "rank": row.get("rank"),
        "eligible_rank": row.get("eligible_rank"),
        "sample_bucket": row.get("sample_bucket"),
        "title": row.get("title"),
        "view_count": row.get("view_count"),
        "aid": row.get("aid"),
    }


def apply_review_replacements(
    sampled: list[dict[str, Any]],
    pool: list[dict[str, Any]],
    *,
    min_view_count: int = MIN_VIEW_COUNT,
    seed: int | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Replace rows marked irrelevant with new random draws from the same rank bucket.

    Preserves per-bucket sample counts. Avoids duplicate ``aid`` values in the
    final sample.
    """
    rng = random.Random(seed)
    updated = deepcopy(sampled)

    reserved_aids: set[str] = {
        str(r["aid"])
        for r in updated
        if str(r.get("aid", "")) and not is_irrelevant(r.get("review_marker", ""))
    }

    log_entries: list[dict[str, Any]] = []
    replaced_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    irrelevant_indices = [
        i for i, r in enumerate(updated) if is_irrelevant(r.get("review_marker", ""))
    ]

    for idx in irrelevant_indices:
        row = updated[idx]
        bucket_name = _bucket_name_for_row(row)
        original = _row_snapshot(row)

        replacement, pool_bucket = find_replacement_candidate(
            pool,
            bucket_name,
            rng,
            min_view_count=min_view_count,
            reserved_aids=reserved_aids,
        )
        aid = str(replacement["aid"])
        reserved_aids.add(aid)

        updated[idx] = {
            "page": int(replacement["page"]),
            "rank": int(replacement["rank"]),
            "title": replacement.get("title", ""),
            "view_count": _parse_view_count(replacement.get("view_count")),
            "aid": aid,
            "eligible_rank": replacement.get("eligible_rank", ""),
            "sample_bucket": bucket_name,
            "review_marker": REVIEW_MARKER_OK,
        }

        log_entries.append(
            {
                "replaced_at": replaced_at,
                "page": original["page"],
                "sample_bucket": bucket_name,
                "pool_bucket": pool_bucket,
                "original_rank": original["rank"],
                "original_eligible_rank": original["eligible_rank"],
                "original_title": original["title"],
                "original_view_count": original["view_count"],
                "original_aid": original["aid"],
                "replacement_rank": updated[idx]["rank"],
                "replacement_eligible_rank": updated[idx]["eligible_rank"],
                "replacement_title": updated[idx]["title"],
                "replacement_view_count": updated[idx]["view_count"],
                "replacement_aid": updated[idx]["aid"],
            }
        )

    return updated, log_entries


def load_replacement_log(path: Path | str) -> list[dict[str, Any]]:
    """Load an existing replacement log CSV, or return [] if missing."""
    p = Path(path)
    if not p.is_file():
        return []
    with p.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))
