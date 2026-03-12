#!/usr/bin/env python3
"""
fetch_ads_search_terms_bigquery.py — Fetch Google Ads search terms from BigQuery → PostgreSQL.

Requires Google Ads → BigQuery Transfer configured in GCP.
BigQuery table pattern: <bq_dataset>.SearchTermView_<customer_id>

Usage:
    python3 fetch_ads_search_terms_bigquery.py \
        --project {schema}.\
        --bq-project {schema}.487209 \
        --bq-dataset google_ads \
        --customer-id 8186212095 \
        --days 90

Prerequisites:
    pip3 install google-cloud-bigquery psycopg2-binary
"""

import argparse
import re

import psycopg2
import psycopg2.extras
from google.cloud import bigquery
from google.oauth2 import service_account

# ── Configuration ─────────────────────────────────────────────────────────────

SERVICE_ACCOUNT_FILE = "/Users/adam/Documents/credentials/gcp-service-accounts/pronatal-487209-e7ffaaf00c76.json"

DB_CONFIG = {
    "host": "78.46.190.162",
    "port": 5432,
    "dbname": "seo",
    "user": "n8n",
    "password": "n8npass",
}

# Geo criterion ID → ISO 3166-1 alpha-3 (same map as API script)
GEO_ID_TO_ALPHA3 = {
    "2203": "CZE", "2276": "DEU", "2040": "AUT", "2756": "CHE",
    "2826": "GBR", "2372": "IRL", "2250": "FRA", "2380": "ITA",
    "2528": "NLD", "2056": "BEL", "2616": "POL", "2191": "HRV",
    "2688": "SRB", "2070": "BIH", "2840": "USA", "2752": "SWE",
    "2578": "NOR", "2208": "DNK", "2348": "HUN", "2703": "SVK",
    "2705": "SVN", "2642": "ROU", "2100": "BGR", "2300": "GRC",
    "2804": "UKR", "2643": "RUS",
}

# ── BigQuery SQL ───────────────────────────────────────────────────────────────
# Google Ads BQ transfer schema: SearchTermView table
# Ref: https://developers.google.com/google-ads/api/docs/reporting/scheduling

BQ_QUERY = """
SELECT
    segments_date                           AS date,
    search_term_view_search_term            AS search_term,
    CAST(campaign_id AS STRING)             AS campaign_id,
    campaign_name                           AS campaign_name,
    CAST(ad_group_id AS STRING)             AS ad_group_id,
    ad_group_name                           AS ad_group_name,
    CAST(segments_country_criterion_id AS STRING) AS geo_id,
    SUM(metrics_impressions)                AS impressions,
    SUM(metrics_clicks)                     AS clicks,
    SUM(metrics_cost_micros) / 1000000.0    AS cost_czk,
    SUM(metrics_conversions)                AS conversions
FROM `{bq_project}.{bq_dataset}.SearchTermView_{customer_id}`
WHERE DATE(segments_date) >= DATE_SUB(CURRENT_DATE(), INTERVAL {days} DAY)
  AND search_term_view_status != 'ADDED_EXCLUDED'
GROUP BY 1, 2, 3, 4, 5, 6, 7
ORDER BY impressions DESC
"""


def normalize_customer_id(cid: str) -> str:
    return re.sub(r"[^0-9]", "", cid)


def build_bq_client() -> bigquery.Client:
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    return bigquery.Client(credentials=creds, project=creds.project_id)


def fetch_from_bigquery(bq_project: str, bq_dataset: str, customer_id: str, days: int) -> list:
    client = build_bq_client()
    query = BQ_QUERY.format(
        bq_project=bq_project,
        bq_dataset=bq_dataset,
        customer_id=customer_id,
        days=days,
    )
    full_table = f"{bq_project}.{bq_dataset}.SearchTermView_{customer_id}"
    print(f"\nQuerying BigQuery: {full_table}")
    print(f"  Period: last {days} days")
    result = client.query(query)
    rows = list(result)
    print(f"  Rows returned: {len(rows)}")
    return rows


def parse_bq_rows(rows, project: str) -> list[dict]:
    records = []
    for row in rows:
        geo_id = str(row["geo_id"]) if row["geo_id"] else None
        country = GEO_ID_TO_ALPHA3.get(geo_id, geo_id) if geo_id else None

        records.append({
            "project":       project,
            "date":          row["date"].isoformat() if row["date"] else None,
            "search_term":   row["search_term"],
            "campaign_id":   row["campaign_id"],
            "campaign_name": row["campaign_name"],
            "ad_group_id":   row["ad_group_id"],
            "ad_group_name": row["ad_group_name"],
            "country":       country,
            "impressions":   int(row["impressions"] or 0),
            "clicks":        int(row["clicks"] or 0),
            "cost_czk":      round(float(row["cost_czk"] or 0), 4),
            "conversions":   round(float(row["conversions"] or 0), 2),
            "source":        "bigquery",
        })
    return records


def upsert_to_postgres(records: list[dict], project: str, schema: str) -> int:
    if not records:
        print("  No records to insert.")
        return 0

    conn = psycopg2.connect(**DB_CONFIG)
    cur  = conn.cursor()

    query = f"""
        INSERT INTO {schema}.ads_search_terms
            (project, date, search_term, campaign_id, campaign_name,
             ad_group_id, ad_group_name, country,
             impressions, clicks, cost_czk, conversions, source)
        VALUES
            (%(project)s, %(date)s, %(search_term)s, %(campaign_id)s, %(campaign_name)s,
             %(ad_group_id)s, %(ad_group_name)s, %(country)s,
             %(impressions)s, %(clicks)s, %(cost_czk)s, %(conversions)s, %(source)s)
        ON CONFLICT (project, date, search_term, campaign_id, ad_group_id, country)
        DO UPDATE SET
            campaign_name = EXCLUDED.campaign_name,
            ad_group_name = EXCLUDED.ad_group_name,
            impressions   = EXCLUDED.impressions,
            clicks        = EXCLUDED.clicks,
            cost_czk      = EXCLUDED.cost_czk,
            conversions   = EXCLUDED.conversions,
            fetched_at    = NOW(),
            source        = EXCLUDED.source;
    """

    psycopg2.extras.execute_batch(cur, query, records, page_size=500)
    conn.commit()
    count = len(records)
    cur.close()
    conn.close()
    return count


def main():
    parser = argparse.ArgumentParser(
        description="Fetch Google Ads search terms from BigQuery → PostgreSQL"
    )
    parser.add_argument("--project",     required=True, help="Project slug stored in DB")
    parser.add_argument("--bq-project",  default="{schema}.487209", help="GCP project ID")
    parser.add_argument("--bq-dataset",  default="google_ads",       help="BigQuery dataset name")
    parser.add_argument("--customer-id", required=True, help="Google Ads customer ID (digits only or dashes)")
    parser.add_argument("--days",        type=int, default=90, help="Days back (default: 90)")
    parser.add_argument("--schema", required=True, help="PostgreSQL schema to save data to (e.g. client_name)")

    args = parser.parse_args()

    cid = normalize_customer_id(args.customer_id)

    rows    = fetch_from_bigquery(args.bq_project, args.bq_dataset, cid, args.days)
    records = parse_bq_rows(rows, args.project)

    print(f"\nUpserting {len(records)} rows into {args.schema}.ads_search_terms ...")
    inserted = upsert_to_postgres(records, args.project, args.schema)
    print(f"✅ Done — {inserted} rows upserted.")


if __name__ == "__main__":
    main()
