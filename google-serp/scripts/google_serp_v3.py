#!/usr/bin/env python3
"""
Google SERP scraper — v3
Technique: persistent Chrome profile (cookies + session survive between runs).
Google sees a real returning user, not a fresh headless bot.

Usage: python google_serp_v3.py <query> [options]

Options:
  --lang      Language code, e.g. cs, en, de   (default: cs)
  --country   Country code, e.g. cz, us, de    (default: cz)
  --output    Output dir for CSV files         (default: ~/google_serp_outputs)
  --no-csv    Print tables only, skip CSV
  --proxy     SOCKS5 proxy URL                 (e.g. socks5://127.0.0.1:1080)
  --profile   Path to Chrome profile dir       (default: ~/.google_serp_profile)
  --headless  Run headless (default: False — visible window is less detectable)
  --chrome    Path to Chrome binary            (auto-detected if omitted)
"""

import asyncio
import argparse
import csv
import json
import random
import time
import sys
import os
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus


# ── Chrome binary discovery ─────────────────────────────────────────────────

def _find_chrome() -> str | None:
    """Return path to installed Chrome/Chromium, or None to use bundled Chromium."""
    candidates = [
        # macOS
        '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
        '/Applications/Chromium.app/Contents/MacOS/Chromium',
        # Linux
        '/usr/bin/google-chrome',
        '/usr/bin/google-chrome-stable',
        '/usr/bin/chromium',
        '/usr/bin/chromium-browser',
        # Windows
        r'C:\Program Files\Google\Chrome\Application\chrome.exe',
        r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
    ]
    # Prefer CHROME_PATH env var
    env_path = os.environ.get('CHROME_PATH')
    if env_path and Path(env_path).exists():
        return env_path

    for c in candidates:
        if Path(c).exists():
            return c
    return None


# ── CAPTCHA detection ───────────────────────────────────────────────────────

def _is_captcha(url: str, body: str) -> bool:
    if '/sorry/' in url:
        return True
    b = body.lower()
    if 'unusual traffic' in b:
        return True
    if 'neobvyklého provozu' in body:
        return True
    return False


async def _check_captcha(page, ctx):
    """Raise RuntimeError if CAPTCHA detected. Also catches navigation-mid-eval."""
    try:
        body = await page.evaluate('document.body.innerText')
    except Exception:
        await ctx.close()
        raise RuntimeError(
            "Google returned CAPTCHA. Try again later or use a different IP."
        )
    if _is_captcha(page.url, body):
        await ctx.close()
        raise RuntimeError(
            "Google returned CAPTCHA. Try again later or use a different IP."
        )
    return body


# ── Core scrape ─────────────────────────────────────────────────────────────

BLOCKED_PARAMS = ['tbs', 'tbm', 'source', 'udm', 'start', 'fbs', 'uds', 'ei']

_EXTRACT_JS = '''
({query, blocked}) => {
    const orig = query.toLowerCase();

    // ── Organic results ──────────────────────────────────────────────────
    const organic = [];
    const seenOrg = new Set();
    document.querySelectorAll("h3").forEach(h3 => {
        const title = h3.innerText.trim();
        if (!title || title.length < 4) return;
        let a = h3.closest("a") || h3.parentElement?.closest("a");
        if (!a || !a.href || seenOrg.has(a.href)) return;
        if (a.href.includes("google")) return;
        seenOrg.add(a.href);
        let desc = "";
        const c = h3.closest(".g") || h3.closest("[data-sokoban-container]");
        if (c) {
            const d = c.querySelector(".VwiC3b")
                   || c.querySelector("[data-sncf='1']")
                   || c.querySelector("[data-sncf]")
                   || c.querySelector("div[style*='webkit-line-clamp']");
            if (d) desc = d.innerText.trim().substring(0, 300);
        }
        organic.push({ position: organic.length + 1, title, url: a.href, description: desc });
    });

    // ── People Also Ask ──────────────────────────────────────────────────
    const paa = new Set();
    document.querySelectorAll("[jsname='yEVEwb'], .related-question-pair").forEach(el => {
        const h = el.querySelector("[role=heading], h3");
        const t = (h || el).innerText?.trim();
        if (t && t.endsWith("?") && t.length > 8 && t.length < 200) paa.add(t);
    });

    // ── Related searches ─────────────────────────────────────────────────
    const related = [];
    const seenRel = new Set();
    document.querySelectorAll("a[href]").forEach(a => {
        try {
            const href = a.getAttribute("href") || "";
            if (!href.includes("/search?")) return;
            const url = new URL(a.href);
            const p = url.searchParams;
            const q = p.get("q");
            if (!q || q.toLowerCase() === orig) return;
            if (q.includes("site:")) return;
            if (blocked.some(b => p.has(b))) return;
            const text = a.innerText?.trim();
            if (!text || text.length < 3 || text.length > 100 || seenRel.has(text)) return;
            seenRel.add(text);
            related.push(text);
        } catch(e) {}
    });

    return { organic, paa: [...paa], related };
}
'''


async def _scrape(
    query: str,
    lang: str,
    country: str,
    proxy: str | None,
    profile_dir: str,
    headless: bool,
    chrome_path: str | None,
) -> dict:
    from playwright.async_api import async_playwright

    search_url = (
        f"https://www.google.{country}/search"
        f"?q={quote_plus(query)}&hl={lang}&gl={country}&num=10&pws=0"
    )

    Path(profile_dir).mkdir(parents=True, exist_ok=True)

    launch_kwargs: dict = dict(
        headless=headless,
        viewport={'width': 1280, 'height': 900},
        args=[
            '--disable-blink-features=AutomationControlled',
            '--disable-infobars',
            '--no-first-run',
            '--no-default-browser-check',
            '--disable-extensions-except=',
        ],
    )
    if chrome_path:
        launch_kwargs['executable_path'] = chrome_path
    if proxy:
        launch_kwargs['proxy'] = {'server': proxy}

    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(profile_dir, **launch_kwargs)

        # Suppress webdriver flag on every new page
        await ctx.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )

        page = await ctx.new_page()

        # ── Go directly to search URL (like the reference repo) ──────────
        print(f"  → {search_url}", flush=True)
        await page.goto(search_url, wait_until='domcontentloaded', timeout=30000)

        # ── Cookie consent (only needed on first run / fresh profile) ─────
        for label in ['Přijmout vše', 'Accept all', 'Alle akzeptieren',
                       'Tout accepter', 'Aceptar todo']:
            try:
                btn = await page.wait_for_selector(
                    f'button:has-text("{label}")', timeout=2000
                )
                await btn.click()
                await page.wait_for_load_state('domcontentloaded', timeout=10000)
                print(f"  → Cookie consent: '{label}' clicked", flush=True)
                break
            except Exception:
                continue

        # ── Wait for results or CAPTCHA ───────────────────────────────────
        await page.wait_for_load_state('networkidle', timeout=15000)

        # ── CAPTCHA check ─────────────────────────────────────────────────
        await _check_captcha(page, ctx)

        # ── Random delay (1–2.5 s) — mirrors the reference repo ──────────
        await page.wait_for_timeout(1000 + random.randint(0, 1500))

        # ── Extract ───────────────────────────────────────────────────────
        result = await page.evaluate(_EXTRACT_JS, {'query': query, 'blocked': BLOCKED_PARAMS})

        await ctx.close()
        return result


def scrape(
    query: str,
    lang: str = 'cs',
    country: str = 'cz',
    proxy: str | None = None,
    profile_dir: str = str(Path('~/.google_serp_profile').expanduser()),
    headless: bool = True,
    chrome_path: str | None = None,
) -> dict:
    if chrome_path is None:
        chrome_path = _find_chrome()
    try:
        data = asyncio.run(_scrape(query, lang, country, proxy, profile_dir, headless, chrome_path))
        data['status'] = 'SUCCESS'
        data['error'] = ''
        return data
    except Exception as e:
        return {'organic': [], 'paa': [], 'related': [], 'status': 'ERROR', 'error': str(e)}


def scrape_with_pause(
    query: str,
    lang: str = 'cs',
    country: str = 'cz',
    proxy: str | None = None,
    profile_dir: str = str(Path('~/.google_serp_profile').expanduser()),
    headless: bool = True,
    pause_min: int = 8,
    pause_max: int = 15,
) -> dict:
    wait = random.uniform(pause_min, pause_max)
    print(f"  ⏳ Waiting {wait:.1f}s before \"{query}\"...", file=sys.stderr)
    time.sleep(wait)
    return scrape(query, lang, country, proxy, profile_dir, headless)


# ── Formatting ───────────────────────────────────────────────────────────────

def _print_table(title: str, headers: list[str], rows: list[list]):
    if not rows:
        print(f"\n{title}\n  (no results)\n")
        return
    widths = [max(len(str(rows[r][c])) for r in range(len(rows))) for c in range(len(headers))]
    widths = [max(widths[i], len(headers[i])) for i in range(len(headers))]
    sep = '+-' + '-+-'.join('-' * w for w in widths) + '-+'
    fmt = '| ' + ' | '.join(f'{{:<{w}}}' for w in widths) + ' |'
    print(f"\n{'=' * len(sep)}\n{title}\n{'=' * len(sep)}")
    print(sep)
    print(fmt.format(*headers))
    print(sep)
    for row in rows:
        print(fmt.format(*[str(c)[:widths[i]] for i, c in enumerate(row)]))
    print(sep)


def print_results(data: dict, query: str):
    _print_table(
        f"ORGANIC — \"{query}\"",
        ['#', 'Title', 'Description', 'URL'],
        [[r['position'], r['title'][:55], r['description'][:75], r['url'][:65]]
         for r in data['organic']],
    )
    _print_table("PEOPLE ALSO ASK", ['#', 'Question'],
                 [[i + 1, q] for i, q in enumerate(data['paa'][:10])])
    _print_table("RELATED SEARCHES", ['#', 'Query'],
                 [[i + 1, x] for i, x in enumerate(data['related'])])


# ── CSV export ───────────────────────────────────────────────────────────────

def save_csv(data: dict, query: str, output_dir: str,
             lang: str = 'cs', country: str = 'cz') -> list[str]:
    out = Path(output_dir).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    slug = query.replace(' ', '_')[:40]
    paths = []

    if data['organic']:
        p = out / f"serp_organic_{slug}_{ts}.csv"
        with open(p, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=['position', 'title', 'description', 'url', 'language', 'country'])
            w.writeheader()
            for row in data['organic']:
                w.writerow({**row, 'language': lang, 'country': country})
        paths.append(str(p))
        print(f"Organic CSV : {p}")

    if data['paa']:
        p = out / f"serp_paa_{slug}_{ts}.csv"
        with open(p, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['position', 'question', 'language', 'country'])
            for i, q in enumerate(data['paa'], 1):
                w.writerow([i, q, lang, country])
        paths.append(str(p))
        print(f"PAA CSV     : {p}")

    if data['related']:
        p = out / f"serp_related_{slug}_{ts}.csv"
        with open(p, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['position', 'query', 'language', 'country'])
            for i, x in enumerate(data['related'], 1):
                w.writerow([i, x, lang, country])
        paths.append(str(p))
        print(f"Related CSV : {p}")

    p = out / f"serp_status_{slug}_{ts}.csv"
    with open(p, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['keyword', 'status', 'error_message', 'results_count', 'language', 'country'])
        w.writeheader()
        w.writerow({'keyword': query, 'status': data.get('status', 'SUCCESS'),
                    'error_message': data.get('error', ''),
                    'results_count': len(data.get('organic', [])),
                    'language': lang, 'country': country})
    paths.append(str(p))
    print(f"Status CSV  : {p}")
    return paths


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Google SERP scraper v3 — persistent profile, always num=10'
    )
    parser.add_argument('query')
    parser.add_argument('--lang',     default='cs')
    parser.add_argument('--country',  default='cz')
    parser.add_argument('--output',   default='~/google_serp_outputs')
    parser.add_argument('--no-csv',   action='store_true')
    parser.add_argument('--json',     action='store_true')
    parser.add_argument('--proxy',    default=None)
    parser.add_argument('--profile',  default=str(Path('~/.google_serp_profile').expanduser()))
    parser.add_argument('--headless', action='store_true', default=False,
                        help='Run headless (default: visible window)')
    parser.add_argument('--chrome',   default=None, help='Path to Chrome binary')
    args = parser.parse_args()

    chrome = args.chrome or _find_chrome()

    print(f"Scraping : \"{args.query}\" | google.{args.country} | lang={args.lang} | num=10")
    print(f"Profile  : {args.profile}")
    print(f"Chrome   : {chrome or '(bundled Chromium)'}")
    print(f"Headless : {args.headless}")
    if args.proxy:
        print(f"Proxy    : {args.proxy}")

    data = scrape(args.query, lang=args.lang, country=args.country,
                  proxy=args.proxy, profile_dir=args.profile,
                  headless=args.headless, chrome_path=chrome)

    if data['status'] == 'ERROR':
        print(f"\n❌ {data['error']}", file=sys.stderr)
        sys.exit(1)

    print(f"\n✅ organic={len(data['organic'])} paa={len(data['paa'])} related={len(data['related'])}")
    print_results(data, args.query)

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))

    if not args.no_csv:
        save_csv(data, args.query, args.output, lang=args.lang, country=args.country)


if __name__ == '__main__':
    main()
