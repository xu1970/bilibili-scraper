"""Export scraped comments to CSV."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CSV_COLUMNS = [
    "page",
    "rpid",
    "comment_text",
    "username",
    "timestamp",
    "like_count",
    "reply_count",
]

SAMPLED_COMMENTS_CSV_COLUMNS = [
    "aid",
    "comment_level",
    "is_top_comment",
    "rpid",
    "parent_rpid",
    "root_rpid",
    "username",
    "comment_text",
    "timestamp",
    "like_count",
    "reply_count",
]


def _format_timestamp(unix_ts: int) -> str:
    if not unix_ts:
        return ""
    return datetime.fromtimestamp(unix_ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _export_timestamp(value: Any) -> str:
    """Accept unix int or an already-formatted timestamp string."""
    if value is None or value == "":
        return ""
    if isinstance(value, (int, float)):
        return _format_timestamp(int(value))
    text = str(value).strip()
    if text.isdigit():
        return _format_timestamp(int(text))
    return text


def write_comments_csv(rows: list[dict[str, Any]], path: Path | str) -> Path:
    """Write comment rows to CSV with human-readable timestamps."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)

    with out.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "page": row.get("page", ""),
                    "rpid": row.get("rpid", ""),
                    "comment_text": row.get("comment_text", ""),
                    "username": row.get("username", ""),
                    "timestamp": _export_timestamp(row.get("timestamp")),
                    "like_count": row.get("like_count", 0),
                    "reply_count": row.get("reply_count", 0),
                }
            )

    return out


def _sampled_row_for_csv(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "aid": row.get("video_aid", row.get("aid", "")),
        "comment_level": row.get("comment_level", ""),
        "is_top_comment": row.get("is_top_comment", "no"),
        "rpid": row.get("rpid", ""),
        "parent_rpid": row.get("parent_rpid", ""),
        "root_rpid": row.get("root_rpid", ""),
        "username": row.get("username", ""),
        "comment_text": row.get("comment_text", ""),
        "timestamp": _export_timestamp(row.get("timestamp")),
        "like_count": row.get("like_count", 0),
        "reply_count": row.get("reply_count", ""),
    }


def write_sampled_comments_csv(rows: list[dict[str, Any]], path: Path | str) -> Path:
    """Write scraped comments from sampled videos to one combined CSV."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)

    with out.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=SAMPLED_COMMENTS_CSV_COLUMNS, extrasaction="ignore"
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(_sampled_row_for_csv(row))

    return out


class IncrementalCommentSink:
    """
    Append comment rows to a CSV and flush after each batch.

    Call ``prepare_video_output`` before scraping a video so prior rows for that
    aid are removed, then ``append`` + ``flush`` as each primary page is processed.
    """

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("a", encoding="utf-8-sig", newline="")
        self._writer = csv.DictWriter(
            self._file,
            fieldnames=SAMPLED_COMMENTS_CSV_COLUMNS,
            extrasaction="ignore",
        )
        self.rows_written = 0

    @classmethod
    def prepare_video_output(
        cls,
        path: Path | str,
        video_aid: str,
        *,
        keep_rows: list[dict[str, Any]],
    ) -> IncrementalCommentSink:
        """Rewrite CSV without ``video_aid``, then open for append."""
        write_sampled_comments_csv(keep_rows, path)
        return cls(path)

    def append(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        for row in rows:
            self._writer.writerow(_sampled_row_for_csv(row))
        self.rows_written += len(rows)
        self.flush()

    def flush(self) -> None:
        self._file.flush()

    def close(self) -> None:
        self._file.close()


SEARCH_CSV_COLUMNS = [
    "page",
    "rank",
    "search_rank",
    "eligible_rank",
    "bvid",
    "title",
    "uploader",
    "view_count",
    "aid",
    "tags",
    "typename",
    "danmaku",
    "in_sample",
    "exclusion_reason",
]


def write_search_csv(rows: list[dict[str, Any]], path: Path | str) -> Path:
    """Write video search rows to CSV."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)

    with out.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SEARCH_CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "page": row.get("page", ""),
                    "rank": row.get("rank", ""),
                    "search_rank": row.get("search_rank", ""),
                    "eligible_rank": row.get("eligible_rank", ""),
                    "bvid": row.get("bvid", ""),
                    "title": row.get("title", ""),
                    "uploader": row.get("uploader", ""),
                    "view_count": row.get("view_count", ""),
                    "aid": row.get("aid", ""),
                    "tags": row.get("tags", row.get("tag", "")),
                    "typename": row.get("typename", ""),
                    "danmaku": row.get("danmaku", ""),
                    "in_sample": row.get("in_sample", "no"),
                    "exclusion_reason": row.get("exclusion_reason", ""),
                }
            )

    return out


SAMPLED_SEARCH_CSV_COLUMNS = [
    "eligible_rank",
    "sample_bucket",
    "page",
    "rank",
    "title",
    "view_count",
    "aid",
    "review_marker",
]

REPLACEMENT_LOG_COLUMNS = [
    "replaced_at",
    "page",
    "sample_bucket",
    "pool_bucket",
    "original_rank",
    "original_eligible_rank",
    "original_title",
    "original_view_count",
    "original_aid",
    "replacement_rank",
    "replacement_eligible_rank",
    "replacement_title",
    "replacement_view_count",
    "replacement_aid",
]


def write_sampled_search_csv(rows: list[dict[str, Any]], path: Path | str) -> Path:
    """Write stratified sample rows to CSV."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)

    with out.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=SAMPLED_SEARCH_CSV_COLUMNS, extrasaction="ignore"
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "eligible_rank": row.get("eligible_rank", ""),
                    "sample_bucket": row.get("sample_bucket", ""),
                    "page": row.get("page", ""),
                    "rank": row.get("rank", ""),
                    "title": row.get("title", ""),
                    "view_count": row.get("view_count", ""),
                    "aid": row.get("aid", ""),
                    "review_marker": row.get("review_marker", ""),
                }
            )

    return out


def write_replacement_log(
    entries: list[dict[str, Any]],
    path: Path | str,
    *,
    append: bool = True,
) -> Path:
    """Write or append replacement audit log entries."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    write_header = not append or not out.exists() or out.stat().st_size == 0

    with out.open("a" if append else "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=REPLACEMENT_LOG_COLUMNS, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        for entry in entries:
            writer.writerow(entry)

    return out
