#!/usr/bin/env python3
"""
Google SERP scraper using local Playwright.
v2 — always num=10, robust CAPTCHA detection, optional proxy support.

Usage: python google_serp_v2.py <query> [options]

Options:
  --lang      Language code, e.g. cs, en, de  (default: cs)
  --country   Country code, e.g. cz, us, de   (default: cz)
  --output    Output dir for CSV files        (default: ~/google_serp_outputs)
  --no-csv    Print tables only, skip CSV
  --proxy     SOCKS5 proxy URL               (e.g. socks5://127.0.0.1:1080)
"""

import asyncio
import argparse
import csv
import json
import math
import random
import time
import sys
import os
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus


# ── Anti-detection pools ────────────────────────────────────────────────────

USER_AGENTS = [
    # Chrome on macOS
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
    # Chrome on Windows
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
    # Firefox
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:133.0) Gecko/20100101 Firefox/133.0',
    # Safari
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Safari/605.1.15',
    # Edge
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0',
]

VIEWPORTS = [
    {'width': 1920, 'height': 1080},
    {'width': 1536, 'height': 864},
    {'width': 1440, 'height': 900},
    {'width': 1366, 'height': 768},
    {'width': 1280, 'height': 900},
    {'width': 1280, 'height': 720},
]


# ── Human-like mouse movement (anti-detection) ─────────────────────────────

def _bezier_ease(t: float) -> float:
    """Cubic Bézier ease (0.25,0.1,0.25,1) approximation."""
    if t < 0.5:
        return 4 * t * t * t
    else:
        return 1 - (-2 * t + 2) ** 3 / 2


async def _human_mouse_move(page, target_x: float, target_y: float, steps: int = 35):
    """Move mouse from viewport center to target with Bézier easing + jitter."""
    dims = await page.evaluate("() => ({w: window.innerWidth, h: window.innerHeight})")
    start_x = dims['w'] / 2 + random.uniform(-50, 50)
    start_y = dims['h'] / 2 + random.uniform(-50, 50)
    await page.mouse.move(start_x, start_y)

    for i in range(1, steps + 1):
        t = i / steps
        progress = _bezier_ease(t)
        x = start_x + (target_x - start_x) * progress
        y = start_y + (target_y - start_y) * progress
        jx = random.uniform(-2.5, 2.5)
        jy = random.uniform(-2.5, 2.5)
        await page.mouse.move(x + jx, y + jy)
        await page.wait_for_timeout(random.randint(10, 60))

    await page.mouse.move(target_x, target_y)


# ── Playwright check ────────────────────────────────────────────────────────

def ensure_playwright():
    try:
        import playwright
    except ImportError:
        print("Installing playwright...", file=sys.stderr)
        os.system(f"{sys.executable} -m pip install playwright --break-system-packages -q")
    try:
        from playwright.async_api import async_playwright  # noqa
    except ImportError:
        print("ERROR: playwright install failed.", file=sys.stderr)
        sys.exit(1)

    try:
        import playwright_stealth  # noqa
    except ImportError:
        print("Installing playwright-stealth...", file=sys.stderr)
        os.system(f"{sys.executable} -m pip install playwright-stealth --break-system-packages -q")


# ── CAPTCHA detection ───────────────────────────────────────────────────────

def _is_captcha(url: str, body: str) -> bool:
    """Return True if the current page appears to be a Google CAPTCHA/block page."""
    if '/sorry/' in url:
        return True
    body_l = body.lower()
    if 'unusual traffic' in body_l:
        return True
    if 'neobvyklého provozu' in body:
        return True
    return False


async def _check_captcha(page, browser):
    """
    Evaluate page body and raise RuntimeError if CAPTCHA is detected.
    Handles the case where a navigation fires mid-evaluation
    (Execution context destroyed) — that itself signals a CAPTCHA redirect.
    """
    try:
        body = await page.evaluate('document.body.innerText')
    except Exception:
        # Navigation happened while evaluating → likely CAPTCHA redirect
        await browser.close()
        raise RuntimeError(
            "Google returned CAPTCHA. Try again later or use a different IP."
        )

    if _is_captcha(page.url, body):
        await browser.close()
        raise RuntimeError(
            "Google returned CAPTCHA. Try again later or use a different IP."
        )

    return body


# ── Core scrape ─────────────────────────────────────────────────────────────

BLOCKED_PARAMS = ['tbs', 'tbm', 'source', 'udm', 'start', 'fbs', 'uds', 'ei']


async def _scrape(query: str, lang: str, country: str,
                  proxy: str | None = None) -> dict:
    from playwright.async_api import async_playwright

    # Stealth — support both old API (stealth_async) and new (Stealth class)
    _stealth_fn = None
    try:
        from playwright_stealth import stealth_async
        _stealth_fn = stealth_async
    except ImportError:
        try:
            from playwright_stealth import Stealth
            async def _stealth_class(p):
                await Stealth().apply_stealth_async(p)
            _stealth_fn = _stealth_class
        except ImportError:
            pass

    homepage = f"https://www.google.{country}/?hl={lang}&gl={country}"
    ua = random.choice(USER_AGENTS)
    vp = random.choice(VIEWPORTS)

    launch_kwargs = dict(
        headless=True,
        args=[
            '--disable-blink-features=AutomationControlled',
            '--disable-dev-shm-usage',
            '--no-first-run',
            '--no-default-browser-check',
            '--disable-extensions',
        ],
    )
    if proxy:
        launch_kwargs['proxy'] = {'server': proxy}

    async with async_playwright() as p:
        browser = await p.chromium.launch(**launch_kwargs)
        ctx = await browser.new_context(
            viewport=vp,
            locale=f'{lang}-{country.upper()}',
            timezone_id='Europe/Prague',
            user_agent=ua,
            extra_http_headers={'Accept-Language': f'{lang}-{country.upper()},{lang};q=0.9'},
        )
        page = await ctx.new_page()

        if _stealth_fn:
            await _stealth_fn(page)
        else:
            await page.add_init_script(
                "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
            )

        # ── Step 1: Visit Google homepage first (like a real user) ────────
        await page.goto(homepage, wait_until='networkidle', timeout=30000)

        # Human-like mouse movement on homepage
        await _human_mouse_move(page, random.randint(400, 800), random.randint(300, 500))

        # Accept cookie consent if shown
        for label in ['Přijmout vše', 'Accept all', 'Alle akzeptieren',
                       'Tout accepter', 'Aceptar todo']:
            try:
                btn = await page.wait_for_selector(
                    f'button:has-text("{label}")', timeout=2000
                )
                await btn.click()
                await page.wait_for_load_state('networkidle')
                break
            except Exception:
                continue

        await page.wait_for_timeout(random.randint(500, 1500))

        # ── Step 2: Type query into search box (human-like) ───────────────
        search_box = await page.wait_for_selector(
            'textarea[name="q"], input[name="q"]', timeout=10000
        )
        await _human_mouse_move(page, 640, 400)
        await search_box.click()
        await page.wait_for_timeout(random.randint(200, 600))

        for char in query:
            await page.keyboard.type(char, delay=random.randint(30, 120))
            if random.random() < 0.1:
                await page.wait_for_timeout(random.randint(100, 400))

        await page.wait_for_timeout(random.randint(300, 800))
        await page.keyboard.press('Enter')
        await page.wait_for_load_state('networkidle', timeout=30000)

        # ── CAPTCHA check (before any further navigation) ─────────────────
        # Note: always num=10, so no second navigation needed.
        # Check happens here where the page state is known.
        await _check_captcha(page, browser)

        # ── Step 3: Simulate reading results ─────────────────────────────
        await page.wait_for_load_state('domcontentloaded')
        await page.wait_for_timeout(1000)
        await _human_mouse_move(page, random.randint(200, 800), random.randint(150, 500))
        await page.wait_for_timeout(random.randint(800, 2000))
        await page.keyboard.press('Escape')
        await page.wait_for_timeout(random.randint(300, 700))

        # ── Extract results ───────────────────────────────────────────────
        result = await page.evaluate(
            '''({query, blocked}) => {
                const orig = query.toLowerCase();

                // ── Organic results ──────────────────────────────────────
                const organic = [];
                const seenOrg = new Set();
                document.querySelectorAll("h3").forEach((h3, idx) => {
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
                               || c.querySelector("div[style*='webkit-line-clamp']")
                               || c.querySelector(".s3v9rd")
                               || c.querySelector(".st");
                        if (d) {
                            desc = d.innerText.trim().substring(0, 300);
                        }
                    }
                    organic.push({position: organic.length + 1, title, url: a.href, description: desc});
                });

                // ── People Also Ask ──────────────────────────────────────
                const paa = new Set();
                document.querySelectorAll("[jsname='yEVEwb'], .related-question-pair").forEach(el => {
                    const h = el.querySelector("[role=heading], h3");
                    const t = (h || el).innerText?.trim();
                    if (t && t.endsWith("?") && t.length > 8 && t.length < 200) paa.add(t);
                });

                // ── Related searches ─────────────────────────────────────
                const related = [];
                const seenRel = new Set();
                document.querySelectorAll("a[href]").forEach(a => {
                    try {
                        const href = a.getAttribute("href") || "";
                        if (!href.includes("/search?")) return;
                        const url = new URL(a.href);
                        const p = url.searchParams;
                        const q = p.get("q");
                        if (!q) return;
                        if (q.toLowerCase() === orig) return;
                        if (q.includes("site:")) return;
                        if (blocked.some(b => p.has(b))) return;
                        const text = a.innerText?.trim();
                        if (!text || text.length < 3 || text.length > 100 || seenRel.has(text)) return;
                        seenRel.add(text);
                        related.push(text);
                    } catch(e) {}
                });

                return {organic, paa: [...paa], related};
            }''',
            {'query': query, 'blocked': BLOCKED_PARAMS}
        )

        await browser.close()
        return result


def scrape(query: str, lang: str = 'cs', country: str = 'cz',
           proxy: str | None = None) -> dict:
    try:
        data = asyncio.run(_scrape(query, lang, country, proxy))
        data['status'] = 'SUCCESS'
        data['error'] = ''
        return data
    except Exception as e:
        return {'organic': [], 'paa': [], 'related': [], 'status': 'ERROR', 'error': str(e)}


def scrape_with_pause(query: str, lang: str = 'cs', country: str = 'cz',
                      proxy: str | None = None,
                      pause_min: int = 8, pause_max: int = 15) -> dict:
    """Scrape with a mandatory random pause BEFORE the request (for batch usage)."""
    wait = random.uniform(pause_min, pause_max)
    print(f"  ⏳ Waiting {wait:.1f}s before scraping \"{query}\"...", file=sys.stderr)
    time.sleep(wait)
    return scrape(query, lang, country, proxy)


# ── Formatting ───────────────────────────────────────────────────────────────

def _col_widths(rows: list[list], headers: list[str]) -> list[int]:
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))
    return widths


def _print_table(title: str, headers: list[str], rows: list[list]):
    if not rows:
        print(f"\n{title}\n  (no results)\n")
        return

    widths = _col_widths(rows, headers)
    sep = '+-' + '-+-'.join('-' * w for w in widths) + '-+'
    fmt = '| ' + ' | '.join(f'{{:<{w}}}' for w in widths) + ' |'

    print(f"\n{'=' * len(sep)}")
    print(title)
    print('=' * len(sep))
    print(sep)
    print(fmt.format(*headers))
    print(sep)
    for row in rows:
        print(fmt.format(*[str(c) for c in row]))
    print(sep)
    print()


def print_results(data: dict, query: str):
    org_rows = [
        [r['position'], r['title'][:60], r['description'][:80], r['url'][:70]]
        for r in data['organic']
    ]
    _print_table(
        f"ORGANIC RESULTS — \"{query}\"",
        ['#', 'Title', 'Description', 'URL'],
        org_rows
    )

    paa_rows = [[i + 1, q] for i, q in enumerate(data['paa'][:10])]
    _print_table("PEOPLE ALSO ASK", ['#', 'Question'], paa_rows)

    rel_rows = [[i + 1, x] for i, x in enumerate(data['related'])]
    _print_table("RELATED SEARCHES", ['#', 'Query'], rel_rows)


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
                row['language'] = lang
                row['country'] = country
                w.writerow(row)
        paths.append(str(p))
        print(f"Organic CSV: {p}")

    if data['paa']:
        p = out / f"serp_paa_{slug}_{ts}.csv"
        with open(p, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['position', 'question', 'language', 'country'])
            for i, q in enumerate(data['paa'], 1):
                w.writerow([i, q, lang, country])
        paths.append(str(p))
        print(f"PAA CSV:     {p}")

    if data['related']:
        p = out / f"serp_related_{slug}_{ts}.csv"
        with open(p, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['position', 'query', 'language', 'country'])
            for i, x in enumerate(data['related'], 1):
                w.writerow([i, x, lang, country])
        paths.append(str(p))
        print(f"Related CSV: {p}")

    p = out / f"serp_status_{slug}_{ts}.csv"
    with open(p, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['keyword', 'status', 'error_message', 'results_count', 'language', 'country'])
        w.writeheader()
        w.writerow({
            'keyword': query,
            'status': data.get('status', 'SUCCESS'),
            'error_message': data.get('error', ''),
            'results_count': len(data.get('organic', [])),
            'language': lang,
            'country': country,
        })
    paths.append(str(p))
    print(f"Status CSV:  {p}")

    return paths


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Scrape Google SERP using local Playwright (v2, always num=10)'
    )
    parser.add_argument('query',               help='Search query')
    parser.add_argument('--lang',    default='cs',                    help='Language code (default: cs)')
    parser.add_argument('--country', default='cz',                    help='Country code (default: cz)')
    parser.add_argument('--output',  default='~/google_serp_outputs', help='Output directory')
    parser.add_argument('--no-csv',  action='store_true',             help='Skip CSV output')
    parser.add_argument('--json',    action='store_true',             help='Also dump raw JSON')
    parser.add_argument('--proxy',   default=None,                    help='SOCKS5 proxy (e.g. socks5://127.0.0.1:1080)')
    args = parser.parse_args()

    ensure_playwright()

    print(f"Scraping: \"{args.query}\" | google.{args.country} | lang={args.lang} | num=10 (fixed)"
          + (f" | proxy={args.proxy}" if args.proxy else ""))

    data = scrape(args.query, lang=args.lang, country=args.country, proxy=args.proxy)

    if data['status'] == 'ERROR':
        print(f"\n❌ ERROR: {data['error']}", file=sys.stderr)
        sys.exit(1)

    print_results(data, args.query)

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))

    if not args.no_csv:
        save_csv(data, args.query, args.output, lang=args.lang, country=args.country)


if __name__ == '__main__':
    main()
