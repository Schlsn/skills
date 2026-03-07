#!/usr/bin/env python3
"""
Quick-test: spustí každý SERP scraper s jedním dotazem a vypíše souhrn.

Použití (na serveru):
  cd /opt/n8n-stack/scripts
  python3 test_scrapers_quick.py

Nebo s vlastním dotazem:
  python3 test_scrapers_quick.py --query "ivf clinic prague"
"""

import sys
import os
import json
import time
import argparse
import importlib.util
from pathlib import Path

# ── Barvy ─────────────────────────────────────────────────────────────────────
GREEN = '\033[92m'
RED   = '\033[91m'
CYAN  = '\033[96m'
YELLOW = '\033[93m'
RESET = '\033[0m'


def load_module(name: str, path: str):
    """Dynamicky načte Python modul ze souboru."""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)
        return mod
    except Exception as e:
        print(f"  {RED}⚠️  Import error: {e}{RESET}")
        return None


def test_scraper(name: str, scrape_fn, kwargs: dict) -> dict:
    """Spustí scraper a vrátí výsledek + timing."""
    print(f"\n{CYAN}{'━' * 60}{RESET}")
    print(f"{CYAN}▶ {name}{RESET}")
    print(f"  kwargs: {kwargs}")
    
    t0 = time.time()
    try:
        data = scrape_fn(**kwargs)
        elapsed = time.time() - t0
        
        n_organic = len(data.get('organic', []))
        n_paa     = len(data.get('paa', []))
        n_related = len(data.get('related', []))
        status    = data.get('status', '?')
        error     = data.get('error', '')
        
        if status == 'SUCCESS' and n_organic > 0:
            print(f"  {GREEN}✅ {status} — organic={n_organic} paa={n_paa} related={n_related} ({elapsed:.1f}s){RESET}")
            # Ukázka top 3
            for r in data['organic'][:3]:
                print(f"     {r['position']}. {r['title'][:60]}")
                print(f"        {r['url'][:80]}")
        elif status == 'SUCCESS' and n_organic == 0:
            print(f"  {YELLOW}⚠️  {status} ale 0 organic výsledků ({elapsed:.1f}s){RESET}")
        else:
            print(f"  {RED}❌ {status}: {error[:120]} ({elapsed:.1f}s){RESET}")
        
        return {
            'name': name, 'status': status, 'organic': n_organic,
            'paa': n_paa, 'related': n_related, 'time': elapsed,
            'error': error,
        }
    except Exception as e:
        elapsed = time.time() - t0
        print(f"  {RED}❌ EXCEPTION: {e} ({elapsed:.1f}s){RESET}")
        return {
            'name': name, 'status': 'EXCEPTION', 'organic': 0,
            'paa': 0, 'related': 0, 'time': elapsed,
            'error': str(e),
        }


def main():
    parser = argparse.ArgumentParser(description='Quick test all SERP scrapers')
    parser.add_argument('--query', default='ivf clinic prague',
                        help='Test query (default: "ivf clinic prague")')
    parser.add_argument('--query-cz', default='klinika ivf praha',
                        help='Czech test query (default: "klinika ivf praha")')
    parser.add_argument('--scripts-dir', default='/opt/n8n-stack/scripts',
                        help='Path to scripts directory')
    args = parser.parse_args()

    script_dir = Path(args.scripts_dir)
    results = []

    print(f"\n{'=' * 60}")
    print(f"  SERP Scraper Quick Test")
    print(f"  Query EN: \"{args.query}\"")
    print(f"  Query CZ: \"{args.query_cz}\"")
    print(f"  Scripts:  {script_dir}")
    print(f"{'=' * 60}")

    # ── 1. Google SERP v4 ─────────────────────────────────────────────────
    gpath = script_dir / 'google_serp_v4.py'
    if gpath.exists():
        mod = load_module('google_serp_v4', str(gpath))
        if mod:
            results.append(test_scraper(
                'Google (CZ)',
                mod.scrape,
                {'query': args.query_cz, 'lang': 'cs', 'country': 'cz'}
            ))
    else:
        print(f"\n{YELLOW}⏭️  google_serp_v4.py nenalezen{RESET}")

    # ── 2. DuckDuckGo SERP ────────────────────────────────────────────────
    dpath = script_dir / 'duckduckgo_serp.py'
    if dpath.exists():
        mod = load_module('duckduckgo_serp', str(dpath))
        if mod:
            # JS mode
            results.append(test_scraper(
                'DuckDuckGo JS (CZ)',
                mod.scrape,
                {'query': args.query_cz, 'kl': 'cz-cs'}
            ))
            # HTML lite mode
            results.append(test_scraper(
                'DuckDuckGo HTML (EN)',
                mod.scrape,
                {'query': args.query, 'kl': 'us-en', 'html_mode': True}
            ))
    else:
        print(f"\n{YELLOW}⏭️  duckduckgo_serp.py nenalezen{RESET}")

    # ── 3. Bing SERP ─────────────────────────────────────────────────────
    bpath = script_dir / 'bing_serp.py'
    if bpath.exists():
        mod = load_module('bing_serp', str(bpath))
        if mod:
            results.append(test_scraper(
                'Bing (CZ)',
                mod.scrape,
                {'query': args.query_cz, 'mkt': 'cs-CZ'}
            ))
            results.append(test_scraper(
                'Bing (EN, 20 results)',
                mod.scrape,
                {'query': args.query, 'mkt': 'en-US', 'num': 20}
            ))
    else:
        print(f"\n{YELLOW}⏭️  bing_serp.py nenalezen{RESET}")

    # ── 4. Brave SERP ────────────────────────────────────────────────────
    brpath = script_dir / 'brave_serp.py'
    if brpath.exists():
        mod = load_module('brave_serp', str(brpath))
        if mod:
            results.append(test_scraper(
                'Brave (CZ)',
                mod.scrape,
                {'query': args.query_cz, 'country': 'cz', 'lang': 'cs'}
            ))
            results.append(test_scraper(
                'Brave (EN)',
                mod.scrape,
                {'query': args.query, 'country': 'us', 'lang': 'en'}
            ))
    else:
        print(f"\n{YELLOW}⏭️  brave_serp.py nenalezen{RESET}")

    # ── 5. api_runner.py (jen info) ──────────────────────────────────────
    apath = script_dir / 'api_runner.py'
    if apath.exists():
        print(f"\n{CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}")
        print(f"{CYAN}▶ api_runner.py nalezen{RESET}")
        print(f"  Velikost: {apath.stat().st_size} bytes")

    # ── 6. scrape_google_reviews.py (jen info) ───────────────────────────
    rpath = script_dir / 'scrape_google_reviews.py'
    if rpath.exists():
        print(f"\n{CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}")
        print(f"{CYAN}▶ scrape_google_reviews.py nalezen{RESET}")
        print(f"  Velikost: {rpath.stat().st_size} bytes")

    # ── SOUHRN ────────────────────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print(f"  SOUHRN")
    print(f"{'=' * 60}")
    print(f"  {'Scraper':<30} {'Status':<10} {'Organic':>8} {'PAA':>5} {'Rel':>5} {'Time':>6}")
    print(f"  {'─' * 68}")
    
    for r in results:
        color = GREEN if r['status'] == 'SUCCESS' and r['organic'] > 0 else RED
        print(f"  {r['name']:<30} {color}{r['status']:<10}{RESET} {r['organic']:>8} {r['paa']:>5} {r['related']:>5} {r['time']:>5.1f}s")

    passed = sum(1 for r in results if r['status'] == 'SUCCESS' and r['organic'] > 0)
    total = len(results)
    print(f"\n  {GREEN}✅ {passed}/{total} testů prošlo{RESET}")
    
    if passed < total:
        print(f"  {RED}❌ {total - passed} testů selhalo{RESET}")
        for r in results:
            if r['status'] != 'SUCCESS' or r['organic'] == 0:
                print(f"     → {r['name']}: {r['error'][:100]}")
    
    print()


if __name__ == '__main__':
    main()
