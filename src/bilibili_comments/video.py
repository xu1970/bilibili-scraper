"""Resolve Bilibili video IDs (BV, av, numeric aid) for comment scraping."""

from __future__ import annotations

import re
from dataclasses import dataclass

from bilibili_api import aid2bvid, bvid2aid

_BV_BODY_RE = re.compile(r"^[a-zA-Z0-9]{10}$")
_BV_FULL_RE = re.compile(r"^BV[a-zA-Z0-9]{10}$")
_AV_RE = re.compile(r"^av(\d+)$", re.IGNORECASE)
_AID_RE = re.compile(r"^\d+$")


@dataclass(frozen=True)
class VideoRef:
    """A resolved Bilibili video identifier."""

    bvid: str
    aid: int


def normalize_bvid(bvid: str) -> str:
    """
    Normalize a BV id for use with bilibili-api.

    Strips whitespace and ensures a ``BV`` prefix. The 10-character body is
  left unchanged (Bilibili BV ids are case-sensitive).
    """
    text = bvid.strip()
    if len(text) == 12 and text[:2].lower() == "bv":
        body = text[2:]
        if not _BV_BODY_RE.fullmatch(body):
            raise ValueError(
                f"Invalid BV id {bvid!r}: expected BV + 10 alphanumeric characters."
            )
        return "BV" + body

    if _BV_BODY_RE.fullmatch(text):
        return "BV" + text

    raise ValueError(
        f"Invalid BV id {bvid!r}: expected BVxxxxxxxxxx or 10 alphanumeric characters."
    )


def bvid_to_aid(bvid: str) -> int:
    """Convert a BV id to numeric aid (comment API ``oid`` for videos)."""
    normalized = normalize_bvid(bvid)
    aid = bvid2aid(normalized)
    if aid <= 0:
        raise ValueError(f"BV id {bvid!r} resolved to invalid aid {aid}.")
    return aid


def aid_to_bvid(aid: int) -> str:
    """Convert numeric aid to BV id."""
    if aid <= 0:
        raise ValueError(f"aid must be a positive integer, got {aid}.")
    bvid = aid2bvid(aid)
    if not _BV_FULL_RE.fullmatch(bvid):
        raise ValueError(f"aid {aid} resolved to invalid bvid {bvid!r}.")
    return bvid


def parse_video_ref(ref: str) -> VideoRef:
    """
    Parse a user-supplied video reference into ``(bvid, aid)``.

    Accepted forms:
      - ``BV1xxxxxxxxxx`` (case-sensitive body; ``bv`` prefix allowed)
      - ``av170001`` / ``AV170001``
      - ``170001`` (plain positive integer aid)
    """
    text = ref.strip()
    if not text:
        raise ValueError("Video reference cannot be empty.")

    av_match = _AV_RE.fullmatch(text)
    if av_match:
        aid = int(av_match.group(1))
        return VideoRef(bvid=aid_to_bvid(aid), aid=aid)

    if _AID_RE.fullmatch(text):
        aid = int(text)
        return VideoRef(bvid=aid_to_bvid(aid), aid=aid)

    if text[:2].lower() == "bv" or (
        len(text) == 10 and _BV_BODY_RE.fullmatch(text)
    ):
        bvid = normalize_bvid(text)
        return VideoRef(bvid=bvid, aid=bvid_to_aid(bvid))

    raise ValueError(
        f"Unrecognized video reference {ref!r}. "
        "Use BVxxxxxxxxxx, av<aid>, or a numeric aid."
    )


if __name__ == "__main__":
    import sys

    sample = sys.argv[1] if len(sys.argv) > 1 else "BV1GJ411x7h7"
    resolved = parse_video_ref(sample)
    print(f"input:  {sample}")
    print(f"bvid:   {resolved.bvid}")
    print(f"aid:    {resolved.aid}")
    roundtrip = aid_to_bvid(resolved.aid)
    print(f"roundtrip bvid: {roundtrip} ({'ok' if roundtrip == resolved.bvid else 'mismatch'})")
