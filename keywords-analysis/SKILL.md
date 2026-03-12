---
name: keywords-analysis
description: Workflow and analysis layer for comprehensive keyword research. Guides the step-by-step process of collecting keyword data using existing skills (GSC, DataForSEO, KW Planner, Autocomplete, SERP) into PostgreSQL, then provides SQL-based analysis — dedup, gap detection, volume distribution, and export for clustering. Use when the user wants to run a full keyword analysis, plan keyword research, or analyze collected keyword data.
---

# Keywords Analysis — Workflow & Analysis

Kompletní workflow pro sběr, čistění a clusterizaci SEO klíčových slov do PostgreSQL.

**Princip:** Každý krok používá svůj vlastní skill. Všechna data jdou do jedné databáze (PostgreSQL). Workflow má tři hlavní fáze: **Sběr → Čistění → Clusterizace**.

---

## Data mapping

> Kde co končí — přehled kam každý krok ukládá data.

| Fáze | Krok | Skill / Zdroj | → PostgreSQL tabulka | Klíčové sloupce |
|------|------|---------------|----------------------|-----------------|
| Sběr | A. Seed KWs | manuálně + LLM | `{schema}.seed_keywords` | keyword, language |
| Sběr | B1. GSC | `gsc-ads-keyword-data` | `seo_kws.gsc_search_terms` | query, position, impressions, clicks |
| Sběr | B2. Ads search terms | `gsc-ads-keyword-data` | `seo_kws.ads_search_terms` | search_term, impressions, cost |
| Sběr | C. Konkurenti | `dataforseo-competitors` | `seo.competitor_keywords` | keyword, search_volume, rank_absolute, competitor_domain |
| Sběr | D. KW Planner rozšíření | `google-ads-keyword-planner` | `{schema}.keyword_planner` | keyword, avg_monthly_searches, competition |
| Sběr | E. Autocomplete | `google-autocomplete` | `{schema}.suggestions` | seed_keyword, suggestion |
| Sběr | F. SERP | `google-serp` | `seo_kws.serp_organic`, `{schema}.related_queries` | keyword, position, url |
| Sběr | G. Volume lookup | `google-ads-keyword-planner` | `{schema}.keyword_planner` | doplní volume ke krokům B, E, F |
| Čistění | H1. Nulová hledanost | SQL | — | odstraní KWs bez dat |
| Čistění | H2. Sémantické čistění | `keyword-cleaning` | relevance_score v source tabulkách | is_relevant = true/false |
| Cluster. | I. Clusterizace | `keyword-categorization` | export → CSV | Main_Category, Subcategory, SERP_Cluster |

---

## Workflow

### Prerekvizity

Vždy se zeptej na:
1. Klienta / projekt (slug pro PostgreSQL schéma)
2. Lokalitu a jazyk (ovlivňuje KAŽDÝ krok)
3. Web klienta (URL pro LLM analýzu seed KWs)
4. Přístupy ke zdrojům (GSC API / BigQuery, Ads Customer ID, DataForSEO credentials)

---

### A. Seed Keywords (Vstupní data)

Seed keywords = hlavní produkty, služby a témata webu. Jsou **zlatý standard** pro celý workflow — čistění i clusterizace se od nich odvíjí.

**Zdroj 1 — Od klienta (ruční input):**
Vyžaduj min. 10–30 seed keywords pokrývající všechny pilíře webu.

**Zdroj 2 — LLM analýza webu (nové):**
Projdi web klienta a identifikuj hlavní témata:
1. Fetch homepage + klíčové landing pages
2. Identifikuj produkty/služby, kategorie, FAQ témata
3. Navrhni 20–50 seed keywords (vč. long-tail variant)
4. Předlož klientovi k odsouhlasení

**Uložení do DB:**
```sql
CREATE TABLE IF NOT EXISTS {schema}.seed_keywords (
    keyword TEXT,
    language TEXT NOT NULL,
    PRIMARY KEY (keyword, language)
);

INSERT INTO {schema}.seed_keywords (keyword, language) VALUES
('produkt 1', 'cs'), ('produkt 2', 'cs')
ON CONFLICT DO NOTHING;
```

---

### B. Reálná data — GSC + Google Ads

> ⭐ Klíčový krok — reálné dotazy z vlastního webu.

**Použij skill `gsc-ads-keyword-data`**

Filtry (standardní pro keyword analysis):
- **GSC:** posledních 90 dní, jen pozice **≤ 20** (reálně viditelné výsledky)
- **Google Ads:** posledních 90 dní, min. **10 impresí** (odfiltruje statistický šum)

```bash
# GSC data (API varianta)
python3 ../gsc-ads-keyword-data/scripts/fetch_gsc_api.py \
  --project {schema} --site sc-domain:klient.cz --days 90

# Ads search terms (API varianta)
python3 ../gsc-ads-keyword-data/scripts/fetch_ads_search_terms_api.py \
  --project {schema} --customer-id 123-456-7890 --days 90
```

Data jdou do `seo_kws.gsc_search_terms` a `seo_kws.ads_search_terms`.

---

### C. Konkurenti — DataForSEO

**Potřebujeme min. 5 konkurentů.** Jak je identifikovat:
- GSC URL overlap (kdo se zobrazuje na stejné KWs)
- SimilarWeb / Ahrefs
- LLM: "Kdo jsou hlavní online konkurenti pro {web} v {lokalita}?"
- Ruční input od klienta

**Použij skill `dataforseo-competitors`** pro každého konkurenta:

```bash
python3 ../dataforseo-competitors/scripts/competitor_keywords.py {schema} konkurent1.cz --location 2203 --language cs
python3 ../dataforseo-competitors/scripts/competitor_keywords.py {schema} konkurent2.cz --location 2203 --language cs
# ... pro všech 5+ konkurentů
```

Data jdou do `seo.competitor_keywords` (vč. search_volume, rank_absolute, search_intent).

---

### D. Google Ads Keyword Planner — rozšíření seed KWs

**Vstup:** seed keywords + top competitor keywords (top 50 by search_volume)

```sql
-- Top competitor KWs pro KW Planner seeds
SELECT DISTINCT keyword FROM seo.competitor_keywords
WHERE project = '{schema}'
ORDER BY search_volume DESC LIMIT 50;
```

**Použij skill `google-ads-keyword-planner`** — max 20 seeds na batch:

```python
# Batch zpracování seed KWs (max 20 per call)
get_keyword_ideas(language_id=1021, geo_ids=[2203], seed_keywords=batch_of_20)
```

Výsledky ulož do `{schema}.keyword_planner`.

---

### E. Google Autocomplete — 5 zdrojů vstupů

> ⚠️ Každé KW trvá ~2 minuty (49 requestů × 2.5s pauza).

**Vstupní KWs pro autocomplete expansion (5 zdrojů):**

```sql
-- 1. Seed keywords (vždy)
SELECT keyword FROM {schema}.seed_keywords WHERE language = 'cs';

-- 2. Návrhy z KW Planneru (top by volume)
SELECT DISTINCT keyword FROM {schema}.keyword_planner
ORDER BY avg_monthly_searches DESC LIMIT 30;

-- 3. DataForSEO competitor KWs (top by volume)
SELECT DISTINCT keyword FROM seo.competitor_keywords
WHERE project = '{schema}'
ORDER BY search_volume DESC LIMIT 30;

-- 4. Top 10% ze GSC (by impressions)
SELECT query FROM seo_kws.gsc_search_terms
WHERE project = '{schema}'
ORDER BY impressions DESC
LIMIT (SELECT COUNT(*)/10 FROM seo_kws.gsc_search_terms WHERE project = '{schema}');

-- 5. Top 10% z Google Ads (by impressions)
SELECT search_term FROM seo_kws.ads_search_terms
WHERE project = '{schema}'
ORDER BY impressions DESC
LIMIT (SELECT COUNT(*)/10 FROM seo_kws.ads_search_terms WHERE project = '{schema}');
```

**Použij skill `google-autocomplete`** pro každé KW (včetně alphabet expansion a question prefixes):

Výsledky ulož do `{schema}.suggestions`.

---

### F. Google SERP

**Vstup:** seed keywords + top competitor keywords (ne vše — cca 50–100 KWs)

```sql
-- Vstupy pro SERP scraping
SELECT keyword FROM {schema}.seed_keywords
UNION
SELECT keyword FROM seo.competitor_keywords
WHERE project = '{schema}' ORDER BY search_volume DESC LIMIT 50;
```

**Použij skill `google-serp`** (n8n workflow, batch mode):

```bash
curl -s -X POST "https://s.smuz.cz/webhook/.../serp/ingest" \
  -d '{"client": "{schema}", "keywords": [...], "lang": "cs", "country": "cz", "num": 10}'
```

Výstup: organic results v `seo_kws.serp_organic`, related queries v `{schema}.related_queries`.

---

### G. Volume Lookup — doplnění hledanosti

Všechna KWs bez `avg_monthly_searches` → Google Ads KW Planner:

```sql
-- KWs z autocomplete bez volume
SELECT DISTINCT s.suggestion AS keyword
FROM {schema}.suggestions s
LEFT JOIN {schema}.keyword_planner kp ON LOWER(s.suggestion) = LOWER(kp.keyword)
WHERE kp.keyword IS NULL;

-- KWs z related_queries bez volume
SELECT DISTINCT r.related_query AS keyword
FROM {schema}.related_queries r
LEFT JOIN {schema}.keyword_planner kp ON LOWER(r.related_query) = LOWER(kp.keyword)
WHERE kp.keyword IS NULL;
```

Výsledky doplní do `{schema}.keyword_planner`.

---

## Fáze čistění

### H1. Odstranění nulové hledanosti

Před sémantickým čistěním odstraníme KWs bez dat (ušetří čas modelu):

```sql
-- Označení nulových KWs v suggestions
UPDATE {schema}.suggestions s
SET is_relevant = false
FROM {schema}.keyword_planner kp
WHERE LOWER(s.suggestion) = LOWER(kp.keyword)
  AND (kp.avg_monthly_searches = 0 OR kp.avg_monthly_searches IS NULL);

-- Totéž pro related_queries
UPDATE {schema}.related_queries r
SET is_relevant = false
FROM {schema}.keyword_planner kp
WHERE LOWER(r.related_query) = LOWER(kp.keyword)
  AND (kp.avg_monthly_searches = 0 OR kp.avg_monthly_searches IS NULL);
```

### H2. Sémantické čistění *(KWs vs. Seed Keywords)*

> **Co se děje:** Model porovná každé KW se seed keywords. KWs nepodobná žádnému seedy jsou nerelevantní a vyřadí se.

**Použij skill `keyword-cleaning`** (model `paraphrase-multilingual-MiniLM-L12-v2`):

```bash
# 1. Průzkum — najdi threshold (zkontroluj vzorky na různých hranicích)
python3 ../keyword-cleaning/scripts/semantic_cleaner.py \
  --schema {schema} --table suggestions --analyze-only

# 2. Aplikuj řez (typicky 0.25–0.35)
python3 ../keyword-cleaning/scripts/semantic_cleaner.py \
  --schema {schema} --table suggestions --apply-threshold 0.28

# Totéž pro related_queries
python3 ../keyword-cleaning/scripts/semantic_cleaner.py \
  --schema {schema} --table related_queries --apply-threshold 0.28
```

Po čistění: jen KWs s `is_relevant = true` postupují do clusterizace.

---

## Fáze clusterizace

### I. Clusterizace *(KWs vs. KWs — shlukování mezi sebou)*

> **Co se děje:** Relevantní KWs se shlukují mezi sebou do témat a pilířů. Model hledá skupiny podobných KWs — ne porovnává se seedami.

**Použij skill `keyword-categorization`** (nová pipeline: SBERT + UMAP + Agglomerative/HDBSCAN + SERP Jaccard):

```sql
-- Export relevantních KWs pro clusterizaci
SELECT k.keyword, kp.avg_monthly_searches AS search_volume
FROM (
  SELECT suggestion AS keyword FROM {schema}.suggestions WHERE is_relevant = true
  UNION
  SELECT related_query FROM {schema}.related_queries WHERE is_relevant = true
  UNION
  SELECT query FROM seo_kws.gsc_search_terms WHERE project = '{schema}' AND position <= 20
) k
JOIN {schema}.keyword_planner kp ON LOWER(k.keyword) = LOWER(kp.keyword)
WHERE kp.avg_monthly_searches > 0
ORDER BY kp.avg_monthly_searches DESC;
```

```bash
# Export CSV
\copy (<SQL výše>) TO '/tmp/kw_{schema}_for_clustering.csv' CSV HEADER;

# Spusť clustering
python3 ../keyword-categorization/scripts/cluster_keywords.py \
  /tmp/kw_{schema}_for_clustering.csv
```

---

## Klíčové zásady

- **Lokalita a jazyk** — nastav správně v KAŽDÉM kroku (GSC site URL, DataForSEO location, KW Planner geo_id, Autocomplete GL/HL)
- **Min. 5 konkurentů** — DataForSEO bez dostatečného počtu konkurentů dá nekompletní obraz trhu
- **Autocomplete = 5 zdrojů** — seed KWs jsou jen jeden z nich, nezapomeň na GSC/Ads top 10%
- **Čistění před clusterizací** — nikdy neklusteruj nečistá data, model by tvořil shluky z odpadků
- **H1 před H2** — nejdřív odstranit nulovou hledanost (rychlé SQL), pak teprve spouštět model (pomalé)
- **Volume je základ** — KWs bez volume nejsou v kroku H1 automaticky odstraněny, použij `IS NULL` i `= 0`
