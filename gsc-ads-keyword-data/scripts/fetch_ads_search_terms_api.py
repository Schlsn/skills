#!/usr/bin/env python3
"""
fetch_ads_search_terms_api.py — Fetch Google Ads search term data via GAQL → PostgreSQL.

Uses the Google Ads Python SDK (google-ads) with service account credentials.
Queries search_term_view for the last N days with country segmentation.

Usage:
    python3 fetch_ads_search_terms_api.py \
        --project {schema}.\
        --customer-id 818-621-2095 \
        --days 90

    # Specific campaigns only:
    python3 fetch_ads_search_terms_api.py \
        --project {schema}.\
        --customer-id 818-621-2095 \
        --campaign-ids 123456789,987654321 \
        --days 90

Prerequisites:
    pip3 install google-ads psycopg2-binary
"""

import argparse
import re
from datetime import date, timedelta

import psycopg2
import psycopg2.extras
from google.ads.googleads.client import GoogleAdsClient

# ── Configuration ─────────────────────────────────────────────────────────────

GOOGLE_ADS_YAML = "/Users/adam/Documents/credentials/google-ads-service-account.yaml"

DB_CONFIG = {
    "host": "78.46.190.162",
    "port": 5432,
    "dbname": "seo",
    "user": "n8n",
    "password": "n8npass",
}

# Google Ads geo_target resource → ISO 3166-1 alpha-3 (most common for {schema}.
# Full mapping not feasible here — we parse the numeric ID from the resource name
# and rely on the country_criterion_id to alpha-3 conversion below.
# Country segments come as resource names: "geoTargetConstants/2203"
GEO_ID_TO_ALPHA3 = {
    "2203": "CZE",
    "2276": "DEU",
    "2040": "AUT",
    "2756": "CHE",
    "2826": "GBR",
    "2372": "IRL",
    "2250": "FRA",
    "2380": "ITA",
    "2528": "NLD",
    "2056": "BEL",
    "2616": "POL",
    "2191": "HRV",
    "2688": "SRB",
    "2070": "BIH",
    "2840": "USA",
    "2752": "SWE",
    "2578": "NOR",
    "2208": "DNK",
    "2348": "HUN",
    "2703": "SVK",
    "2705": "SVN",
    "2642": "ROU",
    "2100": "BGR",
    "2300": "GRC",
    "2804": "UKR",
    "2643": "RUS",
}


def normalize_customer_id(cid: str) -> str:
    """Convert '818-621-2095' or '8186212095' to '8186212095'."""
    return re.sub(r"[^0-9]", "", cid)


def geo_resource_to_alpha3(geo_resource: str) -> str | None:
    """Convert 'geoTargetConstants/2203' to 'CZE'."""
    if not geo_resource:
        return None
    geo_id = geo_resource.split("/")[-1]
    return GEO_ID_TO_ALPHA3.get(geo_id, geo_id)  # fallback to raw ID if unknown


def build_gaql(start_date: str, end_date: str, campaign_ids: list[str] | None = None) -> str:
    campaign_filter = ""
    if campaign_ids:
        ids_str = ", ".join(f"'{c}'" for c in campaign_ids)
        campaign_filter = f"  AND campaign.id IN ({ids_str})\n"

    return f"""
SELECT
    segments.date,
    search_term_view.search_term,
    campaign.id,
    campaign.name,
    ad_group.id,
    ad_group.name,
    metrics.impressions,
    metrics.clicks,
    metrics.cost_micros,
    metrics.conversions
FROM search_term_view
WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
  AND search_term_view.status != 'ADDED_EXCLUDED'
  AND metrics.impressions > 0
{campaign_filter}ORDER BY metrics.impressions DESC
""".strip()


def fetch_search_terms(customer_id: str, days: int, campaign_ids: list[str] | None, login_customer_id: str | None = None) -> list[dict]:
    end_date = date.today().isoformat()
    start_date = (date.today() - timedelta(days=days)).isoformat()
    
    client = GoogleAdsClient.load_from_storage(GOOGLE_ADS_YAML)
    if login_customer_id:
        client.login_customer_id = normalize_customer_id(login_customer_id)
        
    ga_service = client.get_service("GoogleAdsService")

    gaql = build_gaql(start_date, end_date, campaign_ids)
    print(f"\nRunning GAQL on customer {customer_id} ...")

    records = []
    response = ga_service.search_stream(customer_id=customer_id, query=gaql)

    for batch in response:
        for row in batch.results:
            seg = row.segments
            m   = row.metrics

            records.append({
                "date":          seg.date,
                "search_term":   row.search_term_view.search_term,
                "campaign_id":   str(row.campaign.id),
                "campaign_name": row.campaign.name,
                "ad_group_id":   str(row.ad_group.id),
                "ad_group_name": row.ad_group.name,
                "country":       None,
                "impressions":   m.impressions,
                "clicks":        m.clicks,
                "cost_czk":      round(m.cost_micros / 1_000_000, 4),
                "conversions":   round(m.conversions, 2),
            })

    print(f"  Rows fetched: {len(records)}")
    return records


def upsert_to_postgres(records: list[dict], project: str, schema: str) -> int:
    if not records:
        print("  No records to insert.")
        return 0

    for r in records:
        r["project"] = project
        r["source"]  = "api"

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
        description="Fetch Google Ads search terms via API → PostgreSQL"
    )
    parser.add_argument("--project",     required=True, help="Project slug stored in DB")
    parser.add_argument("--customer-id", required=True, help="Google Ads customer ID")
    parser.add_argument("--days",        type=int, default=90,
                        help="Days back — max 90 for search_term_view (default: 90)")
    parser.add_argument("--campaign-ids", default=None,
                        help="Comma-separated campaign IDs to filter (optional)")
    parser.add_argument("--schema", required=True, help="PostgreSQL schema to save data to (e.g. client_name)")
    parser.add_argument("--login-customer-id", default="1764032686", help="MCC login customer ID if logging in via manager account")

    args = parser.parse_args()

    if args.days > 90:
        print("⚠️  Google Ads search_term_view supports max 90 days. Clamping to 90.")
        args.days = 90

    cid = normalize_customer_id(args.customer_id)
    campaign_ids = [c.strip() for c in args.campaign_ids.split(",")] if args.campaign_ids else None

    records = fetch_search_terms(cid, args.days, campaign_ids, args.login_customer_id)

    print(f"\nUpserting {len(records)} rows into {args.schema}.ads_search_terms ...")
    inserted = upsert_to_postgres(records, args.project, args.schema)
    print(f"✅ Done — {inserted} rows upserted.")


if __name__ == "__main__":
    main()
