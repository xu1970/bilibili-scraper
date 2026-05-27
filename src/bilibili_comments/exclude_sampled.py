"""Exclude videos that have already been sampled under other keywords."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


def _read_aids_from_sampled_csv(path: Path | str) -> set[str]:
    p = Path(path)
    if not p.is_file():
        return set()
    with p.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        aids: set[str] = set()
        for row in reader:
            aid = str(row.get("aid", "") or "").strip()
            if aid:
                aids.add(aid)
    return aids


def collect_sampled_aids(sampled_csv_paths: list[Path | str]) -> set[str]:
    """Union all `aid` values in the provided sampled CSVs."""
    aids: set[str] = set()
    for path in sampled_csv_paths:
        aids |= _read_aids_from_sampled_csv(path)
    return aids


def apply_exclude_aids(
    rows: list[dict[str, Any]],
    excluded_aids: set[str],
    *,
    reason: str = "already_sampled",
) -> int:
    """
    Mark rows excluded when their `aid` is in `excluded_aids`.

    Uses `manual_exclusion_reason` so it participates in normal filtering logic.
    Returns count of rows newly marked excluded by this rule.
    """
    newly_excluded = 0
    for row in rows:
        aid = str(row.get("aid", "") or "").strip()
        if not aid or aid not in excluded_aids:
            continue
        existing = str(row.get("manual_exclusion_reason", "") or "").strip()
        if existing:
            # don't double-append the same reason
            if reason not in existing.split("; "):
                row["manual_exclusion_reason"] = f"{existing}; {reason}"
        else:
            row["manual_exclusion_reason"] = reason
        newly_excluded += 1
    return newly_excluded

