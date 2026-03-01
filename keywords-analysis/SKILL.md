---
name: keywords-analysis
description: Workflow and analysis layer for comprehensive keyword research. Guides the step-by-step process of collecting keyword data using existing skills (GSC, DataForSEO, KW Planner, Autocomplete, SERP) into a DuckDB project, then provides SQL-based analysis — dedup, gap detection, volume distribution, and export for clustering. Use when the user wants to run a full keyword analysis, plan keyword research, or analyze collected keyword data.
---

# Keywords Analysis — Workflow & Analysis

Workflow for collecting SEO keyword data into a DuckDB project + analysis scripts for what comes after.

## Workflow: Data Collection

> **Each step uses its own skill.** Run them in order, all data lands in one DuckDB project.

### 0. Create DuckDB project

```bash
python3 ../duckdb-keywords/scripts/kw_db.py create <project_name>
```

### 1. GSC data (pos ≤ 20)

Pull Search Console data via BigQuery or API. Store to `search_console` table.

```python
# BigQuery approach
from google.cloud import bigquery
client = bigquery.Client()
query = """
    SELECT query, page, SUM(clicks) AS clicks, SUM(impressions) AS impressions,
           AVG(average_ctr) AS ctr, AVG(average_position) AS position
    FROM `<bq_dataset>.searchdata_site_impression`
    WHERE search_type = 'WEB' AND average_position <= 20
    GROUP BY query, page HAVING SUM(impressions) > 0
    ORDER BY impressions DESC
"""
# Export as CSV, then:
python3 ../duckdb-keywords/scripts/kw_db.py import <project> search_console gsc_export.csv
```

### 2. Competitor keywords (DataForSEO)

```bash
python3 ../dataforseo-competitors/scripts/competitor_keywords.py <project> competitor1.com
python3 ../dataforseo-competitors/scripts/competitor_keywords.py <project> competitor2.com
```

### 3. KW Planner ideas

Use `google-ads-keyword-planner` skill to get keyword ideas from seed keywords. Export results and import:

```bash
python3 ../duckdb-keywords/scripts/kw_db.py import <project> keyword_planner kw_planner_export.csv
```

### 4. Google Autocomplete

Run `google-autocomplete` skill for top keywords by volume. Import suggestions:

```bash
python3 ../duckdb-keywords/scripts/kw_db.py import <project> suggestions autocomplete_results.csv
```

### 5. Volume lookup

For keywords collected without search volume (autocomplete suggestions, related queries), run KW Planner to get volumes. Import results.

### 6. SERP scrape (top 100 by volume)

```bash
# Use google-serp skill for top keywords
python3 ../google-serp/scripts/google_serp.py "keyword" --lang cs --country cz

# Import organic results, related queries, and PAA
python3 ../duckdb-keywords/scripts/kw_db.py import <project> serp serp_organic_*.csv
```

### 7. Volume for related + PAA

Get volumes for newly discovered related queries and PAA questions via KW Planner.

### 8. Categorization

```bash
# Export all keywords with volume from DuckDB, then cluster
python3 scripts/analyze.py <project> export-for-clustering
python3 ../keyword-categorization/scripts/cluster_keywords.py /tmp/kw_<project>_for_clustering.csv
```

---

## Analysis Script

`scripts/analyze.py` — works with data already collected in DuckDB.

```bash
# Dedup report — find duplicates across tables
python3 scripts/analyze.py <project> dedup

# Overview — keyword counts, volume distribution, source breakdown
python3 scripts/analyze.py <project> overview

# Top keywords — unified view by volume
python3 scripts/analyze.py <project> top [N]

# Gaps — keywords competitors rank for but not in GSC
python3 scripts/analyze.py <project> gaps

# Export for clustering
python3 scripts/analyze.py <project> export-for-clustering

# Export all unique keywords with volumes to CSV
python3 scripts/analyze.py <project> export-all
```

## Key principles

- **Each skill collects its own data** — this skill only analyzes
- **DuckDB is the single source of truth** — all data goes there
- **Dedup continuously** — run `analyze.py dedup` after each import step
- **Volume is king** — always enrich keywords without volume via KW Planner before analysis
