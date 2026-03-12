---
name: dataforseo-competitors
description: Competitor keyword analysis using DataForSEO Labs Ranked Keywords API. Fetches all keywords a competitor domain ranks for in the top 20, parses keyword data (search volume, CPC, competition, intent, monthly trends) and SERP position data (rank, URL, title, etv), and stores everything into PostgreSQL (seo.competitor_keywords). Use when the user asks to analyze competitor rankings, find competitor keywords, or compare domains.
---

# DataForSEO Competitors — Ranked Keywords Analysis

Fetches keywords a competitor domain ranks for (top 20 positions) from DataForSEO Labs and stores them in PostgreSQL.

## Prerequisites

- **DataForSEO credentials** configured (`~/.dataforseo_config.json`)
- **PostgreSQL connection** — set `DATABASE_URL` env variable, or add `postgres_dsn` to `~/.dataforseo_config.json`
- **Migration applied** — run `migrations/001_competitor_keywords.sql` once against your database
- `pip3 install psycopg2-binary` (auto-installed if missing)

## Setup

### 1. Configure PostgreSQL connection

Either set the environment variable:
```bash
export DATABASE_URL="postgresql://user:password@localhost:5432/dbname"
```

Or add to `~/.dataforseo_config.json`:
```json
{
  "login": "...",
  "password": "...",
  "postgres_dsn": "postgresql://user:password@localhost:5432/seo"
}
```

### 2. Apply migration

```bash
psql $DATABASE_URL -f migrations/001_competitor_keywords.sql
```

## Quick Start

```bash
SCRIPT="scripts/competitor_keywords.py"

# Fetch top-20 ranked keywords for a competitor and save to PostgreSQL
python3 $SCRIPT pronatal pronatal.cz

# Custom location, language, and limit
python3 $SCRIPT pronatal pronatal.cz --location 2203 --language cs --limit 500

# Also export to CSV
python3 $SCRIPT pronatal pronatal.cz --csv ~/exports/pronatal_keywords.csv

# Force re-fetch (bypass 30-day freshness check)
python3 $SCRIPT pronatal pronatal.cz --force
```

## CLI Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `project` | Project name (stored as column) | required |
| `domain` | Competitor domain to analyze | required |
| `--location` | Location code (2203 = CZ, 2840 = US) | `2203` |
| `--language` | Language code | `cs` |
| `--limit` | Max keywords to fetch (API limit) | `500` |
| `--csv` | Also export results to this CSV path | none |
| `--date` | Download date (YYYY-MM-DD) | today |
| `--force` | Skip freshness check, always fetch | false |

## Python API

```python
import sys, os
sys.path.insert(0, os.path.expanduser('~/.agents/skills/dataforseo-competitors/scripts'))
from competitor_keywords import fetch_competitor_keywords, store_to_psql, check_freshness

# Check freshness before fetching
latest = check_freshness("pronatal", "pronatal.cz")  # returns "2026-02-01" or None

# Fetch
items = fetch_competitor_keywords(
    domain="pronatal.cz",
    location_code=2203,
    language_code="cs",
    limit=1000
)

# Store
store_to_psql("pronatal", items, downloaded_at="2026-03-01")
```

## Database Schema

Table: `seo.competitor_keywords`

| Field | Type | Source |
|-------|------|--------|
| `id` | BIGSERIAL | auto |
| `project` | VARCHAR | CLI arg |
| `competitor_domain` | VARCHAR | The analyzed domain |
| `keyword` | VARCHAR | Keyword text |
| `search_volume` | INTEGER | Monthly search volume |
| `competition` | DOUBLE PRECISION | Competition score (0–1) |
| `cpc` | DOUBLE PRECISION | Cost per click |
| `search_intent` | VARCHAR | transactional / informational / etc. |
| `rank_absolute` | INTEGER | SERP position (1–20) |
| `serp_type` | VARCHAR | organic / image / video / local_pack |
| `url` | TEXT | Ranking URL |
| `title` | TEXT | SERP title |
| `description` | TEXT | SERP snippet |
| `etv` | DOUBLE PRECISION | Estimated traffic value |
| `is_paid` | BOOLEAN | Whether paid result |
| `monthly_searches_json` | TEXT | 12-month search trend (JSON) |
| `language` | VARCHAR | Language code |
| `country` | VARCHAR | Location code |
| `imported_at` | TIMESTAMPTZ | When inserted into DB |
| `downloaded_at` | DATE | API fetch date |

## Useful Queries

```sql
-- Top keywords by search volume for a competitor
SELECT keyword, search_volume, rank_absolute, url
FROM seo.competitor_keywords
WHERE project = 'pronatal' AND competitor_domain = 'pronatal.cz'
ORDER BY search_volume DESC LIMIT 20;

-- Compare two competitors
SELECT a.keyword, a.rank_absolute AS pos_a, b.rank_absolute AS pos_b,
       a.search_volume
FROM seo.competitor_keywords a
JOIN seo.competitor_keywords b
  ON a.keyword = b.keyword AND a.project = b.project
WHERE a.competitor_domain = 'pronatal.cz'
  AND b.competitor_domain = 'ivfcube.cz'
  AND a.project = 'pronatal'
ORDER BY a.search_volume DESC;

-- Keywords where competitor ranks top 5
SELECT keyword, rank_absolute, url, search_volume, etv
FROM seo.competitor_keywords
WHERE project = 'pronatal' AND competitor_domain = 'pronatal.cz'
  AND rank_absolute <= 5
ORDER BY etv DESC;

-- Search intent distribution
SELECT search_intent, COUNT(*) AS cnt, AVG(search_volume) AS avg_sv
FROM seo.competitor_keywords
WHERE project = 'pronatal' AND competitor_domain = 'pronatal.cz'
GROUP BY search_intent ORDER BY cnt DESC;

-- Freshness check
SELECT competitor_domain, MAX(downloaded_at) AS last_fetch,
       NOW()::date - MAX(downloaded_at) AS days_old
FROM seo.competitor_keywords
WHERE project = 'pronatal'
GROUP BY competitor_domain;
```

## Keyword Analysis Workflow — Požadavky

Při použití v rámci `keywords-analysis` workflow:

**Minimum 5 konkurentů.** Méně konkurentů = neúplný obraz trhu a nekompletní keyword gap.

**Jak identifikovat konkurenty (pokud klient nedodá):**
1. **GSC URL overlap** — kdo se zobrazuje na stejných KWs jako klient (viz `serp_organic`)
2. **LLM analýza** — "Kdo jsou hlavní online konkurenti pro {web} v {lokalita}?"
3. **SimilarWeb / Ahrefs** — "Similar sites"
4. **Ruční input** — zeptej se klienta

**Pro každého konkurenta:**
- Zkontroluj freshness (< 30 dní) a pokud data existují, nevolej API znovu
- Limit alespoň 500 KWs na konkurenta pro dostatečnou pokrytost

```bash
# Šablona pro 5 konkurentů
for domain in konkurent1.cz konkurent2.cz konkurent3.cz konkurent4.cz konkurent5.cz; do
  python3 scripts/competitor_keywords.py {schema} $domain --location 2203 --language cs --limit 500
done
```

---

## AI Instructions

**CRITICAL: Freshness Check Before Fetching**
Before running the `competitor_keywords.py` script to fetch data from the API, you MUST check PostgreSQL to see if data for the requested `competitor_domain` already exists and is less than 30 days old.

Use `check_freshness(project, domain)` from the Python API, or run:
```sql
SELECT MAX(downloaded_at) FROM seo.competitor_keywords
WHERE project = '<project>' AND competitor_domain = '<domain>';
```

- If fresh data (< 30 days old) exists → DO NOT run the fetch script, save API credits.
- If no data or older than 30 days → proceed with the fetch.
- Use `--force` flag to bypass when explicitly needed.

## Notes

- API filter `rank_absolute <= 20` is applied server-side (efficient, no wasted credits)
- Results ordered by `search_volume DESC` from the API
- Monthly search trends stored as JSON for seasonality analysis
- Multiple competitor imports stack in the same table (differentiated by `project` + `competitor_domain`)
- Cache stored at `~/dataforseo_cache/competitor_keywords/YYYY-MM-DD_<domain>.csv`
