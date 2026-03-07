#!/usr/bin/env python3
"""
Bing SERP scraper — v1
Playwright + playwright-stealth + randomised UA/viewport.

Extracts: organic results, People Also Ask, related searches.
Bing is more lenient than Google but still detects headless browsers.

Language/locale is set via the --mkt parameter (BCP-47 market code).
Use --mkt directly  or  --lang + --country  (auto-converted).

Usage:
  python bing_serp.py "seo nástroje" --mkt cs-CZ
  python bing_serp.py "seo tools" --lang en --country us --num 30
  python bing_serp.py "Keyword" --mkt de-DE --no-headless

Common mkt codes (BCP-47: {lang}-{COUNTRY}):
  cs-CZ  Czech / Czech Republic    sk-SK  Slovak / Slovakia
  en-US  English / United States   en-GB  English / United Kingdom
  en-AU  English / Australia       en-CA  English / Canada
  de-DE  German / Germany          de-AT  German / Austria
  fr-FR  French / France           fr-BE  French / Belgium
  pl-PL  Polish / Poland           nl-NL  Dutch / Netherlands
  es-ES  Spanish / Spain           it-IT  Italian / Italy
  pt-BR  Portuguese / Brazil       ru-RU  Russian / Russia
  hu-HU  Hungarian / Hungary       sv-SE  Swedish / Sweden
  da-DK  Danish / Denmark          fi-FI  Finnish / Finland
  nb-NO  Norwegian / Norway        ja-JP  Japanese / Japan
  ko-KR  Korean / South Korea      zh-CN  Chinese / China

Notes:
  --num: 1–50 per request (Bing hard-cap). Paginated fetches not yet supported.
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


# ── Market code helpers ───────────────────────────────────────────────────────

# Bing uses BCP-47 format: {lang}-{COUNTRY_UPPER}, e.g. "cs-CZ", "en-US"
_MKT_MAP: dict[tuple[str, str], str] = {
    ('cs', 'cz'): 'cs-CZ',
    ('sk', 'sk'): 'sk-SK',
    ('en', 'us'): 'en-US',
    ('en', 'gb'): 'en-GB',
    ('en', 'au'): 'en-AU',
    ('en', 'ca'): 'en-CA',
    ('en', 'in'): 'en-IN',
    ('de', 'de'): 'de-DE',
    ('de', 'at'): 'de-AT',
    ('de', 'ch'): 'de-CH',
    ('fr', 'fr'): 'fr-FR',
    ('fr', 'be'): 'fr-BE',
    ('fr', 'ch'): 'fr-CH',
    ('nl', 'nl'): 'nl-NL',
    ('nl', 'be'): 'nl-BE',
    ('pl', 'pl'): 'pl-PL',
    ('es', 'es'): 'es-ES',
    ('es', 'mx'): 'es-MX',
    ('it', 'it'): 'it-IT',
    ('pt', 'br'): 'pt-BR',
    ('pt', 'pt'): 'pt-PT',
    ('ru', 'ru'): 'ru-RU',
    ('hu', 'hu'): 'hu-HU',
    ('ro', 'ro'): 'ro-RO',
    ('sv', 'se'): 'sv-SE',
    ('da', 'dk'): 'da-DK',
    ('fi', 'fi'): 'fi-FI',
    ('nb', 'no'): 'nb-NO',
    ('ja', 'jp'): 'ja-JP',
    ('zh', 'cn'): 'zh-CN',
    ('zh', 'tw'): 'zh-TW',
    ('ko', 'kr'): 'ko-KR',
    ('tr', 'tr'): 'tr-TR',
    ('ar', 'sa'): 'ar-SA',
}


def lang_country_to_mkt(lang: str, country: str) -> str:
    """Convert lang + country to Bing market code. Falls back to '{lang}-{COUNTRY}'."""
    key = (lang.lower(), country.lower())
    if key in _MKT_MAP:
        return _MKT_MAP[key]
    return f'{lang.lower()}-{country.upper()}'


# ── Block detection ───────────────────────────────────────────────────────────

def _is_blocked(url: str, body: str) -> bool:
    if 'bing.com/sorry' in url or '/rewso/' in url:
        return True
    b = body.lower()
    return any(s in b for s in [
        'automated queries',
        'unusual activity',
        'captcha',
        'access denied',
        'too many requests',
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

    // ── Organic: li.b_algo in #b_results ─────────────────────────────────
    const items = document.querySelectorAll('#b_results > li.b_algo');
    for (const item of items) {
        const link = item.querySelector('h2 a[href]');
        if (!link) continue;

        // Bing often wraps URLs through bing.com/ck/a?... redirect.
        // Try to get the real URL from the cite element first.
        let url = '';
        const cite = item.querySelector('cite');
        if (cite) {
            let citeText = (cite.innerText || cite.textContent || '').trim();
            // cite may show truncated URL like "www.example.com › path"
            // convert to a proper URL
            citeText = citeText.replace(/\s*›\s*/g, '/');
            if (citeText && !citeText.includes('bing.com')) {
                url = citeText.startsWith('http') ? citeText : 'https://' + citeText;
            }
        }
        // Fallback: use the link href if it's not a bing redirect
        if (!url) {
            const rawHref = link.href || '';
            if (rawHref && !rawHref.includes('bing.com/') && !rawHref.includes('microsoft.com/')) {
                url = rawHref;
            }
        }
        if (!url || seenUrls.has(url)) continue;
        seenUrls.add(url);

        const title = (link.innerText || link.textContent || '').trim();
        if (title.length < 3) continue;

        // Snippet: try several Bing snippet classes
        const snip = item.querySelector('.b_caption p')
                  || item.querySelector('.b_algoSlug')
                  || item.querySelector('.b_snippet p')
                  || item.querySelector('p');
        const description = snip ? snip.innerText.trim().substring(0, 300) : '';

        organic.push({ position: organic.length + 1, title, url, description });
    }

    // ── Related searches ──────────────────────────────────────────────────
    const related = [];
    const seenRel = new Set();

    // Bing related: sidebar .b_rs list, or inline #relatedSearchesLi
    const relEls = document.querySelectorAll(
        '.b_rs li a, #relatedSearchesLi a, .b_relatedSearches a'
    );
    for (const el of relEls) {
        const t = (el.innerText || el.textContent || '').trim();
        if (t && t.length > 2 && t.length < 150 && !seenRel.has(t)) {
            seenRel.add(t);
            related.push(t);
        }
    }

    // ── People Also Ask ───────────────────────────────────────────────────
    const paa = [];
    const seenPaa = new Set();

    // Bing PAA: .df_ques buttons (expandable panel), or newer .b_expando
    const paaEls = document.querySelectorAll(
        '.df_ques button, .df_ques .b_expando_title, ' +
        '[data-tag="RelatedSearches"] a'
    );
    for (const el of paaEls) {
        const t = (el.innerText || el.textContent || '').trim();
        if (t && t.length > 8 && t.length < 200 && !seenPaa.has(t)) {
            seenPaa.add(t);
            paa.push(t);
        }
    }

    return { organic, related, paa };
})()
'''


# ── Core scraper ──────────────────────────────────────────────────────────────

async def _scrape(
    query: str,
    mkt: str,
    num: int,
    proxy: str | None,
    headless: bool,
    chrome_path: str | None,
) -> dict:
    from playwright.async_api import async_playwright

    ua, viewport = _pick_ua_and_viewport()
    count = min(num, 50)  # Bing hard-cap per page

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

        # Block bandwidth-heavy resources
        _BLOCK_TYPES = {'image', 'media', 'font', 'websocket', 'other'}
        _BLOCK_DOMAINS = {'doubleclick.net', 'bat.bing.com', 'clarity.ms',
                          'bing.com/fd/', 'bing.com/th/'}

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

        # ── Navigate ──────────────────────────────────────────────────────
        # mkt   = language/region for results ranking
        # setlang = UI language (extracted from mkt lang part)
        lang_part = mkt.split('-')[0]   # "cs" from "cs-CZ"
        search_url = (
            f"https://www.bing.com/search"
            f"?q={quote_plus(query)}"
            f"&mkt={mkt}"
            f"&setlang={lang_part}"
            f"&count={count}"
            f"&safeSearch=Off"
        )
        print(f"  → {search_url}", flush=True)
        await page.goto(search_url, wait_until='domcontentloaded', timeout=30000)

        # ── Cookie/consent banner (Bing shows this in EU) ─────────────────
        for selector in [
            'button#bnp_btn_accept',      # "Accept all"
            'button[id*="accept"]',
            'button:has-text("Accept")',
            'button:has-text("Akceptovat")',
            'button:has-text("Souhlasím")',
        ]:
            try:
                btn = await page.wait_for_selector(selector, timeout=1500)
                await btn.click()
                print(f"  → Cookie consent dismissed", flush=True)
                break
            except Exception:
                pass

        # ── Wait for results ──────────────────────────────────────────────
        try:
            await page.wait_for_selector('#b_results li.b_algo', timeout=15000)
        except Exception:
            body = await page.evaluate('document.body.innerText') or ''
            await browser.close()
            if _is_blocked(page.url, body):
                raise RuntimeError("Bing blocked the request.")
            raise RuntimeError("Bing results did not load in time.")

        try:
            await page.wait_for_load_state('networkidle', timeout=10000)
        except Exception:
            pass  # results already loaded; Bing tracking keeps connections alive

        # ── Human behaviour ───────────────────────────────────────────────
        vp = page.viewport_size or {'width': 1280, 'height': 900}
        await _human_mouse_move(
            page,
            random.uniform(150, min(650, vp['width'] - 100)),
            random.uniform(180, min(430, vp['height'] - 100)),
        )
        await asyncio.sleep(random.uniform(0.4, 0.9))
        await _human_scroll(page, count=random.randint(2, 4))
        for _ in range(random.randint(1, 2)):
            await _human_mouse_move(
                page,
                random.uniform(80, vp['width'] - 80),
                random.uniform(80, vp['height'] - 80),
            )
            await asyncio.sleep(random.uniform(0.15, 0.4))

        # ── Extract ───────────────────────────────────────────────────────
        result = await page.evaluate(_EXTRACT_JS)
        await browser.close()

    result['organic'] = result['organic'][:num]
    return result


# ── Public API ────────────────────────────────────────────────────────────────

def scrape(
    query: str,
    mkt: str = 'cs-CZ',
    num: int = 10,
    proxy: str | None = _DEFAULT_PROXY,
    headless: bool = True,
    chrome_path: str | None = None,
) -> dict:
    """
    Scrape Bing and return dict with keys:
      organic  : list of {position, title, url, description}
      related  : list of str
      paa      : list of str (People Also Ask questions)
      status   : 'SUCCESS' | 'ERROR'
      error    : str
      mkt      : str (market used)
      query    : str
    """
    if chrome_path is None:
        chrome_path = _find_chrome()
    try:
        data = asyncio.run(_scrape(query, mkt, num, proxy, headless, chrome_path))
        data['status'] = 'SUCCESS'
        data['error'] = ''
        data['mkt'] = mkt
        data['query'] = query
        return data
    except Exception as e:
        return {
            'organic': [], 'related': [], 'paa': [],
            'status': 'ERROR', 'error': str(e),
            'mkt': mkt, 'query': query,
        }


def scrape_with_pause(
    query: str,
    mkt: str = 'cs-CZ',
    num: int = 10,
    proxy: str | None = _DEFAULT_PROXY,
    headless: bool = True,
    chrome_path: str | None = None,
    pause_min: int = 5,
    pause_max: int = 12,
) -> dict:
    wait = random.uniform(pause_min, pause_max)
    print(f"  ⏳ Waiting {wait:.1f}s before \"{query}\"…", file=sys.stderr)
    time.sleep(wait)
    return scrape(query, mkt=mkt, num=num, proxy=proxy,
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
    mkt = data.get('mkt', '')
    _print_table(
        f'ORGANIC — "{query}"  (mkt={mkt})',
        ['#', 'Title', 'Description', 'URL'],
        [[r['position'], r['title'][:55], r['description'][:75], r['url'][:65]]
         for r in data['organic']],
    )
    _print_table(
        'PEOPLE ALSO ASK', ['#', 'Question'],
        [[i+1, q] for i, q in enumerate(data['paa'][:10])],
    )
    _print_table(
        'RELATED SEARCHES', ['#', 'Query'],
        [[i+1, x] for i, x in enumerate(data['related'])],
    )


# ── CSV export ────────────────────────────────────────────────────────────────

def save_csv(data: dict, output_dir: str) -> list[str]:
    query = data.get('query', 'query')
    mkt = data.get('mkt', '')
    out = Path(output_dir).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    slug = query.replace(' ', '_')[:40]
    paths = []

    if data['organic']:
        p = out / f"bing_organic_{slug}_{ts}.csv"
        with open(p, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=['position', 'title', 'description', 'url', 'mkt', 'query'])
            w.writeheader()
            for row in data['organic']:
                w.writerow({**row, 'mkt': mkt, 'query': query})
        paths.append(str(p)); print(f"Organic CSV : {p}")

    if data['paa']:
        p = out / f"bing_paa_{slug}_{ts}.csv"
        with open(p, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['position', 'question', 'mkt', 'query'])
            for i, q in enumerate(data['paa'], 1):
                w.writerow([i, q, mkt, query])
        paths.append(str(p)); print(f"PAA CSV     : {p}")

    if data['related']:
        p = out / f"bing_related_{slug}_{ts}.csv"
        with open(p, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['position', 'query_text', 'mkt', 'search_query'])
            for i, x in enumerate(data['related'], 1):
                w.writerow([i, x, mkt, query])
        paths.append(str(p)); print(f"Related CSV : {p}")

    p = out / f"bing_status_{slug}_{ts}.csv"
    with open(p, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['keyword', 'status', 'error_message', 'results_count', 'mkt'])
        w.writeheader()
        w.writerow({
            'keyword': query, 'status': data.get('status', 'SUCCESS'),
            'error_message': data.get('error', ''),
            'results_count': len(data.get('organic', [])), 'mkt': mkt,
        })
    paths.append(str(p)); print(f"Status CSV  : {p}")
    return paths


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Bing SERP scraper — Playwright + stealth + human mouse',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Czech results
  python bing_serp.py "seo nástroje" --mkt cs-CZ

  # US English, 30 results
  python bing_serp.py "keyword research" --mkt en-US --num 30

  # Use lang + country instead of mkt
  python bing_serp.py "SEO" --lang de --country de

  # Visible window for debugging
  python bing_serp.py "query" --no-headless

  # With proxy
  python bing_serp.py "query" --proxy socks5://127.0.0.1:1080

Market codes (--mkt):
  cs-CZ  en-US  en-GB  de-DE  de-AT  fr-FR  pl-PL  sk-SK
  es-ES  it-IT  nl-NL  pt-BR  ru-RU  hu-HU  ja-JP  ko-KR
""",
    )
    parser.add_argument('query', help='Search query')

    locale_group = parser.add_mutually_exclusive_group()
    locale_group.add_argument('--mkt', default=None,
                              help='Bing market code (default: cs-CZ). E.g. en-US, de-DE')
    locale_group.add_argument('--lang', default=None, metavar='LANG',
                              help='Language code — use with --country')

    parser.add_argument('--country', default=None, metavar='CC',
                        help='Country code — use with --lang')
    parser.add_argument('--num', type=int, default=10,
                        help='Results to fetch (default: 10, max: 50)')
    parser.add_argument('--proxy', default=None)
    parser.add_argument('--no-headless', dest='headless', action='store_false')
    parser.add_argument('--chrome', default=None)
    parser.add_argument('--output', default='~/google_serp_outputs')
    parser.add_argument('--no-csv', action='store_true')
    parser.add_argument('--json', dest='json_out', action='store_true')
    parser.set_defaults(headless=True)
    args = parser.parse_args()

    if args.mkt:
        mkt = args.mkt
    elif args.lang and args.country:
        mkt = lang_country_to_mkt(args.lang, args.country)
    elif args.lang:
        mkt = lang_country_to_mkt(args.lang, args.lang)
    else:
        mkt = 'cs-CZ'

    chrome = args.chrome or _find_chrome()
    num = max(1, min(args.num, 50))

    print(f"Scraping : \"{args.query}\"")
    print(f"Market   : {mkt}")
    print(f"Num      : {num}")
    print(f"Chrome   : {chrome or '(bundled Chromium)'}")
    print(f"Headless : {args.headless}")
    print(f"Stealth  : {_STEALTH_MODE}")
    if args.proxy:
        print(f"Proxy    : {args.proxy}")

    data = scrape(args.query, mkt=mkt, num=num, proxy=args.proxy,
                  headless=args.headless, chrome_path=chrome)

    if data['status'] == 'ERROR':
        print(f"\n❌ {data['error']}", file=sys.stderr)
        sys.exit(1)

    print(f"\n✅ organic={len(data['organic'])} paa={len(data['paa'])} related={len(data['related'])}")
    print_results(data)

    if args.json_out:
        print(json.dumps(data, ensure_ascii=False, indent=2))

    if not args.no_csv:
        save_csv(data, args.output)


if __name__ == '__main__':
    main()
