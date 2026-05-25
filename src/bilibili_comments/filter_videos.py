"""Automatic exclusion rules applied before stratified sampling."""

from __future__ import annotations

from re import I
from typing import Any

# (reason label, keywords matched in tags or typename/label)
CATEGORY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "category:mods/mod推荐",
        (
            "mod推荐",
            "模组推荐",
            "模组",
            "mods",
            "mod",
        ),
    ),
    (
        "category:games",
        (
            "游戏",
            "电竞",
            "单机",
            "网络游戏",
            "手游",
            "mugen",
            "game",
            "games",
        ),
    ),
    (
        "category:movies",
        (
            "电影",
            "影视",
            "单片",
            "剧情",
            "movies",
            "movie",
        ),
    ),
    (
        "category:animation",
        (
            "动画",
            "动漫",
            "番剧",
            "animation",
            "anime",
        ),
    ),
    (
        "category:fiction/literature/novels",
        (
            "小说",
            "文学",
            "网文",
            "轻小说",
            "读书",
            "fiction",
            "novel",
            "literature",
        ),
    ),
    (
        "category:food content",
        (
            "美食",
            "吃播",
            "烹饪",
            "厨艺",
            "探店",
            "零食",
            "food",
            "吃货",
        ),
    ),
)

MIN_DANMAKU_EXCLUSIVE = 10  # exclude when danmaku <= this value


def _parse_int(value: Any, default: int = 0) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _split_tags(tag_field: str) -> list[str]:
    return [part.strip().lower() for part in (tag_field or "").split(",") if part.strip()]


def _label_text(row: dict[str, Any]) -> str:
    """Combined lowercase text from tags and partition label (typename)."""
    tag_field = str(row.get("tags") or row.get("tag") or "")
    typename = str(row.get("typename") or row.get("label") or "")
    return f"{tag_field},{typename}".lower()


def _tag_tokens(row: dict[str, Any]) -> list[str]:
    return _split_tags(str(row.get("tags") or row.get("tag") or ""))


def _matches_category_keyword(keyword: str, row: dict[str, Any]) -> bool:
    kw = keyword.lower()
    label = _label_text(row)
    if kw in label:
        return True

    for token in _tag_tokens(row):
        if kw == "mod":
            if token in ("mod", "mods") or "mod推荐" in token or "模组" in token:
                return True
        elif token == kw or kw in token:
            return True
    return False


def category_exclusion_reasons(row: dict[str, Any]) -> list[str]:
    """Return category exclusion reason labels that apply to this row."""
    reasons: list[str] = []
    for reason_label, keywords in CATEGORY_RULES:
        if any(_matches_category_keyword(kw, row) for kw in keywords):
            reasons.append(reason_label)
    return reasons


def danmaku_exclusion_reason(row: dict[str, Any]) -> str | None:
    """Return exclusion reason if danmaku count is too low."""
    danmaku = _parse_int(row.get("danmaku"), default=-1)
    if danmaku <= MIN_DANMAKU_EXCLUSIVE:
        return "danmaku<=10"
    return None


def compute_exclusion_reason(row: dict[str, Any]) -> str:
    """
  Return a semicolon-separated exclusion reason, or empty string if eligible.
    """
    reasons: list[str] = []
    reasons.extend(category_exclusion_reasons(row))
    dm_reason = danmaku_exclusion_reason(row)
    if dm_reason:
        reasons.append(dm_reason)
    return "; ".join(reasons)


def is_eligible_for_sampling(row: dict[str, Any]) -> bool:
    """True if the row passed automatic filters (not excluded)."""
    return not compute_exclusion_reason(row)


def apply_search_filters(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Set ``exclusion_reason`` and reset ``in_sample`` to ``no`` on all rows.

    Does not change rows already marked ``in_sample=yes`` unless they are
    newly excluded (caller may reset sample flags separately).
    """
    for row in rows:
        row["exclusion_reason"] = compute_exclusion_reason(row)
        if row.get("in_sample", "no").lower() != "yes":
            row["in_sample"] = "no"
    return rows


def filter_summary(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Count eligible vs excluded rows."""
    eligible = sum(1 for r in rows if is_eligible_for_sampling(r))
    return {
        "total": len(rows),
        "eligible": eligible,
        "excluded": len(rows) - eligible,
        "in_sample": sum(1 for r in rows if str(r.get("in_sample", "")).lower() == "yes"),
    }
