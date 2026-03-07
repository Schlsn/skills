#!/usr/bin/env python3
"""
General Web Scraper for n8n integration.
Uses Playwright with stealth techniques (--headless=new) to bypass bot detection.
Outputs JSON.

Usage:
  python3 general_scraper.py --url https://example.com [--text] [--html] [--screenshot /path/to/capture.png]
"""

import sys
import json
import asyncio
import argparse
from pathlib import Path

# ── Default proxy (Tailscale → Home Assistant residential IP) ─────────────────
_DEFAULT_PROXY = 'socks5://172.18.0.1:1080'

async def scrape_url(
    url: str,
    proxy: str | None = _DEFAULT_PROXY,
    extract_text: bool = True,
    extract_html: bool = False,
    screenshot_path: str | None = None,
    wait_time: int = 2,
    headless: bool = True,
) -> dict:
    from playwright.async_api import async_playwright
    
    try:
        from playwright_stealth import Stealth
        stealth = Stealth()
    except ImportError:
        stealth = None

    result = {
        'status': 'ERROR',
        'url': url,
        'final_url': None,
        'title': None,
        'text': None,
        'html': None,
        'error': None
    }

    launch_args = [
        '--disable-blink-features=AutomationControlled',
        '--disable-infobars',
        '--no-first-run',
        '--no-default-browser-check',
        '--disable-extensions-except=',
        '--disable-default-apps',
        '--no-service-autorun',
        '--password-store=basic',
    ]
    if headless:
        launch_args.append('--headless=new')

    launch_kwargs: dict = dict(
        headless=False,
        args=launch_args,
    )
    if proxy:
        launch_kwargs['proxy'] = {'server': proxy}

    async with async_playwright() as p:
        browser = await p.chromium.launch(**launch_kwargs)
        
        ctx = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        )
        
        # Suppress webdriver flag
        await ctx.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        
        if stealth:
            await stealth.apply_stealth_async(ctx)

        page = await ctx.new_page()

        try:
            resp = await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            
            # Wait for any dynamic content
            if wait_time > 0:
                await asyncio.sleep(wait_time)
                
            try:
                await page.wait_for_load_state('networkidle', timeout=5000)
            except Exception:
                pass # Many pages never reach networkidle due to tracking

            result['final_url'] = page.url
            result['title'] = await page.title()
            result['status'] = 'SUCCESS'

            if extract_text:
                result['text'] = await page.evaluate('document.body.innerText')
                
            if extract_html:
                result['html'] = await page.content()
                
            if screenshot_path:
                await page.screenshot(path=screenshot_path, full_page=True)
                result['screenshot_saved'] = screenshot_path

        except Exception as e:
            result['error'] = str(e)
        finally:
            await browser.close()
            
    return result

def main():
    parser = argparse.ArgumentParser(description="General Web Scraper")
    parser.add_argument('-u', '--url', required=True, help="URL to scrape")
    parser.add_argument('--text', action='store_true', help="Extract page text (innerText)")
    parser.add_argument('--html', action='store_true', help="Extract raw HTML content")
    parser.add_argument('--screenshot', type=str, help="Path to save full page screenshot")
    parser.add_argument('--wait', type=int, default=2, help="Wait time in seconds after load")
    parser.add_argument('--proxy', type=str, default=_DEFAULT_PROXY, help="Proxy URL")
    parser.add_argument('--no-proxy', action='store_true', help="Disable proxy")
    
    args = parser.parse_args()
    
    # If neither text nor html are requested, default to text
    extract_text = args.text
    if not args.text and not args.html and not args.screenshot:
        extract_text = True
        
    proxy = None if args.no_proxy else args.proxy
    
    data = asyncio.run(scrape_url(
        url=args.url,
        proxy=proxy,
        extract_text=extract_text,
        extract_html=args.html,
        screenshot_path=args.screenshot,
        wait_time=args.wait
    ))
    
    print(json.dumps(data, indent=2, ensure_ascii=False))

if __name__ == '__main__':
    main()
