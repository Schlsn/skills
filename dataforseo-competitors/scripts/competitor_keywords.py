#!/usr/bin/env python3
"""
DataForSEO Competitors — Ranked Keywords Fetcher & DuckDB Importer

Fetches keywords a competitor domain ranks for (top 20 positions)
using DataForSEO Labs Ranked Keywords API and stores them in DuckDB.

Usage:
  python3 competitor_keywords.py <project> <domain> [options]

Examples:
  python3 competitor_keywords.py pronatal pronatal.cz
  python3 competitor_keywords.py pronatal pronatal.cz --location 2203 --language cs --limit 500
  python3 competitor_keywords.py pronatal pronatal.cz --csv ~/exports/pronatal.csv
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# ── DataForSEO credentials ─────────────────────────────────────────────────

CONFIG_PATH = Path.home() / ".dataforseo_config.json"


def _load_credentials() -> tuple[str, str]:
    """Load DataForSEO credentials from config file."""
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            "DataForSEO credentials not found. "
            "Set up via the 'dataforseo' skill first: "
            "python dataforseo_client.py --setup"
        )
    with open(CONFIG_PATH) as f:
        config = json.load(f)
    return config["login"], config["password"]


# ── API call ────────────────────────────────────────────────────────────────

def fetch_competitor_keywords(
    domain: str,
    location_code: int = 2203,
    language_code: str = "cs",
    limit: int = 500,
) -> list[dict]:
    """
    Fetch ranked keywords for a domain (top 20 positions).

    Returns a list of parsed keyword dicts ready for DuckDB insertion.
    """
    import base64
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError, URLError

    login, password = _load_credentials()
    auth = base64.b64encode(f"{login}:{password}".encode()).decode()

    url = "https://api.dataforseo.com/v3/dataforseo_labs/google/ranked_keywords/live"
    payload = [{
        "target": domain,
        "location_code": location_code,
        "language_code": language_code,
        "historical_serp_mode": "live",
        "ignore_synonyms": False,
        "include_clickstream_data": False,
        "load_rank_absolute": False,
        "limit": limit,
        "filters": [
            "ranked_serp_element.serp_item.rank_absolute", "<=", 20
        ],
        "order_by": ["keyword_data.keyword_info.search_volume,desc"],
    }]

    req = Request(url, method="POST")
    req.add_header("Authorization", f"Basic {auth}")
    req.add_header("Content-Type", "application/json")
    req.data = json.dumps(payload).encode()

    try:
        with urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode())
    except HTTPError as e:
        body = e.read().decode() if e.fp else str(e)
        raise RuntimeError(f"API error {e.code}: {body}")
    except URLError as e:
        raise RuntimeError(f"Connection error: {e.reason}")

    # Validate response
    if data.get("status_code") != 20000:
        raise RuntimeError(
            f"API returned status {data.get('status_code')}: "
            f"{data.get('status_message', 'Unknown error')}"
        )

    # Parse tasks → results → items
    tasks = data.get("tasks", [])
    if not tasks:
        print("No tasks in response", file=sys.stderr)
        return []

    task = tasks[0]
    if task.get("status_code") != 20000:
        raise RuntimeError(
            f"Task error {task.get('status_code')}: {task.get('status_message')}"
        )

    results = task.get("result", [])
    if not results:
        print("No results in task", file=sys.stderr)
        return []

    result = results[0]
    items = result.get("items", [])
    if not items:
        print("No items in result", file=sys.stderr)
        return []

    # Print summary metrics
    metrics = result.get("metrics", {})
    total_count = result.get("total_count", 0)
    print(f"Domain: {result.get('target', domain)}")
    print(f"Total ranked keywords: {total_count}")
    print(f"Fetched items (top 20): {len(items)}")
    if metrics:
        organic = metrics.get("organic", {})
        if organic:
            print(f"  Organic — pos 1: {organic.get('pos_1', 0)}, "
                  f"pos 2-3: {organic.get('pos_2_3', 0)}, "
                  f"pos 4-10: {organic.get('pos_4_10', 0)}, "
                  f"ETV: {organic.get('etv', 0):.1f}")

    # Parse each item
    parsed = []
    for item in items:
        try:
            parsed.append(_parse_item(item, domain))
        except Exception as e:
            print(f"Warning: skipping item due to error: {e}", file=sys.stderr)

    print(f"Successfully parsed: {len(parsed)} keywords")
    return parsed


def _parse_item(item: dict, domain: str) -> dict:
    """Parse a single ranked keyword item from the API response."""
    kw_data = item.get("keyword_data", {})
    kw_info = kw_data.get("keyword_info", {})
    intent_info = kw_data.get("search_intent_info", {})

    serp_elem = item.get("ranked_serp_element", {})
    serp_item = serp_elem.get("serp_item", {})

    # Monthly searches → JSON string
    monthly = kw_info.get("monthly_searches")
    monthly_json = json.dumps(monthly) if monthly else None

    return {
        "competitor_domain": domain,
        "keyword": kw_data.get("keyword"),
        "search_volume": kw_info.get("search_volume"),
        "competition": kw_info.get("competition"),
        "cpc": kw_info.get("cpc"),
        "search_intent": intent_info.get("main_intent"),
        "rank_absolute": serp_item.get("rank_absolute"),
        "serp_type": serp_item.get("type"),
        "url": serp_item.get("url"),
        "title": serp_item.get("title"),
        "description": serp_item.get("description"),
        "etv": serp_item.get("etv"),
        "is_paid": serp_item.get("is_paid"),
        "monthly_searches_json": monthly_json,
    }


# ── Freshness check ────────────────────────────────────────────────────────

DB_BASE = Path.home() / "kw_projects"


def check_freshness(project: str, domain: str, max_age_days: int = 30) -> dict | None:
    """
    Check if fresh data already exists for this domain in DuckDB.

    Returns a summary dict if fresh data found, None otherwise.
    """
    db_path = DB_BASE / f"{project}.duckdb"
    if not db_path.exists():
        return None

    try:
        import duckdb
        con = duckdb.connect(str(db_path))
        result = con.sql(f"""
            SELECT
                COUNT(*) AS total_rows,
                MAX(downloaded_at) AS last_download,
                MAX(imported_at) AS last_import,
                SUM(search_volume) AS total_volume
            FROM competitor_keywords
            WHERE competitor_domain = '{domain}'
              AND downloaded_at >= CURRENT_DATE - INTERVAL '{max_age_days}' DAY
        """).fetchone()
        con.close()

        if result and result[0] > 0:
            return {
                'rows': result[0],
                'last_download': str(result[1]),
                'last_import': str(result[2]),
                'total_volume': result[3],
            }
    except Exception:
        pass

    return None


# ── DuckDB storage ─────────────────────────────────────────────────────────

COMPETITOR_KEYWORDS_SCHEMA = """
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
    imported_at TIMESTAMP DEFAULT current_timestamp,
    downloaded_at DATE
)
"""


def store_to_duckdb(
    project: str,
    items: list[dict],
    downloaded_at: str | None = None,
    remote: bool = False,
) -> str:
    """Store parsed competitor keyword items into DuckDB."""
    if not items:
        return "No items to store"

    try:
        import duckdb
    except ImportError:
        print("Installing duckdb...", file=sys.stderr)
        os.system(f"{sys.executable} -m pip install duckdb --break-system-packages -q")
        import duckdb

    db_path = str(DB_BASE / f"{project}.duckdb")
    if not os.path.exists(db_path):
        raise FileNotFoundError(
            f"Project '{project}' not found at {db_path}. "
            f"Create it first: python3 kw_db.py create {project}"
        )

    dl_date = downloaded_at or datetime.now().strftime("%Y-%m-%d")

    con = duckdb.connect(db_path)
    try:
        # Ensure table exists
        con.sql(COMPETITOR_KEYWORDS_SCHEMA)

        # Insert rows
        cols = [
            "competitor_domain", "keyword", "search_volume", "competition",
            "cpc", "search_intent", "rank_absolute", "serp_type", "url",
            "title", "description", "etv", "is_paid", "monthly_searches_json",
            "downloaded_at",
        ]
        placeholders = ", ".join(["?"] * len(cols))
        insert_sql = f"INSERT INTO competitor_keywords ({', '.join(cols)}) VALUES ({placeholders})"

        inserted = 0
        for item in items:
            values = [
                item.get("competitor_domain"),
                item.get("keyword"),
                item.get("search_volume"),
                item.get("competition"),
                item.get("cpc"),
                item.get("search_intent"),
                item.get("rank_absolute"),
                item.get("serp_type"),
                item.get("url"),
                item.get("title"),
                item.get("description"),
                item.get("etv"),
                item.get("is_paid"),
                item.get("monthly_searches_json"),
                dl_date,
            ]
            con.execute(insert_sql, values)
            inserted += 1

        # Get total count
        total = con.sql(
            "SELECT COUNT(*) FROM competitor_keywords "
            f"WHERE competitor_domain = '{item.get('competitor_domain')}'"
        ).fetchone()[0]

    finally:
        con.close()

    return (
        f"Stored {inserted} keywords for '{items[0]['competitor_domain']}'\n"
        f"  Project: {project} ({db_path})\n"
        f"  Downloaded: {dl_date}\n"
        f"  Total rows for this domain: {total}"
    )


# ── CSV export ──────────────────────────────────────────────────────────────

def export_csv(items: list[dict], csv_path: str) -> str:
    """Export parsed items to CSV."""
    if not items:
        return "No items to export"

    csv_path = os.path.expanduser(csv_path)
    Path(csv_path).parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "competitor_domain", "keyword", "search_volume", "competition",
        "cpc", "search_intent", "rank_absolute", "serp_type", "url",
        "title", "description", "etv", "is_paid", "monthly_searches_json",
    ]

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(items)

    return f"Exported {len(items)} rows to {csv_path}"


# ── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Fetch competitor ranked keywords (top 20) and store in DuckDB"
    )
    parser.add_argument("project", help="DuckDB project name")
    parser.add_argument("domain", help="Competitor domain (e.g. pronatal.cz)")
    parser.add_argument("--location", type=int, default=2203,
                        help="Location code (default: 2203 = Czech Republic)")
    parser.add_argument("--language", default="cs",
                        help="Language code (default: cs)")
    parser.add_argument("--limit", type=int, default=500,
                        help="Max keywords to fetch (default: 500)")
    parser.add_argument("--csv", default=None,
                        help="Also export to CSV at this path")
    parser.add_argument("--date", default=None,
                        help="Download date for DuckDB (YYYY-MM-DD, default: today)")

    parser.add_argument("--force", action="store_true",
                        help="Skip freshness check and fetch anyway")

    args = parser.parse_args()

    # Freshness check — skip if data < 30 days old
    if not args.force:
        existing = check_freshness(args.project, args.domain)
        if existing:
            print(f"⏭  Fresh data already exists for '{args.domain}':")
            print(f"   Rows: {existing['rows']:,}")
            print(f"   Last download: {existing['last_download']}")
            print(f"   Total volume: {existing['total_volume']:,}")
            print(f"   Use --force to re-download anyway.")
            sys.exit(0)

    print(f"Fetching top-20 keywords for: {args.domain}")
    print(f"Location: {args.location}, Language: {args.language}, Limit: {args.limit}")
    print("─" * 60)

    # Fetch from API
    items = fetch_competitor_keywords(
        domain=args.domain,
        location_code=args.location,
        language_code=args.language,
        limit=args.limit,
    )

    if not items:
        print("No keywords found.")
        sys.exit(0)

    print("─" * 60)

    # Store to DuckDB
    result = store_to_duckdb(args.project, items, downloaded_at=args.date)
    print(result)

    # Optional CSV export
    if args.csv:
        csv_result = export_csv(items, args.csv)
        print(csv_result)

    print("─" * 60)
    print("Done!")


if __name__ == "__main__":
    main()
