"""Scrape comments for manually approved sampled videos."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Callable
from typing import Any

from bilibili_api import aid2bvid, comment
from bilibili_api.exceptions import ApiException, ResponseCodeException
from bilibili_api.utils.credential import Credential

from .request_guard import call_with_retry, configure_http_timeouts
from .review import is_irrelevant
from .scrape import (
    MAX_PAGES_PER_VIDEO,
    CommentSort,
    PageBudget,
    comment_text,
    extract_replies,
    fetch_all_top_level,
    replies_is_empty,
)
from .throttle import random_sleep
from .export import write_sampled_comments_csv
from .video import parse_video_ref

PROGRESS_LOG_EVERY_PAGES = 10
# Safety cap for nested-reply pagination (API page size is 10).
_MAX_SUB_COMMENT_PAGES = 500


class ScrapeProgress:
    """Console progress for long-running per-video scrapes."""

    def __init__(self, bvid: str, *, log_every: int = PROGRESS_LOG_EVERY_PAGES) -> None:
        self.bvid = bvid or "?"
        self.log_every = log_every
        self.total_rows = 0

    def add_rows(self, count: int) -> None:
        self.total_rows += count

    def on_primary_page(self, page_num: int, primary_count: int) -> None:
        if page_num % self.log_every == 0:
            print(
                f"  Fetched primary page {page_num} for {self.bvid} "
                f"(primaries: {primary_count}, total rows: {self.total_rows})",
                flush=True,
            )

    def on_secondary_page(self, page_num: int, root_rpid: int, collected: int) -> None:
        if page_num % self.log_every == 0:
            print(
                f"  Fetched page {page_num} of replies for {self.bvid} "
                f"(rpid {root_rpid}, replies: {collected}, total rows: {self.total_rows})",
                flush=True,
            )


def resume_state_path(output_path: Path | str) -> Path:
    """Sidecar JSON path tracking fully scraped videos."""
    out = Path(output_path)
    return out.with_name(f"{out.stem}.resume.json")


def aids_with_primary_comments(rows: list[dict[str, Any]]) -> set[str]:
    """Aids that already have at least one primary comment row in export data."""
    completed: set[str] = set()
    for row in rows:
        if str(row.get("comment_level", "")).lower() != "primary":
            continue
        aid = str(row.get("video_aid") or row.get("aid") or "").strip()
        if aid:
            completed.add(aid)
    return completed


def load_resume_state(output_path: Path | str) -> dict[str, Any]:
    """Load resume sidecar; return empty structure if missing."""
    path = resume_state_path(output_path)
    if not path.is_file():
        return {"completed": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"completed": []}
    if not isinstance(data, dict):
        return {"completed": []}
    data.setdefault("completed", [])
    return data


def save_resume_state(output_path: Path | str, state: dict[str, Any]) -> Path:
    """Persist resume sidecar."""
    path = resume_state_path(output_path)
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def completed_aid_set(
    output_path: Path | str,
    existing_rows: list[dict[str, Any]],
) -> set[str]:
    """
    Aids considered fully scraped: listed in resume JSON or present in CSV output.

    CSV detection requires at least one primary row for that aid (written only after
    a full successful video scrape in resumable mode).
    """
    aids = aids_with_primary_comments(existing_rows)
    state = load_resume_state(output_path)
    for entry in state.get("completed", []):
        if isinstance(entry, dict):
            aid = str(entry.get("aid", "")).strip()
            if aid:
                aids.add(aid)
    return aids


def mark_video_completed(
    output_path: Path | str,
    *,
    aid: str,
    bvid: str,
    row_count: int,
) -> None:
    """Record a successfully finished video in the resume sidecar."""
    state = load_resume_state(output_path)
    completed: list[dict[str, Any]] = [
        e
        for e in state.get("completed", [])
        if isinstance(e, dict) and str(e.get("aid", "")) != str(aid)
    ]
    completed.append(
        {
            "aid": str(aid),
            "bvid": bvid,
            "row_count": row_count,
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    state["completed"] = completed
    save_resume_state(output_path, state)


def load_sampled_videos(
    sampled_path: Path | str,
    *,
    master_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Load sampled videos, optionally enriching with bvid from master search CSV."""
    rows: list[dict[str, Any]] = []
    with Path(sampled_path).open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if is_irrelevant(row.get("review_marker", "")):
                continue
            rows.append(
                {
                    "aid": str(row.get("aid", "")),
                    "title": row.get("title", ""),
                    "sample_bucket": row.get("sample_bucket", ""),
                    "eligible_rank": row.get("eligible_rank", ""),
                    "view_count": row.get("view_count", ""),
                }
            )

    if master_path and Path(master_path).is_file():
        from .sample import load_search_csv

        by_aid = {str(r["aid"]): r for r in load_search_csv(master_path)}
        for row in rows:
            master = by_aid.get(row["aid"], {})
            row["bvid"] = master.get("bvid", "")
            if not row["title"]:
                row["title"] = master.get("title", "")

    for row in rows:
        if not row.get("bvid") and row.get("aid"):
            try:
                row["bvid"] = aid2bvid(int(row["aid"]))
            except (TypeError, ValueError):
                row["bvid"] = ""

    return rows


def _parse_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _comment_row(
    reply: dict[str, Any],
    *,
    video: dict[str, Any],
    level: str,
    is_top: bool,
    parent_rpid: int | str = "",
) -> dict[str, Any]:
    member = reply.get("member") or {}
    rpid = reply.get("rpid", "")
    root = reply.get("root", parent_rpid or rpid)
    return {
        "video_aid": video["aid"],
        "comment_level": level,
        "is_top_comment": "yes" if is_top else "no",
        "rpid": rpid,
        "parent_rpid": parent_rpid if level == "secondary" else "",
        "root_rpid": root,
        "username": member.get("uname", ""),
        "comment_text": comment_text(reply),
        "timestamp": _parse_int(reply.get("ctime", 0)),
        "like_count": _parse_int(reply.get("like", 0)),
        "reply_count": _parse_int(reply.get("count", 0)) if level == "primary" else "",
    }


async def fetch_all_sub_comments(
    oid: int,
    root_rpid: int,
    credential: Credential,
    *,
    expected_count: int,
    delay_seconds: float = 1.0,
    on_page_fetched: Callable[[int, int, int], None] | None = None,
    bvid: str = "",
    page_budget: PageBudget | None = None,
) -> list[dict[str, Any]]:
    """Paginate sub-comments for one top-level thread."""
    collected: list[dict[str, Any]] = []
    seen: set[int] = set()
    page_index = 1
    page_size = 10
    max_pages = min(
        _MAX_SUB_COMMENT_PAGES,
        max(1, (expected_count // page_size) + 3),
    )
    if page_budget is not None:
        max_pages = min(max_pages, page_budget.remaining())
    label = bvid or str(oid)

    while page_index <= max_pages:
        if page_budget is not None and page_budget.exhausted:
            break

        cm = comment.Comment(
            oid=oid,
            type_=comment.CommentResourceType.VIDEO,
            rpid=root_rpid,
            credential=credential,
        )
        try:
            page = await call_with_retry(
                lambda p=page_index: cm.get_sub_comments(p),
                label=f"{label} sub-replies page {page_index} (rpid {root_rpid})",
            )
        except (ResponseCodeException, ApiException) as exc:
            print(
                f"  WARNING: sub-replies page {page_index} failed for {label} "
                f"rpid {root_rpid} ({exc}); skipping to next page",
                flush=True,
            )
            page_index += 1
            continue

        if replies_is_empty(page):
            break

        replies = extract_replies(page)

        added_this_page = 0
        for reply in replies:
            rpid = reply.get("rpid")
            if rpid is None:
                continue
            rpid_int = int(rpid)
            if rpid_int in seen:
                continue
            seen.add(rpid_int)
            collected.append(reply)
            added_this_page += 1

        if page_budget is not None:
            page_budget.record(1)

        if on_page_fetched is not None:
            on_page_fetched(page_index, root_rpid, len(collected))

        if page_budget is not None and page_budget.exhausted:
            break

        # API returned rows but none were new — thread end or stuck cursor.
        if added_this_page == 0:
            break

        page_info = page.get("page") or {}
        page_count = _parse_int(page_info.get("count"), len(collected))
        page_size = max(1, _parse_int(page_info.get("size"), 10))
        if len(collected) >= expected_count or len(replies) < page_size:
            break
        if page_index * page_size >= page_count:
            break

        page_index += 1
        if delay_seconds > 0:
            await random_sleep(delay_seconds)

    return collected


async def scrape_video_comments(
    video: dict[str, Any],
    credential: Credential,
    *,
    sort: CommentSort = CommentSort.HOT,
    delay_seconds: float = 1.0,
    max_primaries: int | None = None,
    progress: ScrapeProgress | None = None,
) -> list[dict[str, Any]]:
    """Scrape all primary + their secondary comments for one video."""
    aid = int(video["aid"])
    rows: list[dict[str, Any]] = []
    bvid = video.get("bvid") or str(aid)
    prog = progress or ScrapeProgress(str(bvid))

    def on_primary_page(page_num: int, primary_count: int) -> None:
        prog.on_primary_page(page_num, primary_count)

    configure_http_timeouts()
    page_budget = PageBudget(MAX_PAGES_PER_VIDEO)

    primaries, top_rpids = await fetch_all_top_level(
        aid,
        credential,
        sort=sort,
        delay_seconds=delay_seconds,
        max_primaries=max_primaries,
        on_page_fetched=on_primary_page,
        page_budget=page_budget,
    )

    if page_budget.exhausted:
        print(
            f"  Page limit ({MAX_PAGES_PER_VIDEO}) reached for {bvid} "
            f"during primary fetch; saving partial results",
            flush=True,
        )

    for primary in primaries:
        if page_budget.exhausted:
            break

        rpid = int(primary["rpid"])
        is_top = rpid in top_rpids
        rows.append(
            _comment_row(primary, video=video, level="primary", is_top=is_top)
        )
        prog.add_rows(1)

        inline = primary.get("replies") or []
        secondary_seen: set[int] = set()

        for sub in inline:
            if sub.get("rpid") is None:
                continue
            sub_id = int(sub["rpid"])
            secondary_seen.add(sub_id)
            rows.append(
                _comment_row(
                    sub,
                    video=video,
                    level="secondary",
                    is_top=False,
                    parent_rpid=rpid,
                )
            )
            prog.add_rows(1)

        total_subs = _parse_int(primary.get("count", 0))
        if total_subs > len(secondary_seen) and not page_budget.exhausted:

            def on_secondary_page(
                page_num: int, thread_rpid: int, collected: int
            ) -> None:
                prog.on_secondary_page(page_num, thread_rpid, collected)

            extra = await fetch_all_sub_comments(
                aid,
                rpid,
                credential,
                expected_count=total_subs,
                delay_seconds=delay_seconds,
                on_page_fetched=on_secondary_page,
                bvid=str(bvid),
                page_budget=page_budget,
            )
            if page_budget.exhausted:
                print(
                    f"  Page limit ({MAX_PAGES_PER_VIDEO}) reached for {bvid}; "
                    "saving partial results",
                    flush=True,
                )
                break
            for sub in extra:
                if sub.get("rpid") is None:
                    continue
                sub_id = int(sub["rpid"])
                if sub_id in secondary_seen:
                    continue
                secondary_seen.add(sub_id)
                rows.append(
                    _comment_row(
                        sub,
                        video=video,
                        level="secondary",
                        is_top=False,
                        parent_rpid=rpid,
                    )
                )
                prog.add_rows(1)

        if delay_seconds > 0:
            await random_sleep(delay_seconds)

    return rows


async def scrape_sampled_videos(
    videos: list[dict[str, Any]],
    credential: Credential,
    *,
    sort: CommentSort = CommentSort.HOT,
    delay_seconds: float = 1.0,
    max_primaries: int | None = None,
    output_path: Path | str | None = None,
    resume: bool = True,
) -> list[dict[str, Any]]:
    """
    Scrape comments for all sampled videos.

    When ``output_path`` is set and ``resume`` is true, loads existing CSV/JSON
    sidecar state, skips completed BV ids, and writes the CSV after each video.
    """
    configure_http_timeouts()
    all_rows: list[dict[str, Any]] = []
    completed_aids: set[str] = set()

    if output_path is not None and resume:
        all_rows = load_existing_comments_csv(output_path)
        completed_aids = completed_aid_set(output_path, all_rows)
        if completed_aids:
            print(
                f"resume:   {len(completed_aids)} video(s) already in "
                f"{Path(output_path).name}",
                flush=True,
            )

    total = len(videos)

    for i, video in enumerate(videos, start=1):
        aid = str(video.get("aid", ""))
        label = video.get("bvid") or aid

        if resume and aid in completed_aids:
            print(f"[{i}/{total}] [Skipping] {label} already processed", flush=True)
            continue

        print(f"[{i}/{total}] Scraping {label} …", flush=True)
        progress = ScrapeProgress(str(label))
        try:
            rows = await scrape_video_comments(
                video,
                credential,
                sort=sort,
                delay_seconds=delay_seconds,
                max_primaries=max_primaries,
                progress=progress,
            )
            all_rows = merge_comments_for_video(all_rows, rows, aid)
            print(f"  → {len(rows)} comments (total rows: {len(all_rows)})", flush=True)

            if output_path is not None:
                write_sampled_comments_csv(all_rows, output_path)
                mark_video_completed(
                    output_path, aid=aid, bvid=str(label), row_count=len(rows)
                )
                completed_aids.add(aid)
        except Exception as exc:
            print(f"  → FAILED: {exc}", flush=True)

        has_more_to_scrape = any(
            str(v.get("aid", "")) not in completed_aids for v in videos[i:]
        )
        if delay_seconds > 0 and has_more_to_scrape:
            await random_sleep(delay_seconds)

    return all_rows


def load_existing_comments_csv(path: Path | str) -> list[dict[str, Any]]:
    """Load an existing comments export (any column set)."""
    p = Path(path)
    if not p.is_file():
        return []
    rows: list[dict[str, Any]] = []
    with p.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            aid = row.get("aid") or row.get("video_aid") or ""
            rows.append({**row, "video_aid": str(aid), "aid": str(aid)})
    return rows


def merge_comments_for_video(
    existing: list[dict[str, Any]],
    new_rows: list[dict[str, Any]],
    video_aid: str,
) -> list[dict[str, Any]]:
    """Replace all rows for ``video_aid`` with ``new_rows``, keep other videos."""
    aid = str(video_aid)
    kept = [
        r
        for r in existing
        if str(r.get("video_aid", r.get("aid", ""))) != aid
    ]
    return kept + new_rows
