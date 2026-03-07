#!/usr/bin/env python3
"""
Brave Search SERP scraper — v1
Playwright + playwright-stealth + randomised UA/viewport.

Brave Search is a privacy-focused search engine with very lenient bot detection.
No profile rotation needed.

Language is set via separate --country + --lang parameters (both optional).
Brave does not use a combined locale code — country and language are independent.

Usage:
  python brave_serp.py "seo nástroje" --country cz --lang cs
  python brave_serp.py "keyword research" --country us --lang en --num 20
  python brave_serp.py "SEO" --country de --lang de
  python brave_serp.py "query" --no-headless --json

Country codes (--country, ISO 3166-1 alpha-2, lowercase):
  cz  sk  us  gb  au  ca  de  at  fr  pl  es  it  nl  br  ru  hu  se  dk  fi

Language codes (--lang, ISO 639-1, lowercase):
  cs  sk  en  de  fr  pl  es  it  nl  pt  ru  hu  sv  da  fi  ja  ko  zh

Brave specifics:
  - Default ~20 results per page; --num up to 20 (no pagination in v1)
  - Returns: organic results + related queries (no PAA)
  - safe_search can be off / moderate / strict
  - No consent banner (Brave is privacy-first)
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

# ── Default proxy (Tailscale → Home Assistant residential IP) ─────────────────
_DEFAULT_PROXY = 'socks5://172.18.0.1:1080'


# ── Stealth compatibility ─────────────────────────────────────────────────────

_STEALTH_MODE = 'none'

try:
    from playwright_stealth import stealth_async
    _STEALTH_MODE = 'async_fn'
except ImportError:
    try:
        from playwright_stealth import Stealth as _Stealth
        async def stealth_async(page):
            await _Stealth().apply_stealth_async(page)
        _STEALTH_MODE = 'class'
    except ImportError:
        async def stealth_async(page):  # noqa: F811
            pass
        print("⚠️  playwright-stealth not installed — running without stealth", file=sys.stderr)


# ── UA + viewport pools ───────────────────────────────────────────────────────

_RANDOM_UAS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36',
]

_RANDOM_VIEWPORTS = [
    (1366, 768), (1440, 900), (1536, 864), (1600, 900), (1920, 1080),
    (1280, 720), (1280, 800), (1360, 768), (1024, 768), (1680, 1050),
]


def _pick_ua_and_viewport() -> tuple[str, dict]:
    ua = random.choice(_RANDOM_UAS)
    w, h = random.choice(_RANDOM_VIEWPORTS)
    w += random.randint(-8, 8)
    h += random.randint(-6, 6)
    return ua, {'width': w, 'height': h}


# ── Chrome discovery ──────────────────────────────────────────────────────────

def _find_chrome() -> str | None:
    candidates = [
        '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
        '/Applications/Chromium.app/Contents/MacOS/Chromium',
        '/usr/bin/google-chrome', '/usr/bin/google-chrome-stable',
        '/usr/bin/chromium', '/usr/bin/chromium-browser',
        r'C:\Program Files\Google\Chrome\Application\chrome.exe',
        r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
    ]
    env_path = os.environ.get('CHROME_PATH')
    if env_path and Path(env_path).exists():
        return env_path
    for c in candidates:
        if Path(c).exists():
            return c
    return None


# ── Block detection ───────────────────────────────────────────────────────────

def _is_blocked(url: str, body: str) -> bool:
    if 'search.brave.com/error' in url or 'search.brave.com/blocked' in url:
        return True
    b = body.lower()
    return any(s in b for s in [
        'rate limit',
        'too many requests',
        'access denied',
        'captcha',
        '429',
    ])


# ── Human-like mouse ──────────────────────────────────────────────────────────

def _bezier_point(t, p0, p1, p2, p3):
    mt = 1.0 - t
    x = mt**3*p0[0] + 3*mt**2*t*p1[0] + 3*mt*t**2*p2[0] + t**3*p3[0]
    y = mt**3*p0[1] + 3*mt**2*t*p1[1] + 3*mt*t**2*p2[1] + t**3*p3[1]
    return x, y


async def _human_mouse_move(page, tx, ty, steps=None):
    if steps is None:
        steps = random.randint(18, 35)
    vp = page.viewport_size or {'width': 1280, 'height': 900}
    sx = random.uniform(vp['width']*0.15, vp['width']*0.85)
    sy = random.uniform(vp['height']*0.15, vp['height']*0.75)
    cp1 = (sx + random.uniform(-120, 120), sy + random.uniform(-80, 80))
    cp2 = (tx + random.uniform(-90, 90), ty + random.uniform(-70, 70))
    for i in range(1, steps+1):
        t = i / steps
        ts = t*t*(3.0 - 2.0*t)
        px, py = _bezier_point(ts, (sx, sy), cp1, cp2, (tx, ty))
        await page.mouse.move(px, py)
        await asyncio.sleep(random.uniform(4, 18) * (1.0 + 1.2*abs(t - 0.5)) / 1000)


async def _human_scroll(page, count=3):
    for _ in range(count):
        await page.mouse.wheel(0, random.randint(200, 480))
        await asyncio.sleep(random.uniform(0.3, 0.8))


# ── JS extraction ─────────────────────────────────────────────────────────────

_EXTRACT_JS = '''
(() => {
    const organic = [];
    const seenUrls = new Set();

    // ── Organic results ───────────────────────────────────────────────────
    // Brave uses div.snippet[data-type="web"] or div[data-pos] inside #results.
    // Title link is a.title or the first external <a> within the snippet.
    // Description is in .snippet-description or p within the snippet.
    const snippets = document.querySelectorAll(
        '#results div.snippet, ' +
        '#results [data-type="web"], ' +
        '#results article'
    );

    for (const item of snippets) {
        // Skip non-web snippets (news, video, etc.)
        const dtype = item.getAttribute('data-type');
        if (dtype && !['web', null].includes(dtype)) continue;

        // Skip Brave AI summary boxes
        if (item.id === 'ai-answer' || item.closest('#ai-answer')) continue;

        // Find the title link — external URL only
        const link = item.querySelector('a.title[href]')
                  || item.querySelector('a.result-header[href]')
                  || (() => {
                        for (const a of item.querySelectorAll('a[href]')) {
                            const h = a.href || '';
                            if (!h.startsWith('https://search.brave.com')
                                && !h.startsWith('/')
                                && h.startsWith('http')) return a;
                        }
                        return null;
                     })();

        if (!link) continue;

        const url = link.href;
        if (!url || url.includes('search.brave.com') || seenUrls.has(url)) continue;
        seenUrls.add(url);

        // Title text: direct text or text inside a child div
        const title = link.innerText?.trim()
                   || link.querySelector('span, div')?.innerText?.trim()
                   || '';
        if (title.length < 3) continue;

        // Description / snippet text
        const snip = item.querySelector('.snippet-description')
                  || item.querySelector('p.body')
                  || item.querySelector('[class*="description"]')
                  || item.querySelector('p');
        const description = snip?.innerText?.trim().substring(0, 300) || '';

        organic.push({ position: organic.length + 1, title, url, description });
    }

    // Fallback: if no .snippet found, try any h2/h3 link pointing outward
    if (organic.length === 0) {
        const links = document.querySelectorAll('#results h2 a, #results h3 a');
        for (const link of links) {
            const url = link.href;
            if (!url || url.includes('brave.com') || seenUrls.has(url)) continue;
            seenUrls.add(url);
            const title = link.innerText?.trim() || '';
            if (title.length < 3) continue;
            organic.push({ position: organic.length + 1, title, url, description: '' });
        }
    }

    // ── Related queries ───────────────────────────────────────────────────
    const related = [];
    const seenRel = new Set();

    // Brave shows related queries at the bottom or top as chip links
    const relSels = [
        '#related-queries a',
        '.related-queries a',
        '[data-key="related-queries"] a',
        '[class*="related-queries"] a',
        '[class*="relatedqueries"] a',
        'section[aria-label*="related"] a',
    ];

    for (const sel of relSels) {
        const els = document.querySelectorAll(sel);
        for (const el of els) {
            const t = (el.innerText || el.textContent || '').trim();
            if (t && t.length > 2 && t.length < 150 && !seenRel.has(t)) {
                seenRel.add(t);
                related.push(t);
            }
        }
        if (related.length > 0) break;
    }

    return { organic, related };
})()
'''


# ── Core scraper ──────────────────────────────────────────────────────────────

async def _scrape(
    query: str,
    country: str | None,
    lang: str | None,
    num: int,
    safe_search: str,
    proxy: str | None,
    headless: bool,
    chrome_path: str | None,
) -> dict:
    from playwright.async_api import async_playwright

    ua, viewport = _pick_ua_and_viewport()

    _launch_args = [
        '--disable-blink-features=AutomationControlled',
        '--disable-infobars',
        '--no-first-run',
        '--no-default-browser-check',
        '--disable-extensions-except=',
        '--disable-default-apps',
        '--no-service-autorun',
        '--password-store=basic',
        f'--window-size={viewport["width"]},{viewport["height"]}',
    ]
    if headless:
        _launch_args.append('--headless=new')

    launch_kwargs: dict = dict(
        headless=False,
        args=_launch_args,
    )
    if chrome_path:
        launch_kwargs['executable_path'] = chrome_path
    if proxy:
        launch_kwargs['proxy'] = {'server': proxy}

    async with async_playwright() as p:
        browser = await p.chromium.launch(**launch_kwargs)
        ctx = await browser.new_context(viewport=viewport, user_agent=ua)

        await ctx.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )

        page = await ctx.new_page()
        await stealth_async(page)

        # Block heavy resources
        _BLOCK_TYPES = {'image', 'media', 'font', 'websocket', 'other'}
        _BLOCK_DOMAINS = {'doubleclick.net', 'googlesyndication.com',
                          'brave.com/assets/', 'brave.com/fonts/'}

        async def _route(route):
            rt = route.request.resource_type
            url = route.request.url
            if rt in _BLOCK_TYPES or any(d in url for d in _BLOCK_DOMAINS):
                await route.abort()
            else:
                await route.continue_()

        await page.route('**/*', _route)

        print(f"  → UA     : {ua[:80]}…", flush=True)
        print(f"  → View   : {viewport['width']}×{viewport['height']}", flush=True)

        # ── Build URL ─────────────────────────────────────────────────────
        # Brave params:
        #   source=web      → force web tab (not news/images)
        #   country         → ISO 3166-1 alpha-2, lowercase (e.g. "cz")
        #   lang            → ISO 639-1, lowercase (e.g. "cs")
        #   safe_search     → off | moderate | strict
        params = [
            f"q={quote_plus(query)}",
            "source=web",
            f"safe_search={safe_search}",
        ]
        if country:
            params.append(f"country={country.lower()}")
        if lang:
            params.append(f"lang={lang.lower()}")

        search_url = f"https://search.brave.com/search?{'&'.join(params)}"
        print(f"  → {search_url}", flush=True)
        await page.goto(search_url, wait_until='domcontentloaded', timeout=30000)

        # ── Wait for results ──────────────────────────────────────────────
        try:
            await page.wait_for_selector(
                '#results div.snippet, #results article, #results .web-result',
                timeout=15000
            )
        except Exception:
            body = await page.evaluate('document.body.innerText') or ''
            await browser.close()
            if _is_blocked(page.url, body):
                raise RuntimeError("Brave Search blocked the request (rate limit).")
            raise RuntimeError("Brave results did not load in time.")

        try:
            await page.wait_for_load_state('networkidle', timeout=8000)
        except Exception:
            pass  # results already loaded; Brave tracking keeps connections alive

        # ── Human behaviour ───────────────────────────────────────────────
        vp = page.viewport_size or {'width': 1280, 'height': 900}
        await _human_mouse_move(
            page,
            random.uniform(150, min(650, vp['width'] - 100)),
            random.uniform(180, min(430, vp['height'] - 100)),
        )
        await asyncio.sleep(random.uniform(0.3, 0.8))
        await _human_scroll(page, count=random.randint(2, 3))

        # ── Extract ───────────────────────────────────────────────────────
        result = await page.evaluate(_EXTRACT_JS)
        await browser.close()

    result['organic'] = result['organic'][:num]
    return result


# ── Public API ────────────────────────────────────────────────────────────────

def scrape(
    query: str,
    country: str | None = 'cz',
    lang: str | None = 'cs',
    num: int = 10,
    safe_search: str = 'off',
    proxy: str | None = _DEFAULT_PROXY,
    headless: bool = True,
    chrome_path: str | None = None,
) -> dict:
    """
    Scrape Brave Search and return dict with keys:
      organic     : list of {position, title, url, description}
      related     : list of str (related queries)
      status      : 'SUCCESS' | 'ERROR'
      error       : str
      country     : str | None
      lang        : str | None
      query       : str
    """
    if chrome_path is None:
        chrome_path = _find_chrome()
    try:
        data = asyncio.run(
            _scrape(query, country, lang, num, safe_search, proxy, headless, chrome_path)
        )
        data['status'] = 'SUCCESS'
        data['error'] = ''
        data['country'] = country
        data['lang'] = lang
        data['query'] = query
        return data
    except Exception as e:
        return {
            'organic': [], 'related': [],
            'status': 'ERROR', 'error': str(e),
            'country': country, 'lang': lang, 'query': query,
        }


def scrape_with_pause(
    query: str,
    country: str | None = 'cz',
    lang: str | None = 'cs',
    num: int = 10,
    safe_search: str = 'off',
    proxy: str | None = _DEFAULT_PROXY,
    headless: bool = True,
    chrome_path: str | None = None,
    pause_min: int = 4,
    pause_max: int = 10,
) -> dict:
    wait = random.uniform(pause_min, pause_max)
    print(f"  ⏳ Waiting {wait:.1f}s before \"{query}\"…", file=sys.stderr)
    time.sleep(wait)
    return scrape(query, country=country, lang=lang, num=num,
                  safe_search=safe_search, proxy=proxy,
                  headless=headless, chrome_path=chrome_path)


# ── Formatting ────────────────────────────────────────────────────────────────

def _print_table(title, headers, rows):
    if not rows:
        print(f"\n{title}\n  (no results)\n")
        return
    widths = [max(len(str(rows[r][c])) for r in range(len(rows))) for c in range(len(headers))]
    widths = [max(widths[i], len(headers[i])) for i in range(len(headers))]
    sep = '+-' + '-+-'.join('-'*w for w in widths) + '-+'
    fmt = '| ' + ' | '.join(f'{{:<{w}}}' for w in widths) + ' |'
    print(f"\n{'='*len(sep)}\n{title}\n{'='*len(sep)}")
    print(sep); print(fmt.format(*headers)); print(sep)
    for row in rows:
        print(fmt.format(*[str(c)[:widths[i]] for i, c in enumerate(row)]))
    print(sep)


def print_results(data: dict):
    query = data.get('query', '')
    country = data.get('country', '')
    lang = data.get('lang', '')
    locale = f"country={country} lang={lang}" if (country or lang) else 'no locale'
    _print_table(
        f'ORGANIC — "{query}"  ({locale})',
        ['#', 'Title', 'Description', 'URL'],
        [[r['position'], r['title'][:55], r['description'][:75], r['url'][:65]]
         for r in data['organic']],
    )
    _print_table(
        'RELATED QUERIES', ['#', 'Query'],
        [[i+1, x] for i, x in enumerate(data['related'])],
    )


# ── CSV export ────────────────────────────────────────────────────────────────

def save_csv(data: dict, output_dir: str) -> list[str]:
    query = data.get('query', 'query')
    country = data.get('country', '') or ''
    lang = data.get('lang', '') or ''
    out = Path(output_dir).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    slug = query.replace(' ', '_')[:40]
    paths = []

    if data['organic']:
        p = out / f"brave_organic_{slug}_{ts}.csv"
        with open(p, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(
                f, fieldnames=['position', 'title', 'description', 'url', 'country', 'lang', 'query']
            )
            w.writeheader()
            for row in data['organic']:
                w.writerow({**row, 'country': country, 'lang': lang, 'query': query})
        paths.append(str(p)); print(f"Organic CSV : {p}")

    if data['related']:
        p = out / f"brave_related_{slug}_{ts}.csv"
        with open(p, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['position', 'query_text', 'country', 'lang', 'search_query'])
            for i, x in enumerate(data['related'], 1):
                w.writerow([i, x, country, lang, query])
        paths.append(str(p)); print(f"Related CSV : {p}")

    p = out / f"brave_status_{slug}_{ts}.csv"
    with open(p, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(
            f, fieldnames=['keyword', 'status', 'error_message',
                           'results_count', 'country', 'lang']
        )
        w.writeheader()
        w.writerow({
            'keyword': query, 'status': data.get('status', 'SUCCESS'),
            'error_message': data.get('error', ''),
            'results_count': len(data.get('organic', [])),
            'country': country, 'lang': lang,
        })
    paths.append(str(p)); print(f"Status CSV  : {p}")
    return paths


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Brave Search SERP scraper — Playwright + stealth + human mouse',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Czech results
  python brave_serp.py "seo nástroje" --country cz --lang cs

  # US English
  python brave_serp.py "keyword research" --country us --lang en

  # No locale (international, Brave default)
  python brave_serp.py "SEO tools"

  # German, 20 results, visible window
  python brave_serp.py "SEO" --country de --lang de --num 20 --no-headless

  # With SOCKS5 proxy
  python brave_serp.py "query" --proxy socks5://127.0.0.1:1080

Country (--country):  cz sk us gb au ca de at fr pl es it nl br ru hu se dk fi
Language (--lang):    cs sk en de fr pl es it nl pt ru hu sv da fi ja ko zh
""",
    )
    parser.add_argument('query', help='Search query')
    parser.add_argument('--country', default=None, metavar='CC',
                        help='Country code (ISO 3166-1 alpha-2, e.g. cz, us, de)')
    parser.add_argument('--lang', default=None, metavar='LANG',
                        help='Language code (ISO 639-1, e.g. cs, en, de)')
    parser.add_argument('--num', type=int, default=10,
                        help='Number of results (default: 10, max: 20)')
    parser.add_argument('--safe-search', default='off',
                        choices=['off', 'moderate', 'strict'],
                        help='Safe search level (default: off)')
    parser.add_argument('--proxy', default=None)
    parser.add_argument('--no-headless', dest='headless', action='store_false')
    parser.add_argument('--chrome', default=None)
    parser.add_argument('--output', default='~/google_serp_outputs')
    parser.add_argument('--no-csv', action='store_true')
    parser.add_argument('--json', dest='json_out', action='store_true')
    parser.set_defaults(headless=True)
    args = parser.parse_args()

    chrome = args.chrome or _find_chrome()
    num = max(1, min(args.num, 20))

    locale_str = ''
    if args.country:
        locale_str += f'country={args.country}'
    if args.lang:
        locale_str += f'{" " if locale_str else ""}lang={args.lang}'

    print(f"Scraping : \"{args.query}\"")
    print(f"Locale   : {locale_str or '(none — Brave default)'}")
    print(f"Num      : {num}")
    print(f"Safe     : {args.safe_search}")
    print(f"Chrome   : {chrome or '(bundled Chromium)'}")
    print(f"Headless : {args.headless}")
    print(f"Stealth  : {_STEALTH_MODE}")
    if args.proxy:
        print(f"Proxy    : {args.proxy}")

    data = scrape(
        args.query,
        country=args.country,
        lang=args.lang,
        num=num,
        safe_search=args.safe_search,
        proxy=args.proxy,
        headless=args.headless,
        chrome_path=chrome,
    )

    if data['status'] == 'ERROR':
        print(f"\n❌ {data['error']}", file=sys.stderr)
        sys.exit(1)

    print(f"\n✅ organic={len(data['organic'])} related={len(data['related'])}")
    print_results(data)

    if args.json_out:
        print(json.dumps(data, ensure_ascii=False, indent=2))

    if not args.no_csv:
        save_csv(data, args.output)


if __name__ == '__main__':
    main()
