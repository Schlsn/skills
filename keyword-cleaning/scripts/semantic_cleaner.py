#!/usr/bin/env python3
"""
semantic_cleaner.py

CLI tool for semantic keyword cleaning. Calculates the cosine similarity of keywords
in a given table against the user's `seed_keywords` table using `sentence-transformers`.
Updates the DB with `relevance_score` and optionally sets `is_relevant = false` based on a threshold.

Usage:
  python3 semantic_cleaner.py --schema pronatal --table suggestions --analyze-only
  python3 semantic_cleaner.py --schema pronatal --table suggestions --apply-threshold 0.28
"""

import argparse
import psycopg2
from psycopg2.extras import execute_batch
import pandas as pd
import numpy as np
import torch
from sentence_transformers import SentenceTransformer

DB_CONFIG = {
    "host": "78.46.190.162",
    "port": 5432,
    "dbname": "seo",
    "user": "n8n",
    "password": "n8npass",
}

MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
BATCH_SIZE = 512

def ensure_columns_exist(conn, schema, table_name, suffix=""):
    """Ensures `relevance_score`, `is_relevant`, and `matched_seed` columns exist in the target table."""
    cur = conn.cursor()
    cur.execute(f"ALTER TABLE {schema}.{table_name} ADD COLUMN IF NOT EXISTS relevance_score{suffix} NUMERIC(5,4);")
    cur.execute(f"ALTER TABLE {schema}.{table_name} ADD COLUMN IF NOT EXISTS is_relevant{suffix} BOOLEAN DEFAULT true;")
    cur.execute(f"ALTER TABLE {schema}.{table_name} ADD COLUMN IF NOT EXISTS matched_seed{suffix} TEXT;")
    conn.commit()
    cur.close()

def load_data(conn, schema, table_name, suffix="", limit=None):
    """Load uncalculated keywords and seed keywords."""
    print(f"Loading seeds from {schema}.seed_keywords...")
    seeds_df = pd.read_sql_query(f"SELECT DISTINCT keyword FROM {schema}.seed_keywords WHERE keyword IS NOT NULL AND keyword != ''", conn)
    seed_list = seeds_df['keyword'].tolist()
    if not seed_list:
        raise ValueError("Seed list is empty. Add seeds to {schema}.seed_keywords first.")
    
    # Determine the PK / KW column of the target table
    kw_col = 'keyword'
    if table_name == 'suggestions':
        kw_col = 'suggestion'
    elif table_name == 'related_queries':
        kw_col = 'related_query'
    elif table_name == 'people_also_ask':
        kw_col = 'question'

    print(f"Executing query: {query}")
    kws_df = pd.read_sql_query(query, conn)
    print(f"Loaded {len(kws_df)} pending keywords.")
    pending_kws = kws_df['keyword'].tolist()
    
    return seed_list, pending_kws, kw_col

def compute_similarities(model, seed_list, pending_kws):
    """Compute the max cosine similarity for each pending keyword against all seeds."""
    print(f"Encoding {len(seed_list)} seed keywords...")
    seed_embeddings = model.encode(seed_list, convert_to_tensor=True, batch_size=BATCH_SIZE)
    
    print(f"Encoding {len(pending_kws)} target keywords (this may take a while)...")
    results = []
    
    # Process in batches to save memory
    for i in range(0, len(pending_kws), BATCH_SIZE):
        batch = pending_kws[i:i+BATCH_SIZE]
        batch_embeddings = model.encode(batch, convert_to_tensor=True, batch_size=BATCH_SIZE)
        
        # Cross similarity matrix (batch_size x num_seeds)
        cosine_scores = torch.nn.functional.cosine_similarity(
            batch_embeddings.unsqueeze(1), seed_embeddings.unsqueeze(0), dim=-1
        )
        
        # Max score and index across all seeds for each keyword
        max_scores, max_indices = torch.max(cosine_scores, dim=1)
        max_scores = max_scores.cpu().numpy()
        max_indices = max_indices.cpu().numpy()
        
        for kw, score, idx in zip(batch, max_scores, max_indices):
            matched_seed = seed_list[idx]
            results.append((float(score), matched_seed, kw))
            
        print(f"  Processed {min(i+BATCH_SIZE, len(pending_kws))}/{len(pending_kws)}")
        
    return results

def save_scores(conn, schema, table_name, kw_col, results, suffix=""):
    """Save calculated relevance scores back to the DB mapping."""
    if not results: return
    print(f"Saving {len(results)} scores to database...")
    
    cur = conn.cursor()
    query = f"UPDATE {schema}.{table_name} SET relevance_score{suffix} = %s, matched_seed{suffix} = %s WHERE {kw_col} = %s"
    execute_batch(cur, query, results, page_size=1000)
    conn.commit()
    cur.close()

def print_samples(conn, schema, table_name, kw_col, suffix=""):
    """Print sample keywords surrounding various threshold lines so the user can inspect."""
    cur = conn.cursor()
    breaks = [0.6, 0.4, 0.35, 0.3, 0.28, 0.25, 0.20, 0.15]
    print("\n--- Calibration Samples (Inspection) ---")
    
    for b in breaks:
        cur.execute(f"SELECT {kw_col}, relevance_score{suffix}, matched_seed{suffix} FROM {schema}.{table_name} WHERE relevance_score{suffix} >= %s AND relevance_score{suffix} <= %s ORDER BY RANDOM() LIMIT 5", (b - 0.01, b + 0.01))
        samples = cur.fetchall()
        print(f"\n Threshold ~ {b}:")
        for s in samples:
            print(f"    [{s[1]:.3f}] (seed: {s[2]}) {s[0]}")
            
    print("\nTo apply a threshold cutoff, run:")
    print(f"  python3 semantic_cleaner.py --schema {schema} --table {table_name} --apply-threshold X.XX --suffix '{suffix}'")
    cur.close()

def apply_threshold(conn, schema, table_name, threshold, suffix=""):
    """Set is_relevant = false where relevance_score < threshold."""
    cur = conn.cursor()
    cur.execute(f"UPDATE {schema}.{table_name} SET is_relevant{suffix} = false WHERE relevance_score{suffix} < %s", (threshold,))
    conn.commit()
    removed = cur.rowcount
    
    cur.execute(f"UPDATE {schema}.{table_name} SET is_relevant{suffix} = true WHERE relevance_score{suffix} >= %s", (threshold,))
    conn.commit()
    kept = cur.rowcount
    
    cur.close()
    print(f"✅ Cutoff applied at {threshold}.")
    print(f"  Kept: {kept} (is_relevant=true)")
    print(f"  Removed: {removed} (is_relevant=false)")

def main():
    parser = argparse.ArgumentParser(description="Semantic Keyword Cleaner")
    parser.add_argument("--schema", required=True, help="Database schema (e.g. pronatal)")
    parser.add_argument("--table", required=True, help="Table to clean (e.g. suggestions, related_queries)")
    parser.add_argument("--analyze-only", action="store_true", help="Calculate scores and show samples")
    parser.add_argument("--apply-threshold", type=float, help="Apply threshold and disable non-relevant keywords")
    parser.add_argument("--model-name", default=MODEL_NAME, help="HuggingFace model to use")
    parser.add_argument("--suffix", default="", help="Column suffix for DB (e.g. '_cz' -> relevance_score_cz)")
    parser.add_argument("--limit", type=int, help="Limit number of keywords to process")
    
    args = parser.parse_args()
    
    if not args.analyze_only and args.apply_threshold is None:
        parser.error("Must specify either --analyze-only or --apply-threshold X.XX")
        
    conn = psycopg2.connect(**DB_CONFIG)
    ensure_columns_exist(conn, args.schema, args.table, args.suffix)
    
    if args.apply_threshold is not None:
        apply_threshold(conn, args.schema, args.table, args.apply_threshold, args.suffix)
    else:
        seed_list, pending_kws, kw_col = load_data(conn, args.schema, args.table, args.suffix, args.limit)
        
        if pending_kws:
            print(f"Loading '{args.model_name}' model (this may take a minute with 2.2GB size)...")
            model = SentenceTransformer(args.model_name)
            print("Model loaded into memory.")
            # Use MPS (Metal) on Mac if available, otherwise CUDA or CPU
            if torch.backends.mps.is_available():
                model.to(torch.device("mps"))
                print("Using Apple Silicon (MPS) for inference.")
            elif torch.cuda.is_available():
                print("Using CUDA for inference.")
            else:
                print("Using CPU for inference.")
                
            results = compute_similarities(model, seed_list, pending_kws)
            save_scores(conn, args.schema, args.table, kw_col, results, args.suffix)
        else:
            print("All keywords already have relevance scores encoded for this suffix.")
            
        print_samples(conn, args.schema, args.table, kw_col, args.suffix)
        
    conn.close()

if __name__ == "__main__":
    main()
