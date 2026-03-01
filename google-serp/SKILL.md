---
name: google-serp
description: Scrape Google Search results using local Playwright (headless Chromium). Returns organic results, People Also Ask, and Related Searches as formatted tables and CSV files. Use when the user asks to scrape Google, get SERP results, check rankings, or analyze search results for any keyword.
---

# Google SERP Scraper

Scrapes live Google Search results using local Playwright Chromium. No API key required.
Works across all Google country/language variants.

## Script location
`scripts/google_serp.py` (relative to this skill directory)

## Quick start

```python
import sys, os
skill_dir = os.path.dirname(os.path.abspath(__file__))  # or resolve from SKILL.md location
sys.path.insert(0, os.path.join(skill_dir, 'scripts'))
from google_serp import scrape, scrape_with_pause, print_results, save_csv

# Single query
data = scrape("pronatal", lang="cs", country="cz", num=10)
print_results(data, "pronatal")

# Batch — MUST use scrape_with_pause (8-15s random wait before each request)
for kw in ["ivf", "icsi", "fertility clinic"]:
    data = scrape_with_pause(kw, lang="cs", country="cz")
    print_results(data, kw)
```

Or directly from CLI:
```bash
python3 scripts/google_serp.py "pronatal"
python3 scripts/google_serp.py "coffee prague" --lang en --country cz
python3 scripts/google_serp.py "seo tools" --lang en --country us --num 20
```

## ⚠️ Mandatory pause between calls

**When scraping multiple keywords, you MUST wait at least 8–15 seconds between requests.**
Use `scrape_with_pause()` (Python) or `sleep` (CLI). Failure to pause will trigger Google CAPTCHA.

```bash
# CLI batch example:
for kw in "ivf" "icsi" "embryo"; do
  python3 scripts/google_serp.py "$kw" --no-csv
  sleep $(( RANDOM % 8 + 8 ))
done
```

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `query`   | required | Search query |
| `--lang`  | `cs`    | Language code (cs, en, de, fr, ...) |
| `--country` | `cz`  | Google TLD / country (cz, com, de, co.uk, ...) |
| `--num`   | `10`    | Number of results (max ~100) |
| `--output` | `~/google_serp_outputs` | CSV output directory |
| `--no-csv` | false  | Print tables only, skip CSV |
| `--json`  | false   | Also print raw JSON |

## Output

Three tables printed to stdout + three CSV files saved:

1. **Organic results** — position, title, description, URL
2. **People Also Ask** — position, question
3. **Related Searches** — position, query

CSV files named: `serp_organic_<query>_<timestamp>.csv` etc.

## Anti-detection features

- **Randomized User-Agent** — pool of 8 real browser UAs (Chrome/Firefox/Safari/Edge, Mac/Win)
- **Randomized viewport** — 6 common desktop resolutions (1920×1080 down to 1280×720)
- **Human-like search flow** — visits Google homepage first, types query character-by-character
- **Bézier mouse movements** — smooth cursor paths with ±2.5px jitter + 10–60ms random delays
- **playwright-stealth** — patches navigator.webdriver and other browser fingerprint leaks
- **Extra Chromium args** — disables automation flags, extensions, first-run dialogs

## Notes

- Uses `headless=True` Chromium — runs invisibly in the background
- Handles cookie consent banners automatically (all languages)
- Related searches detection is language-agnostic (structural URL analysis)
- CAPTCHA may occur on datacenter IPs — works best on residential/home IPs
- Playwright must be installed: `pip3 install playwright playwright-stealth --break-system-packages && python3 -m playwright install chromium`
