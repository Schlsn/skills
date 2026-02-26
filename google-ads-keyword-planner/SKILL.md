---
name: google-ads-keyword-planner
description: Use when the user wants keyword ideas, search volumes, competition data, or bid estimates from Google Keyword Planner. Triggers include "keyword research," "keyword ideas," "search volumes," "what keywords should I target," "keyword opportunities," "keyword gaps," "find keywords for," or any request to pull keyword data from Google Ads API. Uses the Google Ads Python SDK (KeywordPlanIdeaService) directly — not GAQL. Requires google-ads.yaml credentials.
---

# Google Ads Keyword Planner

Fetch keyword ideas, search volumes, competition index, and bid estimates directly from the Google Ads API using the Python SDK.

## How It Works

The Google Ads Keyword Planner API (`KeywordPlanIdeaService`) is a **separate service from GAQL** — it cannot be queried via the MCP reporting tool. Use the Python SDK instead.

### Prerequisites

1. **SDK installed**: `pip3 install google-ads --break-system-packages` (if not already present)
2. **Credentials**: `~/.google-ads.yaml` or check `/Users/adam/Documents/credentials/google-ads.yaml`
3. **Customer ID**: The account to bill the query against (not necessarily the account being researched)

---

## Core Script

```python
from google.ads.googleads.client import GoogleAdsClient

client = GoogleAdsClient.load_from_storage("/Users/adam/Documents/credentials/google-ads.yaml")
kp_idea_service = client.get_service("KeywordPlanIdeaService")
ga_service = client.get_service("GoogleAdsService")

def get_keyword_ideas(customer_id, language_id, geo_ids, seed_keywords):
    """
    customer_id   : str  — Google Ads account ID (digits only, no dashes)
    language_id   : str  — see Language IDs table below
    geo_ids       : list — see Geo IDs table below
    seed_keywords : list — max 20 items per call
    """
    request = client.get_type("GenerateKeywordIdeasRequest")
    request.customer_id = customer_id
    request.language = ga_service.language_constant_path(language_id)
    for geo_id in geo_ids:
        request.geo_target_constants.append(
            ga_service.geo_target_constant_path(geo_id)
        )
    request.include_adult_keywords = False
    request.keyword_plan_network = client.enums.KeywordPlanNetworkEnum.GOOGLE_SEARCH
    request.keyword_seed.keywords.extend(seed_keywords[:20])

    results = []
    for idea in kp_idea_service.generate_keyword_ideas(request=request):
        m = idea.keyword_idea_metrics
        bid_low  = m.low_top_of_page_bid_micros  / 1_000_000 if m.low_top_of_page_bid_micros  else 0
        bid_high = m.high_top_of_page_bid_micros / 1_000_000 if m.high_top_of_page_bid_micros else 0
        results.append({
            "keyword":       idea.text,
            "searches":      m.avg_monthly_searches,
            "competition":   m.competition_index,   # 0–100
            "bid_low_czk":  bid_low,
            "bid_high_czk": bid_high,
        })
    return sorted(results, key=lambda x: x["searches"], reverse=True)


def print_results(label, results, account_currency="CZK", fx_rate=1.0, fx_label="CZK", min_searches=10):
    print(f"\n{'='*100}")
    print(f"  {label}  [bids in {account_currency}, přepočet ÷ {fx_rate:.0f} → {fx_label}]")
    print(f"{'='*100}")
    print(f"{'Keyword':<50} {'Searches/mo':>12} {'Comp.':>7} {'Bid low':>18} {'Bid high':>18}")
    print(f"{'-'*100}")
    for r in results:
        if r["searches"] >= min_searches:
            converted_low  = r["bid_low_czk"]  / fx_rate
            converted_high = r["bid_high_czk"] / fx_rate
            print(
                f"{r['keyword']:<50} {r['searches']:>12,} {r['competition']:>7} "
                f"{r['bid_low_czk']:>5.0f} {account_currency} ({converted_low:.2f} {fx_label})   "
                f"{r['bid_high_czk']:>5.0f} {account_currency} ({converted_high:.2f} {fx_label})"
            )
```

---

## Important Gotchas

| Issue | Detail |
|---|---|
| **Max 20 seed keywords** | API hard limit. Split larger lists into batches of ≤ 20 |
| **Currency = account currency** | Bids are returned in the *billing currency of the queried account*, NOT the target market currency. Always check the account's `currency_code` via GAQL first and convert manually |
| **`average_cpc_micros` is often 0** | Use `low_top_of_page_bid_micros` / `high_top_of_page_bid_micros` for meaningful CPC estimates |
| **Language ≠ Geo** | You can set language DE with geo CZ to simulate German speakers searching in Czech Republic — useful for medical tourism use cases |
| **Ideas ≠ seed keywords only** | The API returns related keywords beyond your seeds. Filter by `searches >= N` to remove noise |

### Check account currency before reporting bids

```python
query = "SELECT customer.currency_code, customer.descriptive_name FROM customer LIMIT 1"
for row in ga_service.search(customer_id=customer_id, query=query):
    print(row.customer.currency_code)  # e.g. "CZK", "EUR", "GBP"
```

---

## Reference Tables

### Language IDs (common)

| Language | ID |
|---|---|
| English | 1000 |
| German | 1001 |
| French | 1002 |
| Italian | 1004 |
| Dutch | 1010 |
| Polish | 1020 |
| Czech | 1021 |
| Croatian | 1022 |
| Serbian | 1034 |
| Ukrainian | 1036 |
| Swedish | 1015 |

### Geo Target IDs (common)

| Country | ID |
|---|---|
| Czech Republic | 2203 |
| Germany | 2276 |
| Austria | 2040 |
| Switzerland | 2756 |
| United Kingdom | 2826 |
| Ireland | 2372 |
| France | 2250 |
| Italy | 2380 |
| Netherlands | 2528 |
| Belgium | 2056 |
| Poland | 2616 |
| Croatia | 2191 |
| Serbia | 2688 |
| Bosnia & Herzegovina | 2070 |
| United States | 2840 |
| Sweden | 2752 |
| Norway | 2578 |
| Denmark | 2208 |

---

## Workflow

1. **Clarify scope**: What market (language + geo)? What topic / seed keywords?
2. **Check account currency** via GAQL snippet above
3. **Batch seeds** into groups of ≤ 20
4. **Run `get_keyword_ideas`** for each market / language combo
5. **Convert bids** to target market currency using current FX rate
6. **Filter + rank**: Remove `searches < 10`, sort by volume descending
7. **Interpret competition_index**: 0–25 = low, 26–55 = medium, 56–100 = high
8. **Present results** grouped by market with bid context

---

## Output Format

Present results as a table per market:

```
Market: DE (German speakers, geo: Germany)
Account currency: CZK → EUR (÷ 25)

Keyword                              Searches/mo   Comp.   Bid low     Bid high
social freezing                            3,600      29    8 Kč (0.34€)  60 Kč (2.40€)
präimplantationsdiagnostik                 2,400       4   15 Kč (0.61€)  67 Kč (2.67€)
...
```

Follow with a brief commentary on:
- Top volume opportunities
- Any surprisingly low/high competition keywords
- Keywords with strong commercial intent (high competition + Tschechien/abroad modifiers = user ready to buy)
