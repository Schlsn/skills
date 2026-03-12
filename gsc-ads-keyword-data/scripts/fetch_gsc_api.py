#!/usr/bin/env python3
"""
fetch_gsc_api.py — Fetch Google Search Console search analytics via API.

Fetches data for the last N days with dimensions: query, page, country, device.
Stores results in {schema}.gsc_search_terms (upsert).

Usage:
    python3 fetch_gsc_api.py --project {schema}.--site sc-domain:{schema}.cz --days 90

Prerequisites:
    pip3 install google-auth google-auth-httplib2 google-api-python-client psycopg2-binary
    Service account must have "Search Console" permission on the property.
"""

import argparse
import sys
from datetime import date, timedelta

import psycopg2
import psycopg2.extras
from google.oauth2 import service_account
from googleapiclient.discovery import build

# ── Configuration ─────────────────────────────────────────────────────────────

SERVICE_ACCOUNT_FILE = "/Users/adam/Documents/credentials/gcp-service-accounts/pronatal-487209-e7ffaaf00c76.json"
SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]

DB_CONFIG = {
    "host": "78.46.190.162",
    "port": 5432,
    "dbname": "seo",
    "user": "n8n",
    "password": "n8npass",
}

ROW_LIMIT = 25_000  # max per GSC API request

# ── GSC country codes are ISO 3166-1 alpha-3 already ──────────────────────────


def build_service():
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    return build("searchconsole", "v1", credentials=creds)


def fetch_rows(service, site_url: str, start_date: str, end_date: str) -> list[dict]:
    """Paginate through GSC searchanalytics.query — returns all rows."""
    all_rows = []
    start_row = 0

    while True:
        body = {
            "startDate": start_date,
            "endDate": end_date,
            "dimensions": ["query", "page", "country", "device"],
            "rowLimit": ROW_LIMIT,
            "startRow": start_row,
            "dataState": "final",
        }
        response = (
            service.searchanalytics()
            .query(siteUrl=site_url, body=body)
            .execute()
        )
        rows = response.get("rows", [])
        if not rows:
            break

        all_rows.extend(rows)
        print(f"  Fetched rows {start_row + 1}–{start_row + len(rows)} ...")

        if len(rows) < ROW_LIMIT:
            break  # last page
        start_row += ROW_LIMIT

    return all_rows


def parse_rows(rows: list[dict], project: str, source: str = "api") -> list[dict]:
    """Convert raw GSC response rows to dicts ready for DB insertion."""
    records = []
    for row in rows:
        keys = row.get("keys", [])
        # dimensions order matches request: query, page, country, device
        query   = keys[0] if len(keys) > 0 else None
        page    = keys[1] if len(keys) > 1 else None
        country = keys[2].upper() if len(keys) > 2 else None   # GSC returns ISO alpha-3
        device  = keys[3].lower() if len(keys) > 3 else None

        records.append({
            "project":     project,
            "date":        None,   # GSC aggregated over range — date set in caller
            "query":       query,
            "page":        page,
            "country":     country,
            "device":      device,
            "clicks":      int(row.get("clicks", 0)),
            "impressions": int(row.get("impressions", 0)),
            "ctr":         round(row.get("ctr", 0), 6),
            "position":    round(row.get("position", 0), 2),
            "source":      source,
        })
    return records


def fetch_by_date_range(service, site_url: str, start_date: str, end_date: str, project: str) -> list[dict]:
    """Fetch all rows and tag them with the query end_date as the date marker."""
    print(f"\nFetching GSC data for {site_url}")
    print(f"  Period: {start_date} → {end_date}")
    rows = fetch_rows(service, site_url, start_date, end_date)
    print(f"  Total rows fetched: {len(rows)}")
    records = parse_rows(rows, project)
    # Tag all records with end_date (represents the period)
    for r in records:
        r["date"] = end_date
    return records


def upsert_to_postgres(records: list[dict], project: str, schema: str) -> int:
    """Upsert records into {schema}.gsc_search_terms. Returns row count inserted/updated."""
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
        description="Fetch GSC search analytics → PostgreSQL"
    )
    parser.add_argument("--project", required=True, help="Project slug stored in DB")
    parser.add_argument(
        "--site",
        required=True,
        help="GSC property (e.g. sc-domain:{schema}.cz or https://{schema}.cz/)",
    )
    parser.add_argument(
        "--days", type=int, default=90, help="Number of days back (default: 90)"
    )
    parser.add_argument(
        "--end-date",
        default=None,
        help="End date YYYY-MM-DD (default: yesterday)",
    )
    parser.add_argument("--schema", required=True, help="PostgreSQL schema to save data to (e.g. client_name)")

    args = parser.parse_args()

    # GSC data typically has a 3-day delay; use yesterday as safe end date
    end = date.fromisoformat(args.end_date) if args.end_date else date.today() - timedelta(days=3)
    start = end - timedelta(days=args.days - 1)
    end_str   = end.isoformat()
    start_str = start.isoformat()

    service = build_service()
    records = fetch_by_date_range(service, args.site, start_str, end_str, args.project)

    print(f"\nUpserting {len(records)} rows into {args.schema}.gsc_search_terms ...")
    inserted = upsert_to_postgres(records, args.project, args.schema)
    print(f"✅ Done — {inserted} rows upserted.")


if __name__ == "__main__":
    main()
