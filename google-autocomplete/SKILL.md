---
name: google-autocomplete
description: Use when the user wants to discover keyword variations, long-tail terms, or user intent signals via Google Autocomplete / Google Suggest. Triggers include "google suggest", "autocomplete keywords", "keyword expansion", "suggest scraper", "autocomplete analysis", "klíčová slova autocomplete", "návrhy google", or any request to fetch autocomplete suggestions for a base keyword. Generates alphabet variants (keyword + a/b/c…), question-prefix variants (jak, proč, kdy / how, why, when…), and deduplicates all results. No API key required.
---

# Google Autocomplete — Keyword Suggestion Scraper

Discover keyword variations and user intent signals by systematically querying Google Autocomplete. For a given base keyword the script generates:

1. **Alphabet expansion** — `pronatal a`, `pronatal b` … `pronatal z`
2. **Question prefixes** — `jak pronatal`, `proč pronatal`, `kdy pronatal` (Czech) + `how pronatal`, `why pronatal`, `when pronatal` (English) — extensible to any language
3. **Base keyword alone** — bare query to capture direct suggestions

All results are deduplicated and sorted alphabetically.

---

## How It Works

- Uses the unofficial `suggestqueries.google.com/complete/search` endpoint with `client=chrome` (returns JSON)
- Rotates User-Agent headers on every request to reduce fingerprinting
- Adds random delay (default 1.5–3.5 s) between requests to avoid rate limiting
- Handles HTTP 429 with an automatic 30 s back-off
- Language and country are configurable via `HL` / `GL` parameters
- Saves results to a `.txt` file alongside printing them

---

## Prerequisites

```bash
pip install requests
```

---

## Full Script

```python
import requests
import time
import random
import json
import string

# ─── CONFIGURATION ────────────────────────────────────────────────────────────
BASE_KW   = "pronatal"   # ← change to your base keyword
HL        = "cs"         # host language: cs, en, de, sk, pl, fr, es, it, hu …
GL        = "CZ"         # country code:  CZ, US, DE, AT, SK, PL, GB, FR …
MIN_DELAY = 1.5          # minimum seconds between requests
MAX_DELAY = 3.5          # maximum seconds between requests
# ──────────────────────────────────────────────────────────────────────────────

# Question prefixes per language — add more languages as needed
QUESTION_PREFIXES: dict[str, list[str]] = {
    "cs": ["jak", "proč", "kdy", "co je", "kde", "pro koho", "kdo", "cena", "zkušenosti", "recenze", "jak dlouho", "co obsahuje"],
    "en": ["how", "why", "when", "what is", "where", "who", "best", "review", "price", "vs", "how long", "side effects"],
    "de": ["wie", "warum", "wann", "was ist", "wo", "wer", "preis", "erfahrungen", "nebenwirkungen"],
    "sk": ["ako", "prečo", "kedy", "čo je", "kde", "kto", "cena", "skúsenosti"],
    "pl": ["jak", "dlaczego", "kiedy", "co to", "gdzie", "kto", "cena", "opinie"],
    "fr": ["comment", "pourquoi", "quand", "qu'est-ce que", "où", "qui", "prix", "avis"],
    "es": ["cómo", "por qué", "cuándo", "qué es", "dónde", "quién", "precio", "opiniones"],
    "it": ["come", "perché", "quando", "cos'è", "dove", "chi", "prezzo", "recensioni"],
    "hu": ["hogyan", "miért", "mikor", "mi az", "hol", "ki", "ár", "vélemények"],
    "nl": ["hoe", "waarom", "wanneer", "wat is", "waar", "wie", "prijs", "ervaringen"],
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]


def _headers() -> dict[str, str]:
    return {
        "User-Agent":      random.choice(USER_AGENTS),
        "Accept":          "application/json, text/plain, */*",
        "Accept-Language": f"{HL},{HL}-{GL};q=0.9,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer":         "https://www.google.com/",
        "DNT":             "1",
        "Connection":      "keep-alive",
    }


def fetch_suggestions(query: str, session: requests.Session) -> list[str]:
    url = "https://suggestqueries.google.com/complete/search"
    params = {"client": "chrome", "q": query, "hl": HL, "gl": GL}
    try:
        r = session.get(url, params=params, headers=_headers(), timeout=10)
        if r.status_code == 200:
            data = json.loads(r.text)
            return data[1] if len(data) > 1 else []
        elif r.status_code == 429:
            print("  [RATE LIMITED] Backing off 30 s …")
            time.sleep(30)
            # one retry after back-off
            r2 = session.get(url, params=params, headers=_headers(), timeout=10)
            if r2.status_code == 200:
                data = json.loads(r2.text)
                return data[1] if len(data) > 1 else []
        else:
            print(f"  [HTTP {r.status_code}] skipping: {query!r}")
    except Exception as e:
        print(f"  [ERROR] {e} — skipping: {query!r}")
    return []


def build_queries(base_kw: str) -> list[str]:
    queries: list[str] = []

    # 0. Base keyword
    queries.append(base_kw)

    # 1. Alphabet expansion
    for letter in string.ascii_lowercase:
        queries.append(f"{base_kw} {letter}")

    # 2. Question prefixes for the selected language + English (always included)
    prefixes = list(QUESTION_PREFIXES.get(HL, []))
    if HL != "en":
        prefixes += QUESTION_PREFIXES.get("en", [])
    # Deduplicate prefixes while preserving order
    seen: set[str] = set()
    unique_prefixes: list[str] = []
    for p in prefixes:
        if p not in seen:
            seen.add(p)
            unique_prefixes.append(p)

    for prefix in unique_prefixes:
        queries.append(f"{prefix} {base_kw}")

    return queries


def collect_suggestions(base_kw: str) -> list[str]:
    session   = requests.Session()
    all_lower: set[str] = set()   # for deduplication
    all_orig:  dict[str, str] = {}  # lower → original casing

    queries = build_queries(base_kw)
    total   = len(queries)
    print(f"\nBase keyword : '{base_kw}'")
    print(f"Language     : {HL}  |  Country: {GL}")
    print(f"Queries      : {total}")
    print("─" * 50)

    for i, query in enumerate(queries, 1):
        suggestions = fetch_suggestions(query, session)
        new = 0
        for s in suggestions:
            key = s.lower().strip()
            if key not in all_lower:
                all_lower.add(key)
                all_orig[key] = s.strip()
                new += 1
        print(f"[{i:>3}/{total}] {query:<45}  → {len(suggestions)} suggestions, {new} new")

        if i < total:
            time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))

    # Return deduplicated list sorted alphabetically (original casing)
    return sorted(all_orig.values(), key=str.lower)


def print_results(base_kw: str, suggestions: list[str]) -> None:
    print(f"\n{'='*60}")
    print(f"  Autocomplete analysis: '{base_kw}'")
    print(f"  Language: {HL}  |  Country: {GL}")
    print(f"  Unique suggestions: {len(suggestions)}")
    print(f"{'='*60}")
    for i, s in enumerate(suggestions, 1):
        print(f"  {i:>3}. {s}")
    print()


def save_results(base_kw: str, suggestions: list[str]) -> str:
    filename = f"suggestions_{base_kw.replace(' ', '_')}_{HL}_{GL}.txt"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"# Google Autocomplete: {base_kw} | {HL} | {GL}\n")
        f.write(f"# Total unique suggestions: {len(suggestions)}\n\n")
        for s in suggestions:
            f.write(f"{s}\n")
    print(f"Saved → {filename}")
    return filename


if __name__ == "__main__":
    results = collect_suggestions(BASE_KW)
    print_results(BASE_KW, results)
    save_results(BASE_KW, results)
```

---

## Example Output

### Czech — `pronatal`, `HL=cs`, `GL=CZ`

```
Base keyword : 'pronatal'
Language     : cs  |  Country: CZ
Queries      : 49
──────────────────────────────────────────────────
[  1/49] pronatal                          → 8 suggestions, 8 new
[  2/49] pronatal a                        → 7 suggestions, 6 new
[  3/49] pronatal b                        → 5 suggestions, 4 new
...
[ 27/49] pronatal z                        → 3 suggestions, 2 new
[ 28/49] jak pronatal                      → 8 suggestions, 5 new
[ 29/49] proč pronatal                     → 6 suggestions, 4 new
[ 30/49] kdy pronatal                      → 7 suggestions, 6 new
...

============================================================
  Autocomplete analysis: 'pronatal'
  Language: cs  |  Country: CZ
  Unique suggestions: 63
============================================================
    1. cena pronatal
    2. co je pronatal
    3. jak dlouho brát pronatal
    4. jak pronatal užívat
    5. kdy začít brát pronatal
    6. proč pronatal
    7. pronatal a alkohol
    8. pronatal advanced
    9. pronatal b12
    10. pronatal složení
    ...
```

### English — `iphone`, `HL=en`, `GL=US`

```
Base keyword : 'iphone'
Language     : en  |  Country: US
Queries      : 49
...
============================================================
  Autocomplete analysis: 'iphone'
  Language: en  |  Country: US
  Unique suggestions: 87
============================================================
    1. best iphone
    2. how to reset iphone
    3. iphone 15 price
    4. iphone 15 pro max
    5. iphone 16
    ...
```

---

## Configuration Reference

| Variable | Default | Description |
|---|---|---|
| `BASE_KW` | `"pronatal"` | Base keyword to analyse |
| `HL` | `"cs"` | Host language — controls which `QUESTION_PREFIXES` are used and the `hl=` param |
| `GL` | `"CZ"` | Country code — influences localised suggestions via `gl=` param |
| `MIN_DELAY` | `1.5` | Minimum seconds between requests |
| `MAX_DELAY` | `3.5` | Maximum seconds between requests |

### Adding a new language

Add an entry to `QUESTION_PREFIXES` with the ISO 639-1 code and desired prefixes:

```python
"ja": ["どうやって", "なぜ", "いつ", "何は", "どこで", "口コミ", "価格"],
```

Then set `HL = "ja"` and `GL = "JP"`.

---

## Rate-Limiting & Safety Notes

| Risk | Mitigation |
|---|---|
| IP block / CAPTCHA | Random delay 1.5–3.5 s per request; 30 s back-off on HTTP 429 |
| Pattern detection | User-Agent rotated per request; `Referer: google.com` set |
| Bulk scraping | Script is intentionally sequential — do NOT parallelise requests |
| Repeated runs | Increase `MIN_DELAY` / `MAX_DELAY` if you run multiple keywords back-to-back |

**Typical run time**: ~49 queries × ~2.5 s average delay ≈ 2 minutes per keyword.

---

## Workflow

1. Set `BASE_KW`, `HL`, `GL` in the **Configuration** block at the top of the script
2. Run: `python autocomplete.py`
3. Results are printed to stdout and saved to `suggestions_<kw>_<hl>_<gl>.txt`
4. Feed the deduplicated list into your content strategy, keyword planner, or ad groups
