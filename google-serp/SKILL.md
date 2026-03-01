---
name: google-serp
description: Scrape Google Search results using local Playwright (headless=False Chromium). Returns organic results, People Also Ask, and Related Searches as formatted tables and CSV files. Use when the user asks to scrape Google, get SERP results, check rankings, or analyze search results for any keyword.
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
from google_serp import scrape, print_results, save_csv

data = scrape("pronatal", lang="cs", country="cz", num=10)
print_results(data, "pronatal")
save_csv(data, "pronatal", "~/google_serp_outputs")
```

Or directly from CLI:
```bash
python3 scripts/google_serp.py "pronatal"
python3 scripts/google_serp.py "coffee prague" --lang en --country cz
python3 scripts/google_serp.py "seo tools" --lang en --country us --num 20
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

## Using from Claude

When user asks to scrape Google for a keyword, use the Bash tool to run:

```bash
python3 scripts/google_serp.py "<query>" --lang <lang> --country <country>
```

Then display the output tables to the user.

**Default for Czech Google:** `--lang cs --country cz`
**For English Google US:** `--lang en --country com`
**For German Google:** `--lang de --country de`

## Notes

- Uses `headless=True` Chromium — runs invisibly in the background
- **Anti-detection**: human-like mouse movements with Bézier easing, random jitter (±2.5px), and randomized delays (10–60ms) to minimize CAPTCHA risk
- Handles cookie consent banners automatically (all languages)
- Related searches detection is language-agnostic (structural URL analysis, not text matching)
- CAPTCHA may occur on datacenter IPs — works best on residential/home IPs
- Playwright must be installed: `pip3 install playwright --break-system-packages && python3 -m playwright install chromium`
