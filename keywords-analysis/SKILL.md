---
name: keywords-analysis
description: Full keyword analysis pipeline orchestrator. Chains GSC data, DataForSEO competitor analysis, Google Ads Keyword Planner, Google Autocomplete, SERP scraping, and semantic clustering into one automated flow. Requires a config JSON with project name, seed keywords, market settings, and API credentials. Use when the user wants a complete keyword analysis, keyword research workflow, or end-to-end SEO keyword pipeline.
---

# Keywords Analysis — Full Pipeline Orchestrator

Automated 10-step keyword research pipeline that chains 6 skills.

## Script location
`scripts/keyword_analysis.py`

## Quick start

```bash
# 1. Create config file (see example below)
# 2. Run (takes 20–60 min depending on config)
python3 scripts/keyword_analysis.py config.json

# Dry run — validates config, prints plan without executing
python3 scripts/keyword_analysis.py config.json --dry-run
```

## Config file (JSON, required)

```json
{
  "project": "findbestclinic",
  "seed_keywords": ["ivf", "icsi", "fertility clinic", "egg freezing"],
  "competitors": ["pronatal.cz", "ivfcube.cz"],
  "language": "cs",
  "country": "cz",
  "location_code": 2203,
  "gsc_property": "sc-domain:findbestclinic.com",
  "gsc_source": "bigquery",
  "bq_dataset": "searchconsole_findbestclinic",
  "google_ads_customer_id": "1764032686",
  "autocomplete_top_n": 30,
  "serp_top_n": 100
}
```

### Required fields

| Field | Description |
|-------|-------------|
| `project` | DuckDB project name (auto-created if missing) |
| `seed_keywords` | Initial keyword list |
| `language` | Language code (cs, en, de, ...) |
| `country` | Country code (cz, us, de, ...) |
| `gsc_property` | GSC property identifier |
| `gsc_source` | `bigquery` (primary) or `api` (secondary) |

### Optional fields

| Field | Default | Description |
|-------|---------|-------------|
| `competitors` | `[]` | Domains for DataForSEO competitor analysis |
| `location_code` | `2203` | DataForSEO location (2203=CZ, 2840=US) |
| `bq_dataset` | — | BigQuery dataset for GSC (required if `gsc_source=bigquery`) |
| `bq_table` | `searchdata_site_impression` | BigQuery table name |
| `google_ads_yaml` | `~/Documents/credentials/google-ads.yaml` | Path to Google Ads config |
| `google_ads_customer_id` | from yaml | Google Ads account ID |
| `autocomplete_top_n` | `30` | How many top KWs to expand via autocomplete |
| `serp_top_n` | `100` | How many top KWs to scrape SERP for |
| `openrouter_api_key` | env `OPENROUTER_API_KEY` | For semantic clustering |
| `date` | today | Download date for DuckDB tracking |

## Pipeline (10 steps)

| Step | Action | Skill used | Est. time |
|------|--------|-----------|-----------|
| 1 | GSC data (pos ≤ 20) | BigQuery / GSC API | ~10s |
| 2 | Competitor keywords | `dataforseo-competitors` | ~5s/domain |
| 3 | KW Planner ideas | `google-ads-keyword-planner` | ~2s/batch of 20 |
| 4 | Autocomplete expansion | `google-autocomplete` | ~2min/keyword |
| 5 | Volume lookup (new KWs) | `google-ads-keyword-planner` | ~2s/batch of 20 |
| 6 | SERP scrape (top N) | `google-serp` | ~12s/keyword |
| 7 | Volume for related + PAA | `google-ads-keyword-planner` | ~2s/batch of 20 |
| 8 | Semantic categorization | `keyword-categorization` | ~30s |
| 9 | Dedup check | internal | instant |
| 10 | Final summary | internal | instant |

**Dedup** runs continuously — a central `KeywordPool` tracks all seen keywords (lowercased) and skips duplicates across all steps.

## Output

All data stored to DuckDB project database (`~/kw_projects/<project>.duckdb`):

| Table | Data source |
|-------|-------------|
| `search_console` | Step 1 (GSC) |
| `competitor_keywords` | Step 2 (DataForSEO) |
| `keyword_planner` | Steps 3, 5, 7 (KW Planner) |
| `suggestions` | Step 4 (Autocomplete) |
| `serp` | Step 6 (SERP organic) |
| `related_queries` | Step 6 (SERP related) |
| `people_also_ask` | Step 6 (SERP PAA) |

## Progress output

```
═══ Keywords Analysis: findbestclinic ═══
  Market: cs/cz | Seeds: 4 | Competitors: 2

Step 1/10: GSC data (pos ≤ 20)
  → 1,247 keywords from Search Console
  → 1,247 total unique keywords

Step 2/10: Competitor analysis (DataForSEO)
  → pronatal.cz: 485 keywords (312 new)
  → ivfcube.cz: 391 keywords (198 new)
  → 1,757 total unique keywords
...
═══ DONE: 3,241 keywords in project 'findbestclinic' ═══
```

## Dependencies

```bash
pip3 install duckdb google-cloud-bigquery google-ads google-api-python-client \
  google-auth requests openai sentence-transformers scikit-learn torch \
  playwright playwright-stealth pandas --break-system-packages
```

## Notes

- Script refuses to start without valid config
- All API calls include rate limiting and pauses
- `--dry-run` validates config and prints what would happen without making API calls
- Autocomplete is the slowest step (~2 min per keyword)
- SERP scraping uses 8–15s random pauses between requests
- KW Planner batches seeds in groups of 20 (API limit)
