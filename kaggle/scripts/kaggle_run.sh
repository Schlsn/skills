#!/usr/bin/env bash
# kaggle_run.sh — Full Kaggle workflow: upload dataset → push notebook → wait → download
#
# Usage:
#   bash scripts/kaggle_run.sh \
#     --file /path/to/data.csv \
#     --dataset-title "My Dataset" \
#     --notebook /path/to/notebook.ipynb \
#     --kernel-slug my-kernel \
#     --output-dir ./output/
#
# Optional:
#   --username adamschlesien    (default)
#   --token KGAT_...            (or set KAGGLE_API_TOKEN env var)
#   --no-gpu                    disable GPU
#   --update-dataset            add new version instead of creating

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="python3"

# ── Defaults ──────────────────────────────────────────────────────────────────
USERNAME="adamschlesien"
TOKEN="${KAGGLE_API_TOKEN:-}"
FILE=""
DATASET_TITLE=""
NOTEBOOK=""
KERNEL_SLUG=""
OUTPUT_DIR="./kaggle-output"
GPU_FLAG="--gpu"
UPDATE_FLAG=""

# ── Argument parsing ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --file)           FILE="$2";          shift 2 ;;
    --dataset-title)  DATASET_TITLE="$2"; shift 2 ;;
    --notebook)       NOTEBOOK="$2";      shift 2 ;;
    --kernel-slug)    KERNEL_SLUG="$2";   shift 2 ;;
    --output-dir)     OUTPUT_DIR="$2";    shift 2 ;;
    --username)       USERNAME="$2";      shift 2 ;;
    --token)          TOKEN="$2";         shift 2 ;;
    --no-gpu)         GPU_FLAG="--no-gpu"; shift ;;
    --update-dataset) UPDATE_FLAG="--update"; shift ;;
    *) echo "Unknown argument: $1"; exit 1 ;;
  esac
done

# ── Validation ────────────────────────────────────────────────────────────────
for var in FILE DATASET_TITLE NOTEBOOK KERNEL_SLUG; do
  [[ -z "${!var}" ]] && { echo "ERROR: --${var,,} is required (use underscores → hyphens)"; exit 1; }
done
[[ -z "$TOKEN" ]] && { echo "ERROR: --token or KAGGLE_API_TOKEN env var required"; exit 1; }
[[ ! -f "$FILE" ]]     && { echo "ERROR: File not found: $FILE"; exit 1; }
[[ ! -f "$NOTEBOOK" ]] && { echo "ERROR: Notebook not found: $NOTEBOOK"; exit 1; }

export KAGGLE_API_TOKEN="$TOKEN"

echo "═══════════════════════════════════════════════"
echo " Kaggle Full Workflow"
echo "═══════════════════════════════════════════════"
echo " File:     $FILE"
echo " Dataset:  $DATASET_TITLE"
echo " Notebook: $NOTEBOOK"
echo " Kernel:   $USERNAME/$KERNEL_SLUG"
echo " Output:   $OUTPUT_DIR"
echo "═══════════════════════════════════════════════"
echo ""

# ── Step 1: Upload dataset ────────────────────────────────────────────────────
echo "[1/2] Uploading dataset..."
$PYTHON "$SCRIPT_DIR/kaggle_upload_dataset.py" \
  --file "$FILE" \
  --title "$DATASET_TITLE" \
  --username "$USERNAME" \
  --token "$TOKEN" \
  $UPDATE_FLAG

# Derive dataset slug (same logic as Python slugify)
DATASET_SLUG=$(echo "$DATASET_TITLE" | tr '[:upper:]' '[:lower:]' | \
  sed 's/[^a-z0-9 -]//g' | sed 's/[ _]\+/-/g' | sed 's/-\+/-/g' | \
  sed 's/^-\|-$//g' | cut -c1-50)

echo ""
echo "[2/2] Pushing notebook and waiting for results..."
$PYTHON "$SCRIPT_DIR/kaggle_push_notebook.py" \
  --notebook "$NOTEBOOK" \
  --kernel-slug "$KERNEL_SLUG" \
  --dataset "$USERNAME/$DATASET_SLUG" \
  --output-dir "$OUTPUT_DIR" \
  --username "$USERNAME" \
  --token "$TOKEN" \
  $GPU_FLAG

echo ""
echo "═══════════════════════════════════════════════"
echo " Done! Results in: $OUTPUT_DIR"
ls -lh "$OUTPUT_DIR" 2>/dev/null || true
echo "═══════════════════════════════════════════════"
