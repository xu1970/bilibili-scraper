## Overview

This repo scrapes Bilibili video metadata and comments for a given keyword, with:

- **Search**: pull pages of results for a keyword
- **Filter**: apply automatic exclusions (category + low danmaku) and **exclude videos already sampled for prior keywords**
- **Sample**: draw a 50-video sample (rank-based / adaptive tiers)
- **Manual review**: mark irrelevant rows and generate replacements
- **Scrape comments**: scrape primary + secondary replies and export one CSV, resumable

All commands below assume you run from the project root (`Scraping/`) and use:

```bash
PYTHONPATH=src
```

## Keyword 2 workflow: `生育意愿`

### 1) Search → `search_生育意愿_p20.csv`

```bash
PYTHONPATH=src python3 scripts/search_to_csv.py \
  --keyword "生育意愿" \
  --pages 34 \
  --delay 1.0 \
  --output "search_生育意愿_p20.csv"
```

### 2) Filter (auto rules + exclude previously sampled videos)

This step applies the existing auto-filter rules **and** excludes any video whose `aid`
appears in previously created sampled CSVs (by default: `search_*_sampled*.csv`).

```bash
PYTHONPATH=src python3 scripts/filter_search_csv.py \
  --input "search_生育意愿_p20.csv" \
  --output "search_生育意愿_p20.csv" \
  --exclude-sampled-glob "search_*_sampled*.csv"
```

Notes:
- The exclusion is recorded as `manual_exclusion_reason=already_sampled`, and flows into `exclusion_reason`.
- If you want to be explicit (recommended), pass the `生育` sample file directly:

```bash
PYTHONPATH=src python3 scripts/filter_search_csv.py \
  --input "search_生育意愿_p20.csv" \
  --exclude-sampled "search_生育_p20_sampled.csv"
```

### 3) Sample → `search_生育意愿_p20_sampled.csv`

```bash
PYTHONPATH=src python3 scripts/sample_search_csv.py \
  --input "search_生育意愿_p20.csv" \
  --output "search_生育意愿_p20_sampled.csv" \
  --seed 42
```

### 4) Manual review + replacements

Open `search_生育意愿_p20_sampled.csv` and fill `review_marker` for rows you want to replace
(`x`, `irrelevant`, `exclude`, etc.).

Create replacements file (same format as existing workflow) and apply:

```bash
PYTHONPATH=src python3 scripts/apply_review_replacements.py
```

This produces/uses `search_生育意愿_p20_sampled_replacements.csv` and writes an updated sampled CSV.

### 5) Scrape comments → `comments_sampled_生育意愿.csv`

```bash
PYTHONPATH=src python3 scripts/scrape_sampled_comments.py \
  --sampled "search_生育意愿_p20_sampled.csv" \
  --master "search_生育意愿_p20.csv" \
  --output "comments_sampled_生育意愿.csv" \
  --delay 1.0
```

Resuming is enabled by default via the sidecar:

`comments_sampled_生育意愿.resume.json`

If you want to re-scrape a specific BV id, first remove it from the comments CSV + resume state:

```bash
PYTHONPATH=src python3 scripts/remove_video_comments.py BVxxxxxxxxxxx \
  --output "comments_sampled_生育意愿.csv"
```

