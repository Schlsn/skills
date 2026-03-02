import requests
import time
import random
import json
import string

# Question prefixes per language
QUESTION_PREFIXES: dict[str, list[str]] = {
    "cs": ["jak", "proč", "kdy", "co je", "kde", "pro koho", "kdo", "cena", "zkušenosti", "recenze", "jak dlouho", "co obsahuje"],
    "en": ["how", "why", "when", "what is", "where", "who", "best", "review", "price", "vs", "how long", "side effects"],
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
]

def _headers(hl="cs", gl="CZ") -> dict[str, str]:
    return {
        "User-Agent":      random.choice(USER_AGENTS),
        "Accept":          "application/json, text/plain, */*",
        "Accept-Language": f"{hl},{hl}-{gl};q=0.9,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer":         "https://www.google.com/",
        "DNT":             "1",
        "Connection":      "keep-alive",
    }


def fetch_suggestions(query: str, session: requests.Session, hl="cs", gl="CZ") -> list[str]:
    url = "https://suggestqueries.google.com/complete/search"
    params = {"client": "chrome", "q": query, "hl": hl, "gl": gl}
    try:
        r = session.get(url, params=params, headers=_headers(hl, gl), timeout=10)
        if r.status_code == 200:
            data = json.loads(r.text)
            return data[1] if len(data) > 1 else []
        elif r.status_code == 429:
            print("  [RATE LIMITED] Backing off 30 s …")
            time.sleep(30)
            # one retry after back-off
            r2 = session.get(url, params=params, headers=_headers(hl, gl), timeout=10)
            if r2.status_code == 200:
                data = json.loads(r2.text)
                return data[1] if len(data) > 1 else []
        else:
            print(f"  [HTTP {r.status_code}] skipping: {query!r}")
    except Exception as e:
        print(f"  [ERROR] {e} — skipping: {query!r}")
    return []

def build_queries(base_kw: str, hl="cs") -> list[str]:
    queries: list[str] = [base_kw]
    for letter in string.ascii_lowercase:
        queries.append(f"{base_kw} {letter}")
    prefixes = list(QUESTION_PREFIXES.get(hl, []))
    if hl != "en":
        prefixes += QUESTION_PREFIXES.get("en", [])
    
    seen: set[str] = set()
    unique_prefixes: list[str] = []
    for p in prefixes:
        if p not in seen:
            seen.add(p)
            unique_prefixes.append(p)
    for prefix in unique_prefixes:
        queries.append(f"{prefix} {base_kw}")
    return queries

def collect_suggestions(base_kw: str, hl="cs", gl="CZ", min_delay=1.0, max_delay=2.5) -> list[str]:
    session   = requests.Session()
    all_lower: set[str] = set()
    all_orig:  dict[str, str] = {}
    queries = build_queries(base_kw, hl)
    total   = len(queries)
    print(f"\nAutocomplete: {base_kw} ({total} queries)")
    for i, query in enumerate(queries, 1):
        suggestions = fetch_suggestions(query, session, hl, gl)
        for s in suggestions:
            key = s.lower().strip()
            if key not in all_lower:
                all_lower.add(key)
                all_orig[key] = s.strip()
        if i < total:
            time.sleep(random.uniform(min_delay, max_delay))
            
    return sorted(all_orig.values(), key=str.lower)
