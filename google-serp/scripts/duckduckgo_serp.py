#!/usr/bin/env python3
"""
DuckDuckGo SERP scraper — v1
Playwright + playwright-stealth + randomised UA/viewport.
No profile rotation needed — DDG is far more lenient than Google.

Modes
  default   : Full JS version (duckduckgo.com) — richer, supports num > 10 via scroll
  --html-mode: Lite HTML version (html.duckduckgo.com) — faster, zero-JS, always 10 results

Language/locale is set via the DDG `kl` parameter (country-lang code).
Use --kl directly  or  --lang + --country  (auto-converted).

Usage:
  python duckduckgo_serp.py "seo nástroje"
  python duckduckgo_serp.py "seo tools" --kl us-en --num 20
  python duckduckgo_serp.py "SEO" --lang en --country gb
  python duckduckgo_serp.py "Keyword" --html-mode --kl de-de

Common kl codes:
  cz-cs  Czech Republic / Czech        sk-sk  Slovakia / Slovak
  us-en  United States / English       gb-en  United Kingdom / English
  de-de  Germany / German              at-de  Austria / German
  pl-pl  Poland / Polish               fr-fr  France / French
  es-es  Spain / Spanish               it-it  Italy / Italian
  nl-nl  Netherlands / Dutch           br-pt  Brazil / Portuguese
  ru-ru  Russia / Russian              hu-hu  Hungary / Hungarian
  wt-wt  (no region — international)
"""

import asyncio
import argparse
import csv
import json
import random
import re
import time
import sys
import os
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

# ── Default proxy (Tailscale → Home Assistant residential IP) ─────────────────
# autossh SOCKS5 tunnel: Hetzner → Tailscale → Home Assistant (100.81.216.51)
# Docker containers reach host via bridge IP 172.18.0.1
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


# ── Realistic UA + viewport pool ──────────────────────────────────────────────

_RANDOM_UAS = [
    # Windows — Chrome 120–132
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36',
    # macOS — Chrome 120–132
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36',
    # Linux — Chrome 120–132
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
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


# ── Chrome binary discovery ───────────────────────────────────────────────────

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


# ── Locale helpers ────────────────────────────────────────────────────────────

# Most common lang+country → DDG kl mapping.
# DDG format is always {country}-{lang}, e.g. "cz-cs", "us-en"
_KL_MAP: dict[tuple[str, str], str] = {
    ('cs', 'cz'): 'cz-cs',
    ('sk', 'sk'): 'sk-sk',
    ('en', 'us'): 'us-en',
    ('en', 'gb'): 'gb-en',
    ('en', 'au'): 'au-en',
    ('en', 'ca'): 'ca-en',
    ('de', 'de'): 'de-de',
    ('de', 'at'): 'at-de',
    ('de', 'ch'): 'ch-de',
    ('fr', 'fr'): 'fr-fr',
    ('fr', 'be'): 'be-fr',
    ('fr', 'ch'): 'ch-fr',
    ('nl', 'nl'): 'nl-nl',
    ('nl', 'be'): 'be-nl',
    ('pl', 'pl'): 'pl-pl',
    ('es', 'es'): 'es-es',
    ('es', 'mx'): 'mx-es',
    ('it', 'it'): 'it-it',
    ('pt', 'br'): 'br-pt',
    ('pt', 'pt'): 'pt-pt',
    ('ru', 'ru'): 'ru-ru',
    ('hu', 'hu'): 'hu-hu',
    ('ro', 'ro'): 'ro-ro',
    ('sv', 'se'): 'se-sv',
    ('da', 'dk'): 'dk-da',
    ('fi', 'fi'): 'fi-fi',
    ('nb', 'no'): 'no-nb',
    ('ja', 'jp'): 'jp-jp',
    ('zh', 'cn'): 'cn-zh',
    ('zh', 'tw'): 'tw-tzh',
    ('ko', 'kr'): 'kr-kr',
}


def lang_country_to_kl(lang: str, country: str) -> str:
    """Convert lang + country codes to DDG kl locale. Falls back to '{country}-{lang}'."""
    key = (lang.lower(), country.lower())
    if key in _KL_MAP:
        return _KL_MAP[key]
    # Fallback: DDG uses country-lang order
    return f'{country.lower()}-{lang.lower()}'


# ── Block / rate-limit detection ──────────────────────────────────────────────

def _is_blocked(url: str, body: str) -> bool:
    if 'duckduckgo.com/sorry' in url:
        return True
    b = body.lower()
    return any(s in b for s in [
        'unusual traffic',
        'rate limit',
        'access denied',
        'too many requests',
    ])


# ── Human-like mouse movement (identical to v4) ───────────────────────────────

def _bezier_point(t: float, p0, p1, p2, p3) -> tuple[float, float]:
    mt = 1.0 - t
    x = mt**3 * p0[0] + 3*mt**2*t * p1[0] + 3*mt*t**2 * p2[0] + t**3 * p3[0]
    y = mt**3 * p0[1] + 3*mt**2*t * p1[1] + 3*mt*t**2 * p2[1] + t**3 * p3[1]
    return x, y


async def _human_mouse_move(page, target_x: float, target_y: float,
                             steps: int | None = None):
    if steps is None:
        steps = random.randint(18, 35)
    vp = page.viewport_size or {'width': 1280, 'height': 900}
    start_x = random.uniform(vp['width'] * 0.15, vp['width'] * 0.85)
    start_y = random.uniform(vp['height'] * 0.15, vp['height'] * 0.75)
    cp1 = (start_x + random.uniform(-120, 120), start_y + random.uniform(-80, 80))
    cp2 = (target_x + random.uniform(-90, 90), target_y + random.uniform(-70, 70))
    for i in range(1, steps + 1):
        t = i / steps
        t_smooth = t * t * (3.0 - 2.0 * t)
        px, py = _bezier_point(t_smooth, (start_x, start_y), cp1, cp2, (target_x, target_y))
        await page.mouse.move(px, py)
        edge_factor = 1.0 + 1.2 * abs(t - 0.5)
        await asyncio.sleep(random.uniform(4, 18) * edge_factor / 1000)


async def _human_scroll(page, count: int = 3):
    for _ in range(count):
        delta = random.randint(250, 500)
        await page.mouse.wheel(0, delta)
        await asyncio.sleep(random.uniform(0.3, 0.8))


# ── JS extraction for full DDG ────────────────────────────────────────────────

_EXTRACT_JS = '''
(() => {
    const organic = [];
    const seenUrls = new Set();

    // ── Organic results ───────────────────────────────────────────────────
    // Strategy: find all heading-level links pointing to external URLs.
    // Covers: article[data-testid="result"], li[data-layout], .result.result--web
    const titleLinks = Array.from(document.querySelectorAll(
        '[data-testid="result-title-a"], h3 a[href], h2 a[href]'
    ));

    for (const link of titleLinks) {
        const href = link.href || '';
        // Skip DDG-internal, anchors, JS links
        if (!href || href.startsWith('https://duckduckgo.com') ||
            href.startsWith('/') || href.startsWith('#') ||
            href.startsWith('javascript')) continue;

        // DDG wraps external URLs in a redirect — decode if needed
        let url = href;
        try {
            const u = new URL(href);
            // DDG redirect: //duckduckgo.com/l/?uddg=...
            const uddg = u.searchParams.get('uddg') || u.searchParams.get('u3');
            if (uddg) url = decodeURIComponent(uddg);
        } catch(e) {}

        if (seenUrls.has(url)) continue;
        seenUrls.add(url);

        const title = link.innerText?.trim() || link.textContent?.trim() || '';
        if (title.length < 3) continue;

        // Walk up to find the result container for the snippet
        const container = link.closest('article')
                       || link.closest('li[data-layout]')
                       || link.closest('.result')
                       || link.closest('[class*="result"]');

        let description = '';
        if (container) {
            const snip = container.querySelector(
                '[data-testid="result-snippet"],' +
                '.result__snippet,' +
                'span[class*="snippet"],' +
                'div[class*="snippet"]'
            );
            description = snip?.innerText?.trim().substring(0, 300) || '';

            // Fallback: first non-title <span> or <p> with reasonable length
            if (!description) {
                for (const el of container.querySelectorAll('span, p')) {
                    const t = el.innerText?.trim() || '';
                    if (t.length > 30 && t.length < 400 && t !== title) {
                        description = t.substring(0, 300);
                        break;
                    }
                }
            }
        }

        organic.push({ position: organic.length + 1, title, url, description });
    }

    // ── Related searches ──────────────────────────────────────────────────
    const related = [];
    const seenRel = new Set();

    // DDG shows related searches as chips (top or bottom) in various layouts
    const relSels = [
        '[data-testid="related-searches-chip"]',
        '[class*="RelatedSearch"] a',
        '.related-searches__item a',
        '.related-searches a',
        '[aria-label*="related"] a',
        '[class*="related-search"] a',
    ];

    for (const sel of relSels) {
        const els = document.querySelectorAll(sel);
        for (const el of els) {
            const t = (el.innerText || el.textContent || el.getAttribute('value') || '').trim();
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


# ── HTML parsing for lite mode ────────────────────────────────────────────────

def _parse_html_results(html: str) -> dict:
    """
    Parse html.duckduckgo.com response (plain HTML, no JavaScript).
    Selectors are stable and have barely changed in years.
    """
    organic = []
    related = []

    # Organic: each result is in <div class="result result--web ...">
    result_blocks = re.findall(
        r'<div[^>]+class="[^"]*result[^"]*result--web[^"]*"[^>]*>(.*?)</div>\s*</div>\s*</div>',
        html, re.DOTALL
    )

    for i, block in enumerate(result_blocks, 1):
        # Title + URL
        title_match = re.search(
            r'class="[^"]*result__title[^"]*"[^>]*>.*?<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
            block, re.DOTALL
        )
        if not title_match:
            continue
        raw_url = title_match.group(1)
        title = re.sub(r'<[^>]+>', '', title_match.group(2)).strip()

        # Decode DDG redirect URLs
        url = raw_url
        uddg = re.search(r'[?&]uddg=([^&]+)', raw_url)
        if uddg:
            from urllib.parse import unquote
            url = unquote(uddg.group(1))

        # Snippet
        snip_match = re.search(
            r'class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</[a-z]+>',
            block, re.DOTALL
        )
        description = ''
        if snip_match:
            description = re.sub(r'<[^>]+>', '', snip_match.group(1)).strip()[:300]

        if title and url:
            organic.append({'position': i, 'title': title, 'url': url, 'description': description})

    # Related: in a section with class "related-searches" or similar
    rel_matches = re.findall(
        r'<a[^>]+href="[^"]*q=([^"&]+)[^"]*"[^>]*class="[^"]*related-searches[^"]*"[^>]*>(.*?)</a>',
        html, re.DOTALL | re.IGNORECASE
    )
    for q, text in rel_matches:
        from urllib.parse import unquote_plus
        t = re.sub(r'<[^>]+>', '', text).strip() or unquote_plus(q).strip()
        if t and len(t) > 2:
            related.append(t)

    return {'organic': organic, 'related': related}


# ── Core scrapers ─────────────────────────────────────────────────────────────

async def _scrape_js(
    query: str,
    kl: str,
    num: int,
    proxy: str | None,
    headless: bool,
    chrome_path: str | None,
) -> dict:
    """Full JS scrape via duckduckgo.com."""
    from playwright.async_api import async_playwright

    ua, viewport = _pick_ua_and_viewport()

    launch_args = [
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
        launch_args.append('--headless=new')

    launch_kwargs: dict = dict(
        headless=False,
        args=launch_args,
    )
    if chrome_path:
        launch_kwargs['executable_path'] = chrome_path
    if proxy:
        launch_kwargs['proxy'] = {'server': proxy}

    async with async_playwright() as p:
        browser = await p.chromium.launch(**launch_kwargs)
        ctx = await browser.new_context(
            viewport=viewport,
            user_agent=ua,
        )

        # Suppress webdriver flag
        await ctx.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )

        page = await ctx.new_page()
        await stealth_async(page)

        # Block bandwidth-heavy resources
        _BLOCK_TYPES = {'image', 'media', 'font', 'websocket', 'other'}
        _BLOCK_DOMAINS = {'doubleclick.net', 'google-analytics.com',
                          'googletagmanager.com', 'facebook.com'}

        async def _route_handler(route):
            rt = route.request.resource_type
            url = route.request.url
            if rt in _BLOCK_TYPES or any(d in url for d in _BLOCK_DOMAINS):
                await route.abort()
            else:
                await route.continue_()

        await page.route('**/*', _route_handler)

        print(f"  → UA     : {ua[:80]}…", flush=True)
        print(f"  → View   : {viewport['width']}×{viewport['height']}", flush=True)

        # ── Navigate to DDG search ─────────────────────────────────────────
        # kp=-1: safe search off  |  ia=web: force web tab
        search_url = (
            f"https://duckduckgo.com/?q={quote_plus(query)}"
            f"&kl={kl}&kp=-1&ia=web"
        )
        print(f"  → {search_url}", flush=True)
        await page.goto(search_url, wait_until='domcontentloaded', timeout=30000)

        # ── Dismiss cookie / privacy banner if present ─────────────────────
        for label in ['Accept all', 'I Accept', 'Agree', 'Accept']:
            try:
                btn = await page.wait_for_selector(
                    f'button:has-text("{label}")', timeout=1500
                )
                await btn.click()
                print(f"  → Banner dismissed: '{label}'", flush=True)
                break
            except Exception:
                pass

        # ── Wait for first organic result ──────────────────────────────────
        try:
            await page.wait_for_selector(
                '[data-testid="result-title-a"], h3 a, #links .result',
                timeout=15000
            )
        except Exception:
            body = await page.evaluate('document.body.innerText') or ''
            await browser.close()
            if _is_blocked(page.url, body):
                raise RuntimeError("DuckDuckGo blocked the request (rate limit).")
            raise RuntimeError("Results did not load in time.")

        # ── Scroll to load more results if num > 10 ────────────────────────
        if num > 10:
            max_scrolls = min((num // 10) + 2, 8)   # cap at 8 scroll rounds
            for _ in range(max_scrolls):
                # Check current count
                current = await page.evaluate(
                    "document.querySelectorAll('[data-testid=\"result-title-a\"], #links h3 a').length"
                )
                if current >= num:
                    break
                await _human_scroll(page, count=3)
                # Wait for new results to render
                try:
                    await page.wait_for_load_state('networkidle', timeout=5000)
                except Exception:
                    pass
                await asyncio.sleep(random.uniform(0.5, 1.2))

        # ── Simulate human reading behaviour ──────────────────────────────
        vp = page.viewport_size or {'width': 1280, 'height': 900}
        await _human_mouse_move(
            page,
            random.uniform(150, min(650, vp['width'] - 100)),
            random.uniform(180, min(430, vp['height'] - 100)),
        )
        await asyncio.sleep(random.uniform(0.4, 0.9))
        await _human_scroll(page, count=random.randint(1, 3))

        # ── Extract ────────────────────────────────────────────────────────
        result = await page.evaluate(_EXTRACT_JS)
        await browser.close()

    # Trim to requested num
    result['organic'] = result['organic'][:num]
    return result


async def _scrape_html(
    query: str,
    kl: str,
    proxy: str | None,
    headless: bool,
    chrome_path: str | None,
) -> dict:
    """
    Lite scrape via html.duckduckgo.com — plain HTML, no JS rendering.
    Always returns ~10 results; `num` has no effect here.
    """
    from playwright.async_api import async_playwright

    ua, viewport = _pick_ua_and_viewport()

    _html_args = ['--disable-blink-features=AutomationControlled', '--no-first-run']
    if headless:
        _html_args.append('--headless=new')
    launch_kwargs: dict = dict(
        headless=False,
        args=_html_args,
    )
    if chrome_path:
        launch_kwargs['executable_path'] = chrome_path
    if proxy:
        launch_kwargs['proxy'] = {'server': proxy}

    async with async_playwright() as p:
        browser = await p.chromium.launch(**launch_kwargs)
        ctx = await browser.new_context(viewport=viewport, user_agent=ua)
        page = await ctx.new_page()
        await stealth_async(page)

        search_url = (
            f"https://html.duckduckgo.com/html/"
            f"?q={quote_plus(query)}&kl={kl}&kp=-1"
        )
        print(f"  → [HTML mode] {search_url}", flush=True)
        await page.goto(search_url, wait_until='domcontentloaded', timeout=30000)

        html = await page.content()
        await browser.close()

    if _is_blocked(page.url, html):
        raise RuntimeError("DuckDuckGo blocked the request (rate limit).")

    return _parse_html_results(html)


# ── Public API ────────────────────────────────────────────────────────────────

def scrape(
    query: str,
    kl: str = 'cz-cs',
    num: int = 10,
    proxy: str | None = _DEFAULT_PROXY,
    headless: bool = True,
    chrome_path: str | None = None,
    html_mode: bool = False,
) -> dict:
    """
    Scrape DuckDuckGo and return dict with keys:
      organic  : list of {position, title, url, description}
      related  : list of str
      status   : 'SUCCESS' | 'ERROR'
      error    : str (empty on success)
      kl       : str (locale used)
      query    : str
    """
    if chrome_path is None:
        chrome_path = _find_chrome()
    try:
        if html_mode:
            data = asyncio.run(_scrape_html(query, kl, proxy, headless, chrome_path))
        else:
            data = asyncio.run(_scrape_js(query, kl, num, proxy, headless, chrome_path))
        data['status'] = 'SUCCESS'
        data['error'] = ''
        data['kl'] = kl
        data['query'] = query
        return data
    except Exception as e:
        return {
            'organic': [], 'related': [],
            'status': 'ERROR', 'error': str(e),
            'kl': kl, 'query': query,
        }


def scrape_with_pause(
    query: str,
    kl: str = 'cz-cs',
    num: int = 10,
    proxy: str | None = _DEFAULT_PROXY,
    headless: bool = True,
    chrome_path: str | None = None,
    html_mode: bool = False,
    pause_min: int = 6,
    pause_max: int = 14,
) -> dict:
    """Same as scrape() but waits pause_min–pause_max seconds first."""
    wait = random.uniform(pause_min, pause_max)
    print(f"  ⏳ Waiting {wait:.1f}s before \"{query}\"…", file=sys.stderr)
    time.sleep(wait)
    return scrape(query, kl=kl, num=num, proxy=proxy,
                  headless=headless, chrome_path=chrome_path, html_mode=html_mode)


# ── Formatting ────────────────────────────────────────────────────────────────

def _print_table(title: str, headers: list[str], rows: list[list]):
    if not rows:
        print(f"\n{title}\n  (no results)\n")
        return
    widths = [
        max(len(str(rows[r][c])) for r in range(len(rows)))
        for c in range(len(headers))
    ]
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


def print_results(data: dict):
    query = data.get('query', '')
    kl = data.get('kl', '')
    _print_table(
        f'ORGANIC — "{query}"  (kl={kl})',
        ['#', 'Title', 'Description', 'URL'],
        [[r['position'], r['title'][:55], r['description'][:75], r['url'][:65]]
         for r in data['organic']],
    )
    _print_table(
        'RELATED SEARCHES', ['#', 'Query'],
        [[i + 1, x] for i, x in enumerate(data['related'])],
    )


# ── CSV export ────────────────────────────────────────────────────────────────

def save_csv(data: dict, output_dir: str) -> list[str]:
    query = data.get('query', 'query')
    kl = data.get('kl', '')
    out = Path(output_dir).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    slug = query.replace(' ', '_')[:40]
    paths = []

    if data['organic']:
        p = out / f"ddg_organic_{slug}_{ts}.csv"
        with open(p, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(
                f, fieldnames=['position', 'title', 'description', 'url', 'kl', 'query']
            )
            w.writeheader()
            for row in data['organic']:
                w.writerow({**row, 'kl': kl, 'query': query})
        paths.append(str(p))
        print(f"Organic CSV : {p}")

    if data['related']:
        p = out / f"ddg_related_{slug}_{ts}.csv"
        with open(p, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['position', 'query_text', 'kl', 'search_query'])
            for i, x in enumerate(data['related'], 1):
                w.writerow([i, x, kl, query])
        paths.append(str(p))
        print(f"Related CSV : {p}")

    p = out / f"ddg_status_{slug}_{ts}.csv"
    with open(p, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(
            f, fieldnames=['keyword', 'status', 'error_message',
                           'results_count', 'kl']
        )
        w.writeheader()
        w.writerow({
            'keyword': query,
            'status': data.get('status', 'SUCCESS'),
            'error_message': data.get('error', ''),
            'results_count': len(data.get('organic', [])),
            'kl': kl,
        })
    paths.append(str(p))
    print(f"Status CSV  : {p}")
    return paths


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='DuckDuckGo SERP scraper — Playwright + stealth + human mouse',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Czech results
  python duckduckgo_serp.py "seo nástroje" --kl cz-cs

  # US English, 20 results
  python duckduckgo_serp.py "keyword research tools" --kl us-en --num 20

  # Use lang+country instead of kl
  python duckduckgo_serp.py "Keyword" --lang de --country de

  # Fast HTML lite mode (always ~10 results)
  python duckduckgo_serp.py "query" --html-mode

  # With SOCKS5 proxy
  python duckduckgo_serp.py "query" --proxy socks5://127.0.0.1:1080

  # Output JSON only (no CSV)
  python duckduckgo_serp.py "query" --json --no-csv

Locale codes (--kl):
  cz-cs us-en gb-en de-de at-de fr-fr pl-pl sk-sk es-es it-it
  nl-nl br-pt ru-ru hu-hu se-sv dk-da fi-fi jp-jp kr-kr wt-wt
""",
    )
    parser.add_argument('query', help='Search query')

    locale_group = parser.add_mutually_exclusive_group()
    locale_group.add_argument('--kl', default=None,
                              help='DDG locale code (default: cz-cs). Examples: us-en, de-de, gb-en')
    locale_group.add_argument('--lang', default=None, metavar='LANG',
                              help='Language code (e.g. cs, en, de) — use with --country')

    parser.add_argument('--country', default=None, metavar='CC',
                        help='Country code (e.g. cz, us, de) — use with --lang')
    parser.add_argument('--num', type=int, default=10,
                        help='Number of results to fetch (default: 10; JS mode only)')
    parser.add_argument('--proxy', default=_DEFAULT_PROXY,
                        help=f'Proxy URL (default: {_DEFAULT_PROXY}). Use --no-proxy to disable.')
    parser.add_argument('--no-proxy', action='store_true',
                        help='Disable proxy (direct connection)')
    parser.add_argument('--no-headless', dest='headless', action='store_false',
                        help='Show browser window')
    parser.add_argument('--chrome', default=None, help='Path to Chrome binary')
    parser.add_argument('--html-mode', action='store_true',
                        help='Use HTML lite endpoint (html.duckduckgo.com) — faster, no JS')
    parser.add_argument('--output', default='~/google_serp_outputs',
                        help='Output directory for CSV files')
    parser.add_argument('--no-csv', action='store_true', help='Skip CSV export')
    parser.add_argument('--json', dest='json_out', action='store_true',
                        help='Print JSON to stdout')
    parser.set_defaults(headless=True)
    args = parser.parse_args()

    # Resolve locale
    if args.kl:
        kl = args.kl
    elif args.lang and args.country:
        kl = lang_country_to_kl(args.lang, args.country)
    elif args.lang:
        kl = lang_country_to_kl(args.lang, args.lang)  # e.g. de → de-de
    else:
        kl = 'cz-cs'

    chrome = args.chrome or _find_chrome()

    print(f"Scraping : \"{args.query}\"")
    print(f"Locale   : {kl}")
    print(f"Mode     : {'HTML lite' if args.html_mode else 'JS'}")
    print(f"Num      : {args.num}{' (ignored in HTML mode)' if args.html_mode else ''}")
    print(f"Chrome   : {chrome or '(bundled Chromium)'}")
    print(f"Headless : {args.headless}")
    print(f"Stealth  : {_STEALTH_MODE}")
    if args.no_proxy:
        args.proxy = None
    print(f"Proxy    : {args.proxy or '(none)'}")

    data = scrape(
        args.query,
        kl=kl,
        num=args.num,
        proxy=args.proxy,
        headless=args.headless,
        chrome_path=chrome,
        html_mode=args.html_mode,
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
