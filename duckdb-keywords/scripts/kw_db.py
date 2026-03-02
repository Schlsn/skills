#!/usr/bin/env python3
"""
DuckDB Keyword Analysis — project-based database management.

Each project gets its own .duckdb file with standardized table schemas
for SEO data sources. Supports local and remote (SSH) execution.

Usage:
  python kw_db.py create myproject
  python kw_db.py import myproject google_ads ~/exports/gads.csv
  python kw_db.py query myproject "SELECT * FROM google_ads LIMIT 10"
  python kw_db.py tables myproject
  python kw_db.py projects
"""

import argparse
import csv
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

# ── Configuration ───────────────────────────────────────────────────────────

LOCAL_BASE = Path.home() / "kw_projects"
REMOTE_BASE = "/root/kw_projects"
REMOTE_HOST = "hetzner-n8n"

# ── Table schemas ───────────────────────────────────────────────────────────
# Each schema: (table_name, create_sql, csv_column_mapping)
# csv_column_mapping: dict that maps common CSV header variations → our column name

SCHEMAS = {
    "google_ads": {
        "description": "Google Ads keyword data export",
        "create": """
            CREATE TABLE IF NOT EXISTS google_ads (
                keyword VARCHAR NOT NULL,
                search_volume INTEGER,
                competition VARCHAR,
                competition_index DOUBLE,
                cpc DOUBLE,
                currency VARCHAR DEFAULT 'CZK',
                campaign VARCHAR,
                ad_group VARCHAR,
                match_type VARCHAR,
                language VARCHAR,
                country VARCHAR,
                imported_at TIMESTAMP DEFAULT current_timestamp,
                downloaded_at DATE
            )
        """,
        "columns": {
            "keyword": ["keyword", "keywords", "search term", "search terms", "klíčové slovo"],
            "search_volume": ["search volume", "avg. monthly searches", "search_volume", "volume", "hledanost"],
            "competition": ["competition", "konkurence"],
            "competition_index": ["competition (indexed value)", "competition_index"],
            "cpc": ["top of page bid (high range)", "cpc", "avg. cpc", "max cpc"],
            "currency": ["currency", "měna"],
            "campaign": ["campaign", "kampaň"],
            "ad_group": ["ad group", "sestava"],
            "match_type": ["match type", "typ shody"],
            "language": ["language", "jazyk", "lang"],
            "country": ["country", "země", "geo", "loc"],
        },
    },
    "keyword_planner": {
        "description": "Google Keyword Planner export",
        "create": """
            CREATE TABLE IF NOT EXISTS keyword_planner (
                keyword VARCHAR NOT NULL,
                avg_monthly_searches INTEGER,
                competition VARCHAR,
                competition_index DOUBLE,
                top_bid_low DOUBLE,
                top_bid_high DOUBLE,
                currency VARCHAR DEFAULT 'CZK',
                yoy_change DOUBLE,
                three_month_change DOUBLE,
                language VARCHAR,
                country VARCHAR,
                imported_at TIMESTAMP DEFAULT current_timestamp,
                downloaded_at DATE
            )
        """,
        "columns": {
            "keyword": ["keyword", "keywords", "klíčové slovo"],
            "avg_monthly_searches": ["avg. monthly searches", "avg_monthly_searches", "search volume", "volume", "průměrné měsíční vyhledávání"],
            "competition": ["competition", "konkurence"],
            "competition_index": ["competition (indexed value)", "competition_index"],
            "top_bid_low": ["top of page bid (low range)", "low bid", "cpc_low_top_of_page"],
            "top_bid_high": ["top of page bid (high range)", "high bid", "cpc_high_top_of_page"],
            "currency": ["currency", "currency code"],
            "yoy_change": ["yoy change", "year-over-year change"],
            "three_month_change": ["three month change"],
            "language": ["language", "jazyk", "lang"],
            "country": ["country", "země", "geo", "loc"],
        },
    },
    "serp": {
        "description": "Google SERP organic results (from google-serp skill)",
        "create": """
            CREATE TABLE IF NOT EXISTS serp (
                keyword VARCHAR NOT NULL,
                position INTEGER,
                title VARCHAR,
                url VARCHAR,
                description VARCHAR,
                language VARCHAR,
                country VARCHAR,
                imported_at TIMESTAMP DEFAULT current_timestamp,
                downloaded_at DATE
            )
        """,
        "columns": {
            "keyword": ["keyword", "query", "klíčové slovo"],
            "position": ["position", "rank", "pozice", "#"],
            "title": ["title", "nadpis"],
            "url": ["url", "link", "odkaz"],
            "description": ["description", "snippet", "popis"],
            "language": ["language", "jazyk", "lang"],
            "country": ["country", "země", "geo", "loc"],
        },
    },
    "serp_status": {
        "description": "Google SERP execution status tracker",
        "create": """
            CREATE TABLE IF NOT EXISTS serp_status (
                keyword VARCHAR NOT NULL,
                status VARCHAR NOT NULL,
                error_message VARCHAR,
                results_count INTEGER,
                language VARCHAR,
                country VARCHAR,
                imported_at TIMESTAMP DEFAULT current_timestamp,
                downloaded_at DATE
            )
        """,
        "columns": {
            "keyword": ["keyword", "query", "klíčové slovo"],
            "status": ["status", "stav"],
            "error_message": ["error_message", "error", "chyba"],
            "results_count": ["results_count", "results", "počet"],
            "language": ["language", "jazyk", "lang"],
            "country": ["country", "země", "geo", "loc"],
        }
    },
    "suggestions": {
        "description": "Google Autocomplete / Suggest results",
        "create": """
            CREATE TABLE IF NOT EXISTS suggestions (
                seed_keyword VARCHAR NOT NULL,
                suggestion VARCHAR NOT NULL,
                position INTEGER,
                modifier VARCHAR,
                language VARCHAR,
                country VARCHAR,
                imported_at TIMESTAMP DEFAULT current_timestamp,
                downloaded_at DATE
            )
        """,
        "columns": {
            "seed_keyword": ["seed_keyword", "seed", "keyword", "query"],
            "suggestion": ["suggestion", "suggest", "autocomplete", "návrh"],
            "position": ["position", "rank", "pozice"],
            "modifier": ["modifier", "prefix", "suffix"],
            "language": ["language", "jazyk", "lang"],
            "country": ["country", "země", "geo", "loc"],
        },
    },
    "related_queries": {
        "description": "Google Related Searches from SERP",
        "create": """
            CREATE TABLE IF NOT EXISTS related_queries (
                seed_keyword VARCHAR NOT NULL,
                related_query VARCHAR NOT NULL,
                position INTEGER,
                language VARCHAR,
                country VARCHAR,
                imported_at TIMESTAMP DEFAULT current_timestamp,
                downloaded_at DATE
            )
        """,
        "columns": {
            "seed_keyword": ["seed_keyword", "seed", "keyword", "query"],
            "related_query": ["related_query", "related", "query", "související dotaz"],
            "position": ["position", "rank", "pozice"],
            "language": ["language", "jazyk", "lang"],
            "country": ["country", "země", "geo", "loc"],
        },
    },
    "people_also_ask": {
        "description": "People Also Ask questions from SERP",
        "create": """
            CREATE TABLE IF NOT EXISTS people_also_ask (
                seed_keyword VARCHAR NOT NULL,
                question VARCHAR NOT NULL,
                position INTEGER,
                answer_snippet VARCHAR,
                source_url VARCHAR,
                language VARCHAR,
                country VARCHAR,
                imported_at TIMESTAMP DEFAULT current_timestamp,
                downloaded_at DATE
            )
        """,
        "columns": {
            "seed_keyword": ["seed_keyword", "seed", "keyword", "query"],
            "question": ["question", "otázka", "paa"],
            "position": ["position", "rank", "pozice"],
            "answer_snippet": ["answer", "snippet", "answer_snippet"],
            "source_url": ["source_url", "url", "source"],
            "language": ["language", "jazyk", "lang"],
            "country": ["country", "země", "geo", "loc"],
        },
    },
    "search_console": {
        "description": "Google Search Console performance data",
        "create": """
            CREATE TABLE IF NOT EXISTS search_console (
                query VARCHAR NOT NULL,
                page VARCHAR,
                clicks INTEGER,
                impressions INTEGER,
                ctr DOUBLE,
                position DOUBLE,
                country VARCHAR,
                device VARCHAR,
                date DATE,
                language VARCHAR,
                imported_at TIMESTAMP DEFAULT current_timestamp,
                downloaded_at DATE
            )
        """,
        "columns": {
            "query": ["query", "queries", "top queries", "keyword", "dotaz"],
            "page": ["page", "pages", "top pages", "url", "stránka"],
            "clicks": ["clicks", "kliknutí"],
            "impressions": ["impressions", "zobrazení"],
            "ctr": ["ctr", "click through rate", "míra prokliku"],
            "position": ["position", "average position", "pozice"],
            "country": ["country", "země"],
            "device": ["device", "zařízení"],
            "date": ["date", "datum"],
            "language": ["language", "jazyk", "lang"],
        },
    },
    "competitor_keywords": {
        "description": "DataForSEO competitor ranked keywords (top 20)",
        "create": """
            CREATE TABLE IF NOT EXISTS competitor_keywords (
                competitor_domain VARCHAR NOT NULL,
                keyword VARCHAR NOT NULL,
                search_volume INTEGER,
                competition DOUBLE,
                cpc DOUBLE,
                search_intent VARCHAR,
                rank_absolute INTEGER,
                serp_type VARCHAR,
                url VARCHAR,
                title VARCHAR,
                description VARCHAR,
                etv DOUBLE,
                is_paid BOOLEAN,
                monthly_searches_json VARCHAR,
                language VARCHAR,
                country VARCHAR,
                imported_at TIMESTAMP DEFAULT current_timestamp,
                downloaded_at DATE
            )
        """,
        "columns": {
            "competitor_domain": ["competitor_domain", "domain", "target"],
            "keyword": ["keyword", "keywords", "klíčové slovo"],
            "search_volume": ["search_volume", "volume", "hledanost"],
            "competition": ["competition", "konkurence"],
            "cpc": ["cpc", "cost per click"],
            "search_intent": ["search_intent", "intent", "záměr"],
            "rank_absolute": ["rank_absolute", "position", "rank", "pozice"],
            "serp_type": ["serp_type", "type"],
            "url": ["url", "link", "odkaz"],
            "title": ["title", "nadpis"],
            "description": ["description", "snippet", "popis"],
            "etv": ["etv", "estimated_traffic"],
            "is_paid": ["is_paid"],
            "monthly_searches_json": ["monthly_searches_json", "monthly_searches"],
            "language": ["language", "jazyk", "lang"],
            "country": ["country", "země", "geo", "loc", "location"],
        },
    },
}


# ── Column mapping ──────────────────────────────────────────────────────────

def _map_columns(csv_headers: list[str], schema_columns: dict) -> dict[str, str]:
    """Map CSV headers to schema columns. Returns {csv_header: schema_col}."""
    mapping = {}
    csv_lower = {h: h.lower().strip() for h in csv_headers}

    for schema_col, aliases in schema_columns.items():
        for header, header_low in csv_lower.items():
            if header_low in [a.lower() for a in aliases]:
                mapping[header] = schema_col
                break

    return mapping


# ── DuckDB execution ───────────────────────────────────────────────────────

def _run_local(db_path: str, sql: str) -> str:
    """Execute SQL against a local DuckDB database."""
    try:
        import duckdb
    except ImportError:
        print("Installing duckdb locally...", file=sys.stderr)
        os.system(f"{sys.executable} -m pip install duckdb --break-system-packages -q")
        import duckdb

    con = duckdb.connect(db_path)
    try:
        result = con.sql(sql)
        if result is not None:
            return result.fetchdf().to_string(index=False)
        return "OK"
    finally:
        con.close()


def _run_remote(db_path: str, sql: str) -> str:
    """Execute SQL on the remote Hetzner server via SSH."""
    # Escape for shell
    escaped_sql = sql.replace("'", "'\\''")
    cmd = (
        f"ssh {REMOTE_HOST} "
        f"\"python3 -c \\\"import duckdb; con = duckdb.connect('{db_path}'); "
        f"r = con.sql('{escaped_sql}'); "
        f"print(r.fetchdf().to_string(index=False) if r is not None else 'OK'); "
        f"con.close()\\\"\""
    )
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"Remote execution failed: {result.stderr.strip()}")
    return result.stdout.strip()


def run_sql(project: str, sql: str, remote: bool = False) -> str:
    """Execute SQL against a project database."""
    if remote:
        db_path = f"{REMOTE_BASE}/{project}.duckdb"
        return _run_remote(db_path, sql)
    else:
        db_path = str(LOCAL_BASE / f"{project}.duckdb")
        return _run_local(db_path, sql)


# ── Project management ─────────────────────────────────────────────────────

def create_project(project: str, remote: bool = False) -> str:
    """Create a new project database with all table schemas."""
    if remote:
        db_dir = REMOTE_BASE
        subprocess.run(f"ssh {REMOTE_HOST} 'mkdir -p {db_dir}'",
                        shell=True, check=True)
    else:
        LOCAL_BASE.mkdir(parents=True, exist_ok=True)

    # Create all tables
    for name, schema in SCHEMAS.items():
        run_sql(project, schema["create"], remote=remote)

    location = f"{REMOTE_HOST}:{REMOTE_BASE}" if remote else str(LOCAL_BASE)
    return f"Project '{project}' created at {location}/{project}.duckdb"


def list_projects(remote: bool = False) -> str:
    """List all project databases."""
    if remote:
        result = subprocess.run(
            f"ssh {REMOTE_HOST} 'ls -lh {REMOTE_BASE}/*.duckdb 2>/dev/null || echo \"No projects\"'",
            shell=True, capture_output=True, text=True
        )
        return result.stdout.strip()
    else:
        LOCAL_BASE.mkdir(parents=True, exist_ok=True)
        files = list(LOCAL_BASE.glob("*.duckdb"))
        if not files:
            return "No projects"
        lines = []
        for f in sorted(files):
            size = f.stat().st_size / (1024 * 1024)
            lines.append(f"  {f.stem:30s} {size:8.1f} MB")
        return "\n".join(lines)


def show_tables(project: str, remote: bool = False) -> str:
    """Show all tables and row counts for a project."""
    tables = []
    for name in SCHEMAS:
        try:
            result = run_sql(project, f"SELECT COUNT(*) AS n FROM {name}", remote=remote)
            # Parse count from result
            count = result.strip().split('\n')[-1].strip()
            tables.append(f"  {name:25s} {count:>10s} rows")
        except Exception:
            tables.append(f"  {name:25s}      0 rows")
    return "\n".join(tables)


# ── CSV Import ──────────────────────────────────────────────────────────────

def import_csv(
    project: str,
    table: str,
    csv_path: str,
    downloaded_at: str | None = None,
    csv_sep: str = ',',
    remote: bool = False,
) -> str:
    """Import a CSV file into a project table with column auto-mapping."""
    if table not in SCHEMAS:
        available = ", ".join(SCHEMAS.keys())
        raise ValueError(f"Unknown table '{table}'. Available: {available}")

    schema = SCHEMAS[table]
    csv_path = os.path.expanduser(csv_path)

    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    # Read CSV headers
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f, delimiter=csv_sep)
        headers = next(reader)

    # Map columns
    mapping = _map_columns(headers, schema["columns"])
    if not mapping:
        raise ValueError(
            f"No columns matched for table '{table}'.\n"
            f"  CSV headers: {headers}\n"
            f"  Expected: {list(schema['columns'].keys())}"
        )

    # Download date
    dl_date = downloaded_at or datetime.now().strftime('%Y-%m-%d')

    if remote:
        # Upload CSV to server, then import
        remote_csv = f"/tmp/kw_import_{table}_{os.getpid()}.csv"
        subprocess.run(f"scp '{csv_path}' {REMOTE_HOST}:{remote_csv}",
                        shell=True, check=True)

        # Build import SQL
        select_cols = ", ".join(
            f'"{csv_col}" AS {schema_col}' for csv_col, schema_col in mapping.items()
        )
        sql = (
            f"{schema['create']}; "
            f"INSERT INTO {table} ({', '.join(mapping.values())}, downloaded_at) "
            f"SELECT {select_cols}, DATE '{dl_date}' "
            f"FROM read_csv_auto('{remote_csv}', delim='{csv_sep}', header=true);"
        )
        run_sql(project, sql, remote=True)

        # Cleanup
        subprocess.run(f"ssh {REMOTE_HOST} 'rm -f {remote_csv}'", shell=True)
    else:
        import duckdb

        db_path = str(LOCAL_BASE / f"{project}.duckdb")
        con = duckdb.connect(db_path)

        # Ensure table exists
        con.sql(schema["create"])

        # Import with mapping
        select_cols = ", ".join(
            f'"{csv_col}" AS {schema_col}' for csv_col, schema_col in mapping.items()
        )
        con.sql(
            f"INSERT INTO {table} ({', '.join(mapping.values())}, downloaded_at) "
            f"SELECT {select_cols}, DATE '{dl_date}' "
            f"FROM read_csv_auto('{csv_path}', delim='{csv_sep}', header=true)"
        )
        con.close()

    # Count
    count = run_sql(project, f"SELECT COUNT(*) FROM {table}", remote=remote)
    mapped_cols = list(mapping.values())
    return (
        f"Imported into {table} (downloaded: {dl_date})\n"
        f"  Mapped columns: {mapped_cols}\n"
        f"  Total rows now: {count.strip().split(chr(10))[-1].strip()}"
    )


# ── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='DuckDB Keyword Analysis — Project Database Manager'
    )
    parser.add_argument('--remote', '-r', action='store_true',
                        help='Run on remote Hetzner server via SSH')
    sub = parser.add_subparsers(dest='command', required=True)

    # create
    p_create = sub.add_parser('create', help='Create a new project database')
    p_create.add_argument('project', help='Project name (becomes <name>.duckdb)')

    # projects
    sub.add_parser('projects', help='List all project databases')

    # tables
    p_tables = sub.add_parser('tables', help='Show tables and row counts')
    p_tables.add_argument('project', help='Project name')

    # import
    p_import = sub.add_parser('import', help='Import CSV into a table')
    p_import.add_argument('project', help='Project name')
    p_import.add_argument('table', choices=list(SCHEMAS.keys()), help='Target table')
    p_import.add_argument('csv', help='Path to CSV file')
    p_import.add_argument('--date', default=None, help='Download date (YYYY-MM-DD, default: today)')
    p_import.add_argument('--sep', default=',', help='CSV separator (default: ,)')

    # query
    p_query = sub.add_parser('query', help='Run SQL query')
    p_query.add_argument('project', help='Project name')
    p_query.add_argument('sql', help='SQL query string')

    # schemas
    sub.add_parser('schemas', help='Show all available table schemas')

    args = parser.parse_args()

    if args.command == 'create':
        print(create_project(args.project, remote=args.remote))
    elif args.command == 'projects':
        print(list_projects(remote=args.remote))
    elif args.command == 'tables':
        print(show_tables(args.project, remote=args.remote))
    elif args.command == 'import':
        print(import_csv(args.project, args.table, args.csv,
                          downloaded_at=args.date, csv_sep=args.sep,
                          remote=args.remote))
    elif args.command == 'query':
        print(run_sql(args.project, args.sql, remote=args.remote))
    elif args.command == 'schemas':
        for name, schema in SCHEMAS.items():
            print(f"\n{'─' * 60}")
            print(f"  {name}: {schema['description']}")
            print(f"  Columns: {', '.join(schema['columns'].keys())}")
        print()


if __name__ == '__main__':
    main()
