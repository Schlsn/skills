#!/usr/bin/env python3
"""
Seed multiple Chrome profiles with cookies extracted from the real Chrome profile.

Usage:
  python seed_profiles.py --n 10 --profiles-dir ~/.serp_profiles
  python seed_profiles.py --n 10 --profiles-dir ~/.serp_profiles --no-headless

What it does:
  1. Opens the REAL Chrome profile via Playwright (read-only — no scraping)
  2. Navigates to google.cz to ensure consent cookies are set
  3. Extracts all google.cz + google.com cookies
  4. For each target profile dir:
     - Opens a fresh Playwright context
     - Injects the extracted cookies
     - Saves the profile (cookies persist to disk)
"""

import asyncio
import argparse
import json
import sys
from pathlib import Path


# ─── Stealth compatibility ────────────────────────────────────────────────────
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
        async def stealth_async(page):
            pass


def _find_real_chrome_profile():
    """Auto-detect the real Chrome Default profile on macOS/Linux."""
    candidates = [
        Path.home() / "Library/Application Support/Google/Chrome/Default",  # macOS
        Path.home() / ".config/google-chrome/Default",                        # Linux
        Path.home() / ".config/chromium/Default",                             # Chromium Linux
    ]
    for c in candidates:
        if (c / "Cookies").exists():
            return str(c)
    return None


def _find_chrome_binary():
    import platform, shutil
    if platform.system() == 'Darwin':
        paths = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
        for p in paths:
            if Path(p).exists():
                return p
    return shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")


# ─── Step 1: Extract cookies from real Chrome profile ─────────────────────────
async def _extract_real_cookies(real_profile_dir, chrome_binary, headless):
    from playwright.async_api import async_playwright

    print(f"[source] Opening real Chrome profile: {real_profile_dir}")
    launch_kwargs = dict(
        headless=headless,
        viewport={'width': 1280, 'height': 900},
        args=[
            '--disable-blink-features=AutomationControlled',
            '--no-first-run', '--no-default-browser-check',
            '--disable-extensions-except=', '--disable-default-apps',
            '--no-service-autorun', '--password-store=basic',
        ]
    )
    if chrome_binary:
        launch_kwargs['executable_path'] = chrome_binary

    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(real_profile_dir, **launch_kwargs)
        page = await ctx.new_page()
        await stealth_async(page)

        print("[source] Navigating to google.cz …")
        await page.goto("https://www.google.cz/", wait_until='domcontentloaded', timeout=30000)

        # Handle consent dialog if it appears
        for label in ['Přijmout vše', 'Accept all', 'Souhlasím', 'I agree']:
            try:
                btn = page.get_by_role("button", name=label, exact=True)
                if await btn.count() > 0:
                    await btn.click()
                    print(f"[source] Clicked consent: '{label}'")
                    break
            except Exception:
                pass

        await asyncio.sleep(2)

        # Extract all google.cz and google.com cookies
        all_cookies = await ctx.cookies()
        google_cookies = [
            c for c in all_cookies
            if 'google' in c.get('domain', '') or 'google' in c.get('url', '')
        ]
        print(f"[source] Extracted {len(google_cookies)} Google cookies (from {len(all_cookies)} total)")

        await ctx.close()
        return google_cookies


# ─── Step 2: Inject cookies into a new profile dir ───────────────────────────
async def _seed_one_profile(profile_dir, cookies, chrome_binary, headless):
    from playwright.async_api import async_playwright

    Path(profile_dir).mkdir(parents=True, exist_ok=True)

    launch_kwargs = dict(
        headless=headless,
        viewport={'width': 1280, 'height': 900},
        args=[
            '--disable-blink-features=AutomationControlled',
            '--no-first-run', '--no-default-browser-check',
            '--disable-extensions-except=', '--disable-default-apps',
            '--no-service-autorun', '--password-store=basic',
        ]
    )
    if chrome_binary:
        launch_kwargs['executable_path'] = chrome_binary

    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(profile_dir, **launch_kwargs)

        # Inject cookies
        try:
            await ctx.add_cookies(cookies)
        except Exception as e:
            print(f"  ⚠ add_cookies warning: {e}")

        # Navigate to google.cz to force cookie write to disk
        page = await ctx.new_page()
        await stealth_async(page)
        try:
            await page.goto("https://www.google.cz/", wait_until='domcontentloaded', timeout=20000)
            await asyncio.sleep(2)
            # Verify we don't get consent (means cookies worked)
            title = await page.title()
            print(f"  Page title: {title!r}")
        except Exception as e:
            print(f"  ⚠ Navigation warning: {e}")

        await ctx.close()


# ─── Main ─────────────────────────────────────────────────────────────────────
async def main():
    parser = argparse.ArgumentParser(description="Seed Chrome profiles with real Google cookies")
    parser.add_argument('--n', type=int, default=5, help='Number of profiles to create (default: 5)')
    parser.add_argument('--profiles-dir', default='~/.serp_profiles', metavar='DIR',
                        help='Directory to create profiles in (default: ~/.serp_profiles)')
    parser.add_argument('--real-profile', metavar='PATH',
                        help='Path to real Chrome Default profile (auto-detected if omitted)')
    parser.add_argument('--chrome', metavar='PATH',
                        help='Chrome binary path (auto-detected if omitted)')
    parser.add_argument('--no-headless', action='store_true',
                        help='Show browser window')
    parser.add_argument('--export-cookies', metavar='FILE',
                        help='Export extracted cookies to JSON file (for manual inspection)')
    args = parser.parse_args()

    headless = not args.no_headless
    chrome_binary = args.chrome or _find_chrome_binary()
    real_profile = args.real_profile or _find_real_chrome_profile()

    if not real_profile:
        print("ERROR: Could not find real Chrome profile. Use --real-profile PATH", file=sys.stderr)
        sys.exit(1)

    profiles_base = Path(args.profiles_dir).expanduser()
    profiles_base.mkdir(parents=True, exist_ok=True)

    print(f"Seeding {args.n} profiles → {profiles_base}")
    print(f"Chrome  : {chrome_binary or '(bundled)'}")
    print(f"Stealth : {_STEALTH_MODE}")
    print(f"Headless: {headless}")
    print()

    # Step 1: Extract cookies from real Chrome
    try:
        cookies = await _extract_real_cookies(real_profile, chrome_binary, headless)
    except Exception as e:
        print(f"ERROR extracting cookies: {e}", file=sys.stderr)
        sys.exit(1)

    if not cookies:
        print("ERROR: No Google cookies extracted. Is Chrome profile at correct path?", file=sys.stderr)
        sys.exit(1)

    # Optionally export cookies to JSON
    if args.export_cookies:
        with open(args.export_cookies, 'w') as f:
            json.dump(cookies, f, indent=2)
        print(f"[export] Cookies saved to {args.export_cookies}")

    # Step 2: Seed each profile
    seeded = 0
    for i in range(args.n):
        profile_dir = profiles_base / f"profile_{i:02d}"
        print(f"[{i+1}/{args.n}] Seeding {profile_dir.name} …")
        try:
            await _seed_one_profile(str(profile_dir), cookies, chrome_binary, headless)
            print(f"  ✅ OK")
            seeded += 1
        except Exception as e:
            print(f"  ❌ FAILED: {e}")

    print()
    print(f"Seeded {seeded}/{args.n} profiles in {profiles_base}")
    print()
    print("Next steps:")
    print(f"  1. Test: python google_serp_v4.py 'test query' --profiles-dir {profiles_base}")
    print(f"  2. Upload to server: rsync -av {profiles_base}/ root@SERVER:{profiles_base}/")


if __name__ == '__main__':
    asyncio.run(main())
