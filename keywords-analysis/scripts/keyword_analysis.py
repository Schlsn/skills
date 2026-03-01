#!/usr/bin/env python3
"""
Keywords Analysis — Full pipeline orchestrator.

Chains 6 skills into an automated keyword research flow:
  1. GSC data (pos ≤ 20) via BigQuery or API
  2. DataForSEO competitor keywords
  3. KW Planner keyword ideas
  4. Google Autocomplete expansion
  5. Volume lookup for new keywords
  6. SERP scrape top N
  7. Volume for related queries + PAA
  8. Semantic categorization

Usage:
  python3 keyword_analysis.py config.json
  python3 keyword_analysis.py config.json --dry-run
"""

import argparse
import json
import os
import sys
import time
import random
from datetime import datetime
from pathlib import Path

# ── Resolve sibling skill paths ─────────────────────────────────────────────

SKILLS_DIR = Path(__file__).resolve().parent.parent.parent
SKILL_PATHS = {
    'google_serp': SKILLS_DIR / 'google-serp' / 'scripts',
    'dataforseo': SKILLS_DIR / 'dataforseo-competitors' / 'scripts',
    'duckdb_kw': SKILLS_DIR / 'duckdb-keywords' / 'scripts',
    'categorization': SKILLS_DIR / 'keyword-categorization' / 'scripts',
}

for name, path in SKILL_PATHS.items():
    if path.exists():
        sys.path.insert(0, str(path))


# ── Config ──────────────────────────────────────────────────────────────────

REQUIRED_FIELDS = [
    'project', 'seed_keywords', 'language', 'country',
    'gsc_property', 'gsc_source',
]

DEFAULTS = {
    'competitors': [],
    'location_code': 2203,
    'autocomplete_top_n': 30,
    'serp_top_n': 100,
    'google_ads_yaml': '/Users/adam/Documents/credentials/google-ads.yaml',
    'google_ads_customer_id': None,  # read from yaml if not set
    'bq_dataset': None,
    'bq_table': 'searchdata_site_impression',
    'openrouter_api_key': None,  # env OPENROUTER_API_KEY fallback
    'date': None,  # defaults to today
}


def load_config(path: str) -> dict:
    """Load and validate config JSON."""
    with open(path) as f:
        cfg = json.load(f)

    # Apply defaults
    for k, v in DEFAULTS.items():
        cfg.setdefault(k, v)

    # Validate
    missing = [f for f in REQUIRED_FIELDS if not cfg.get(f)]
    if missing:
        raise ValueError(f"Missing required config fields: {missing}")

    if cfg['gsc_source'] == 'bigquery' and not cfg.get('bq_dataset'):
        raise ValueError("gsc_source='bigquery' requires 'bq_dataset' field")

    cfg['date'] = cfg['date'] or datetime.now().strftime('%Y-%m-%d')
    return cfg


# ── Progress printing ───────────────────────────────────────────────────────

def _banner(msg: str):
    print(f"\n{'═' * 60}", file=sys.stderr)
    print(f"  {msg}", file=sys.stderr)
    print(f"{'═' * 60}", file=sys.stderr)


def _step(n: int, total: int, msg: str):
    print(f"\nStep {n}/{total}: {msg}", file=sys.stderr)


def _info(msg: str):
    print(f"  → {msg}", file=sys.stderr)


def _warn(msg: str):
    print(f"  ⚠ {msg}", file=sys.stderr)


# ── Dedup helpers ───────────────────────────────────────────────────────────

class KeywordPool:
    """Central dedup tracker across all pipeline steps."""

    def __init__(self):
        self._seen: set[str] = set()
        self._all: list[dict] = []  # {'keyword': str, 'search_volume': int, 'source': str}

    def add(self, keyword: str, search_volume: int = 0, source: str = '') -> bool:
        """Add keyword if new. Returns True if added, False if duplicate."""
        key = keyword.lower().strip()
        if not key or key in self._seen:
            return False
        self._seen.add(key)
        self._all.append({
            'keyword': keyword.strip(),
            'search_volume': search_volume,
            'source': source,
        })
        return True

    def add_many(self, keywords: list[dict], source: str = '') -> int:
        """Add multiple {'keyword': str, 'search_volume': int} dicts. Returns count of new."""
        new = 0
        for kw in keywords:
            word = kw.get('keyword') or kw.get('query') or ''
            vol = kw.get('search_volume') or kw.get('avg_monthly_searches') or kw.get('searches') or 0
            if self.add(word, int(vol), source):
                new += 1
        return new

    def contains(self, keyword: str) -> bool:
        return keyword.lower().strip() in self._seen

    @property
    def count(self) -> int:
        return len(self._seen)

    def top_by_volume(self, n: int) -> list[dict]:
        """Return top N keywords by search volume."""
        return sorted(self._all, key=lambda x: x['search_volume'], reverse=True)[:n]

    def without_volume(self) -> list[str]:
        """Return keywords with zero search volume."""
        return [kw['keyword'] for kw in self._all if kw['search_volume'] == 0]

    def all_keywords(self) -> list[str]:
        return [kw['keyword'] for kw in self._all]


# ── Step 1: GSC data ───────────────────────────────────────────────────────

def step_gsc(cfg: dict, pool: KeywordPool, dry_run: bool = False):
    """Fetch GSC data (position ≤ 20) via BigQuery or API."""
    _step(1, 10, f"GSC data (pos ≤ 20) via {cfg['gsc_source']}")

    if dry_run:
        _info("DRY RUN — skipping GSC fetch")
        return

    if cfg['gsc_source'] == 'bigquery':
        _gsc_bigquery(cfg, pool)
    else:
        _gsc_api(cfg, pool)


def _gsc_bigquery(cfg: dict, pool: KeywordPool):
    """Query GSC data from BigQuery export."""
    try:
        from google.cloud import bigquery
    except ImportError:
        os.system(f"{sys.executable} -m pip install google-cloud-bigquery --break-system-packages -q")
        from google.cloud import bigquery

    client = bigquery.Client()
    table = f"{cfg['bq_dataset']}.{cfg['bq_table']}"

    query = f"""
        SELECT query, page,
               SUM(clicks) AS clicks,
               SUM(impressions) AS impressions,
               AVG(average_ctr) AS ctr,
               AVG(average_position) AS position
        FROM `{table}`
        WHERE search_type = 'WEB'
          AND average_position <= 20
        GROUP BY query, page
        HAVING SUM(impressions) > 0
        ORDER BY impressions DESC
    """

    _info(f"Querying BigQuery: {table}")
    rows = list(client.query(query).result())
    _info(f"Got {len(rows)} query-page pairs")

    # Store to DuckDB
    _store_gsc_rows(cfg, rows)

    # Add to pool
    new = 0
    for row in rows:
        if pool.add(row.query, 0, 'gsc'):
            new += 1

    _info(f"{new} new keywords from GSC ({pool.count} total)")


def _gsc_api(cfg: dict, pool: KeywordPool):
    """Query GSC data via Search Analytics API."""
    try:
        from googleapiclient.discovery import build
        from google.oauth2 import service_account
    except ImportError:
        os.system(f"{sys.executable} -m pip install google-api-python-client google-auth --break-system-packages -q")
        from googleapiclient.discovery import build
        from google.oauth2 import service_account

    # Use ADC
    service = build('searchconsole', 'v1')

    request_body = {
        'startDate': '2025-09-01',
        'endDate': cfg['date'],
        'dimensions': ['query', 'page'],
        'rowLimit': 25000,
        'dimensionFilterGroups': [{
            'filters': [{
                'dimension': 'query',
                'operator': 'notContains',
                'expression': '',
            }]
        }],
    }

    _info(f"Querying GSC API: {cfg['gsc_property']}")
    response = service.searchanalytics().query(
        siteUrl=cfg['gsc_property'], body=request_body
    ).execute()

    rows = response.get('rows', [])
    # Filter pos ≤ 20
    filtered = [r for r in rows if r.get('position', 100) <= 20]
    _info(f"Got {len(filtered)} query-page pairs (pos ≤ 20)")

    # Store to DuckDB
    _store_gsc_api_rows(cfg, filtered)

    new = 0
    for row in filtered:
        query = row['keys'][0]
        if pool.add(query, 0, 'gsc'):
            new += 1

    _info(f"{new} new keywords from GSC ({pool.count} total)")


def _store_gsc_rows(cfg: dict, rows):
    """Store BigQuery GSC rows to DuckDB."""
    import duckdb
    db_path = str(Path.home() / 'kw_projects' / f"{cfg['project']}.duckdb")
    con = duckdb.connect(db_path)
    for row in rows:
        con.execute(
            "INSERT INTO search_console (query, page, clicks, impressions, ctr, position, downloaded_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [row.query, row.page, int(row.clicks), int(row.impressions),
             float(row.ctr), float(row.position), cfg['date']]
        )
    con.close()
    _info(f"Stored {len(rows)} rows to search_console table")


def _store_gsc_api_rows(cfg: dict, rows):
    """Store API GSC rows to DuckDB."""
    import duckdb
    db_path = str(Path.home() / 'kw_projects' / f"{cfg['project']}.duckdb")
    con = duckdb.connect(db_path)
    for row in rows:
        con.execute(
            "INSERT INTO search_console (query, page, clicks, impressions, ctr, position, downloaded_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [row['keys'][0], row['keys'][1], int(row.get('clicks', 0)),
             int(row.get('impressions', 0)), float(row.get('ctr', 0)),
             float(row.get('position', 0)), cfg['date']]
        )
    con.close()
    _info(f"Stored {len(rows)} rows to search_console table")


# ── Step 2: DataForSEO competitors ──────────────────────────────────────────

def step_competitors(cfg: dict, pool: KeywordPool, dry_run: bool = False):
    """Fetch competitor ranked keywords via DataForSEO."""
    _step(2, 10, "Competitor analysis (DataForSEO)")

    if not cfg['competitors']:
        _info("No competitors configured — skipping")
        return

    if dry_run:
        _info(f"DRY RUN — would fetch {len(cfg['competitors'])} competitors")
        return

    from competitor_keywords import fetch_competitor_keywords, store_to_duckdb

    for domain in cfg['competitors']:
        _info(f"Fetching: {domain}")
        items = fetch_competitor_keywords(
            domain=domain,
            location_code=cfg['location_code'],
            language_code=cfg['language'],
            limit=1000,
        )
        if items:
            store_to_duckdb(cfg['project'], items, downloaded_at=cfg['date'])
            new = pool.add_many(
                [{'keyword': i['keyword'], 'search_volume': i.get('search_volume', 0)}
                 for i in items],
                source=f'competitor:{domain}'
            )
            _info(f"  {domain}: {len(items)} keywords ({new} new)")
        else:
            _warn(f"  {domain}: no keywords returned")

    _info(f"{pool.count} total unique keywords")


# ── Step 3-4: KW Planner ideas ──────────────────────────────────────────────

def _get_kw_planner_client(cfg: dict):
    """Initialize Google Ads client."""
    try:
        from google.ads.googleads.client import GoogleAdsClient
    except ImportError:
        os.system(f"{sys.executable} -m pip install google-ads --break-system-packages -q")
        from google.ads.googleads.client import GoogleAdsClient

    return GoogleAdsClient.load_from_storage(cfg['google_ads_yaml'])


def _kw_planner_ideas(client, customer_id: str, language_id: str,
                       geo_ids: list, seeds: list[str]) -> list[dict]:
    """Get keyword ideas from Google Ads Keyword Planner."""
    kp_service = client.get_service("KeywordPlanIdeaService")
    ga_service = client.get_service("GoogleAdsService")

    request = client.get_type("GenerateKeywordIdeasRequest")
    request.customer_id = customer_id
    request.language = ga_service.language_constant_path(language_id)
    for geo_id in geo_ids:
        request.geo_target_constants.append(
            ga_service.geo_target_constant_path(geo_id)
        )
    request.include_adult_keywords = False
    request.keyword_plan_network = client.enums.KeywordPlanNetworkEnum.GOOGLE_SEARCH
    request.keyword_seed.keywords.extend(seeds[:20])

    results = []
    for idea in kp_service.generate_keyword_ideas(request=request):
        m = idea.keyword_idea_metrics
        results.append({
            'keyword': idea.text,
            'search_volume': m.avg_monthly_searches or 0,
            'competition': m.competition_index or 0,
            'cpc': (m.high_top_of_page_bid_micros or 0) / 1_000_000,
        })
    return results


# Language code → Google Ads language resource ID
LANG_IDS = {
    'cs': '1021', 'en': '1000', 'de': '1001', 'fr': '1002',
    'it': '1004', 'pl': '1020', 'sk': '1033', 'hr': '1022',
    'sr': '1034', 'nl': '1010', 'sv': '1015', 'uk': '1036',
}

# Country code → Google Ads geo target ID
GEO_IDS = {
    'cz': '2203', 'us': '2840', 'de': '2276', 'at': '2040',
    'gb': '2826', 'ie': '2372', 'fr': '2250', 'it': '2380',
    'pl': '2616', 'sk': '2703', 'hr': '2191', 'rs': '2688',
    'nl': '2528', 'be': '2056', 'se': '2752', 'ch': '2756',
}


def step_kw_planner_ideas(cfg: dict, pool: KeywordPool, dry_run: bool = False):
    """Get keyword ideas from KW Planner for seed keywords."""
    _step(3, 10, "KW Planner ideas from seeds")

    seeds = cfg['seed_keywords']
    if dry_run:
        _info(f"DRY RUN — would query KW Planner with {len(seeds)} seeds")
        return

    client = _get_kw_planner_client(cfg)
    customer_id = cfg.get('google_ads_customer_id')
    if not customer_id:
        # Read from yaml
        import yaml
        with open(cfg['google_ads_yaml']) as f:
            ads_cfg = yaml.safe_load(f)
        customer_id = str(ads_cfg.get('login_customer_id', '')).replace('-', '')

    lang_id = LANG_IDS.get(cfg['language'], '1000')
    geo_id = [GEO_IDS.get(cfg['country'], '2203')]

    # Batch seeds in groups of 20
    all_ideas = []
    for i in range(0, len(seeds), 20):
        batch = seeds[i:i + 20]
        _info(f"KW Planner batch {i // 20 + 1}: {batch}")
        ideas = _kw_planner_ideas(client, customer_id, lang_id, geo_id, batch)
        all_ideas.extend(ideas)
        if i + 20 < len(seeds):
            time.sleep(2)  # small pause between batches

    # Store to DuckDB
    _store_kw_planner(cfg, all_ideas)

    new = pool.add_many(
        [{'keyword': i['keyword'], 'search_volume': i['search_volume']} for i in all_ideas],
        source='kw_planner'
    )
    _info(f"{len(all_ideas)} ideas, {new} new keywords ({pool.count} total)")


def _store_kw_planner(cfg: dict, ideas: list[dict]):
    """Store KW Planner results to DuckDB."""
    import duckdb
    db_path = str(Path.home() / 'kw_projects' / f"{cfg['project']}.duckdb")
    con = duckdb.connect(db_path)
    for idea in ideas:
        con.execute(
            "INSERT INTO keyword_planner (keyword, avg_monthly_searches, competition_index, "
            "top_bid_high, downloaded_at) VALUES (?, ?, ?, ?, ?)",
            [idea['keyword'], idea['search_volume'], idea.get('competition', 0),
             idea.get('cpc', 0), cfg['date']]
        )
    con.close()


# ── Step 5: Autocomplete ────────────────────────────────────────────────────

def _fetch_suggestions(query: str, hl: str, gl: str, session) -> list[str]:
    """Fetch Google Autocomplete suggestions for a query."""
    import requests

    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0',
    ]

    headers = {
        'User-Agent': random.choice(user_agents),
        'Accept': 'application/json',
        'Referer': 'https://www.google.com/',
    }
    url = 'https://suggestqueries.google.com/complete/search'
    params = {'client': 'chrome', 'q': query, 'hl': hl, 'gl': gl.upper()}

    try:
        r = session.get(url, params=params, headers=headers, timeout=10)
        if r.status_code == 200:
            data = json.loads(r.text)
            return data[1] if len(data) > 1 else []
        elif r.status_code == 429:
            _warn("Rate limited, backing off 30s...")
            time.sleep(30)
    except Exception as e:
        _warn(f"Autocomplete error: {e}")
    return []


def _autocomplete_expand(keyword: str, hl: str, gl: str) -> list[str]:
    """Full autocomplete expansion for a keyword: base + alphabet + question prefixes."""
    import requests
    import string

    session = requests.Session()
    all_suggestions: set[str] = set()

    question_prefixes = {
        'cs': ['jak', 'proč', 'kdy', 'co je', 'kde', 'cena', 'zkušenosti'],
        'en': ['how', 'why', 'when', 'what is', 'where', 'best', 'review'],
        'de': ['wie', 'warum', 'wann', 'was ist', 'wo', 'preis'],
    }

    queries = [keyword]
    for letter in string.ascii_lowercase:
        queries.append(f"{keyword} {letter}")
    for prefix in question_prefixes.get(hl, question_prefixes['en']):
        queries.append(f"{prefix} {keyword}")

    for query in queries:
        suggestions = _fetch_suggestions(query, hl, gl, session)
        for s in suggestions:
            all_suggestions.add(s.strip())
        time.sleep(random.uniform(1.5, 3.0))

    return list(all_suggestions)


def step_autocomplete(cfg: dict, pool: KeywordPool, dry_run: bool = False):
    """Expand top N keywords via Google Autocomplete."""
    top_n = cfg['autocomplete_top_n']
    _step(4, 10, f"Autocomplete expansion (top {top_n} by volume)")

    top_kws = pool.top_by_volume(top_n)
    keywords_to_expand = [kw['keyword'] for kw in top_kws if kw['search_volume'] > 0]

    if not keywords_to_expand:
        _info("No keywords with volume for autocomplete expansion")
        return

    _info(f"Expanding {len(keywords_to_expand)} keywords (~{len(keywords_to_expand) * 2}min)")

    if dry_run:
        _info("DRY RUN — skipping autocomplete")
        return

    import duckdb
    db_path = str(Path.home() / 'kw_projects' / f"{cfg['project']}.duckdb")

    total_new = 0
    for i, kw in enumerate(keywords_to_expand, 1):
        _info(f"[{i}/{len(keywords_to_expand)}] Autocomplete: \"{kw}\"")
        suggestions = _autocomplete_expand(kw, cfg['language'], cfg['country'])

        # Store suggestions to DuckDB
        con = duckdb.connect(db_path)
        stored = 0
        for j, s in enumerate(suggestions):
            con.execute(
                "INSERT INTO suggestions (seed_keyword, suggestion, position, downloaded_at) "
                "VALUES (?, ?, ?, ?)",
                [kw, s, j + 1, cfg['date']]
            )
            stored += 1
        con.close()

        # Add to pool
        new = 0
        for s in suggestions:
            if pool.add(s, 0, 'autocomplete'):
                new += 1
        total_new += new
        _info(f"  {len(suggestions)} suggestions, {new} new")

    _info(f"{total_new} new keywords from autocomplete ({pool.count} total)")


# ── Step 6: Volume lookup ───────────────────────────────────────────────────

def step_volume_lookup(cfg: dict, pool: KeywordPool, dry_run: bool = False):
    """Get search volumes for keywords without volume data."""
    _step(5, 10, "Volume lookup for new keywords")

    no_volume = pool.without_volume()
    if not no_volume:
        _info("All keywords already have volume data")
        return

    _info(f"{len(no_volume)} keywords need volume lookup")

    if dry_run:
        _info("DRY RUN — skipping volume lookup")
        return

    client = _get_kw_planner_client(cfg)
    customer_id = cfg.get('google_ads_customer_id')
    if not customer_id:
        import yaml
        with open(cfg['google_ads_yaml']) as f:
            ads_cfg = yaml.safe_load(f)
        customer_id = str(ads_cfg.get('login_customer_id', '')).replace('-', '')

    lang_id = LANG_IDS.get(cfg['language'], '1000')
    geo_id = [GEO_IDS.get(cfg['country'], '2203')]

    # Batch in groups of 20
    all_results = []
    for i in range(0, len(no_volume), 20):
        batch = no_volume[i:i + 20]
        _info(f"Volume batch {i // 20 + 1}/{(len(no_volume) - 1) // 20 + 1} ({len(batch)} kws)")
        ideas = _kw_planner_ideas(client, customer_id, lang_id, geo_id, batch)
        all_results.extend(ideas)
        if i + 20 < len(no_volume):
            time.sleep(2)

    # Store and update pool volumes
    _store_kw_planner(cfg, all_results)

    # Update volumes in pool
    volume_map = {i['keyword'].lower(): i['search_volume'] for i in all_results}
    updated = 0
    for kw in pool._all:
        key = kw['keyword'].lower()
        if kw['search_volume'] == 0 and key in volume_map:
            kw['search_volume'] = volume_map[key]
            updated += 1

    _info(f"Updated volumes for {updated} keywords")


# ── Step 7: SERP scrape ─────────────────────────────────────────────────────

def step_serp(cfg: dict, pool: KeywordPool, dry_run: bool = False):
    """Scrape SERP for top N keywords by volume."""
    top_n = cfg['serp_top_n']
    _step(6, 10, f"SERP scrape (top {top_n} by volume)")

    top_kws = pool.top_by_volume(top_n)
    kws_with_volume = [kw for kw in top_kws if kw['search_volume'] > 0]

    _info(f"{len(kws_with_volume)} keywords to scrape (~{len(kws_with_volume) * 12}s)")

    if dry_run:
        _info("DRY RUN — skipping SERP scrape")
        return

    from google_serp import scrape_with_pause

    import duckdb
    db_path = str(Path.home() / 'kw_projects' / f"{cfg['project']}.duckdb")

    for i, kw_data in enumerate(kws_with_volume, 1):
        kw = kw_data['keyword']
        _info(f"[{i}/{len(kws_with_volume)}] SERP: \"{kw}\" (vol: {kw_data['search_volume']})")

        try:
            data = scrape_with_pause(
                kw, lang=cfg['language'], country=cfg['country'], num=10
            )
        except Exception as e:
            _warn(f"SERP failed for \"{kw}\": {e}")
            continue

        # Store organic results
        con = duckdb.connect(db_path)
        for r in data.get('organic', []):
            con.execute(
                "INSERT INTO serp (keyword, position, title, url, description, downloaded_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [kw, r.get('position'), r.get('title'), r.get('url'),
                 r.get('description'), cfg['date']]
            )

        # Store related queries
        for r in data.get('related', []):
            query_text = r.get('query', '')
            con.execute(
                "INSERT INTO related_queries (seed_keyword, related_query, position, downloaded_at) "
                "VALUES (?, ?, ?, ?)",
                [kw, query_text, r.get('position'), cfg['date']]
            )
            pool.add(query_text, 0, 'related')

        # Store PAA
        for r in data.get('paa', []):
            question = r.get('question', '')
            con.execute(
                "INSERT INTO people_also_ask (seed_keyword, question, position, downloaded_at) "
                "VALUES (?, ?, ?, ?)",
                [kw, question, r.get('position'), cfg['date']]
            )
            pool.add(question, 0, 'paa')

        con.close()

    organic_count = sum(len(d) for d in [data.get('organic', [])])
    _info(f"SERP scraping complete ({pool.count} total keywords)")


# ── Step 8: Volume for related + PAA ─────────────────────────────────────────

def step_volume_related_paa(cfg: dict, pool: KeywordPool, dry_run: bool = False):
    """Get volumes for related queries and PAA questions."""
    _step(7, 10, "Volume lookup for related queries + PAA")

    # Collect keywords from related + PAA that have no volume
    no_volume = [kw['keyword'] for kw in pool._all
                 if kw['search_volume'] == 0
                 and kw['source'] in ('related', 'paa')]

    if not no_volume:
        _info("No related/PAA keywords need volume")
        return

    _info(f"{len(no_volume)} related/PAA keywords need volume")

    if dry_run:
        _info("DRY RUN — skipping")
        return

    client = _get_kw_planner_client(cfg)
    customer_id = cfg.get('google_ads_customer_id')
    if not customer_id:
        import yaml
        with open(cfg['google_ads_yaml']) as f:
            ads_cfg = yaml.safe_load(f)
        customer_id = str(ads_cfg.get('login_customer_id', '')).replace('-', '')

    lang_id = LANG_IDS.get(cfg['language'], '1000')
    geo_id = [GEO_IDS.get(cfg['country'], '2203')]

    all_results = []
    for i in range(0, len(no_volume), 20):
        batch = no_volume[i:i + 20]
        _info(f"Volume batch {i // 20 + 1}/{(len(no_volume) - 1) // 20 + 1}")
        ideas = _kw_planner_ideas(client, customer_id, lang_id, geo_id, batch)
        all_results.extend(ideas)
        if i + 20 < len(no_volume):
            time.sleep(2)

    _store_kw_planner(cfg, all_results)

    volume_map = {i['keyword'].lower(): i['search_volume'] for i in all_results}
    updated = 0
    for kw in pool._all:
        key = kw['keyword'].lower()
        if kw['search_volume'] == 0 and key in volume_map:
            kw['search_volume'] = volume_map[key]
            updated += 1

    _info(f"Updated volumes for {updated} keywords")


# ── Step 9: Categorization ──────────────────────────────────────────────────

def step_categorize(cfg: dict, pool: KeywordPool, dry_run: bool = False):
    """Run semantic categorization on all keywords with volume."""
    _step(8, 10, "Semantic categorization (clustering)")

    kws_with_vol = [kw for kw in pool._all if kw['search_volume'] > 0]
    _info(f"{len(kws_with_vol)} keywords with volume to categorize")

    if dry_run:
        _info("DRY RUN — skipping categorization")
        return

    if len(kws_with_vol) < 5:
        _warn("Too few keywords for meaningful clustering, skipping")
        return

    # Export to temp CSV for clustering
    import csv
    import tempfile

    tmp_csv = Path(tempfile.gettempdir()) / f"kw_cluster_{cfg['project']}.csv"
    with open(tmp_csv, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['Keyword', 'Search_Volume'])
        w.writeheader()
        for kw in kws_with_vol:
            w.writerow({'Keyword': kw['keyword'], 'Search_Volume': kw['search_volume']})

    _info(f"Exported {len(kws_with_vol)} keywords to temp CSV for clustering")

    api_key = cfg.get('openrouter_api_key') or os.environ.get('OPENROUTER_API_KEY')
    if not api_key:
        _warn("No OPENROUTER_API_KEY — skipping categorization")
        return

    from cluster_keywords import process_csv

    output_csv = Path(tempfile.gettempdir()) / f"kw_clustered_{cfg['project']}.csv"
    results = process_csv(
        str(tmp_csv),
        output_path=str(output_csv),
        api_key=api_key,
    )

    # Import results back to DuckDB as a summary view
    main_cats = set(r['Main_Category'] for r in results if r['Main_Category'] != 'Nezařazeno')
    sub_cats = set(r['Subcategory'] for r in results if r['Subcategory'] != 'Nezařazeno')
    _info(f"{len(main_cats)} main categories, {len(sub_cats)} subcategories")
    _info(f"Clustered output: {output_csv}")


# ── Step 10: Final summary ──────────────────────────────────────────────────

def step_summary(cfg: dict, pool: KeywordPool):
    """Print final summary of the analysis."""
    _step(9, 10, "Dedup check")

    import duckdb
    db_path = str(Path.home() / 'kw_projects' / f"{cfg['project']}.duckdb")
    con = duckdb.connect(db_path)

    tables = ['search_console', 'competitor_keywords', 'keyword_planner',
              'suggestions', 'serp', 'related_queries', 'people_also_ask']

    _step(10, 10, "Final summary")
    print(f"\n{'═' * 60}", file=sys.stderr)
    print(f"  Project: {cfg['project']}", file=sys.stderr)
    print(f"  Database: {db_path}", file=sys.stderr)
    print(f"  Total unique keywords: {pool.count}", file=sys.stderr)
    print(f"  With volume: {len([k for k in pool._all if k['search_volume'] > 0])}", file=sys.stderr)
    print(f"{'─' * 60}", file=sys.stderr)

    for table in tables:
        try:
            count = con.sql(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"  {table:25s} {count:>8,} rows", file=sys.stderr)
        except Exception:
            print(f"  {table:25s}        0 rows", file=sys.stderr)

    print(f"{'═' * 60}", file=sys.stderr)

    # Source breakdown
    sources = {}
    for kw in pool._all:
        src = kw['source'] or 'unknown'
        src = src.split(':')[0]
        sources[src] = sources.get(src, 0) + 1

    print("  Keyword sources:", file=sys.stderr)
    for src, cnt in sorted(sources.items(), key=lambda x: -x[1]):
        print(f"    {src:20s} {cnt:>6,}", file=sys.stderr)
    print(f"{'═' * 60}\n", file=sys.stderr)

    con.close()


# ── Main pipeline ───────────────────────────────────────────────────────────

def run_pipeline(config_path: str, dry_run: bool = False):
    """Execute the full keyword analysis pipeline."""
    cfg = load_config(config_path)
    pool = KeywordPool()

    _banner(f"Keywords Analysis: {cfg['project']}")
    print(f"  Market: {cfg['language']}/{cfg['country']} | "
          f"Seeds: {len(cfg['seed_keywords'])} | "
          f"Competitors: {len(cfg['competitors'])}", file=sys.stderr)

    # Ensure DuckDB project exists
    from kw_db import create_project
    create_project(cfg['project'])

    # Add seeds to pool
    for seed in cfg['seed_keywords']:
        pool.add(seed, 0, 'seed')

    # Execute pipeline
    step_gsc(cfg, pool, dry_run)
    step_competitors(cfg, pool, dry_run)
    step_kw_planner_ideas(cfg, pool, dry_run)
    step_autocomplete(cfg, pool, dry_run)
    step_volume_lookup(cfg, pool, dry_run)
    step_serp(cfg, pool, dry_run)
    step_volume_related_paa(cfg, pool, dry_run)
    step_categorize(cfg, pool, dry_run)
    step_summary(cfg, pool)


# ── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Keywords Analysis — Full pipeline orchestrator'
    )
    parser.add_argument('config', help='Path to config JSON file')
    parser.add_argument('--dry-run', action='store_true',
                        help='Validate config and print plan without executing')
    args = parser.parse_args()

    run_pipeline(args.config, dry_run=args.dry_run)


if __name__ == '__main__':
    main()
