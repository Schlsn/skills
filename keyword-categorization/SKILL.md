---
name: keyword-categorization
description: Hierarchical semantic clustering of keywords into Main Categories and Subcategories using OpenAI embeddings (via OpenRouter). Includes SEO analyst prompt for naming cleanup, intent mapping, cannibalization detection, and content planning. Use when the user wants to cluster, categorize, or organize keywords for SEO/content strategy.
---

# Keyword Categorization & SEO Content Strategy

Two-phase semantic clustering of keywords + expert SEO analysis layer.

## Script location
`scripts/cluster_keywords.py`

## Quick start

### 1. Cluster keywords (Python script)

```bash
# Set API key (OpenRouter)
export OPENROUTER_API_KEY="sk-or-..."

# Basic usage
python3 scripts/cluster_keywords.py keywords.csv

# Custom thresholds
python3 scripts/cluster_keywords.py keywords.csv --sub-threshold 0.80 --main-threshold 0.60

# Specify separator and output
python3 scripts/cluster_keywords.py keywords.csv --sep ";" -o result.csv
```

### 2. Python API

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scripts'))
from cluster_keywords import process_csv

results = process_csv("keywords.csv", api_key="sk-or-...")
```

## Input CSV format

Must contain at least two columns (auto-detected, case-insensitive):
- **Keyword** (or `Keywords`, `Query`)
- **Search_Volume** (or `Volume`, `Search Volume`, `SV`)

```csv
Keyword,Search_Volume
ivf,12100
umělé oplodnění,8100
icsi metoda,1900
```

## Output

CSV with `;` separator and columns: `Keyword`, `Search_Volume`, `Main_Category`, `Subcategory`

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `input` | required | Input CSV path |
| `-o` / `--output` | `<input>_clustered.csv` | Output CSV path |
| `--sub-threshold` | `0.80` | Cosine similarity for subcategories (higher = tighter clusters) |
| `--main-threshold` | `0.60` | Cosine similarity for main categories (lower = broader groups) |
| `--sep` | `,` | Input CSV separator |
| `--api-key` | env `OPENROUTER_API_KEY` | OpenRouter API key |

## SEO Analysis Prompt

After clustering, analyze the output CSV using this persona:

> **Role**: Expert SEO analyst and content strategist.
> You analyze keywords that passed through two-phase semantic clustering (main categories + subcategories).
> Category names are derived from the highest-volume keyword in each cluster — they may be grammatically awkward.

### Triggers

| Command | Action |
|---------|--------|
| `/vycisti` | Clean up all category names into natural Czech. E.g. "krmivo pes levně" → "Levné krmivo pro psy" |
| `/intent` | Add search intent (Informační/Navigační/Komerční/Transakční) and funnel stage (TOFU/MOFU/BOFU) to each subcategory |
| `/clanek [Subcategory]` | Create detailed article outline for a subcategory: H1, structure, must-include phrases |

### Analysis tasks

1. **Naming** — Rewrite category names into natural, grammatically correct Czech
2. **Search Intent** — Classify each subcategory: Informační (blog), Navigační (brand), Komerční (comparison), Transakční (product/e-shop)
3. **Cannibalization** — Flag overlapping subcategories that should merge into one URL
4. **Content Plan** — On request, create copywriter briefs with H1, article structure, and target phrases

### Rules

- Be concise, use bullet points and tables
- Skip generic SEO theory — user is an expert
- Follow Topic Cluster model: Pillar Page → Cluster Content
- Always output tables, not walls of text

## Dependencies

```bash
pip3 install openai sentence-transformers scikit-learn torch pandas --break-system-packages
```

## Notes

- Embeddings are cached as `<input>_embeddings.npy` — delete to regenerate
- Uses OpenRouter API (`openrouter.ai/api/v1`) with model `openai/text-embedding-3-small`
- Typical cost: ~$0.01 per 1,000 keywords
- For large datasets (10k+), adjust `--sub-threshold` down to avoid too many tiny clusters
