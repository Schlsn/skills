---
name: serp-clustering
description: >
  SERP-based keyword clustering — groups keywords by shared Google search result URLs (same SERP = same intent = same cluster). Produces consolidation scores and cluster recommendations for content strategy and SEO. Use when the user wants to cluster keywords using SERP data, identify content consolidation opportunities, find which keywords should target the same page, reduce keyword cannibalization, or build a URL strategy based on search intent. Triggers on: "cluster keywords", "group keywords by intent", "serp clustering", "which keywords should be on the same page", "content consolidation", "keyword cannibalization", "url strategy from serp". Works with PostgreSQL (seo_kws schema) or CSV input.
---

# SERP Clustering

Groups keywords that share organic search result URLs — if two keywords return the same pages, Google considers them to have the same intent, so they should target the same URL.

**Script:** `scripts/serp_cluster.py` — reads from PostgreSQL or CSV, writes results to PostgreSQL or CSV.

---

## How it works

1. For each keyword, collect its top-10 organic SERP URLs
2. Build a similarity matrix: two keywords are "similar" if they share ≥ N URLs
3. Cluster using connected components (fast, default) or cliques/core strategies
4. Score each cluster 0–100 based on shared URL density, connectivity, and cluster size
5. Output: every keyword gets a `cluster_name` + `consolidation_score` + recommendation

---

## Input sources

### A) PostgreSQL — `seo_kws.serp_organic` (preferred)

Data from the `google-serp` skill (n8n workflow). Requires:
- `job_id` — one or more job IDs to include
- `client_schema` — schema where results are saved (e.g. `pronatal`)

```bash
python3 scripts/serp_cluster.py \
  --source postgres \
  --pg-host 78.46.190.162 --pg-db seo --pg-user n8n --pg-pass n8npass \
  --job-ids 16 17 \
  --output-table pronatal.serp_clusters
```

### B) CSV input (any SERP export)

Expects two columns: `keyword` (or `query`) and `url` (or `link`).
Compatible with ValueSERP, DataForSEO, SEMrush exports.

```bash
python3 scripts/serp_cluster.py \
  --source csv \
  --input-file serp_data.csv \
  --output-file serp_clusters.csv
```

---

## Key parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--common-urls` | `3` | Min shared URLs to link two keywords. Lower = more clusters, higher = tighter clusters. Start with 3, raise to 5 for stricter grouping |
| `--strategy` | `connected` | `connected` (fast, recommended), `cliques` (strict — all members connected to each other), `core` (balanced) |
| `--top-positions` | `10` | Only use top-N SERP positions for matching |
| `--noise-domains` | *(built-in list)* | Domains to exclude from matching (wikipedia, youtube, facebook, zhihu etc.) |

---

## Output columns

| Column | Description |
|--------|-------------|
| `keyword` | The keyword |
| `cluster_name` | Shortest keyword in the cluster — a proxy for the "head term" |
| `cluster_type` | `connected_component` / `clique` / `core_cluster` / `none` |
| `cluster_size` | Number of keywords in this cluster |
| `consolidation_score` | 0–100. Higher = stronger case for a single URL |
| `consolidation_recommendation` | Human-readable verdict (see below) |
| `shared_url_count` | URLs shared by ALL members of the cluster |
| `avg_shared_urls` | Average shared URLs across all pairs |
| `connectivity_score` | 0–1, how densely connected the cluster is |
| `is_in_multiple_clusters` | True if keyword appears in overlapping clusters |
| `top_shared_urls` | First 5 shared URLs (diagnostic) |

**Consolidation recommendations:**
- `Strong consolidation candidate` — score ≥ 80, clear single-page target
- `Good consolidation candidate` — score ≥ 60, worth consolidating
- `Possible consolidation` — score ≥ 40, consider
- `Weak consolidation candidate` — score ≥ 20, probably separate
- `Keep separate` — score < 20, distinct intent

---

## Workflow integration

This skill fits into the keyword research pipeline after SERP scraping:

```
google-serp skill         →   serp-clustering skill    →   content strategy
(scrapes SERPs into DB)       (clusters by shared URL)     (1 URL per cluster)
```

After clustering, use `cluster_name` as the target page concept and `consolidation_score` to prioritize which clusters to address first.

---

## Noise domain filtering

The script automatically filters domains that appear so frequently in SERPs that they produce meaningless clusters (e.g. `wikipedia.org`, `youtube.com`, `zhihu.com`). You can extend the list:

```bash
python3 scripts/serp_cluster.py ... \
  --extra-noise-domains "registrlekaru.cz,firmy.cz,heureka.cz"
```

---

## Tips

- **Too few clusters?** Lower `--common-urls` to 2
- **Clusters too large / noisy?** Raise `--common-urls` to 4–5, or switch to `--strategy cliques`
- **Garbage in top clusters?** Add noise domains with `--extra-noise-domains`
- **Only want relevant clusters?** Filter output: `WHERE consolidation_score >= 60 AND cluster_name != 'NO_CLUSTER'`
- **Re-run after new SERP data?** Script uses `ON CONFLICT ... DO UPDATE`, safe to rerun

---

## Quick start (Pronatal example)

```bash
python3 scripts/serp_cluster.py \
  --source postgres \
  --pg-host 78.46.190.162 --pg-db seo --pg-user n8n --pg-pass n8npass \
  --job-ids 16 \
  --output-table pronatal.serp_clusters \
  --common-urls 3 \
  --strategy connected \
  --extra-noise-domains "registrlekaru.cz,firmy.cz,zhihu.com"
```

Check results:
```sql
SELECT cluster_name, cluster_size, consolidation_score, top_shared_urls
FROM pronatal.serp_clusters
WHERE consolidation_score >= 60
  AND cluster_name != 'NO_CLUSTER'
ORDER BY consolidation_score DESC, cluster_size DESC
LIMIT 30;
```
