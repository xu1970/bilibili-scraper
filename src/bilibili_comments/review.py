"""Manual review and replacement of stratified samples."""

from __future__ import annotations

import csv
import random
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .filter_videos import is_eligible_for_sampling
from .sample import MIN_VIEW_COUNT, _parse_view_count, load_search_csv

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
            rows.append(
                {
                    "page": int(row["page"]),
                    "rank": int(row["rank"]),
                    "title": row.get("title", ""),
                    "view_count": _parse_view_count(row.get("view_count")),
                    "aid": str(row.get("aid", "")),
                    "review_marker": row.get("review_marker", "").strip(),
                }
            )
    return rows


def _group_by_page(rows: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    by_page: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        page = int(row["page"])
        by_page.setdefault(page, []).append(row)
    return by_page


def _row_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "page": row.get("page"),
        "rank": row.get("rank"),
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
    Replace rows marked irrelevant with new random draws from the same page.

    Preserves per-page sample counts. Avoids duplicate ``aid`` values in the
    final sample. Returns updated rows and a list of replacement log entries.
    """
    rng = random.Random(seed)
    pool_by_page = _group_by_page(pool)
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
        page = int(row["page"])
        original = _row_snapshot(row)

        eligible = [
            candidate
            for candidate in pool_by_page.get(page, [])
            if is_eligible_for_sampling(candidate)
            and _parse_view_count(candidate.get("view_count")) >= min_view_count
            and str(candidate.get("aid", ""))
            and str(candidate["aid"]) not in reserved_aids
        ]

        if not eligible:
            raise RuntimeError(
                f"No replacement available for page {page} "
                f"(aid={row.get('aid')!r}). "
                f"All eligible videos on this page are already in the sample."
            )

        replacement = rng.choice(eligible)
        aid = str(replacement["aid"])
        reserved_aids.add(aid)

        updated[idx] = {
            "page": int(replacement["page"]),
            "rank": int(replacement["rank"]),
            "title": replacement.get("title", ""),
            "view_count": _parse_view_count(replacement.get("view_count")),
            "aid": aid,
            "review_marker": REVIEW_MARKER_OK,
        }

        log_entries.append(
            {
                "replaced_at": replaced_at,
                "page": page,
                "original_rank": original["rank"],
                "original_title": original["title"],
                "original_view_count": original["view_count"],
                "original_aid": original["aid"],
                "replacement_rank": updated[idx]["rank"],
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
