---
name: keyword-categorization
description: Hierarchical semantic clustering of keywords into Main Categories and Subcategories using local SBERT embeddings (all-MiniLM-L6-v2), UMAP dimensionality reduction, and Agglomerative Clustering or HDBSCAN. Includes SERP-based URL strategy clustering via Jaccard similarity. Use when the user wants to cluster, categorize, or organize keywords for SEO/content strategy.
---

# Keyword Categorization — Sémantická Clusterizace

Dvouúrovňová hierarchická clusterizace klíčových slov do témat a pilířů + rozhodnutí o URL strategii přes SERP data.

> **Kontext v keywords-analysis workflow:** Toto je **Fáze I** — clusterizace přichází AŽ PO čistění. Vstupem jsou pouze KWs s `is_relevant = true`. Model zde hledá skupiny KWs, které jsou si navzájem podobné (ne porovnání se seed keywords — to je fáze H).

---

## Pipeline přehled

```
CSV (keyword + search_volume)
        │
        ▼
[1] SBERT Embeddings          ← all-MiniLM-L6-v2 (lokální, 384 dim)
        │
        ▼
[2] UMAP redukce              ← 384 dim → 5–10 dim
        │
        ▼
[3] Clustering                ← Agglomerative (doporučeno) nebo HDBSCAN
        │
        ▼
[4] Centroid detection        ← reprezentativní KW pro každý cluster
        │
        ▼
[5] SERP Jaccard Clustering   ← rozhodnutí: vlastní URL vs. pilíř
        │
        ▼
CSV výstup s kategoriemi + URL strategií
```

---

## Quick Start

```bash
# Základní použití
python3 scripts/cluster_keywords.py keywords.csv

# S explicitními thresholdy
python3 scripts/cluster_keywords.py keywords.csv \
  --sub-threshold 0.45 --main-threshold 0.30

# S HDBSCAN místo Agglomerative
python3 scripts/cluster_keywords.py keywords.csv --method hdbscan

# Se SERP clustering (vyžaduje SERP data v DB)
python3 scripts/cluster_keywords.py keywords.csv --serp-clustering \
  --db-schema pronatal
```

---

## Input CSV formát

Musí obsahovat (case-insensitive):
- **Keyword** (nebo `Keywords`, `Query`)
- **Search_Volume** (nebo `Volume`, `Search Volume`, `SV`)

```csv
Keyword,Search_Volume
ivf,12100
umělé oplodnění,8100
icsi metoda,1900
```

---

## Output CSV

Separátor `;`, sloupce:

```
Keyword ; Search_Volume ; Main_Category ; Subcategory ; Centroid_KW ; SERP_Cluster_ID ; URL_Strategy
ivf ; 12100 ; IVF & Asistovaná reprodukce ; IVF procedura ; ivf ; 1 ; pillar_page
```

| Sloupec | Popis |
|---------|-------|
| `Main_Category` | Nadřazené téma (pilíř) |
| `Subcategory` | Podtéma |
| `Centroid_KW` | KW nejblíže středu clusteru — doporučený název |
| `SERP_Cluster_ID` | KWs se stejným SERP_Cluster_ID sdílejí stejné URL |
| `URL_Strategy` | `pillar_page` / `cluster_page` / `merge_to_pillar` |

---

## Detailní popis kroků

### Krok 1 — SBERT Embeddings

Model: **`all-MiniLM-L6-v2`** (lokální, žádné API náklady, ~80 MB)

- Každé KW → 384-dimenzionální numerický vektor
- Zachytí sémantický význam (ne jen slovní podobnost)
- Cache jako `<input>_embeddings.npy` — smaž pro regeneraci

```python
from sentence_transformers import SentenceTransformer
model = SentenceTransformer('all-MiniLM-L6-v2')
embeddings = model.encode(keywords, show_progress_bar=True)
```

### Krok 2 — UMAP redukce dimenzionality

Problém: 384-dimenzionální prostor je příliš hustý pro přesné clustering algoritmy.
Řešení: UMAP komprimuje data do 5–10 dimenzí, zachovává lokální strukturu.

```python
import umap
reducer = umap.UMAP(
    n_neighbors=15,
    n_components=5,        # cíl: 5–10 dimenzí
    metric='cosine',
    random_state=42
)
embeddings_reduced = reducer.fit_transform(embeddings)
```

Parametry pro ladění:
- `n_neighbors`: vyšší = zachovává globální strukturu; nižší = zachovává lokální detaily
- `n_components`: vyšší = více informací, ale pomalejší clustering

### Krok 3 — Clusterizace

#### Varianta A — Agglomerative Clustering (doporučeno)

Vytváří přísnou hierarchickou taxonomii webu. Používá cosine similarity threshold.

```python
from sklearn.cluster import AgglomerativeClustering

# Subkategorie — přísný threshold (těsnější shluky)
sub_clustering = AgglomerativeClustering(
    n_clusters=None,
    distance_threshold=0.55,   # ≈ 1 - cosine_similarity_threshold_0.45
    metric='cosine',
    linkage='average'
)
sub_labels = sub_clustering.fit_predict(embeddings_reduced)

# Hlavní kategorie — volnější threshold (širší skupiny)
main_clustering = AgglomerativeClustering(
    n_clusters=None,
    distance_threshold=0.70,   # ≈ 1 - cosine_similarity_threshold_0.30
    metric='cosine',
    linkage='average'
)
main_labels = main_clustering.fit_predict(embeddings_reduced)
```

Parametry pro ladění:
- `distance_threshold` pro subcategories: `0.45–0.55` (vyšší = více menších clusterů)
- `distance_threshold` pro main categories: `0.25–0.40` (vyšší = více pilířů)

#### Varianta B — HDBSCAN (pro velké datasety nebo šumy)

Automaticky detekuje počet clusterů. Outliers (KWs co nikam nepatří) dostají label `-1`.

```python
import hdbscan
clusterer = hdbscan.HDBSCAN(
    min_cluster_size=10,       # min. počet KWs ve shluku
    min_samples=5,             # přísnost — vyšší = více outlierů
    metric='euclidean',        # po UMAP redukci
    cluster_selection_method='eom'
)
labels = clusterer.fit_predict(embeddings_reduced)
```

Parametry pro ladění:
- `min_cluster_size`: vyšší = větší, obecnější clustery; nižší = granulární témata
- Outliers (label `-1`) zkontroluj ručně — mohou být cenná long-tail KWs

### Krok 4 — Centroid detection

Každý cluster → průměrný vektor → KW nejblíže středu = reprezentativní název.

```python
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

def find_centroid_keyword(cluster_embeddings, cluster_keywords):
    centroid = np.mean(cluster_embeddings, axis=0)
    similarities = cosine_similarity([centroid], cluster_embeddings)[0]
    return cluster_keywords[np.argmax(similarities)]
```

Centroid KW slouží jako automatický název subcategory (před SEO čistěním).

### Krok 5 — SERP Clustering (Jaccard Similarity)

**Účel:** Rozhodnout zda podtopic zaslouží vlastní URL nebo by se měl sloučit do pilíře.

**Princip:** KWs sdílející stejné top 10 organic URLs → stejný search intent → stejná URL.

```python
def jaccard_similarity(set_a, set_b):
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0

# Načtení top 10 URLs pro každé KW z DB
# SELECT keyword, array_agg(url ORDER BY position) as urls
# FROM seo_kws.serp_organic WHERE job_id = X AND position <= 10
# GROUP BY keyword;

# Matice podobností
for kw_a, kw_b in keyword_pairs:
    urls_a = set(serp_data[kw_a])
    urls_b = set(serp_data[kw_b])
    similarity = jaccard_similarity(urls_a, urls_b)

    if similarity >= 0.3:   # > 30% překryv URL
        # Stejná URL → sloučit do pilíře
        assign_same_serp_cluster(kw_a, kw_b)
```

**URL strategie:**
- `SERP Jaccard ≥ 0.3` → `merge_to_pillar` (stejná URL)
- `SERP Jaccard < 0.3` → `cluster_page` (vlastní URL)
- Hlavní kategorie → `pillar_page`

---

## Parametry

| Parametr | Výchozí | Popis |
|----------|---------|-------|
| `input` | required | Input CSV |
| `-o` / `--output` | `<input>_clustered.csv` | Output CSV |
| `--sub-threshold` | `0.45` | Cosine similarity pro subcategories (vyšší = těsnější shluky) |
| `--main-threshold` | `0.30` | Cosine similarity pro main categories (nižší = širší skupiny) |
| `--method` | `agglomerative` | `agglomerative` nebo `hdbscan` |
| `--umap-components` | `5` | Počet dimenzí po UMAP redukci |
| `--min-cluster-size` | `10` | Min. velikost clusteru (HDBSCAN) |
| `--serp-clustering` | `false` | Zapnout SERP Jaccard clustering |
| `--db-schema` | — | PostgreSQL schéma klienta (pro SERP data) |
| `--serp-threshold` | `0.3` | Jaccard threshold pro sloučení do pilíře |
| `--sep` | `,` | Separátor input CSV |

---

## SEO Analýza po clusterizaci

Po clusterizaci analyzuj výstup jako expert SEO analytik:

### Triggers

| Příkaz | Akce |
|--------|------|
| `/intent` | Přidej search intent (Informační/Navigační/Komerční/Transakční) a funnel fázi (TOFU/MOFU/BOFU) ke každé subcategory |
| `/clanek [Subcategory]` | Vytvoř detailní outline článku: H1, struktura, povinné fráze |
| `/kannibalizace` | Identifikuj subcategories, které by měly sdílet jednu URL |

### Úkoly analýzy

1. **Naming** — přejmenuj kategorie z centroid KW na přirozené české/anglické názvy
2. **Search Intent** — klasifikuj každou subcategory
3. **Kannibalizace** — flaguj subcategories vhodné ke sloučení
4. **Content Plan** — na vyžádání vytvoř copywriter briefy

---

## Dependencies

```bash
pip install sentence-transformers umap-learn scikit-learn hdbscan pandas numpy
```

> ⚠️ Pro velké datasety (10k+ KWs) doporučujeme Google Colab s GPU pro SBERT krok.

---

## Notes

- Embeddings jsou cachované jako `<input>_embeddings.npy` — smaž pro regeneraci
- Model `all-MiniLM-L6-v2` je vícejazyčný (CZ, EN, DE, SK, PL…)
- UMAP je stochastický — nastav `random_state=42` pro reprodukovatelnost
- Pro datasety < 500 KWs: UMAP n_components=3 je dostatečné
- SERP clustering vyžaduje předem stažená SERP data (Fáze F v keywords-analysis workflow)
