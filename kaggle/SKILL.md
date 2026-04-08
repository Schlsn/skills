---
name: kaggle
description: >
  Kaggle integration for data analysis workflows — upload private datasets, push and run notebooks on GPU/CPU, poll execution status, and download results. Use when you need compute power for heavy ML workloads (embeddings, clustering, training) that won't run locally. Triggers on: "run on kaggle", "kaggle notebook", "upload to kaggle", "kaggle GPU", "download kaggle results", "semantic clustering on kaggle", "kaggle dataset".
---

# Kaggle Skill

Spouštění výpočetně náročných analýz na Kaggle KKB (Kernel/Notebook Backend) — zdarma GPU (T4/P100), 20 GB RAM, 30h týdně. Vhodné pro embeddings, HDBSCAN clustering, trénink modelů.

---

## Credentials

Token uložen v `~/.kaggle/kaggle.json`:
```json
{"username": "adamschlesien", "key": "KGAT_ace4cd1d3f2180478e5d9a064d448f40"}
```

**Auth metody (podle priority):**
1. `KAGGLE_API_TOKEN` env var — nový formát, preferovaný pro CLI
2. `~/.kaggle/kaggle.json` — funguje pro většinu operací

**Důležité poznatky o KGAT_ tokenech:**
- REST API: `Authorization: Bearer KGAT_...` — funguje pro blob upload, dataset create
- kaggle CLI: `export KAGGLE_API_TOKEN="KGAT_..."` → `kaggle kernels push/status/output`
- Blob upload **vyžaduje** `"type": "DATASET"` v payload (jinak HTTP 400)
- Dataset creation endpoint: `POST /api/v1/datasets/create/new` (ne `/api/v1/datasets`)
- Dataset cesta v notebooku: `/kaggle/input/<dataset-slug>/` — slug se liší od názvu!

---

## Workflow

```
Lokální data (CSV/soubory)
        │
        ▼
[1] Upload dataset          ← scripts/kaggle_upload_dataset.py
        │                      Blob → GCS → POST /api/v1/datasets/create/new
        ▼
[2] Push notebook           ← kaggle kernels push -p ./kernel-dir/
        │                      s kernel-metadata.json (dataset_sources, enable_gpu)
        ▼
[3] Poll status             ← kaggle kernels status username/kernel-slug
        │                      RUNNING → COMPLETE / ERROR
        ▼
[4] Download výsledků       ← kaggle kernels output username/kernel-slug --path ./out/
        │
        ▼
Výsledky (CSV, HTML, modely...)
```

---

## Scripts

### `scripts/kaggle_upload_dataset.py` — Upload souboru jako private dataset

```bash
python3 scripts/kaggle_upload_dataset.py \
  --file /path/to/data.csv \
  --title "My Dataset Title" \
  --username adamschlesien \
  --token KGAT_ace4cd1d3f2180478e5d9a064d448f40
```

Výstup: `Dataset slug: adamschlesien/my-dataset-title`

### `scripts/kaggle_push_notebook.py` — Push + run + download (full workflow)

```bash
python3 scripts/kaggle_push_notebook.py \
  --notebook /path/to/notebook.ipynb \
  --kernel-slug my-kernel-slug \
  --dataset adamschlesien/my-dataset-title \
  --output-dir ./output/ \
  --username adamschlesien \
  --token KGAT_ace4cd1d3f2180478e5d9a064d448f40 \
  [--gpu] [--internet]
```

Automaticky:
1. Vytvoří `kernel-metadata.json`
2. Pushne notebook
3. Polluje status každých 30s
4. Stáhne výsledky do `--output-dir`

---

## Ruční kroky (kaggle CLI)

```bash
export KAGGLE_API_TOKEN="KGAT_ace4cd1d3f2180478e5d9a064d448f40"

# Push notebook z připravené složky
kaggle kernels push -p ./kernel-dir/

# Sledování stavu
kaggle kernels status adamschlesien/kernel-slug

# Stažení výsledků
kaggle kernels output adamschlesien/kernel-slug --path ./output/

# Seznam datasetů
kaggle datasets list --mine

# Nová verze datasetu
kaggle datasets version -p ./dataset-dir/ -m "Update v2"
```

---

## kernel-metadata.json — povinná struktura

```json
{
  "id": "adamschlesien/kernel-slug",
  "title": "Kernel Title",
  "code_file": "notebook.ipynb",
  "language": "python",
  "kernel_type": "notebook",
  "is_private": "true",
  "enable_gpu": "true",
  "enable_tpu": "false",
  "enable_internet": "true",
  "dataset_sources": ["adamschlesien/dataset-slug"],
  "competition_sources": [],
  "kernel_sources": [],
  "model_sources": []
}
```

**Pozor:** `dataset_sources` musí obsahovat slug ve formátu `username/slug` (lowercase, pomlčky).
Cesta v notebooku: `/kaggle/input/<slug-bez-username>/soubor.csv`

---

## Notebook: přístup k datům

Dataset `adamschlesien/pronatal-keywords-for-clustering` je dostupný jako:
```python
INPUT_FILE = '/kaggle/input/pronatal-keywords-for-clustering/pronatal_kws_for_clustering.csv'
```

Obecně: `/kaggle/input/<dataset-slug-bez-username>/<filename>`

---

## Free tier limity

| Resource | Limit |
|----------|-------|
| GPU (T4/P100) | 30h / týden |
| RAM | 20 GB |
| Disk | 20 GB |
| Session timeout | 9h nečinnosti |
| Soukromé datasety | neomezeno |
| Soukromé notebooky | neomezeno |

---

## Časté chyby

| Chyba | Příčina | Řešení |
|-------|---------|--------|
| `FileNotFoundError: /kaggle/input/...` | Špatný dataset slug v cestě | Slug je lowercase s pomlčkami, bez username |
| `HTTP 400 Invalid argument` na blob upload | Chybí `"type": "DATASET"` | Přidat do POST body |
| `HTTP 404` na dataset create | Špatný endpoint | Použít `/api/v1/datasets/create/new` |
| `KernelWorkerStatus.ERROR` | Chyba v notebooku | `kaggle kernels output` → stáhni `.log` soubor |
| `401 Unauthorized` na CLI | Env var není nastavena | `export KAGGLE_API_TOKEN="KGAT_..."` |

---

## Příklad: Sémantické HDBSCAN clustering

Notebook `pronatal_semantic_clustering.ipynb` běžel na P100 GPU:
- Dataset: `adamschlesien/pronatal-keywords-for-clustering` (27,510 KW)
- Kernel: `adamschlesien/pronatal-semantic-clustering`
- Model: `all-MiniLM-L6-v2`, clustering: HDBSCAN
- Výstupy: `pronatal_clusters.csv` + `pronatal_clusters_chart.html`
