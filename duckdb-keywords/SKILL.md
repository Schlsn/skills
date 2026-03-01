---
name: duckdb-keywords
description: Project-based DuckDB database for keyword analysis. Standardized schemas for 8 SEO data sources (Google Ads, Keyword Planner, SERP, Suggestions, Related Queries, PAA, Search Console, Competitor Keywords). Supports local and remote (SSH to Hetzner) execution. Use when the user wants to store, query, import, or analyze keyword data with SQL.
---

# DuckDB Keywords — Project Database Manager

Per-project DuckDB databases with standardized SEO table schemas (8 tables).
Works locally or remotely on Hetzner server via SSH.

## Script location
`scripts/kw_db.py`

## Quick start

```bash
DB="scripts/kw_db.py"

# Create a project
python3 $DB create findbestclinic

# Import data
python3 $DB import findbestclinic google_ads ~/exports/gads_export.csv --date 2026-03-01
python3 $DB import findbestclinic search_console ~/exports/gsc.csv --sep "\t"
python3 $DB import findbestclinic serp ~/google_serp_outputs/serp_organic_ivf.csv

# Query
python3 $DB query findbestclinic "SELECT keyword, search_volume FROM google_ads ORDER BY search_volume DESC LIMIT 20"

# Show project tables
python3 $DB tables findbestclinic

# List all projects
python3 $DB projects
```

### Remote (Hetzner server)

```bash
# Create on Hetzner
python3 $DB -r create findbestclinic

# Import (SCP + import)
python3 $DB -r import findbestclinic google_ads ~/exports/gads.csv --date 2026-03-01

# Query remotely
python3 $DB -r query findbestclinic "SELECT COUNT(*) FROM google_ads"
```

## Table schemas

| Table | Description | Key columns |
|-------|-------------|-------------|
| `google_ads` | Google Ads keywords export | keyword, search_volume, cpc, competition, campaign |
| `keyword_planner` | Keyword Planner export | keyword, avg_monthly_searches, top_bid_low/high |
| `serp` | Organic SERP results | keyword, position, title, url, description |
| `suggestions` | Google Autocomplete | seed_keyword, suggestion, position, modifier |
| `related_queries` | Related Searches from SERP | seed_keyword, related_query, position |
| `people_also_ask` | PAA questions from SERP | seed_keyword, question, answer_snippet |
| `search_console` | GSC performance data | query, page, clicks, impressions, ctr, position, date |
| `competitor_keywords` | DataForSEO competitor ranked kws (top 20) | competitor_domain, keyword, search_volume, rank_absolute, url, etv |

**Every table has:** `imported_at` (auto timestamp) + `downloaded_at` (user-specified date)

> `competitor_keywords` is populated by the `dataforseo-competitors` skill, not by CSV import.

## CLI commands

| Command | Description |
|---------|-------------|
| `create <project>` | Create project with all 8 tables |
| `projects` | List all project databases |
| `tables <project>` | Show tables and row counts |
| `import <project> <table> <csv>` | Import CSV with auto column mapping |
| `query <project> "<sql>"` | Run SQL query |
| `schemas` | Show all table schemas and columns |

**Flags:** `-r` / `--remote` — run on Hetzner via SSH

## CSV auto-mapping

Column names are auto-detected (case-insensitive). Supports Czech and English headers.

Example: a CSV with header `Keyword,Avg. Monthly Searches,Competition` will auto-map to
`keyword_planner.keyword`, `keyword_planner.avg_monthly_searches`, `keyword_planner.competition`.

## Python API

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scripts'))
from kw_db import create_project, import_csv, run_sql, show_tables

create_project("myproject")
import_csv("myproject", "google_ads", "~/exports/gads.csv", downloaded_at="2026-03-01")
print(run_sql("myproject", "SELECT keyword, search_volume FROM google_ads LIMIT 10"))
```

## Project structure

```
~/kw_projects/              # local
  findbestclinic.duckdb
  another_project.duckdb

/root/kw_projects/          # remote (Hetzner)
  findbestclinic.duckdb
```

## Connection

- **Local**: direct DuckDB via Python (`pip install duckdb`)
- **Remote**: SSH via `hetzner-n8n` alias (see `~/.ssh/config`)
  - Server: 78.46.190.162 (root)
  - Key: `/Users/adam/Documents/credentials/servers/hetzner-n8n.pem`

## Useful queries

```sql
-- Top keywords by volume across all sources
SELECT keyword, search_volume, 'google_ads' AS source FROM google_ads
UNION ALL
SELECT keyword, avg_monthly_searches, 'planner' FROM keyword_planner
ORDER BY search_volume DESC LIMIT 50;

-- SERP position distribution
SELECT position, COUNT(*) AS cnt FROM serp GROUP BY position ORDER BY position;

-- GSC top pages by clicks
SELECT page, SUM(clicks) AS total_clicks, AVG(position) AS avg_pos
FROM search_console GROUP BY page ORDER BY total_clicks DESC LIMIT 20;

-- Import history
SELECT table_name, downloaded_at, COUNT(*) AS rows
FROM (
  SELECT 'google_ads' AS table_name, downloaded_at FROM google_ads
  UNION ALL SELECT 'search_console', downloaded_at FROM search_console
) GROUP BY ALL ORDER BY downloaded_at DESC;
```

## Notes

- Each project = one `.duckdb` file (no server process needed)
- DuckDB must be installed: `pip3 install duckdb --break-system-packages`
- Remote requires SSH access to `hetzner-n8n`
- CSV encoding: auto-detected (UTF-8, UTF-8-BOM, Latin-1)
