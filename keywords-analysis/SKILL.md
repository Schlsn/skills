---
name: keywords-analysis
description: Workflow and analysis layer for comprehensive keyword research. Guides the step-by-step process of collecting keyword data using existing skills (GSC, DataForSEO, KW Planner, Autocomplete, SERP) into a DuckDB project, then provides SQL-based analysis — dedup, gap detection, volume distribution, and export for clustering. Use when the user wants to run a full keyword analysis, plan keyword research, or analyze collected keyword data.
---

# Keywords Analysis — Workflow & Analysis

Workflow for collecting SEO keyword data into a DuckDB project + analysis tools.

**Princip:** Každý krok používá svůj vlastní skill. Všechna data jdou do jednoho DuckDB projektu. Po sběru analyzuješ přes `analyze.py`.

---

## Data mapping

> Kde co končí — přehled kam každý krok ukládá data.

| Krok | Zdroj dat | → DuckDB tabulka | Klíčové sloupce |
|------|-----------|-------------------|-----------------|
| 1. GSC | Search Console | `search_console` | query, page, clicks, impressions, position |
| 2. Competitors | DataForSEO | `competitor_keywords` | keyword, search_volume, rank, competitor_domain |
| 3. KW Planner | Google Ads API | `keyword_planner` | keyword, avg_monthly_searches, competition |
| 4. Autocomplete | Google Suggest | `suggestions` | seed_keyword, suggestion, position |
| 5. Volume lookup | Google Ads API | `keyword_planner` | (doplní volume ke krokům 1, 4) |
| 6. SERP | google-serp | `serp` + `related_queries` + `people_also_ask` | keyword, position, title, url |
| 7. Volume related+PAA | Google Ads API | `keyword_planner` | (doplní volume ke kroku 6) |
| 8. Kategorizace | keyword-categorization | export → cluster → CSV | Main_Category, Subcategory |

---

## Workflow

### 0. Vytvoř DuckDB projekt

```bash
python3 ../duckdb-keywords/scripts/kw_db.py create <project>
```

---

### 1. GSC data (pos ≤ 20) ⭐ Klíčový krok

Tato data jsou základ — ukazují na čem web reálně rankuje.

**Varianta A: BigQuery (nejlepší)**

```python
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
```

**Varianta B: Google Search Console API**

```python
from googleapiclient.discovery import build
service = build('searchconsole', 'v1')
response = service.searchanalytics().query(
    siteUrl='sc-domain:example.com',
    body={
        'startDate': '2025-09-01', 'endDate': '2026-03-01',
        'dimensions': ['query', 'page'], 'rowLimit': 25000,
    }
).execute()
# Filtruj rows kde position <= 20
```

**Varianta C: Google Analytics 4 (MCP tool)**

Pokud jsou GA4 data napojená, použij `run_report` s dimenzí `searchTerm` (pokud je GSC propojená s GA4).

**Varianta D: Manuální export z GSC UI**

1. Jdi na https://search.google.com/search-console → Performance
2. Filtruj pozice ≤ 20
3. Exportuj CSV
4. Importuj: `python3 ../duckdb-keywords/scripts/kw_db.py import <project> search_console export.csv`

> ⚠️ **Vždy** se zeptej uživatele, jaký zdroj GSC dat má k dispozici. Nikdy nepřeskakuj tento krok.

```bash
python3 ../duckdb-keywords/scripts/kw_db.py import <project> search_console gsc_export.csv
```

---

### 2. Competitor keywords (DataForSEO)

```bash
# Pro každého konkurenta:
python3 ../dataforseo-competitors/scripts/competitor_keywords.py <project> competitor1.com
python3 ../dataforseo-competitors/scripts/competitor_keywords.py <project> competitor2.com --limit 1000
```

---

### 3. KW Planner ideas

**Vstup:** seed keywords + **top competitor keywords** (ne jen seedy!)

Postup:
1. Vezmi seed keywords od uživatele
2. Z kroku 2 vyber top competitor KWs (podle search_volume)
3. Obojí pošli do Keyword Planneru (max 20 na batch)

```sql
-- Vyber top competitor KWs pro KW Planner seeds
SELECT DISTINCT keyword FROM competitor_keywords
ORDER BY search_volume DESC LIMIT 50
```

Výsledky importuj do `keyword_planner`:
```bash
python3 ../duckdb-keywords/scripts/kw_db.py import <project> keyword_planner kw_planner_results.csv
```

---

### 4. Google Autocomplete

**Limity:**
- **Malý projekt (< 500 KWs):** expand top 10–15 KWs by volume
- **Střední projekt (500–2000 KWs):** expand top 20–30 KWs
- **Velký projekt (2000+ KWs):** expand top 30–50 KWs

> ⚠️ Každé KW trvá ~2 minuty (49 requestů × 2.5s pauza). 30 KWs = ~1 hodina.

Vstup: top N KWs z `keyword_planner` seřazené podle search volume.

```sql
-- Vyber KWs pro autocomplete expansion
SELECT DISTINCT keyword FROM keyword_planner
WHERE avg_monthly_searches > 100
ORDER BY avg_monthly_searches DESC LIMIT 30
```

Výsledky importuj do `suggestions`:
```bash
python3 ../duckdb-keywords/scripts/kw_db.py import <project> suggestions autocomplete_*.txt
```

---

### 5. Volume lookup

Pro všechna nová KW bez hledanosti (z autocomplete, GSC) — pošli přes KW Planner.

```sql
-- KWs které potřebují volume
SELECT DISTINCT s.suggestion AS keyword FROM suggestions s
LEFT JOIN keyword_planner kp ON LOWER(s.suggestion) = LOWER(kp.keyword)
WHERE kp.keyword IS NULL
```

---

### 6. SERP scrape (top 100 by volume)

```bash
# Použij google-serp skill s pauzami
python3 ../google-serp/scripts/google_serp.py "keyword" --lang cs --country cz
```

Importuj:
```bash
python3 ../duckdb-keywords/scripts/kw_db.py import <project> serp serp_organic_*.csv
python3 ../duckdb-keywords/scripts/kw_db.py import <project> related_queries serp_related_*.csv
python3 ../duckdb-keywords/scripts/kw_db.py import <project> people_also_ask serp_paa_*.csv
```

---

### 7. Volume pro related + PAA

Stejný postup jako krok 5 — pošli nová related queries a PAA otázky přes KW Planner.

---

### 8. Kategorizace

```bash
# Export pro clustering
python3 scripts/analyze.py <project> export-for-clustering

# Spusť clustering
python3 ../keyword-categorization/scripts/cluster_keywords.py /tmp/kw_<project>_for_clustering.csv
```

---

## Analysis script

`scripts/analyze.py` — pracuje s daty v DuckDB.

```bash
python3 scripts/analyze.py <project> overview              # Přehled: počty, volume, zdroje
python3 scripts/analyze.py <project> dedup                 # Duplicity a overlap report
python3 scripts/analyze.py <project> top 50                # Top N KWs by volume (všechny zdroje)
python3 scripts/analyze.py <project> gaps                  # KWs kde competitor rankuje a ty ne
python3 scripts/analyze.py <project> export-for-clustering # Export pro keyword-categorization
python3 scripts/analyze.py <project> export-all            # Kompletní export unique KWs
```

---

## Klíčové zásady

- **Nikdy nepřeskoč GSC** — vždycky se zeptej jak data získat
- **KW Planner = seeds + competitor KWs** — ne jen seedy
- **Autocomplete limit domluv s uživatelem** — kolik KWs expandovat
- **Dedup průběžně** — `analyze.py dedup` po každém importním kroku
- **Volume je základ** — KWs bez volume obohať přes KW Planner předtím, než analyzuješ
