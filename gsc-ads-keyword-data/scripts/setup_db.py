#!/usr/bin/env python3
"""
setup_db.py — Create PostgreSQL tables for GSC and Google Ads search term data.

Run once (idempotent — uses IF NOT EXISTS):
    python3 setup_db.py --schema client_name

Tables created in the given schema (seo database).
"""

import argparse
import psycopg2

DB_CONFIG = {
    "host": "78.46.190.162",
    "port": 5432,
    "dbname": "seo",
    "user": "n8n",
    "password": "n8npass",
}

def get_ddl(schema: str) -> str:
    return f"""
CREATE SCHEMA IF NOT EXISTS {schema};

-- -----------------------------------------------------------------------
-- GSC Search Terms
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS {schema}.gsc_search_terms (
    id          SERIAL PRIMARY KEY,
    project     TEXT        NOT NULL,
    date        DATE        NOT NULL,
    query       TEXT        NOT NULL,
    page        TEXT,
    country     TEXT,
    device      TEXT,
    clicks      INTEGER,
    impressions INTEGER,
    ctr         NUMERIC(6,4),
    position    NUMERIC(6,2),
    fetched_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source      TEXT        NOT NULL DEFAULT 'api',
    UNIQUE (project, date, query, page, country, device)
);

CREATE INDEX IF NOT EXISTS gsc_search_terms_project_date_idx ON {schema}.gsc_search_terms (project, date);
CREATE INDEX IF NOT EXISTS gsc_search_terms_query_idx ON {schema}.gsc_search_terms (query);
CREATE INDEX IF NOT EXISTS gsc_search_terms_country_idx ON {schema}.gsc_search_terms (country);

-- -----------------------------------------------------------------------
-- Google Ads Search Terms
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS {schema}.ads_search_terms (
    id            SERIAL PRIMARY KEY,
    project       TEXT        NOT NULL,
    date          DATE        NOT NULL,
    search_term   TEXT        NOT NULL,
    campaign_id   TEXT,
    campaign_name TEXT,
    ad_group_id   TEXT,
    ad_group_name TEXT,
    country       TEXT,
    impressions   INTEGER,
    clicks        INTEGER,
    cost_czk      NUMERIC(12,4),
    conversions   NUMERIC(8,2),
    fetched_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source        TEXT        NOT NULL DEFAULT 'api',
    UNIQUE (project, date, search_term, campaign_id, ad_group_id, country)
);

CREATE INDEX IF NOT EXISTS ads_search_terms_project_date_idx ON {schema}.ads_search_terms (project, date);
CREATE INDEX IF NOT EXISTS ads_search_terms_search_term_idx ON {schema}.ads_search_terms (search_term);
CREATE INDEX IF NOT EXISTS ads_search_terms_country_idx ON {schema}.ads_search_terms (country);
"""

def main():
    parser = argparse.ArgumentParser(description="Create DB tables for keyword data")
    parser.add_argument("--schema", required=True, help="PostgreSQL schema name (e.g. client brand)")
    args = parser.parse_args()

    print(f"Connecting to PostgreSQL: {DB_CONFIG['host']}:{DB_CONFIG['port']} / {DB_CONFIG['dbname']}")
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = True
    cur = conn.cursor()

    print(f"Running DDL for schema '{args.schema}'...")
    cur.execute(get_ddl(args.schema))

    # Verify
    cur.execute(f"""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = '{args.schema}'
          AND table_name IN ('gsc_search_terms', 'ads_search_terms')
        ORDER BY table_name;
    """)
    tables = [r[0] for r in cur.fetchall()]

    print(f"\n✅ Tables in schema '{args.schema}': {', '.join(tables)}")
    if len(tables) == 2:
        print("   Both tables are ready.")
    else:
        print(f"⚠️  Expected 2 tables, found {len(tables)}.")

    cur.close()
    conn.close()

if __name__ == "__main__":
    main()
