#!/usr/bin/env python3
"""
Google SERP scraper — v4
Technique: persistent Chrome profile + playwright-stealth + human-like mouse movement.
Headless by default (Chrome's --headless=new flag, far less detectable than legacy).

Usage: python google_serp_v4.py <query> [options]

Options:
  --lang        Language code, e.g. cs, en, de   (default: cs)
  --country     Country code, e.g. cz, us, de    (default: cz)
  --output      Output dir for CSV files         (default: ~/google_serp_outputs)
  --no-csv      Print tables only, skip CSV
  --proxy       SOCKS5 proxy URL                 (e.g. socks5://127.0.0.1:1080)
  --profile     Path to Chrome profile dir       (default: ~/.google_serp_profile)
  --no-headless Run with visible window
  --chrome      Path to Chrome binary            (auto-detected if omitted)
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


# ── Realistic UA + viewport pool ─────────────────────────────────────────────

# Chrome 120–132, mix of Windows / macOS / Linux — all plausible desktop UAs.
# Keep in sync with the Chromium version bundled by the installed Playwright.
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

# (width, height) — real-world desktop resolutions from StatCounter 2024
_RANDOM_VIEWPORTS = [
    (1366, 768),
    (1440, 900),
    (1536, 864),
    (1600, 900),
    (1920, 1080),
    (1280, 720),
    (1280, 800),
    (1360, 768),
    (1024, 768),
    (1680, 1050),
]


def _pick_ua_and_viewport() -> tuple[str, dict]:
    """Return a random (user_agent, viewport) pair."""
    ua = random.choice(_RANDOM_UAS)
    w, h = random.choice(_RANDOM_VIEWPORTS)
    # Slight jitter so identical resolutions differ slightly between runs
    w += random.randint(-8, 8)
    h += random.randint(-6, 6)
    return ua, {'width': w, 'height': h}


# ── Chrome binary discovery ───────────────────────────────────────────────────

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
    env_path = os.environ.get('CHROME_PATH')
    if env_path and Path(env_path).exists():
        return env_path
    for c in candidates:
        if Path(c).exists():
            return c
    return None


# ── CAPTCHA detection ─────────────────────────────────────────────────────────

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
    """Raise RuntimeError if CAPTCHA detected. Also handles mid-navigation eval."""
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


# ── Human-like mouse movement ─────────────────────────────────────────────────

def _bezier_point(t: float, p0, p1, p2, p3) -> tuple[float, float]:
    """Cubic Bézier point at parameter t."""
    mt = 1.0 - t
    x = mt**3 * p0[0] + 3*mt**2*t * p1[0] + 3*mt*t**2 * p2[0] + t**3 * p3[0]
    y = mt**3 * p0[1] + 3*mt**2*t * p1[1] + 3*mt*t**2 * p2[1] + t**3 * p3[1]
    return x, y


async def _human_mouse_move(page, target_x: float, target_y: float,
                             steps: int | None = None):
    """
    Move mouse to (target_x, target_y) along a randomized cubic Bézier curve
    with variable speed (slow at ends, faster in the middle).
    """
    if steps is None:
        steps = random.randint(18, 35)

    vp = page.viewport_size or {'width': 1280, 'height': 900}
    start_x = random.uniform(vp['width'] * 0.15, vp['width'] * 0.85)
    start_y = random.uniform(vp['height'] * 0.15, vp['height'] * 0.75)

    # Random control points — pulls the curve naturally
    cp1 = (
        start_x + random.uniform(-120, 120),
        start_y + random.uniform(-80, 80),
    )
    cp2 = (
        target_x + random.uniform(-90, 90),
        target_y + random.uniform(-70, 70),
    )

    for i in range(1, steps + 1):
        t = i / steps
        # Smoothstep ease-in-out: slower at start & end
        t_smooth = t * t * (3.0 - 2.0 * t)
        px, py = _bezier_point(t_smooth,
                                (start_x, start_y), cp1, cp2,
                                (target_x, target_y))
        await page.mouse.move(px, py)
        # Delay: 4–18 ms/step, biased slower near ends
        edge_factor = 1.0 + 1.2 * abs(t - 0.5)  # max at t=0 and t=1
        delay_ms = random.uniform(4, 18) * edge_factor
        await asyncio.sleep(delay_ms / 1000)


async def _human_click(page, x: float, y: float):
    """Human-like mouse-move then click."""
    await _human_mouse_move(page, x, y)
    await asyncio.sleep(random.uniform(0.04, 0.12))
    await page.mouse.click(x, y)


async def _human_scroll(page, count: int = 3):
    """Gradual human-like scroll down, with pauses."""
    for _ in range(count):
        delta = random.randint(200, 450)
        await page.mouse.wheel(0, delta)
        await asyncio.sleep(random.uniform(0.35, 0.9))


# ── JS extraction ─────────────────────────────────────────────────────────────

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


# ── Core scrape ───────────────────────────────────────────────────────────────

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

    Path(profile_dir).mkdir(parents=True, exist_ok=True)

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
        viewport=viewport,
        user_agent=ua,
        args=launch_args,
    )
    if chrome_path:
        launch_kwargs['executable_path'] = chrome_path
    if proxy:
        launch_kwargs['proxy'] = {'server': proxy}

    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(profile_dir, **launch_kwargs)

        # Suppress webdriver flag on all new pages
        await ctx.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )

        page = await ctx.new_page()

        # Apply playwright-stealth (must be before navigation)
        await stealth_async(page)

        # ── Block bandwidth-heavy resources (saves ~60–80% data on proxy) ─
        _BLOCK_TYPES = {'image', 'media', 'font', 'websocket', 'other'}
        _BLOCK_DOMAINS = {'googletagmanager.com', 'google-analytics.com',
                          'doubleclick.net', 'googlesyndication.com'}

        async def _route_handler(route):
            rt = route.request.resource_type
            url = route.request.url
            if rt in _BLOCK_TYPES:
                await route.abort()
            elif any(d in url for d in _BLOCK_DOMAINS):
                await route.abort()
            else:
                await route.continue_()

        await page.route('**/*', _route_handler)

        # ── Log chosen UA + viewport ──────────────────────────────────────
        print(f"  → UA     : {ua[:80]}…", flush=True)
        print(f"  → View   : {viewport['width']}×{viewport['height']}", flush=True)

        # ── Step 1: Navigate directly to search URL ───────────────────────
        # (Direct URL = less suspicious than homepage → type → Enter on blocked IPs)
        search_url = (
            f"https://www.google.{country}/search"
            f"?q={quote_plus(query)}&hl={lang}&gl={country}&num=10&pws=0"
        )
        print(f"  → {search_url}", flush=True)
        await page.goto(search_url, wait_until='domcontentloaded', timeout=30000)

        # ── Cookie consent (only on fresh profile) ────────────────────────
        for label in ['Přijmout vše', 'Accept all', 'Alle akzeptieren',
                       'Tout accepter', 'Aceptar todo']:
            try:
                btn = await page.wait_for_selector(
                    f'button:has-text("{label}")', timeout=2000
                )
                box = await btn.bounding_box()
                if box:
                    cx = box['x'] + box['width'] / 2
                    cy = box['y'] + box['height'] / 2
                    await _human_click(page, cx, cy)
                else:
                    await btn.click()
                await page.wait_for_load_state('domcontentloaded', timeout=10000)
                print(f"  → Cookie consent: '{label}' clicked", flush=True)
                break
            except Exception:
                continue

        # ── Wait for full load ────────────────────────────────────────────
        await page.wait_for_load_state('networkidle', timeout=15000)

        # ── CAPTCHA check ─────────────────────────────────────────────────
        await _check_captcha(page, ctx)

        # ── Human behaviour: scroll & random mouse movement ───────────────
        vp = page.viewport_size or {'width': 1280, 'height': 900}

        # Hover near first result
        await _human_mouse_move(
            page,
            random.uniform(200, min(700, vp['width'] - 100)),
            random.uniform(200, min(450, vp['height'] - 100)),
        )
        await asyncio.sleep(random.uniform(0.3, 0.7))

        # Scroll down (like reading results)
        await _human_scroll(page, count=random.randint(2, 4))

        # Wander around a bit more
        for _ in range(random.randint(1, 3)):
            await _human_mouse_move(
                page,
                random.uniform(80, vp['width'] - 80),
                random.uniform(80, vp['height'] - 80),
            )
            await asyncio.sleep(random.uniform(0.15, 0.45))

        # Final short pause
        await page.wait_for_timeout(random.randint(400, 1200))

        # ── Extract results ───────────────────────────────────────────────
        result = await page.evaluate(
            _EXTRACT_JS, {'query': query, 'blocked': BLOCKED_PARAMS}
        )

        await ctx.close()
        return result


def scrape(
    query: str,
    lang: str = 'cs',
    country: str = 'cz',
    proxy: str | None = _DEFAULT_PROXY,
    profile_dir: str = str(Path('~/.google_serp_profile').expanduser()),
    headless: bool = True,
    chrome_path: str | None = None,
) -> dict:
    if chrome_path is None:
        chrome_path = _find_chrome()
    try:
        data = asyncio.run(
            _scrape(query, lang, country, proxy, profile_dir, headless, chrome_path)
        )
        data['status'] = 'SUCCESS'
        data['error'] = ''
        return data
    except Exception as e:
        return {'organic': [], 'paa': [], 'related': [], 'status': 'ERROR', 'error': str(e)}


def scrape_with_pause(
    query: str,
    lang: str = 'cs',
    country: str = 'cz',
    proxy: str | None = _DEFAULT_PROXY,
    profile_dir: str = str(Path('~/.google_serp_profile').expanduser()),
    headless: bool = True,
    pause_min: int = 8,
    pause_max: int = 15,
) -> dict:
    wait = random.uniform(pause_min, pause_max)
    print(f"  ⏳ Waiting {wait:.1f}s before \"{query}\"...", file=sys.stderr)
    time.sleep(wait)
    return scrape(query, lang, country, proxy, profile_dir, headless)


# ── Profile pool management ───────────────────────────────────────────────────

def _list_profiles(profiles_dir: str) -> list[str]:
    """Return sorted list of profile_XX subdirs in profiles_dir."""
    base = Path(profiles_dir).expanduser()
    if not base.exists():
        return []
    return sorted(str(p) for p in base.iterdir() if p.is_dir())


def warm_profiles(
    n: int,
    profiles_dir: str = str(Path('~/.serp_profiles').expanduser()),
    lang: str = 'cs',
    country: str = 'cz',
    proxy: str | None = _DEFAULT_PROXY,
    headless: bool = True,
    chrome_path: str | None = None,
    warmup_query: str = 'počasí',
    pause_min: int = 10,
    pause_max: int = 25,
) -> list[str]:
    """
    Create and warm N Chrome profiles by running a harmless test search.
    Each profile gets cookie-consent cookies saved to disk.
    Returns list of successfully warmed profile dirs.

    Tip: copy the resulting profiles_dir to your Linux server via:
        rsync -av ~/.serp_profiles/ user@server:~/.serp_profiles/
    """
    if chrome_path is None:
        chrome_path = _find_chrome()

    base = Path(profiles_dir).expanduser()
    base.mkdir(parents=True, exist_ok=True)

    existing = _list_profiles(profiles_dir)
    start_idx = len(existing)
    warmed = []

    for i in range(n):
        idx = start_idx + i
        profile_dir = str(base / f'profile_{idx:02d}')
        print(f"\n[{i + 1}/{n}] Warming profile_{idx:02d} …", flush=True)

        result = scrape(warmup_query, lang=lang, country=country,
                        proxy=proxy, profile_dir=profile_dir,
                        headless=headless, chrome_path=chrome_path)

        if result['status'] == 'SUCCESS':
            print(f"  ✅ OK — organic={len(result['organic'])}")
            warmed.append(profile_dir)
        else:
            print(f"  ❌ FAILED: {result['error']}")

        if i < n - 1:
            wait = random.uniform(pause_min, pause_max)
            print(f"  ⏳ Cooling {wait:.0f}s …", flush=True)
            time.sleep(wait)

    print(f"\nWarmed {len(warmed)}/{n} profiles in {base}")
    return warmed


def scrape_with_rotation(
    query: str,
    profiles_dir: str = str(Path('~/.serp_profiles').expanduser()),
    lang: str = 'cs',
    country: str = 'cz',
    proxy: str | None = _DEFAULT_PROXY,
    headless: bool = True,
    chrome_path: str | None = None,
    try_clean_first: bool = True,
) -> dict:
    """
    Scrape with automatic fallback in order:
      1. Clean session (fresh temp dir — no cookies)
      2. Profiles from profiles_dir in random order

    Returns first successful result or last ERROR dict.
    """
    if chrome_path is None:
        chrome_path = _find_chrome()

    attempts: list[tuple[str, dict]] = []

    # ── 1. Clean session ──────────────────────────────────────────────────
    if try_clean_first:
        clean_dir = f'/tmp/serp_clean_{random.randint(10000, 99999)}'
        print(f"  → [clean session]", flush=True)
        result = scrape(query, lang=lang, country=country, proxy=proxy,
                        profile_dir=clean_dir, headless=headless,
                        chrome_path=chrome_path)
        attempts.append(('clean', result))
        if result['status'] == 'SUCCESS':
            print(f"  ✅ clean session worked", flush=True)
            return result
        print(f"  ✗ clean failed: {result['error']}", flush=True)

    # ── 2. Rotate through profiles ────────────────────────────────────────
    profiles = _list_profiles(profiles_dir)
    if not profiles:
        err = f'No profiles found in {profiles_dir}. Run --warm first.'
        return {'organic': [], 'paa': [], 'related': [],
                'status': 'ERROR', 'error': err}

    random.shuffle(profiles)
    for profile in profiles:
        name = Path(profile).name
        print(f"  → [{name}]", flush=True)
        result = scrape(query, lang=lang, country=country, proxy=proxy,
                        profile_dir=profile, headless=headless,
                        chrome_path=chrome_path)
        attempts.append((name, result))
        if result['status'] == 'SUCCESS':
            print(f"  ✅ {name} worked", flush=True)
            return result
        print(f"  ✗ {name} failed: {result['error']}", flush=True)

    # All failed
    last = attempts[-1][1]
    last['error'] = (
        f'All {len(attempts)} attempts failed. Last: {last["error"]}'
    )
    return last


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


def print_results(data: dict, query: str):
    _print_table(
        f"ORGANIC — \"{query}\"",
        ['#', 'Title', 'Description', 'URL'],
        [[r['position'], r['title'][:55], r['description'][:75], r['url'][:65]]
         for r in data['organic']],
    )
    _print_table(
        "PEOPLE ALSO ASK", ['#', 'Question'],
        [[i + 1, q] for i, q in enumerate(data['paa'][:10])],
    )
    _print_table(
        "RELATED SEARCHES", ['#', 'Query'],
        [[i + 1, x] for i, x in enumerate(data['related'])],
    )


# ── CSV export ────────────────────────────────────────────────────────────────

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
            w = csv.DictWriter(
                f, fieldnames=['position', 'title', 'description', 'url', 'language', 'country']
            )
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
        w = csv.DictWriter(
            f, fieldnames=['keyword', 'status', 'error_message', 'results_count', 'language', 'country']
        )
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
    print(f"Status CSV  : {p}")
    return paths


# ── CLI ───────────────────────────────────────────────────────────────────────

_DEFAULT_PROFILES_DIR = str(Path('~/.serp_profiles').expanduser())
_DEFAULT_PROFILE      = str(Path('~/.google_serp_profile').expanduser())


def main():
    parser = argparse.ArgumentParser(
        description='Google SERP scraper v4 — persistent profile + stealth + human mouse',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Warm 5 profiles (run once, then copy to server):
  python google_serp_v4.py --warm 5 --profiles-dir ~/.serp_profiles

  # Scrape with rotation (clean → profiles):
  python google_serp_v4.py "seo nástroje" --profiles-dir ~/.serp_profiles

  # Scrape with single profile:
  python google_serp_v4.py "seo nástroje" --profile ~/.serp_profiles/profile_00

  # Copy profiles to Linux server:
  rsync -av ~/.serp_profiles/ user@server:~/.serp_profiles/
""",
    )
    parser.add_argument('query',         nargs='?', default=None,
                        help='Search query (omit when using --warm)')
    parser.add_argument('--lang',        default='cs')
    parser.add_argument('--country',     default='cz')
    parser.add_argument('--output',      default='~/google_serp_outputs')
    parser.add_argument('--no-csv',      action='store_true')
    parser.add_argument('--json',        action='store_true')
    parser.add_argument('--proxy',       default=None)
    parser.add_argument('--no-headless', dest='headless', action='store_false',
                        help='Run with visible window (default: headless)')
    parser.add_argument('--chrome',      default=None, help='Path to Chrome binary')

    # Profile modes
    profile_group = parser.add_mutually_exclusive_group()
    profile_group.add_argument('--profile',      default=None,
                               help=f'Single profile dir (default: {_DEFAULT_PROFILE})')
    profile_group.add_argument('--profiles-dir', default=None, metavar='DIR',
                               help=f'Pool of profiles → enables rotation (default: {_DEFAULT_PROFILES_DIR})')

    parser.add_argument('--no-try-clean', dest='try_clean', action='store_false',
                        help='Skip clean-session attempt in rotation mode')
    parser.add_argument('--warm',        type=int, default=0, metavar='N',
                        help='Warm N new profiles into --profiles-dir and exit')
    parser.add_argument('--warm-query',  default='počasí',
                        help='Query used for warming (default: počasí)')

    parser.set_defaults(headless=True, try_clean=True)
    args = parser.parse_args()

    chrome = args.chrome or _find_chrome()

    # ── WARM mode ─────────────────────────────────────────────────────────
    if args.warm:
        profiles_dir = args.profiles_dir or _DEFAULT_PROFILES_DIR
        print(f"Warming {args.warm} profiles → {profiles_dir}")
        print(f"Chrome  : {chrome or '(bundled Chromium)'}")
        print(f"Stealth : {_STEALTH_MODE}")
        warm_profiles(
            n=args.warm,
            profiles_dir=profiles_dir,
            lang=args.lang,
            country=args.country,
            proxy=args.proxy,
            headless=args.headless,
            chrome_path=chrome,
            warmup_query=args.warm_query,
        )
        print("\nDone. Copy to server with:")
        print(f"  rsync -av {profiles_dir}/ user@server:{profiles_dir}/")
        return

    # ── SCRAPE mode ───────────────────────────────────────────────────────
    if not args.query:
        parser.error('query is required (or use --warm N to warm profiles)')

    print(f"Scraping : \"{args.query}\" | google.{args.country} | lang={args.lang} | num=10")
    print(f"Chrome   : {chrome or '(bundled Chromium)'}")
    print(f"Headless : {args.headless}")
    print(f"Stealth  : {_STEALTH_MODE}")
    if args.proxy:
        print(f"Proxy    : {args.proxy}")

    if args.profiles_dir is not None:
        # Rotation mode
        profiles = _list_profiles(args.profiles_dir)
        print(f"Mode     : rotation | profiles={len(profiles)} | try_clean={args.try_clean}")
        data = scrape_with_rotation(
            args.query,
            profiles_dir=args.profiles_dir,
            lang=args.lang,
            country=args.country,
            proxy=args.proxy,
            headless=args.headless,
            chrome_path=chrome,
            try_clean_first=args.try_clean,
        )
    else:
        # Single profile mode
        profile = args.profile or _DEFAULT_PROFILE
        print(f"Profile  : {profile}")
        data = scrape(
            args.query,
            lang=args.lang,
            country=args.country,
            proxy=args.proxy,
            profile_dir=profile,
            headless=args.headless,
            chrome_path=chrome,
        )

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
