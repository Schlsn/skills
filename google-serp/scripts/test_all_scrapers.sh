#!/bin/bash
# ===========================================================================
# test_all_scrapers.sh — Otestuje všechny SERP scrapery na Hetzner serveru
#
# Použití:
#   chmod +x test_all_scrapers.sh
#   ./test_all_scrapers.sh
#
# Spouštět z: /opt/n8n-stack/scripts/
# ===========================================================================

set -e

SCRIPT_DIR="/opt/n8n-stack/scripts"
OUTPUT_DIR="/tmp/serp_test_$(date +%Y%m%d_%H%M%S)"
QUERY="ivf clinic prague"     # Testovací dotaz (anglicky, mezinárodní)
QUERY_CZ="klinika ivf praha"  # Testovací dotaz (česky)

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

mkdir -p "$OUTPUT_DIR"

echo "============================================================"
echo "  SERP Scraper Test Suite"
echo "  $(date)"
echo "  Output dir: $OUTPUT_DIR"
echo "============================================================"
echo ""

PASS=0
FAIL=0
SKIP=0

run_test() {
    local name="$1"
    local cmd="$2"
    local description="$3"

    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${YELLOW}▶ TEST: $name${NC}"
    echo -e "  $description"
    echo -e "  CMD: $cmd"
    echo ""

    local logfile="$OUTPUT_DIR/${name}.log"
    local jsonfile="$OUTPUT_DIR/${name}.json"

    if eval "$cmd" > "$logfile" 2>&1; then
        # Zkontroluj, jestli jsou výsledky v JSON
        if [ -f "$jsonfile" ] && python3 -c "
import json, sys
data = json.load(open('$jsonfile'))
n = len(data.get('organic', []))
if n == 0:
    print(f'  ⚠️  0 organic results')
    sys.exit(1)
print(f'  ✅ {n} organic results')
" 2>/dev/null; then
            echo -e "${GREEN}  ✅ PASS — $name${NC}"
            PASS=$((PASS + 1))
        else
            echo -e "${YELLOW}  ⚠️  WARN — scraper ran but 0 organic results (check $logfile)${NC}"
            FAIL=$((FAIL + 1))
        fi
    else
        echo -e "${RED}  ❌ FAIL — $name (exit $?)${NC}"
        echo "  Poslední řádky logu:"
        tail -5 "$logfile" 2>/dev/null | sed 's/^/    /'
        FAIL=$((FAIL + 1))
    fi
    echo ""
}

# ─────────────────────────────────────────────────────────────────────────────
# Test 1: Google SERP v4 (single profile, Czech)
# ─────────────────────────────────────────────────────────────────────────────
run_test "google_cz" \
    "cd $SCRIPT_DIR && python3 google_serp_v4.py '$QUERY_CZ' --lang cs --country cz --json --no-csv > $OUTPUT_DIR/google_cz.json 2>&1" \
    "Google SERP v4 — Czech query, single profile"

# ─────────────────────────────────────────────────────────────────────────────
# Test 2: Google SERP v4 (English, single profile)
# ─────────────────────────────────────────────────────────────────────────────
run_test "google_en" \
    "cd $SCRIPT_DIR && python3 google_serp_v4.py '$QUERY' --lang en --country com --json --no-csv > $OUTPUT_DIR/google_en.json 2>&1" \
    "Google SERP v4 — English query (google.com)"

# ─────────────────────────────────────────────────────────────────────────────
# Test 3: DuckDuckGo SERP (JS mode, Czech)
# ─────────────────────────────────────────────────────────────────────────────
run_test "ddg_js_cz" \
    "cd $SCRIPT_DIR && python3 duckduckgo_serp.py '$QUERY_CZ' --kl cz-cs --json --no-csv > $OUTPUT_DIR/ddg_js_cz.json 2>&1" \
    "DuckDuckGo — JS mode, Czech locale"

# ─────────────────────────────────────────────────────────────────────────────
# Test 4: DuckDuckGo SERP (HTML lite mode)
# ─────────────────────────────────────────────────────────────────────────────
run_test "ddg_html" \
    "cd $SCRIPT_DIR && python3 duckduckgo_serp.py '$QUERY' --kl us-en --html-mode --json --no-csv > $OUTPUT_DIR/ddg_html.json 2>&1" \
    "DuckDuckGo — HTML lite mode, US English"

# ─────────────────────────────────────────────────────────────────────────────
# Test 5: Bing SERP (Czech)
# ─────────────────────────────────────────────────────────────────────────────
run_test "bing_cz" \
    "cd $SCRIPT_DIR && python3 bing_serp.py '$QUERY_CZ' --mkt cs-CZ --json --no-csv > $OUTPUT_DIR/bing_cz.json 2>&1" \
    "Bing — Czech market (cs-CZ)"

# ─────────────────────────────────────────────────────────────────────────────
# Test 6: Bing SERP (English, 20 results)
# ─────────────────────────────────────────────────────────────────────────────
run_test "bing_en" \
    "cd $SCRIPT_DIR && python3 bing_serp.py '$QUERY' --mkt en-US --num 20 --json --no-csv > $OUTPUT_DIR/bing_en.json 2>&1" \
    "Bing — US English, 20 results"

# ─────────────────────────────────────────────────────────────────────────────
# Test 7: Brave SERP (Czech)
# ─────────────────────────────────────────────────────────────────────────────
run_test "brave_cz" \
    "cd $SCRIPT_DIR && python3 brave_serp.py '$QUERY_CZ' --country cz --lang cs --json --no-csv > $OUTPUT_DIR/brave_cz.json 2>&1" \
    "Brave Search — Czech (country=cz, lang=cs)"

# ─────────────────────────────────────────────────────────────────────────────
# Test 8: Brave SERP (English, 15 results)
# ─────────────────────────────────────────────────────────────────────────────
run_test "brave_en" \
    "cd $SCRIPT_DIR && python3 brave_serp.py '$QUERY' --country us --lang en --num 15 --json --no-csv > $OUTPUT_DIR/brave_en.json 2>&1" \
    "Brave Search — US English, 15 results"

# ─────────────────────────────────────────────────────────────────────────────
# Test 9: api_runner.py (pokud existuje)
# ─────────────────────────────────────────────────────────────────────────────
if [ -f "$SCRIPT_DIR/api_runner.py" ]; then
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${YELLOW}▶ INFO: api_runner.py nalezen${NC}"
    echo "  Zobrazuji help:"
    python3 "$SCRIPT_DIR/api_runner.py" --help 2>&1 | head -20 | sed 's/^/    /'
    echo ""
else
    echo -e "${YELLOW}  ⏭️  api_runner.py nenalezen v $SCRIPT_DIR${NC}"
fi

# ─────────────────────────────────────────────────────────────────────────────
# Test 10: scrape_google_reviews.py (pokud existuje)
# ─────────────────────────────────────────────────────────────────────────────
if [ -f "$SCRIPT_DIR/scrape_google_reviews.py" ]; then
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${YELLOW}▶ INFO: scrape_google_reviews.py nalezen${NC}"
    echo "  Zobrazuji help:"
    python3 "$SCRIPT_DIR/scrape_google_reviews.py" --help 2>&1 | head -20 | sed 's/^/    /'
    echo ""
else
    echo -e "${YELLOW}  ⏭️  scrape_google_reviews.py nenalezen v $SCRIPT_DIR${NC}"
fi

# ─────────────────────────────────────────────────────────────────────────────
# SOUHRN
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "============================================================"
echo "  SOUHRN"
echo "============================================================"
echo -e "  ${GREEN}✅ PASS: $PASS${NC}"
echo -e "  ${RED}❌ FAIL: $FAIL${NC}"
echo ""
echo "  JSON výstupy: $OUTPUT_DIR/"
echo "  Logy:         $OUTPUT_DIR/*.log"
echo ""

# ── Zobraz počty organic results ze všech JSON ──
echo "  Přehled organic výsledků:"
for f in "$OUTPUT_DIR"/*.json; do
    [ -f "$f" ] || continue
    name=$(basename "$f" .json)
    count=$(python3 -c "
import json
try:
    data = json.load(open('$f'))
    print(len(data.get('organic', [])))
except:
    print('ERR')
" 2>/dev/null)
    printf "    %-20s  organic=%s\n" "$name" "$count"
done

echo ""
echo "============================================================"

if [ $FAIL -gt 0 ]; then
    exit 1
fi
