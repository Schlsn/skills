---
name: kaggle
description: >
  Kaggle integration for data analysis workflows — upload private datasets, push and run notebooks on GPU/CPU, poll execution status, and download results. Use when you need compute power for heavy ML workloads (embeddings, clustering, training) that won't run locally. Triggers on: "run on kaggle", "kaggle notebook", "upload to kaggle", "kaggle GPU", "download kaggle results", "semantic clustering on kaggle", "kaggle dataset".
---

# Kaggle Skill

Spouštění výpočetně náročných analýz na Kaggle KKB (Kernel/Notebook Backend) — zdarma GPU (T4/P100), 20 GB RAM, 30h týdně. Vhodné pro embeddings, HDBSCAN clustering, trénink modelů.

---

## GPU — vždy používej T4

**Kaggle přiděluje GPU automaticky** (T4 nebo P100). T4 (sm_75) je preferovaná — P100 (sm_60) je starší a **nekompatibilní s novým PyTorch (cu121+)**.

**Řešení: vždy přeinstaluj PyTorch cu118 jako první buňku notebooku** — funguje na T4 i P100:

```python
import subprocess, sys

print('Instalace PyTorch cu118 (kompatibilní s T4 i P100)...')
subprocess.run([
    sys.executable, '-m', 'pip', 'install', '-q',
    'torch', 'torchvision', 'torchaudio',
    '--index-url', 'https://download.pytorch.org/whl/cu118',
], check=True)
print('OK')
```

Pak vždy nastav `device = 'cuda'`:
```python
import torch
device = 'cuda' if torch.cuda.is_available() else 'cpu'
print(f'GPU: {torch.cuda.get_device_name(0)} → {device}')
```

**kernel-metadata.json:** `"enable_gpu": "true"` — povolí GPU, ale typ určuje `--accelerator` při push.

**Výběr GPU při push:**
```bash
kaggle kernels push -p ./kernel-dir/ --accelerator NvidiaTeslaT4   # ← vždy toto
# Dostupné acceleratory (Feb 2026):
# NvidiaTeslaT4, NvidiaTeslaT4Highmem, NvidiaTeslaP100 (default, sm_60!),
# NvidiaTeslaA100, NvidiaL4, NvidiaH100, NvidiaRtxPro6000
# TpuV38, Tpu1VmV38, TpuV5E8, TpuV6E8
```
⚠️ **Vyžaduje kaggle CLI ≥ 2.0** (`pip install kaggle --upgrade`). Starší v1.7.x `--accelerator` nezná.

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

# Push notebook — VŽDY s --accelerator NvidiaTeslaT4
# Default je NvidiaTeslaP100 (sm_60, nekompatibilní s novým PyTorch!)
kaggle kernels push -p ./kernel-dir/ --accelerator NvidiaTeslaT4

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
| `FileNotFoundError: /kaggle/input/...` | Špatný dataset slug v cestě | Slug je lowercase s pomlčkami, bez username — viz auto-detect níže |
| `HTTP 400 Invalid argument` na blob upload | Chybí `"type": "DATASET"` | Přidat do POST body |
| `HTTP 404` na dataset create | Špatný endpoint | Použít `/api/v1/datasets/create/new` |
| `KernelWorkerStatus.ERROR` | Chyba v notebooku | `kaggle kernels output` → stáhni `.log` soubor |
| `401 Unauthorized` na CLI | Env var není nastavena | `export KAGGLE_API_TOKEN="KGAT_..."` |
| `No such option: --no-stem` (typer) | `typer.Option(False, "--stem")` nevytváří `--no-stem` | Příznak s `False` defaultem jednoduše vynech ze seznamu args |
| Kernel verze ignoruje fix | Kaggle může spustit starší verzi při souběhu | Počkej na dokončení běžící verze, pak pushni novou |
| P100: `UserWarning: sm_60 not compatible` + crash | Nový PyTorch (cu121+) nepodporuje P100 sm_60 | Přeinstaluj PyTorch cu118 (podporuje sm_60+) jako první buňku |
| Kaggle přidělil P100 místo T4 | GPU přidělení je automatické, nelze pevně nastavit | PyTorch cu118 funguje na obou — vždy ho instaluj |

### Auto-detect vstupního souboru (vždy přidat do notebooku)

Místo hardcoded cesty vždy použij auto-detect — zabrání `FileNotFoundError`:

```python
import os

DATASET_SLUG = 'pronatal-keywords-for-clustering'  # slug bez username
DATASET_DIR  = f'/kaggle/input/{DATASET_SLUG}'

if os.path.isdir(DATASET_DIR):
    csv_files  = [f for f in os.listdir(DATASET_DIR) if f.endswith('.csv')]
    INPUT_FILE = os.path.join(DATASET_DIR, csv_files[0])
else:
    # Fallback: hledej CSV v celém /kaggle/input/
    found = []
    for root, _, files in os.walk('/kaggle/input/'):
        for f in files:
            if f.endswith('.csv'):
                found.append(os.path.join(root, f))
    INPUT_FILE = found[0] if found else None

print(f'/kaggle/input/ obsah: {os.listdir("/kaggle/input/")}')
print(f'INPUT_FILE = {INPUT_FILE}')
```

---

## Příklady: Sémantické HDBSCAN clustering (Pronatal)

**Varianta 1 — vlastní notebook** (`pronatal-semantic-clustering`):
- Dataset: `adamschlesien/pronatal-keywords-for-clustering` (27,510 KW)
- GPU: Tesla P100, model: `all-MiniLM-L6-v2`
- Výstupy: `pronatal_clusters.csv` + `pronatal_clusters_chart.html`
- Výsledky: 13,639 clusterováno / 2,524 clusterů / 13,857 noise

**Varianta 2 — Lee Foot cluster-hdbscan.py** (`pronatal-lee-foot-hdbscan-clustering`):
- Skript: https://github.com/searchsolved/search-solved-public-seo/.../cluster-hdbscan.py
- CLI: `python cluster-hdbscan.py <file.csv> --device cuda --volume search_volume --chart-type sunburst --min-cluster-size 3 --output-path /kaggle/working/out`
- Výstup: `.xlsx` (2 sheety: PivotTable + Clustered Keywords) + `sunburst.html`
- ⚠️ Konverze na CSV potřeba: `pd.read_excel(xlsx, sheet_name='Clustered Keywords').to_csv(...)`
- ⚠️ `--stem` defaultuje na `False` — nepředávej `--no-stem`, typer ho nezná
