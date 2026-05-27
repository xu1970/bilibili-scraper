"""Remove scraped comments for one or more videos so they can be re-scraped."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .export import write_sampled_comments_csv
from .scrape_sampled import (
    load_existing_comments_csv,
    load_resume_state,
    resume_state_path,
    save_resume_state,
)
from .video import VideoRef, parse_video_ref


def unmark_video_completed(output_path: Path | str, *, aid: str) -> bool:
    """
    Remove a video from the resume sidecar so the scraper will process it again.

    Returns True if an entry was removed.
    """
    state = load_resume_state(output_path)
    aid_str = str(aid)
    before = len(state.get("completed", []))
    state["completed"] = [
        e
        for e in state.get("completed", [])
        if isinstance(e, dict) and str(e.get("aid", "")) != aid_str
    ]
    if len(state["completed"]) == before:
        return False
    save_resume_state(output_path, state)
    return True


def filter_rows_excluding_aid(
    rows: list[dict[str, Any]], aid: str
) -> tuple[list[dict[str, Any]], int]:
    """Drop all comment rows for ``aid``; return (kept rows, removed count)."""
    aid_str = str(aid)
    kept: list[dict[str, Any]] = []
    removed = 0
    for row in rows:
        row_aid = str(row.get("video_aid") or row.get("aid") or "")
        if row_aid == aid_str:
            removed += 1
        else:
            kept.append(row)
    return kept, removed


def remove_comments_for_video(
    ref: str | VideoRef,
    comments_path: Path | str,
    *,
    update_resume: bool = True,
) -> dict[str, Any]:
    """
    Remove all comment rows for a video from the export CSV (and resume sidecar).

    Accepts a BV id (``BV1xx…``), ``av`` id, or numeric aid. Returns a summary dict
    with ``bvid``, ``aid``, ``removed``, ``remaining``, and ``was_in_resume``.
    """
    video = parse_video_ref(ref) if isinstance(ref, str) else ref
    path = Path(comments_path)

    rows = load_existing_comments_csv(path)
    kept, removed = filter_rows_excluding_aid(rows, str(video.aid))

    write_sampled_comments_csv(kept, path)

    was_in_resume = False
    if update_resume:
        was_in_resume = unmark_video_completed(path, aid=str(video.aid))

    return {
        "bvid": video.bvid,
        "aid": str(video.aid),
        "removed": removed,
        "remaining": len(kept),
        "was_in_resume": was_in_resume,
        "comments_path": str(path.resolve()),
        "resume_path": str(resume_state_path(path).resolve()),
    }


def remove_comments_for_videos(
    refs: list[str | VideoRef],
    comments_path: Path | str,
    *,
    update_resume: bool = True,
) -> list[dict[str, Any]]:
    """Remove comments for multiple videos in one pass (rewrites the CSV once)."""
    path = Path(comments_path)
    aids_to_remove: set[str] = set()
    summaries: list[dict[str, Any]] = []

    for ref in refs:
        video = parse_video_ref(ref) if isinstance(ref, str) else ref
        aids_to_remove.add(str(video.aid))

    rows = load_existing_comments_csv(path)
    kept: list[dict[str, Any]] = []
    removed_by_aid: dict[str, int] = {aid: 0 for aid in aids_to_remove}

    for row in rows:
        row_aid = str(row.get("video_aid") or row.get("aid") or "")
        if row_aid in aids_to_remove:
            removed_by_aid[row_aid] = removed_by_aid.get(row_aid, 0) + 1
        else:
            kept.append(row)

    write_sampled_comments_csv(kept, path)

    for ref in refs:
        video = parse_video_ref(ref) if isinstance(ref, str) else ref
        aid = str(video.aid)
        was_in_resume = False
        if update_resume:
            was_in_resume = unmark_video_completed(path, aid=aid)
        summaries.append(
            {
                "bvid": video.bvid,
                "aid": aid,
                "removed": removed_by_aid.get(aid, 0),
                "remaining": len(kept),
                "was_in_resume": was_in_resume,
            }
        )

    return summaries
