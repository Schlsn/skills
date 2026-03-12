#!/usr/bin/env python3
"""
fetch_gsc_bigquery.py — Fetch GSC search data from BigQuery export → PostgreSQL.

Requires Search Console linked to BigQuery (via GSC Settings → BigQuery export).
BigQuery table: searchconsole.searchdata_site_impression

Usage:
    python3 fetch_gsc_bigquery.py \
        --project {schema}.\
        --bq-project {schema}.487209 \
        --bq-dataset searchconsole \
        --days 90

Prerequisites:
    pip3 install google-cloud-bigquery psycopg2-binary
    GOOGLE_APPLICATION_CREDENTIALS or service account via GOOGLE_CLOUD_PROJECT env.
"""

import argparse
import os
from datetime import date, timedelta

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

# ── BigQuery query ─────────────────────────────────────────────────────────────

BQ_QUERY = """
SELECT
    data_date                               AS date,
    query,
    url                                     AS page,
    country                                 AS country,     -- ISO 3166-1 alpha-3
    LOWER(device)                           AS device,
    SUM(clicks)                             AS clicks,
    SUM(impressions)                        AS impressions,
    SAFE_DIVIDE(SUM(clicks), SUM(impressions)) AS ctr,
    AVG(average_position)                   AS position
FROM `{bq_project}.{bq_dataset}.{bq_table}`
WHERE data_date >= DATE_SUB(CURRENT_DATE(), INTERVAL {days} DAY)
  AND search_type = 'WEB'
GROUP BY date, query, url, country, device
ORDER BY impressions DESC
"""


def build_bq_client() -> bigquery.Client:
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    return bigquery.Client(credentials=creds, project=creds.project_id)


def fetch_from_bigquery(
    bq_project: str, bq_dataset: str, bq_table: str, days: int
) -> list[dict]:
    client = build_bq_client()
    query = BQ_QUERY.format(
        bq_project=bq_project,
        bq_dataset=bq_dataset,
        bq_table=bq_table,
        days=days,
    )
    print(f"\nQuerying BigQuery: {bq_project}.{bq_dataset}.{bq_table}")
    print(f"  Period: last {days} days")
    result = client.query(query)
    rows = list(result)
    print(f"  Rows returned: {len(rows)}")
    return rows


def parse_bq_rows(rows, project: str) -> list[dict]:
    records = []
    for row in rows:
        records.append({
            "project":     project,
            "date":        row["date"].isoformat() if row["date"] else None,
            "query":       row["query"],
            "page":        row["page"],
            "country":     row["country"].upper() if row["country"] else None,
            "device":      row["device"],
            "clicks":      int(row["clicks"] or 0),
            "impressions": int(row["impressions"] or 0),
            "ctr":         round(float(row["ctr"] or 0), 6),
            "position":    round(float(row["position"] or 0), 2),
            "source":      "bigquery",
        })
    return records


def upsert_to_postgres(records: list[dict], project: str, schema: str) -> int:
    if not records:
        print("  No records to insert.")
        return 0

    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    query = f"""
        INSERT INTO {schema}.gsc_search_terms
            (project, date, query, page, country, device,
             clicks, impressions, ctr, position, source)
        VALUES
            (%(project)s, %(date)s, %(query)s, %(page)s, %(country)s, %(device)s,
             %(clicks)s, %(impressions)s, %(ctr)s, %(position)s, %(source)s)
        ON CONFLICT (project, date, query, page, country, device)
        DO UPDATE SET
            clicks      = EXCLUDED.clicks,
            impressions = EXCLUDED.impressions,
            ctr         = EXCLUDED.ctr,
            position    = EXCLUDED.position,
            fetched_at  = NOW(),
            source      = EXCLUDED.source;
    """

    psycopg2.extras.execute_batch(cur, query, records, page_size=500)
    conn.commit()
    count = len(records)
    cur.close()
    conn.close()
    return count


def main():
    parser = argparse.ArgumentParser(
        description="Fetch GSC data from BigQuery → PostgreSQL"
    )
    parser.add_argument("--project", required=True, help="Project slug stored in DB")
    parser.add_argument(
        "--bq-project", default="{schema}.487209", help="GCP project ID"
    )
    parser.add_argument(
        "--bq-dataset", default="searchconsole", help="BigQuery dataset name"
    )
    parser.add_argument(
        "--bq-table",
        default="searchdata_site_impression",
        help="BigQuery table name",
    )
    parser.add_argument(
        "--days", type=int, default=90, help="Number of days back (default: 90)"
    )
    parser.add_argument("--schema", required=True, help="PostgreSQL schema to save data to (e.g. client_name)")

    args = parser.parse_args()

    rows = fetch_from_bigquery(args.bq_project, args.bq_dataset, args.bq_table, args.days)
    records = parse_bq_rows(rows, args.project)

    print(f"\nUpserting {len(records)} rows into {args.schema}.gsc_search_terms ...")
    inserted = upsert_to_postgres(records, args.project, args.schema)
    print(f"✅ Done — {inserted} rows upserted.")


if __name__ == "__main__":
    main()
