#!/usr/bin/env python3
"""
Keywords Analysis — DuckDB analytics layer.

Works with keyword data already collected in a DuckDB project.
Provides dedup, overview, gap analysis, and export utilities.

Usage:
  python3 analyze.py <project> overview
  python3 analyze.py <project> dedup
  python3 analyze.py <project> top 50
  python3 analyze.py <project> gaps
  python3 analyze.py <project> export-for-clustering
  python3 analyze.py <project> export-all
"""

import argparse
import csv
import os
import sys
from pathlib import Path

DB_BASE = Path.home() / 'kw_projects'


def _connect(project: str):
    import duckdb
    db_path = str(DB_BASE / f"{project}.duckdb")
    if not os.path.exists(db_path):
        print(f"Project not found: {db_path}", file=sys.stderr)
        sys.exit(1)
    return duckdb.connect(db_path)


# ── Overview ────────────────────────────────────────────────────────────────

def cmd_overview(project: str):
    """Show keyword counts, volume distribution, source breakdown."""
    con = _connect(project)

    print(f"\n{'═' * 60}")
    print(f"  Project: {project}")
    print(f"{'═' * 60}")

    # Table row counts
    tables = ['search_console', 'competitor_keywords', 'keyword_planner',
              'suggestions', 'serp', 'related_queries', 'people_also_ask']

    print(f"\n  Table row counts:")
    for t in tables:
        try:
            n = con.sql(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            print(f"    {t:25s} {n:>8,}")
        except Exception:
            print(f"    {t:25s}        -")

    # Unique keywords across all sources
    unique_sql = """
        SELECT COUNT(DISTINCT kw) FROM (
            SELECT LOWER(query) AS kw FROM search_console
            UNION SELECT LOWER(keyword) FROM competitor_keywords
            UNION SELECT LOWER(keyword) FROM keyword_planner
            UNION SELECT LOWER(suggestion) FROM suggestions
            UNION SELECT LOWER(keyword) FROM serp
            UNION SELECT LOWER(related_query) FROM related_queries
            UNION SELECT LOWER(question) FROM people_also_ask
        )
    """
    try:
        total = con.sql(unique_sql).fetchone()[0]
        print(f"\n  Unique keywords (all sources): {total:,}")
    except Exception:
        pass

    # Volume distribution (from keyword_planner)
    try:
        dist = con.sql("""
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE avg_monthly_searches > 0) AS with_volume,
                COUNT(*) FILTER (WHERE avg_monthly_searches >= 1000) AS vol_1000_plus,
                COUNT(*) FILTER (WHERE avg_monthly_searches >= 100) AS vol_100_plus,
                SUM(avg_monthly_searches) AS total_volume
            FROM keyword_planner
        """).fetchone()
        print(f"\n  Keyword Planner stats:")
        print(f"    Total entries:      {dist[0]:>8,}")
        print(f"    With volume:        {dist[1]:>8,}")
        print(f"    Volume ≥ 1,000:     {dist[2]:>8,}")
        print(f"    Volume ≥ 100:       {dist[3]:>8,}")
        print(f"    Total search vol:   {dist[4]:>8,}")
    except Exception:
        pass

    # Competitors
    try:
        comps = con.sql("""
            SELECT competitor_domain, COUNT(*) AS kws,
                   SUM(search_volume) AS total_vol
            FROM competitor_keywords
            GROUP BY competitor_domain ORDER BY total_vol DESC
        """).fetchdf()
        if len(comps) > 0:
            print(f"\n  Competitors:")
            for _, row in comps.iterrows():
                print(f"    {row['competitor_domain']:30s} {row['kws']:>6,} kws  vol: {row['total_vol']:>10,}")
    except Exception:
        pass

    print(f"\n{'═' * 60}\n")
    con.close()


# ── Dedup ───────────────────────────────────────────────────────────────────

def cmd_dedup(project: str):
    """Find and report duplicate keywords across tables."""
    con = _connect(project)

    print(f"\n  Dedup report: {project}")
    print(f"{'─' * 60}")

    # Dupes within keyword_planner
    try:
        dupes = con.sql("""
            SELECT keyword, COUNT(*) AS cnt
            FROM keyword_planner
            GROUP BY keyword HAVING COUNT(*) > 1
            ORDER BY cnt DESC LIMIT 20
        """).fetchdf()
        print(f"\n  Duplicates in keyword_planner: {len(dupes)}")
        if len(dupes) > 0:
            for _, r in dupes.head(10).iterrows():
                print(f"    {r['keyword']:40s} ×{r['cnt']}")
    except Exception:
        pass

    # Overlap: GSC ∩ Competitors
    try:
        overlap = con.sql("""
            SELECT COUNT(*) FROM (
                SELECT LOWER(query) AS kw FROM search_console
                INTERSECT
                SELECT LOWER(keyword) FROM competitor_keywords
            )
        """).fetchone()[0]
        gsc_total = con.sql("SELECT COUNT(DISTINCT LOWER(query)) FROM search_console").fetchone()[0]
        comp_total = con.sql("SELECT COUNT(DISTINCT LOWER(keyword)) FROM competitor_keywords").fetchone()[0]
        print(f"\n  GSC ∩ Competitors overlap: {overlap:,} keywords")
        print(f"    GSC unique: {gsc_total:,} | Competitor unique: {comp_total:,}")
    except Exception:
        pass

    print()
    con.close()


# ── Top keywords ────────────────────────────────────────────────────────────

def cmd_top(project: str, n: int = 50):
    """Unified top keywords by volume from all sources."""
    con = _connect(project)

    result = con.sql(f"""
        WITH all_kws AS (
            SELECT LOWER(keyword) AS kw, avg_monthly_searches AS vol, 'planner' AS src
            FROM keyword_planner WHERE avg_monthly_searches > 0
            UNION ALL
            SELECT LOWER(keyword), search_volume, 'competitor' FROM competitor_keywords
            WHERE search_volume > 0
        )
        SELECT kw AS keyword, MAX(vol) AS search_volume,
               LIST(DISTINCT src) AS sources
        FROM all_kws
        GROUP BY kw
        ORDER BY search_volume DESC
        LIMIT {n}
    """)

    print(result.fetchdf().to_string(index=False))
    con.close()


# ── Gap analysis ────────────────────────────────────────────────────────────

def cmd_gaps(project: str):
    """Keywords competitors rank for but NOT in GSC (potential opportunities)."""
    con = _connect(project)

    result = con.sql("""
        SELECT c.keyword, c.search_volume, c.rank_absolute AS comp_pos,
               c.competitor_domain, c.url AS comp_url
        FROM competitor_keywords c
        WHERE LOWER(c.keyword) NOT IN (
            SELECT DISTINCT LOWER(query) FROM search_console
        )
        AND c.search_volume > 0
        ORDER BY c.search_volume DESC
        LIMIT 50
    """)

    df = result.fetchdf()
    print(f"\n  Keyword gaps: {len(df)} (competitors rank, you don't)")
    print(f"{'─' * 80}")
    print(df.to_string(index=False))
    print()
    con.close()


# ── Export for clustering ───────────────────────────────────────────────────

def cmd_export_clustering(project: str):
    """Export all unique keywords with volume for semantic clustering."""
    con = _connect(project)

    df = con.sql("""
        WITH all_kws AS (
            SELECT LOWER(keyword) AS kw, avg_monthly_searches AS vol FROM keyword_planner
            UNION ALL
            SELECT LOWER(keyword), search_volume FROM competitor_keywords
            UNION ALL
            SELECT LOWER(query), 0 FROM search_console
        )
        SELECT kw AS Keyword, MAX(vol) AS Search_Volume
        FROM all_kws
        WHERE kw IS NOT NULL AND kw != ''
        GROUP BY kw
        HAVING MAX(vol) > 0
        ORDER BY Search_Volume DESC
    """).fetchdf()

    out_path = f"/tmp/kw_{project}_for_clustering.csv"
    df.to_csv(out_path, index=False)
    print(f"Exported {len(df):,} keywords to {out_path}")
    print(f"Next: python3 ../keyword-categorization/scripts/cluster_keywords.py {out_path}")
    con.close()


# ── Export all ──────────────────────────────────────────────────────────────

def cmd_export_all(project: str):
    """Export all unique keywords with volumes to CSV."""
    con = _connect(project)

    df = con.sql("""
        WITH all_kws AS (
            SELECT LOWER(keyword) AS kw, avg_monthly_searches AS vol, 'planner' AS src FROM keyword_planner
            UNION ALL
            SELECT LOWER(keyword), search_volume, 'competitor' FROM competitor_keywords
            UNION ALL
            SELECT LOWER(suggestion), 0, 'autocomplete' FROM suggestions
            UNION ALL
            SELECT LOWER(related_query), 0, 'related' FROM related_queries
            UNION ALL
            SELECT LOWER(question), 0, 'paa' FROM people_also_ask
            UNION ALL
            SELECT LOWER(query), 0, 'gsc' FROM search_console
        )
        SELECT kw AS keyword, MAX(vol) AS search_volume,
               LIST(DISTINCT src) AS sources
        FROM all_kws
        WHERE kw IS NOT NULL AND kw != ''
        GROUP BY kw
        ORDER BY search_volume DESC
    """).fetchdf()

    out_path = f"/tmp/kw_{project}_all.csv"
    df.to_csv(out_path, index=False)
    print(f"Exported {len(df):,} unique keywords to {out_path}")
    con.close()


# ── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Keywords Analysis — DuckDB analytics')
    parser.add_argument('project', help='DuckDB project name')
    parser.add_argument('command', choices=[
        'overview', 'dedup', 'top', 'gaps',
        'export-for-clustering', 'export-all',
    ])
    parser.add_argument('n', nargs='?', type=int, default=50, help='Limit for top command')
    args = parser.parse_args()

    cmds = {
        'overview': lambda: cmd_overview(args.project),
        'dedup': lambda: cmd_dedup(args.project),
        'top': lambda: cmd_top(args.project, args.n),
        'gaps': lambda: cmd_gaps(args.project),
        'export-for-clustering': lambda: cmd_export_clustering(args.project),
        'export-all': lambda: cmd_export_all(args.project),
    }
    cmds[args.command]()


if __name__ == '__main__':
    main()
