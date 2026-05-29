"""Filename helpers keyed by search keyword."""

from __future__ import annotations

import re
from pathlib import Path


_UNSAFE = re.compile(r"[\\\\/\\s]+")


def keyword_slug(keyword: str) -> str:
    """
    Turn a keyword into a stable filename fragment.

    Keeps Chinese characters as-is, replaces whitespace and path separators with `_`.
    """
    text = (keyword or "").strip()
    if not text:
        raise ValueError("keyword is required")
    return _UNSAFE.sub("_", text)


def search_csv(keyword: str) -> Path:
    return Path(f"search_{keyword_slug(keyword)}.csv")


def sampled_csv(keyword: str) -> Path:
    return Path(f"search_{keyword_slug(keyword)}_sampled.csv")


def replacements_csv(keyword: str) -> Path:
    return Path(f"search_{keyword_slug(keyword)}_sampled_replacements.csv")


def comments_csv(keyword: str) -> Path:
    return Path(f"comments_sampled_{keyword_slug(keyword)}.csv")

