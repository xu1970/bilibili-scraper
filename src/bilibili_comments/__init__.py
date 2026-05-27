"""Bilibili comment scraping utilities."""

from .auth import load_credential, load_credentials
from .export import (
    write_comments_csv,
    write_sampled_comments_csv,
    write_sampled_search_csv,
    write_search_csv,
)
from .filter_videos import apply_search_filters, compute_exclusion_reason, is_eligible_for_sampling
from .remove_video_comments import (
    remove_comments_for_video,
    remove_comments_for_videos,
    unmark_video_completed,
)
from .review import apply_review_replacements, is_irrelevant, load_sampled_csv
from .scrape_sampled import load_sampled_videos, scrape_sampled_videos
from .sample import (
    assign_eligible_ranks,
    load_search_csv,
    rank_based_sample_videos,
)
from .search_videos import search_videos
from .scrape import (
    CommentSort,
    collect_reply_rows,
    comment_text,
    describe_sort_mode,
    extract_replies,
    fetch_all_top_level,
    iter_top_level_pages,
    fetch_comments_for_bvid,
    fetch_n_pages,
    fetch_top_level_page,
    fetch_two_pages,
    format_comment,
    parse_reply_row,
)
from .video import VideoRef, aid_to_bvid, bvid_to_aid, normalize_bvid, parse_video_ref

__all__ = [
    "CommentSort",
    "VideoRef",
    "collect_reply_rows",
    "fetch_n_pages",
    "parse_reply_row",
    "remove_comments_for_video",
    "remove_comments_for_videos",
    "unmark_video_completed",
    "apply_review_replacements",
    "apply_search_filters",
    "compute_exclusion_reason",
    "is_eligible_for_sampling",
    "is_irrelevant",
    "load_sampled_csv",
    "load_sampled_videos",
    "scrape_sampled_videos",
    "write_sampled_comments_csv",
    "load_search_csv",
    "search_videos",
    "assign_eligible_ranks",
    "rank_based_sample_videos",
    "write_comments_csv",
    "write_sampled_search_csv",
    "write_search_csv",
    "aid_to_bvid",
    "bvid_to_aid",
    "comment_text",
    "describe_sort_mode",
    "extract_replies",
    "fetch_all_top_level",
    "iter_top_level_pages",
    "fetch_comments_for_bvid",
    "fetch_top_level_page",
    "fetch_two_pages",
    "format_comment",
    "load_credential",
    "load_credentials",
    "normalize_bvid",
    "parse_video_ref",
]
