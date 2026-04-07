#!/usr/bin/env python3
"""
SERP Clustering — groups keywords by shared organic search result URLs.

Two keywords that return the same pages likely target the same search intent,
so they should point to the same URL. This script identifies those groups
and scores how strong the consolidation opportunity is.

Inspired by Lee Foot's serp_clustering_at_scale.py
https://github.com/searchsolved/search-solved-public-seo

Usage — PostgreSQL input:
    python3 serp_cluster.py \\
        --source postgres \\
        --pg-host HOST --pg-db DB --pg-user USER --pg-pass PASS \\
        --job-ids 16 17 \\
        --output-table myproject.serp_clusters

Usage — CSV input:
    python3 serp_cluster.py \\
        --source csv \\
        --input-file serp_data.csv \\
        --output-file serp_clusters.csv
"""

import argparse
import csv
import importlib.util
import logging
import sys
import time
from collections import defaultdict
from itertools import combinations

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


# ── Deps ─────────────────────────────────────────────────────────────────────

def ensure_deps(postgres: bool):
    import subprocess
    pkgs = {"pandas": "pandas", "tqdm": "tqdm"}
    if postgres:
        pkgs["psycopg2"] = "psycopg2-binary"
    for mod, pkg in pkgs.items():
        if importlib.util.find_spec(mod) is None:
            log.info(f"Installing {pkg}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "-q",
                                   "--break-system-packages"])


# ── Noise domains ─────────────────────────────────────────────────────────────

DEFAULT_NOISE_DOMAINS = {
    "wikipedia.org", "youtube.com", "facebook.com", "instagram.com",
    "twitter.com", "x.com", "linkedin.com", "reddit.com", "pinterest.com",
    "google.com", "bing.com", "amazon.com", "ebay.com", "tiktok.com",
    "zhihu.com", "baidu.com", "weibo.com", "taptap.cn", "japan-reit.com",
}


def is_noise(url: str, noise_domains: set) -> bool:
    url_lower = url.lower()
    return any(d in url_lower for d in noise_domains)


# ── Data loading ──────────────────────────────────────────────────────────────

def load_from_postgres(args, noise_domains: set):
    import psycopg2
    import pandas as pd

    log.info(f"Connecting to PostgreSQL {args.pg_host}/{args.pg_db}...")
    conn = psycopg2.connect(
        host=args.pg_host, port=args.pg_port,
        dbname=args.pg_db, user=args.pg_user, password=args.pg_pass,
    )

    job_ids = [int(x) for x in args.job_ids]
    log.info(f"Loading SERP data for job_ids={job_ids}, top {args.top_positions} positions...")

    query = """
        SELECT LOWER(TRIM(keyword)) AS keyword,
               LOWER(TRIM(url))     AS url
        FROM   seo_kws.serp_organic
        WHERE  job_id = ANY(%s)
          AND  url IS NOT NULL AND url <> ''
          AND  position <= %s
    """
    df = pd.read_sql(query, conn, params=(job_ids, args.top_positions))
    conn.close()

    log.info(f"Loaded {len(df):,} rows, {df['keyword'].nunique():,} unique keywords")
    before = len(df)
    df = df[~df["url"].apply(lambda u: is_noise(u, noise_domains))]
    log.info(f"Removed {before - len(df):,} noise-domain rows")
    return df


def load_from_csv(args, noise_domains: set):
    import pandas as pd

    log.info(f"Loading CSV: {args.input_file}")
    df = pd.read_csv(args.input_file, dtype=str)

    # Flexible column detection
    kw_col  = next((c for c in df.columns if c.lower() in ("keyword", "query", "search.q")), None)
    url_col = next((c for c in df.columns if c.lower() in ("url", "link", "result.organic_results.link")), None)

    if not kw_col or not url_col:
        raise ValueError(
            f"Cannot detect keyword/url columns. Found: {list(df.columns)}\n"
            "Expected columns named 'keyword'/'query' and 'url'/'link'."
        )

    df = df[[kw_col, url_col]].rename(columns={kw_col: "keyword", url_col: "url"})
    df["keyword"] = df["keyword"].str.lower().str.strip()
    df["url"]     = df["url"].str.lower().str.strip()
    df = df.dropna().drop_duplicates()

    before = len(df)
    df = df[~df["url"].apply(lambda u: is_noise(u, noise_domains))]
    log.info(f"Loaded {len(df):,} rows ({before - len(df):,} noise rows removed), "
             f"{df['keyword'].nunique():,} unique keywords")
    return df


# ── Clustering core ───────────────────────────────────────────────────────────

def create_query_map(df):
    """keyword → set of URLs"""
    return df.groupby("keyword")["url"].apply(set).to_dict()


def build_similarity_matrix(query_map: dict, threshold: int):
    """Pairwise comparison — link two keywords if they share ≥ threshold URLs."""
    from tqdm import tqdm

    queries = list(query_map.keys())
    sim = defaultdict(dict)

    log.info(f"Building similarity matrix for {len(queries):,} keywords "
             f"(threshold={threshold} shared URLs)...")

    for i in tqdm(range(len(queries)), desc="Similarity matrix", unit="kw"):
        for j in range(i + 1, len(queries)):
            q1, q2 = queries[i], queries[j]
            shared = len(query_map[q1] & query_map[q2])
            if shared >= threshold:
                sim[q1][q2] = shared
                sim[q2][q1] = shared

    linked = sum(1 for q in queries if q in sim)
    log.info(f"Keywords with ≥1 match: {linked:,} / {len(queries):,}")
    return sim, queries


def find_connected_components(sim: dict, queries: list) -> list:
    """Strategy 1 (default): any transitive link counts."""
    sys.setrecursionlimit(20_000)
    visited = set()
    components = []

    def dfs(q, comp):
        if q in visited:
            return
        visited.add(q)
        comp.add(q)
        for nb in sim.get(q, {}):
            dfs(nb, comp)

    for q in queries:
        if q not in visited and q in sim:
            comp = set()
            dfs(q, comp)
            if len(comp) > 1:
                components.append(comp)
    return components


def find_cliques(sim: dict, queries: list, min_size: int = 2) -> list:
    """Strategy 2: every member must be connected to every other member."""
    from tqdm import tqdm

    def is_clique(s):
        lst = list(s)
        for i in range(len(lst)):
            for j in range(i + 1, len(lst)):
                if lst[j] not in sim.get(lst[i], {}):
                    return False
        return True

    cliques = []
    for q in tqdm(queries, desc="Finding cliques"):
        if q not in sim:
            continue
        candidates = {q} | set(sim[q].keys())
        for size in range(len(candidates), min_size - 1, -1):
            for subset in combinations(candidates, size):
                if is_clique(set(subset)):
                    cl = set(subset)
                    if all(not cl.issubset(ex) for ex in cliques):
                        cliques.append(cl)
                    break

    return [c for c in cliques
            if not any(c != other and c.issubset(other) for other in cliques)]


def find_core_clusters(sim: dict, queries: list, threshold: float = 0.7) -> list:
    """Strategy 3: candidate must be connected to ≥ threshold fraction of existing cluster."""
    from tqdm import tqdm

    clusters = []
    for seed in tqdm(queries, desc="Core clusters"):
        if seed not in sim:
            continue
        cluster = {seed}
        for candidate in sim[seed]:
            connections = sum(1 for m in cluster if candidate in sim.get(m, {}))
            if connections >= len(cluster) * threshold:
                cluster.add(candidate)
        if len(cluster) > 1 and cluster not in clusters:
            clusters.append(cluster)
    return clusters


def cluster_keywords(query_map: dict, threshold: int, strategy: str,
                     core_threshold: float = 0.7):
    sim, queries = build_similarity_matrix(query_map, threshold)

    all_clusters = []

    if strategy in ("connected", "all"):
        for comp in find_connected_components(sim, queries):
            d = _analyze(comp, query_map, sim)
            d["cluster_type"] = "connected_component"
            all_clusters.append(d)

    if strategy in ("cliques", "all"):
        for cl in find_cliques(sim, queries):
            d = _analyze(cl, query_map, sim)
            d["cluster_type"] = "clique"
            all_clusters.append(d)

    if strategy in ("core", "all"):
        for cc in find_core_clusters(sim, queries, core_threshold):
            d = _analyze(cc, query_map, sim)
            d["cluster_type"] = "core_cluster"
            all_clusters.append(d)

    # Mark keywords in multiple clusters
    kw_count = defaultdict(int)
    for c in all_clusters:
        for kw in c["keywords"]:
            kw_count[kw] += 1
    for c in all_clusters:
        c["overlapping"] = [kw for kw in c["keywords"] if kw_count[kw] > 1]

    return all_clusters, sim


def _analyze(cluster_set, query_map, sim):
    kws = list(cluster_set)
    shared_urls = set(query_map[kws[0]]) if kws else set()
    for kw in kws[1:]:
        shared_urls &= query_map[kw]

    metrics = dict(min_s=float("inf"), max_s=0, sum_s=0, pairs=0, actual=0)
    possible = len(kws) * (len(kws) - 1) / 2

    for i in range(len(kws)):
        for j in range(i + 1, len(kws)):
            if kws[j] in sim.get(kws[i], {}):
                s = sim[kws[i]][kws[j]]
                metrics["min_s"] = min(metrics["min_s"], s)
                metrics["max_s"] = max(metrics["max_s"], s)
                metrics["sum_s"] += s
                metrics["pairs"] += 1
                metrics["actual"] += 1

    avg = metrics["sum_s"] / metrics["pairs"] if metrics["pairs"] else 0
    if metrics["min_s"] == float("inf"):
        metrics["min_s"] = 0
    connectivity = metrics["actual"] / possible if possible else 0

    return {
        "keywords": kws,
        "shared_urls": list(shared_urls),
        "shared_url_count": len(shared_urls),
        "avg_shared_urls": avg,
        "min_shared_urls": metrics["min_s"],
        "max_shared_urls": metrics["max_s"],
        "connectivity_score": connectivity,
        "cluster_size": len(kws),
        "overlapping": [],
    }


# ── Scoring ───────────────────────────────────────────────────────────────────

def consolidation_score(avg_shared, connectivity, cluster_size, overlap_count):
    """0–100 score. Higher = stronger case for pointing all keywords to one page."""
    base         = min(40, avg_shared * 4)        # shared URL density
    conn_bonus   = connectivity * 30               # how tightly linked
    size_bonus   = min(20, (cluster_size - 2) * 5) # larger clusters score higher
    overlap_pen  = min(10, overlap_count * 5)      # penalty for overlapping clusters
    return max(0, min(100, round(base + conn_bonus + size_bonus - overlap_pen)))


def score_label(score):
    if score >= 80: return "Strong consolidation candidate"
    if score >= 60: return "Good consolidation candidate"
    if score >= 40: return "Possible consolidation"
    if score >= 20: return "Weak consolidation candidate"
    return "Keep separate"


# ── Results ───────────────────────────────────────────────────────────────────

def build_results(clusters, query_map):
    rows = []
    processed = set()

    for c in clusters:
        cluster_name = min(c["keywords"], key=len)
        score = consolidation_score(
            c["avg_shared_urls"], c["connectivity_score"],
            c["cluster_size"], len(c["overlapping"])
        )
        for kw in c["keywords"]:
            processed.add(kw)
            rows.append({
                "keyword":                    kw,
                "cluster_name":               cluster_name,
                "cluster_type":               c["cluster_type"],
                "cluster_size":               c["cluster_size"],
                "consolidation_score":        score,
                "consolidation_recommendation": score_label(score),
                "shared_url_count":           c["shared_url_count"],
                "avg_shared_urls":            round(c["avg_shared_urls"], 2),
                "connectivity_score":         round(c["connectivity_score"], 4),
                "is_in_multiple_clusters":    kw in c["overlapping"],
                "top_shared_urls":            ", ".join(c["shared_urls"][:5]),
            })

    for kw in query_map:
        if kw not in processed:
            rows.append({
                "keyword": kw, "cluster_name": "NO_CLUSTER", "cluster_type": "none",
                "cluster_size": 1, "consolidation_score": 0,
                "consolidation_recommendation": "Keep separate",
                "shared_url_count": 0, "avg_shared_urls": 0.0, "connectivity_score": 0.0,
                "is_in_multiple_clusters": False, "top_shared_urls": "",
            })

    import pandas as pd
    df = pd.DataFrame(rows)
    return df.sort_values(
        ["consolidation_score", "cluster_name", "keyword"],
        ascending=[False, True, True]
    ).reset_index(drop=True)


# ── Output ────────────────────────────────────────────────────────────────────

def save_to_postgres(df, args):
    import psycopg2, psycopg2.extras

    schema, table = args.output_table.rsplit(".", 1) if "." in args.output_table \
        else ("public", args.output_table)

    log.info(f"Saving {len(df):,} rows to {args.output_table}...")
    conn = psycopg2.connect(
        host=args.pg_host, port=args.pg_port,
        dbname=args.pg_db, user=args.pg_user, password=args.pg_pass,
    )
    cur = conn.cursor()

    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS {schema}.{table} (
            keyword                      TEXT PRIMARY KEY,
            cluster_name                 TEXT,
            cluster_type                 TEXT,
            cluster_size                 INTEGER,
            consolidation_score          INTEGER,
            consolidation_recommendation TEXT,
            shared_url_count             INTEGER,
            avg_shared_urls              NUMERIC(8,2),
            connectivity_score           NUMERIC(8,4),
            is_in_multiple_clusters      BOOLEAN,
            top_shared_urls              TEXT,
            clustered_at                 TIMESTAMP DEFAULT NOW()
        )
    """)

    rows = [
        (r.keyword, r.cluster_name, r.cluster_type, int(r.cluster_size),
         int(r.consolidation_score), r.consolidation_recommendation,
         int(r.shared_url_count), float(r.avg_shared_urls),
         float(r.connectivity_score), bool(r.is_in_multiple_clusters),
         r.top_shared_urls)
        for r in df.itertuples(index=False)
    ]

    psycopg2.extras.execute_values(cur, f"""
        INSERT INTO {schema}.{table}
          (keyword, cluster_name, cluster_type, cluster_size, consolidation_score,
           consolidation_recommendation, shared_url_count, avg_shared_urls,
           connectivity_score, is_in_multiple_clusters, top_shared_urls)
        VALUES %s
        ON CONFLICT (keyword) DO UPDATE SET
          cluster_name                 = EXCLUDED.cluster_name,
          cluster_type                 = EXCLUDED.cluster_type,
          cluster_size                 = EXCLUDED.cluster_size,
          consolidation_score          = EXCLUDED.consolidation_score,
          consolidation_recommendation = EXCLUDED.consolidation_recommendation,
          shared_url_count             = EXCLUDED.shared_url_count,
          avg_shared_urls              = EXCLUDED.avg_shared_urls,
          connectivity_score           = EXCLUDED.connectivity_score,
          is_in_multiple_clusters      = EXCLUDED.is_in_multiple_clusters,
          top_shared_urls              = EXCLUDED.top_shared_urls,
          clustered_at                 = NOW()
    """, rows, page_size=1000)

    conn.commit()
    cur.close()
    conn.close()
    log.info("Saved to PostgreSQL.")


def save_to_csv(df, output_file):
    df.to_csv(output_file, index=False, encoding="utf-8-sig")
    log.info(f"Saved to {output_file}")


def print_summary(df, clusters, elapsed):
    total = df["keyword"].nunique()
    clustered = df[df["cluster_name"] != "NO_CLUSTER"]["keyword"].nunique()
    n_strong = df[df["consolidation_score"] >= 80]["cluster_name"].nunique()
    n_good   = df[(df["consolidation_score"] >= 60) & (df["consolidation_score"] < 80)]["cluster_name"].nunique()

    log.info("=" * 55)
    log.info(f"Total keywords:      {total:,}")
    log.info(f"Clustered:           {clustered:,} / {total:,}  ({100*clustered/total:.1f}%)")
    log.info(f"Total clusters:      {len(clusters)}")
    log.info(f"Strong (score ≥ 80): {n_strong} clusters")
    log.info(f"Good   (score ≥ 60): {n_good} clusters")
    log.info(f"Runtime:             {elapsed:.1f}s")
    log.info("=" * 55)

    top = (df[df["cluster_name"] != "NO_CLUSTER"]
           .groupby("cluster_name")[["cluster_size", "consolidation_score"]]
           .first()
           .sort_values("consolidation_score", ascending=False)
           .head(10))
    log.info("\nTop 10 clusters:")
    for name, row in top.iterrows():
        log.info(f"  [{int(row['consolidation_score']):3}] {name:45} ({int(row['cluster_size'])} kw)")


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="SERP-based keyword clustering")

    p.add_argument("--source", choices=["postgres", "csv"], default="postgres")

    # PostgreSQL
    p.add_argument("--pg-host",  default="78.46.190.162")
    p.add_argument("--pg-port",  type=int, default=5432)
    p.add_argument("--pg-db",    default="seo")
    p.add_argument("--pg-user",  default="n8n")
    p.add_argument("--pg-pass",  default="n8npass")
    p.add_argument("--job-ids",  nargs="+", default=["16"])
    p.add_argument("--output-table", default="public.serp_clusters",
                   help="Schema.table for output, e.g. pronatal.serp_clusters")

    # CSV
    p.add_argument("--input-file",  default="serp_data.csv")
    p.add_argument("--output-file", default="serp_clusters.csv")

    # Clustering
    p.add_argument("--common-urls",   type=int,   default=3,
                   help="Min shared URLs to link two keywords (default 3)")
    p.add_argument("--strategy",      default="connected",
                   choices=["connected", "cliques", "core", "all"])
    p.add_argument("--core-threshold",type=float, default=0.7)
    p.add_argument("--top-positions", type=int,   default=10,
                   help="Only use top-N SERP results for matching")

    # Noise
    p.add_argument("--extra-noise-domains", default="",
                   help="Comma-separated additional domains to exclude")

    return p.parse_args()


def main():
    t0 = time.time()
    args = parse_args()

    ensure_deps(postgres=(args.source == "postgres"))

    # Build noise set
    noise_domains = set(DEFAULT_NOISE_DOMAINS)
    if args.extra_noise_domains:
        noise_domains.update(d.strip() for d in args.extra_noise_domains.split(",") if d.strip())

    # Load
    if args.source == "postgres":
        df_raw = load_from_postgres(args, noise_domains)
    else:
        df_raw = load_from_csv(args, noise_domains)

    if df_raw.empty:
        log.error("No data loaded — check input source / job IDs.")
        sys.exit(1)

    # Cluster
    query_map = create_query_map(df_raw)
    log.info(f"Clustering {len(query_map):,} keywords...")

    clusters, _ = cluster_keywords(
        query_map,
        threshold=args.common_urls,
        strategy=args.strategy,
        core_threshold=args.core_threshold,
    )

    # Build results
    results = build_results(clusters, query_map)

    # Save
    if args.source == "postgres" or args.output_table != "public.serp_clusters":
        save_to_postgres(results, args)
    else:
        save_to_csv(results, args.output_file)

    print_summary(results, clusters, time.time() - t0)


if __name__ == "__main__":
    main()
