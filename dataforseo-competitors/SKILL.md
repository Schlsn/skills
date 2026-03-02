---
name: dataforseo-competitors
description: Competitor keyword analysis using DataForSEO Labs Ranked Keywords API. Fetches all keywords a competitor domain ranks for in the top 20, parses keyword data (search volume, CPC, competition, intent, monthly trends) and SERP position data (rank, URL, title, etv), and stores everything into DuckDB via the duckdb-keywords skill. Use when the user asks to analyze competitor rankings, find competitor keywords, or compare domains.
---

# DataForSEO Competitors — Ranked Keywords Analysis

Fetches keywords a competitor domain ranks for (top 20 positions) from DataForSEO Labs and stores them in DuckDB.

## Prerequisites

- **DataForSEO credentials** configured via the `dataforseo` skill (`~/.dataforseo_config.json`)
- **DuckDB project** created via `duckdb-keywords` skill
- `pip3 install duckdb` (auto-installed if missing)

## Quick Start

```bash
SCRIPT="scripts/competitor_keywords.py"

# Fetch top-20 ranked keywords for a competitor and save to DuckDB
python3 $SCRIPT pronatal pronatal.cz

# Custom location, language, and limit
python3 $SCRIPT pronatal pronatal.cz --location 2203 --language cs --limit 500

# Also export to CSV
python3 $SCRIPT pronatal pronatal.cz --csv ~/exports/pronatal_keywords.csv
```

## CLI Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `project` | DuckDB project name (must exist) | required |
| `domain` | Competitor domain to analyze | required |
| `--location` | Location code (2203 = CZ, 2840 = US) | `2203` |
| `--language` | Language code | `cs` |
| `--limit` | Max keywords to fetch (API limit) | `500` |
| `--csv` | Also export results to this CSV path | none |
| `--date` | Download date for DuckDB (YYYY-MM-DD) | today |

## Python API

```python
import sys, os
sys.path.insert(0, os.path.expanduser('~/.agents/skills/dataforseo-competitors/scripts'))
from competitor_keywords import fetch_competitor_keywords, store_to_duckdb

# Fetch
items = fetch_competitor_keywords(
    domain="pronatal.cz",
    location_code=2203,
    language_code="cs",
    limit=1000
)

# Store
store_to_duckdb("pronatal", items, downloaded_at="2026-03-01")
```

## What Gets Stored

Each keyword row in DuckDB `competitor_keywords` table contains:

| Field | Source |
|-------|--------|
| `competitor_domain` | The analyzed domain |
| `keyword` | Keyword text |
| `search_volume` | Monthly search volume |
| `competition` | Competition score (0–1) |
| `cpc` | Cost per click |
| `search_intent` | transactional / informational / etc. |
| `rank_absolute` | SERP position (1–20) |
| `serp_type` | organic / image / video / local_pack |
| `url` | Ranking URL |
| `title` | SERP title |
| `description` | SERP snippet |
| `etv` | Estimated traffic value |
| `is_paid` | Whether paid result |
| `monthly_searches_json` | 12-month search trend (JSON) |

## Useful Queries

```sql
-- Top keywords by search volume for a competitor
SELECT keyword, search_volume, rank_absolute, url
FROM competitor_keywords
WHERE competitor_domain = 'pronatal.cz'
ORDER BY search_volume DESC LIMIT 20;

-- Compare two competitors
SELECT a.keyword, a.rank_absolute AS pos_a, b.rank_absolute AS pos_b,
       a.search_volume
FROM competitor_keywords a
JOIN competitor_keywords b ON a.keyword = b.keyword
WHERE a.competitor_domain = 'pronatal.cz'
  AND b.competitor_domain = 'ivfcube.cz'
ORDER BY a.search_volume DESC;

-- Keywords where competitor ranks top 5
SELECT keyword, rank_absolute, url, search_volume, etv
FROM competitor_keywords
WHERE competitor_domain = 'pronatal.cz' AND rank_absolute <= 5
ORDER BY etv DESC;

-- Search intent distribution
SELECT search_intent, COUNT(*) AS cnt, AVG(search_volume) AS avg_sv
FROM competitor_keywords
WHERE competitor_domain = 'pronatal.cz'
GROUP BY search_intent ORDER BY cnt DESC;
```

## AI Instructions

**CRITICAL: Freshness Check Before Fetching**
Before running the `competitor_keywords.py` script to fetch data from the API, you MUST check the DuckDB database to see if data for the requested `competitor_domain` already exists and is less than 30 days old.

1. Query DuckDB to check the `downloaded_at` date for the domain.
2. If fresh data (< 30 days old) exists, DO NOT run the fetch script. Skip processing this domain to save API credits.
3. If no data exists, or if it is older than 30 days, proceed with the fetch.

## Notes

- API filter `rank_absolute <= 20` is applied server-side (efficient, no wasted credits)
- Results ordered by `search_volume DESC` from the API
- Monthly search trends stored as JSON for seasonality analysis
- Multiple competitor imports stack in the same table (differentiated by `competitor_domain`)
- DuckDB project must be created first: `python3 kw_db.py create <project>`
