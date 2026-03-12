---
name: gsc-ads-keyword-data
description: Fetch Google Search Console (GSC) search terms and Google Ads search term reports into PostgreSQL for keyword analysis. Supports two fetch modes — direct API or BigQuery export. Outputs data to `seo_kws.gsc_search_terms` and `seo_kws.ads_search_terms` tables. Use when the user wants to pull GSC data, Google Ads search terms, build keyword datasets from real traffic/spend data, or analyze search demand with country breakdowns. ALWAYS ASK the user for the data sources (API vs BQ) and credentials before pulling data.
---

# GSC & Google Ads Keyword Data

Stahuje reálná klíčová slova z Google Search Console a Google Ads search terms do PostgreSQL.  
**Výchozí horizont: 90 dní.**

Dvě varianty pro každý zdroj:
- **Varianta API** — volá přímo Google API (vždy aktuální, bez závislosti na BQ exportu).
- **Varianta BigQuery** — čte z BQ datasetu pokud je export nastaven (výhodné pro velké objemy).

> ⚠️ **DŮLEŽITÉ PŘED SPUŠTĚNÍM:** Tento skill je **univerzální**. Před jakýmkoliv během se **VŽDY ZEPTEJ uživatele**:
> 1. Pro jakého klienta a projekt (službu/doménu) data taháme?
> 2. Odkud máme data brát? (Má klient GSC/Ads API přístup, nebo je to už exportované do BigQuery?)
> 3. Který Service Account JSON soubor máme použít pro daného klienta?

---

## Prerekvizity

```bash
pip3 install google-auth google-auth-httplib2 google-api-python-client \
             google-ads google-cloud-bigquery psycopg2-binary python-dotenv
```

---

## Krok 0 — Připrav DB tabulky

Spusť jednou — vytvoří tabulky v PostgreSQL (schema podle zadání) pokud neexistují:

```bash
python3 scripts/setup_db.py --schema nazev_klienta
```

---

## Google Search Console

### Varianta A: API

```bash
python3 scripts/fetch_gsc_api.py \
  --schema nazev_klienta \
  --project project_slug \
  --site sc-domain:klient.cz \
  --days 90
```

**Parametry:**

| Parametr | Default | Popis |
|---|---|---|
| `--schema` | povinný | PostgreSQL schéma klienta, např. `pronatal` |
| `--project` | povinný | Slug projektu (uloží se do DB) |
| `--site` | povinný | GSC property (`sc-domain:example.com` nebo full URL prefix) |
| `--days` | `90` | Počet dní zpětně |
| `--device` | vše | Volitelně: `desktop`, `mobile`, `tablet` |

---

### Varianta B: BigQuery

Použij pokud má klient Search Console → BigQuery export aktivní.

```bash
python3 scripts/fetch_gsc_bigquery.py \
  --schema nazev_klienta \
  --project project_slug \
  --bq-project klient-gcp-project-id \
  --bq-dataset searchconsole_dataset \
  --days 90
```

| Parametr | Default | Popis |
|---|---|---|
| `--schema` | povinný | PostgreSQL schéma |
| `--project` | povinný | Slug projektu |
| `--bq-project` | `nazev-gcp-projektu` | GCP projekt ID |
| `--bq-dataset` | `searchconsole` | BQ dataset name |
| `--bq-table` | `searchdata_site_impression` | BQ tabulka |
| `--days` | `90` | Počet dní |

---

## Google Ads Search Terms

### Varianta A: API

```bash
python3 scripts/fetch_ads_search_terms_api.py \
  --schema nazev_klienta \
  --project project_slug \
  --customer-id 123-456-7890 \
  --days 90
```

| Parametr | Default | Popis |
|---|---|---|
| `--schema` | povinný | PostgreSQL schéma |
| `--project` | povinný | Slug projektu |
| `--customer-id` | povinný | Google Ads customer ID (s nebo bez pomlček) |
| `--days` | `90` | Počet dní (max 90 pro search terms GAQL) |
| `--campaign-ids` | vše | Volitelně: čárkou oddělené campaign IDs |

---

### Varianta B: BigQuery

Použij pokud má klient Google Ads → BigQuery Transfer aktivní.

```bash
python3 scripts/fetch_ads_search_terms_bigquery.py \
  --schema nazev_klienta \
  --project project_slug \
  --bq-project klient-gcp-project-id \
  --bq-dataset google_ads_dataset \
  --customer-id 1234567890 \
  --days 90
```

| Parametr | Default | Popis |
|---|---|---|
| `--schema` | povinný | PostgreSQL schéma |
| `--bq-dataset` | `google_ads` | BQ dataset name |
| `--customer-id` | povinný | Customer ID bez pomlček (BQ tabulka naming) |
| `--days` | `90` | Počet dní |

---

## DB Schema

**Databáze:** `seo` na `78.46.190.162:5432`, schema `seo_kws`

```
seo_kws.gsc_search_terms
  id            SERIAL PRIMARY KEY
  project       TEXT NOT NULL            -- projekt slug
  date          DATE NOT NULL
  query         TEXT NOT NULL            -- hledaný výraz
  page          TEXT                     -- URL stránky
  country       TEXT                     -- ISO 3166-1 alpha-3 (CZE, DEU, ...)
  device        TEXT                     -- desktop / mobile / tablet
  clicks        INTEGER
  impressions   INTEGER
  ctr           NUMERIC(6,4)
  position      NUMERIC(6,2)
  fetched_at    TIMESTAMPTZ
  source        TEXT                     -- 'api' nebo 'bigquery'
  UNIQUE (project, date, query, page, country, device)

seo_kws.ads_search_terms
  id            SERIAL PRIMARY KEY
  project       TEXT NOT NULL
  date          DATE NOT NULL
  search_term   TEXT NOT NULL
  campaign_id   TEXT
  campaign_name TEXT
  ad_group_id   TEXT
  ad_group_name TEXT
  country       TEXT                     -- ISO 3166-1 alpha-3
  impressions   INTEGER
  clicks        INTEGER
  cost_czk      NUMERIC(12,4)            -- cost / 1_000_000 (micros → CZK)
  conversions   NUMERIC(8,2)
  fetched_at    TIMESTAMPTZ
  source        TEXT                     -- 'api' nebo 'bigquery'
  UNIQUE (project, date, search_term, campaign_id, ad_group_id, country)
```

---

## Standardní filtry pro Keyword Analysis Workflow

Při použití v rámci `keywords-analysis` workflow vždy aplikuj tyto filtry:

**GSC — jen pozice ≤ 20:**
```sql
-- Po importu odfiltruj kws mimo top 20
DELETE FROM seo_kws.gsc_search_terms
WHERE project = '{schema}' AND position > 20;

-- Nebo při exportu pro další kroky
SELECT DISTINCT query FROM seo_kws.gsc_search_terms
WHERE project = '{schema}' AND position <= 20
ORDER BY impressions DESC;
```

**Google Ads — min. 10 impresí:**
```sql
-- Po importu odfiltruj statistický šum
DELETE FROM seo_kws.ads_search_terms
WHERE project = '{schema}' AND impressions < 10;

-- Nebo při exportu
SELECT DISTINCT search_term FROM seo_kws.ads_search_terms
WHERE project = '{schema}' AND impressions >= 10
ORDER BY impressions DESC;
```

> Důvod: GSC zobrazuje až pozici ~50, ale KWs pod pozicí 20 mají zanedbatelný traffic. Ads KWs pod 10 impresemi jsou statistický šum bez dostatečných dat.

---

## Nastavení a Credentials (DŮLEŽITÉ)

Před během skriptů uprav v kódu cesty k souborům s Credentials podle konkrétního klienta:

1. **GCP Service Account (GSC + BQ)**: Najdeš v `/Users/adam/Documents/credentials/gcp-service-accounts/` (zeptej se uživatele jaký).
2. **Google Ads YAML**: Aktuální default je `/Users/adam/Documents/credentials/google-ads.yaml` nebo service account verze.

PostgreSQL DB zůstává stejná: `78.46.190.162:5432` / db `seo` / schema `seo_kws` / user `n8n`.
