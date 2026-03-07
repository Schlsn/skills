#!/usr/bin/env python3
"""Test SerpScrap s opravenými Selenium 4 závislostmi."""

import sys
import os

# Monkey-patch: Selenium 4 nemá executable_path v Chrome() ani chrome_options
# Opravíme přes webdriver-manager + options rename
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# Patch DesiredCapabilities import (deprecated v Selenium 4)
import selenium.webdriver.common.desired_capabilities as _dc
if not hasattr(_dc.DesiredCapabilities, 'CHROME'):
    _dc.DesiredCapabilities.CHROME = {}

# Patch webdriver.Chrome pro Selenium 4 kompatibilitu
_original_Chrome = webdriver.Chrome
class _PatchedChrome(_original_Chrome):
    def __init__(self, executable_path=None, chrome_options=None, options=None, **kwargs):
        # Merge chrome_options → options
        if chrome_options is not None and options is None:
            options = chrome_options
        # executable_path → Service
        if executable_path and executable_path != '':
            service = Service(executable_path=executable_path)
        else:
            service = Service(ChromeDriverManager().install())
        kwargs.pop('desired_capabilities', None)
        super().__init__(service=service, options=options, **kwargs)

webdriver.Chrome = _PatchedChrome

# Teď importuj SerpScrap
import serpscrap

keywords = ['SEO nástroje zdarma']

config = serpscrap.Config()
config.set('scrape_urls', False)        # neprocházej výsledky
config.set('num_pages_for_keyword', 1)  # jen 1 stránka
config.set('chrome_headless', True)     # headless
config.set('sleeping_min', 2)           # kratší čekání pro test
config.set('sleeping_max', 4)
config.set('search_engines', ['google'])
config.set('do_caching', False)

print("=== SerpScrap test ===")
print(f"Keywords: {keywords}")
print(f"Headless: {config.get().get('chrome_headless')}")
print()

scrap = serpscrap.SerpScrap()
scrap.init(config=config.get(), keywords=keywords)

try:
    results = scrap.run()
    print(f"Počet výsledků: {len(results)}")
    for i, r in enumerate(results[:5], 1):
        print(f"\n[{i}] rank={r.get('rank')} | type={r.get('result_type')}")
        print(f"     title: {r.get('title', '')[:80]}")
        print(f"     url:   {r.get('url', '')[:80]}")
        print(f"     snipp: {r.get('snippet', '')[:100]}")
except Exception as e:
    print(f"CHYBA: {e}", file=sys.stderr)
    import traceback
    traceback.print_exc()
