#!/usr/bin/env python3
"""
Google SERP scraper using local Playwright.
Usage: python google_serp.py <query> [options]

Options:
  --lang      Language code, e.g. cs, en, de  (default: cs)
  --country   Country code, e.g. cz, us, de   (default: cz)
  --num       Number of results               (default: 10)
  --output    Output dir for CSV files        (default: ~/google_serp_outputs)
  --no-csv    Print tables only, skip CSV
"""

import asyncio
import argparse
import csv
import json
import sys
import os
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus


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


# ── Core scrape ─────────────────────────────────────────────────────────────

BLOCKED_PARAMS = ['tbs', 'tbm', 'source', 'udm', 'start', 'fbs', 'uds', 'ei']


async def _scrape(query: str, lang: str, country: str, num: int) -> dict:
    from playwright.async_api import async_playwright
    try:
        from playwright_stealth import stealth_async
        _has_stealth = True
    except ImportError:
        _has_stealth = False

    url = (
        f"https://www.google.{country}/search"
        f"?q={quote_plus(query)}&hl={lang}&gl={country}&num={num}&pws=0"
    )

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=['--disable-blink-features=AutomationControlled']
        )
        ctx = await browser.new_context(
            viewport={'width': 1280, 'height': 900},
            locale=f'{lang}-{country.upper()}',
            timezone_id='Europe/Prague',
            user_agent=(
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/122.0.0.0 Safari/537.36'
            ),
            extra_http_headers={'Accept-Language': f'{lang}-{country.upper()},{lang};q=0.9'}
        )
        page = await ctx.new_page()

        if _has_stealth:
            await stealth_async(page)
        else:
            await page.add_init_script(
                "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
            )

        await page.goto(url, wait_until='networkidle', timeout=30000)

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

        await page.wait_for_timeout(2000)
        await page.keyboard.press('Escape')
        await page.wait_for_timeout(500)

        # Check for CAPTCHA
        body_text = await page.evaluate('document.body.innerText')
        if 'unusual traffic' in body_text.lower() or 'neobvyklého provozu' in body_text:
            await browser.close()
            raise RuntimeError(
                "Google returned CAPTCHA. Try again later or use a different IP."
            )

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
                        // Try multiple known description selectors
                        const d = c.querySelector(".VwiC3b")
                               || c.querySelector("[data-sncf='1']")
                               || c.querySelector("[data-sncf]")
                               || c.querySelector("div[style*='webkit-line-clamp']")
                               || c.querySelector(".s3v9rd")
                               || c.querySelector(".st");
                        if (d) {
                            // Strip date prefix like "12. 1. 2024 — "
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

                // ── Related searches — structural (language-agnostic) ────
                // Signal: /search?q=<different_query> with no filter/nav params
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


def scrape(query: str, lang: str = 'cs', country: str = 'cz', num: int = 10) -> dict:
    return asyncio.run(_scrape(query, lang, country, num))


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
    # Organic
    org_rows = [
        [r['position'], r['title'][:60], r['description'][:80], r['url'][:70]]
        for r in data['organic']
    ]
    _print_table(
        f"ORGANIC RESULTS — \"{query}\"",
        ['#', 'Title', 'Description', 'URL'],
        org_rows
    )

    # PAA
    paa_rows = [[i + 1, q] for i, q in enumerate(data['paa'][:10])]
    _print_table(
        "PEOPLE ALSO ASK",
        ['#', 'Question'],
        paa_rows
    )

    # Related searches
    rel_rows = [[i + 1, x] for i, x in enumerate(data['related'])]
    _print_table(
        "RELATED SEARCHES",
        ['#', 'Query'],
        rel_rows
    )


# ── CSV export ───────────────────────────────────────────────────────────────

def save_csv(data: dict, query: str, output_dir: str) -> list[str]:
    out = Path(output_dir).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    slug = query.replace(' ', '_')[:40]
    paths = []

    # Organic
    if data['organic']:
        p = out / f"serp_organic_{slug}_{ts}.csv"
        with open(p, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=['position', 'title', 'description', 'url'])
            w.writeheader()
            w.writerows(data['organic'])
        paths.append(str(p))
        print(f"Organic CSV: {p}")

    # PAA
    if data['paa']:
        p = out / f"serp_paa_{slug}_{ts}.csv"
        with open(p, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['position', 'question'])
            for i, q in enumerate(data['paa'], 1):
                w.writerow([i, q])
        paths.append(str(p))
        print(f"PAA CSV:     {p}")

    # Related searches
    if data['related']:
        p = out / f"serp_related_{slug}_{ts}.csv"
        with open(p, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['position', 'query'])
            for i, x in enumerate(data['related'], 1):
                w.writerow([i, x])
        paths.append(str(p))
        print(f"Related CSV: {p}")

    return paths


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Scrape Google SERP using local Playwright'
    )
    parser.add_argument('query', help='Search query')
    parser.add_argument('--lang',    default='cs',  help='Language code (default: cs)')
    parser.add_argument('--country', default='cz',  help='Country code (default: cz)')
    parser.add_argument('--num',     default=10, type=int, help='Number of results (default: 10)')
    parser.add_argument('--output',  default='~/google_serp_outputs', help='Output directory')
    parser.add_argument('--no-csv',  action='store_true', help='Skip CSV output')
    parser.add_argument('--json',    action='store_true', help='Also dump raw JSON')
    args = parser.parse_args()

    ensure_playwright()

    print(f"Scraping: \"{args.query}\" | google.{args.country} | lang={args.lang} | num={args.num}")

    data = scrape(args.query, lang=args.lang, country=args.country, num=args.num)

    print_results(data, args.query)

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))

    if not args.no_csv:
        save_csv(data, args.query, args.output)


if __name__ == '__main__':
    main()
