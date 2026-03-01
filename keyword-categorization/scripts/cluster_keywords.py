#!/usr/bin/env python3
"""
Hierarchical keyword clustering using OpenAI embeddings via OpenRouter.
Two-phase approach:
  1. Community detection → tight subcategories
  2. Agglomerative clustering → broad main categories

Usage:
  python cluster_keywords.py keywords.csv
  python cluster_keywords.py keywords.csv --sub-threshold 0.80 --main-threshold 0.60
  python cluster_keywords.py keywords.csv -o output.csv --sep ","
"""

import argparse
import csv
import gc
import os
import sys

import numpy as np

# ── Dependency check ────────────────────────────────────────────────────────

def ensure_deps():
    """Install missing dependencies."""
    required = {
        'openai': 'openai',
        'sentence_transformers': 'sentence-transformers',
        'sklearn': 'scikit-learn',
        'torch': 'torch',
    }
    missing = []
    for mod, pkg in required.items():
        try:
            __import__(mod)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"Installing: {', '.join(missing)}", file=sys.stderr)
        os.system(f"{sys.executable} -m pip install {' '.join(missing)} --break-system-packages -q")


# ── OpenRouter embeddings ───────────────────────────────────────────────────

def get_embeddings(texts: list[str], api_key: str, batch_size: int = 500) -> np.ndarray:
    """Fetch embeddings via OpenRouter (OpenAI-compatible API)."""
    from openai import OpenAI

    client = OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
    )

    all_embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        print(f"  Embeddings batch {i // batch_size + 1}/{(len(texts) - 1) // batch_size + 1} "
              f"({len(batch)} items)...", file=sys.stderr)
        response = client.embeddings.create(
            input=batch,
            model="openai/text-embedding-3-small",
        )
        all_embeddings.extend([d.embedding for d in response.data])

    return np.array(all_embeddings, dtype=np.float32)


# ── Clustering ──────────────────────────────────────────────────────────────

def cluster_keywords(
    keywords: list[str],
    volumes: list[float],
    embeddings: np.ndarray,
    sub_threshold: float = 0.80,
    main_threshold: float = 0.60,
) -> list[dict]:
    """Two-phase hierarchical clustering.

    Returns list of dicts with keys:
      Keyword, Search_Volume, Main_Category, Subcategory
    """
    import torch
    from sentence_transformers import util
    from sklearn.cluster import AgglomerativeClustering

    embeddings_tensor = torch.tensor(embeddings)

    # ── Phase 1: Subcategories (community detection) ────────────────────
    print("  Phase 1: Subcategory community detection...", file=sys.stderr)
    sub_clusters = util.community_detection(
        embeddings_tensor, min_community_size=2,
        threshold=sub_threshold, batch_size=1024,
    )

    n = len(keywords)
    subcat_id = [-1] * n
    subcat_name = ['Nezařazeno'] * n
    leader_indices = []

    for cid, community in enumerate(sub_clusters):
        best_idx = max(community, key=lambda idx: volumes[idx])
        name = keywords[best_idx]
        leader_indices.append(best_idx)
        for idx in community:
            subcat_id[idx] = cid
            subcat_name[idx] = name

    print(f"  → {len(sub_clusters)} subcategories created", file=sys.stderr)

    # ── Phase 2: Main categories (agglomerative clustering) ─────────────
    print("  Phase 2: Main category agglomerative clustering...", file=sys.stderr)
    main_cat_id = [-1] * n
    main_cat_name = ['Nezařazeno'] * n

    if leader_indices:
        leaders_emb = embeddings[leader_indices]
        agg = AgglomerativeClustering(
            n_clusters=None,
            distance_threshold=1.0 - main_threshold,
            metric='cosine',
            linkage='average',
        )
        leader_labels = agg.fit_predict(leaders_emb)

        for main_label in set(leader_labels):
            leaders_in_main = [
                leader_indices[i] for i, lbl in enumerate(leader_labels)
                if lbl == main_label
            ]
            best_main_idx = max(leaders_in_main, key=lambda idx: volumes[idx])
            name = keywords[best_main_idx]

            for li in leaders_in_main:
                sid = subcat_id[li]
                for j in range(n):
                    if subcat_id[j] == sid:
                        main_cat_id[j] = int(main_label)
                        main_cat_name[j] = name

        print(f"  → {len(set(leader_labels))} main categories created", file=sys.stderr)

    # ── Build result ────────────────────────────────────────────────────
    results = []
    for i in range(n):
        results.append({
            'Keyword': keywords[i],
            'Search_Volume': volumes[i],
            'Main_Category': main_cat_name[i],
            'Subcategory': subcat_name[i],
        })

    # Sort: main cat desc by total volume, subcat desc, volume desc
    results.sort(key=lambda r: (-volumes[keywords.index(r['Main_Category'])] if r['Main_Category'] != 'Nezařazeno' else 0,
                                 -volumes[keywords.index(r['Subcategory'])] if r['Subcategory'] != 'Nezařazeno' else 0,
                                 -r['Search_Volume']))
    return results


# ── Public API ──────────────────────────────────────────────────────────────

def process_csv(
    input_path: str,
    output_path: str | None = None,
    sub_threshold: float = 0.80,
    main_threshold: float = 0.60,
    input_sep: str = ',',
    api_key: str | None = None,
) -> list[dict]:
    """Full pipeline: read CSV → embed → cluster → write CSV."""
    import pandas as pd

    api_key = api_key or os.environ.get('OPENROUTER_API_KEY')
    if not api_key:
        raise ValueError(
            "No API key. Set OPENROUTER_API_KEY env var or pass --api-key."
        )

    # Read
    print("1. Reading CSV...", file=sys.stderr)
    df = pd.read_csv(input_path, sep=input_sep)

    # Auto-detect columns (case-insensitive)
    cols = {c.lower().strip(): c for c in df.columns}
    kw_col = cols.get('keyword') or cols.get('keywords') or cols.get('query')
    vol_col = cols.get('search_volume') or cols.get('volume') or cols.get('search volume') or cols.get('sv')
    if not kw_col:
        raise ValueError(f"Cannot find keyword column. Available: {list(df.columns)}")
    if not vol_col:
        raise ValueError(f"Cannot find volume column. Available: {list(df.columns)}")

    df = df.dropna(subset=[kw_col, vol_col])
    df = df.drop_duplicates(subset=[kw_col]).reset_index(drop=True)
    df[vol_col] = pd.to_numeric(df[vol_col], errors='coerce').fillna(0)

    keywords = df[kw_col].tolist()
    volumes = df[vol_col].tolist()
    print(f"   {len(keywords)} unique keywords loaded", file=sys.stderr)

    # Embeddings (with cache)
    cache_file = input_path.rsplit('.', 1)[0] + '_embeddings.npy'
    print("2. Generating embeddings...", file=sys.stderr)
    if os.path.exists(cache_file):
        print(f"   Loading cached: {cache_file}", file=sys.stderr)
        embeddings = np.load(cache_file)
        if len(embeddings) != len(keywords):
            print("   Cache size mismatch, regenerating...", file=sys.stderr)
            embeddings = get_embeddings(keywords, api_key)
            np.save(cache_file, embeddings)
    else:
        embeddings = get_embeddings(keywords, api_key)
        np.save(cache_file, embeddings)
        print(f"   Cached to: {cache_file}", file=sys.stderr)

    # Cluster
    print("3. Clustering...", file=sys.stderr)
    results = cluster_keywords(keywords, volumes, embeddings, sub_threshold, main_threshold)

    # Write
    if output_path is None:
        output_path = input_path.rsplit('.', 1)[0] + '_clustered.csv'

    print(f"4. Writing: {output_path}", file=sys.stderr)
    with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=['Keyword', 'Search_Volume', 'Main_Category', 'Subcategory'], delimiter=';')
        w.writeheader()
        w.writerows(results)

    # Summary
    main_cats = set(r['Main_Category'] for r in results if r['Main_Category'] != 'Nezařazeno')
    sub_cats = set(r['Subcategory'] for r in results if r['Subcategory'] != 'Nezařazeno')
    print(f"\n✅ Done: {len(keywords)} keywords → {len(main_cats)} main categories, {len(sub_cats)} subcategories", file=sys.stderr)

    return results


# ── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Hierarchical keyword clustering via OpenRouter embeddings'
    )
    parser.add_argument('input', help='Input CSV file (must have Keyword and Search_Volume columns)')
    parser.add_argument('-o', '--output', default=None, help='Output CSV path (default: <input>_clustered.csv)')
    parser.add_argument('--sub-threshold', type=float, default=0.80,
                        help='Cosine similarity threshold for subcategories (default: 0.80)')
    parser.add_argument('--main-threshold', type=float, default=0.60,
                        help='Cosine similarity threshold for main categories (default: 0.60)')
    parser.add_argument('--sep', default=',', help='Input CSV separator (default: ,)')
    parser.add_argument('--api-key', default=None, help='OpenRouter API key (or set OPENROUTER_API_KEY env var)')
    args = parser.parse_args()

    ensure_deps()

    process_csv(
        input_path=args.input,
        output_path=args.output,
        sub_threshold=args.sub_threshold,
        main_threshold=args.main_threshold,
        input_sep=args.sep,
        api_key=args.api_key,
    )


if __name__ == '__main__':
    main()
