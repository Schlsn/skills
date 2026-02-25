---
name: google-ads-audit
description: Comprehensive Google Ads account audit with actionable recommendations. Use when user wants to audit, analyze, or review a Google Ads account, campaigns, or performance. Triggers include requests to audit account structure, analyze Quality Score, review keywords and search terms, evaluate ads and extensions, check landing pages, identify optimization opportunities, find wasted spend, create improvement roadmaps, analyze negative keywords, check brand vs non-brand split, review bidding strategies, analyze ad copy performance, check Performance Max signals, or expand based on converting search terms. Supports CSV/Excel exports from Google Ads, Python API scripts, or MCP direct queries.
metadata:
  version: 1.1.0
---

# Google Ads Account Audit

Perform comprehensive Google Ads audits producing prioritized, actionable recommendations.

## Workflow Overview

1. **Data intake** - Load and parse Google Ads export data
2. **Structure analysis** - Evaluate naming conventions and organization
3. **Quality Score audit** - Calculate weighted QS, find optimization opportunities
4. **Keyword & Search Term analysis** - Identify waste and scaling opportunities
   - 3b. Match type & cross-campaign overlap
   - 3c. Negative keywords audit — eliminate irrelevant traffic
   - 3d. Brand/Non-Brand split — isolate true prospecting performance
5. **Ad evaluation** - Check RSA adoption, Ad Strength, relevance
   - 4b. Bidding strategy audit — match strategy to conversion volume
   - 4c. Brand keyword match types — verify brand protection keywords
   - 4d. Brand ad copy performance — formatting, USPs, promo alignment
6. **Extensions audit** - Verify coverage across campaigns
7. **Display/Placement review** - Analyze placement distribution (if applicable)
8. **Landing page assessment** - Evaluate relevance and best practices
9. **Anomaly detection** - Flag unusual patterns
   - 9b. New search terms for expansion — convert top performers to keywords/feed/pages
10. **Performance Max signals** - Verify asset group signal configuration
11. **Generate outputs** - Create roadmap document + Excel summary

## Data Sources

### Option 1: Manual CSV Export

Request these reports from Google Ads (CSV/Excel):

| Report | Required Columns |
|--------|-----------------|
| Campaigns | Campaign, Type, Status, Cost, Conversions, Conv. Value, Impressions, Clicks, Impr. Share |
| Ad Groups | Campaign, Ad Group, Status, Cost, Conversions, CPA, Clicks, Impr. Share |
| Keywords | Campaign, Ad Group, Keyword, Match Type, Status, QS, Cost, Conversions, CPA, Clicks, Impressions, Impr. Share |
| Search Terms | Campaign, Ad Group, Search Term, Match Type, Cost, Conversions, CPA, Clicks, Added/Excluded |
| Ads | Campaign, Ad Group, Ad Type, Status, Ad Strength, Headlines, Descriptions, Final URL |
| Extensions | Campaign, Extension Type, Status |
| Placements (Display) | Campaign, Placement, Type, Cost, Conversions |

### Option 2: Google Ads API — Python (Recommended)

For automated data extraction, see [references/google-ads-api.md](references/google-ads-api.md).

Benefits:
- Complete data without manual export
- Consistent column naming
- Can include historical comparisons
- Automatable for recurring audits

### Option 3: MCP (Supplementary)

When a Google Ads MCP is active in the session, use it for ad-hoc queries during the audit — for example to verify negative keyword lists live, check a specific campaign's bidding strategy, or inspect Performance Max signals without re-running full Python scripts.

Useful MCP query topics:
- **Negative keyword candidates**: `search_term_view` WHERE `conversions = 0` AND `cost_micros > 20000000`
- **Existing shared negative lists**: `shared_set` WHERE `type = 'NEGATIVE_KEYWORDS'`
- **Campaign bidding strategies**: `campaign.bidding_strategy_type` + `metrics.conversions`
- **Brand campaign keyword match types**: `keyword_view` WHERE `campaign.name LIKE '%brand%'`
- **PMax asset group signals**: `asset_group` WHERE `advertising_channel_type = 'PERFORMANCE_MAX'`

## Analysis Modules

### 1. Account Structure & Naming

Evaluate naming conventions for clarity:
- **Brand vs Non-brand** - Clear separation (e.g., `[Brand]`, `[NB]`, `_brand_`, `_generic_`)
- **Campaign types** - Identifiable (Search, Display, PMax, Shopping)
- **Geographic/Language** - If applicable, marked in names
- **Consistency** - Same pattern across account

**Output**: Structure score (1-10) + specific naming issues

### 2. Quality Score Analysis

See [references/quality-score.md](references/quality-score.md) for weighted average calculation and distribution analysis.

Key outputs:
- **QS Distribution**: Cost/Conv % by QS level (1-10)
- **Efficiency analysis**: Low QS (1-6) vs High QS (7-10) spend efficiency
- Weighted QS by campaign and ad group
- High-spend + low-QS keywords (improvement opportunities)
- QS component breakdown (Expected CTR, Ad Relevance, Landing Page)
- Estimated savings from QS improvements

Typical finding: 31% cost on QS < 7 yields only 19% conversions

### 3. Keywords & Search Terms

See [references/keyword-analysis.md](references/keyword-analysis.md) for detailed methodology.

Identify:
- **Pause candidates**: High spend, low/no conversions, high CPA
- **Scale candidates**: Low CPA + low impression share
- **Zero-impression keywords**: No activity in analysis period
- **Keyword overlap**: Same keywords across ad groups
- **Search term relevance**: Deviation from target keywords

### 3b. Match Type & Cross-Campaign Overlap

See [references/match-type-overlap.md](references/match-type-overlap.md) for detailed analysis.

**Match Type Performance**:
- Analyze cost vs conversion distribution by match type
- Calculate efficiency ratio (Conv% / Cost%)
- Typical finding: Exact match delivers 70% conv for 45% cost

**Cross-Campaign Overlap**:
- Detect same search terms triggering multiple campaigns
- Identify brand terms leaking to generic campaigns
- Find cannibalization between campaigns

**Recommendations focus**:
- Increase exact match keyword coverage
- Add negative keywords for brand protection
- Use phrase match for specific, high-intent terms

### 3c. Negative Keywords Audit

See [references/keyword-analysis.md](references/keyword-analysis.md) for e-commerce negative categories, detection logic, and three-tier implementation.

Find search terms that will never convert:
- Terms with clicks but zero conversions (filter by cost threshold)
- Low-relevance terms mismatched to ad group intent
- Common irrelevant categories: free/cheap/DIY, job-related, educational, wrong product type

**Implementation levels**:
- **Account-level** shared lists: universal terms that never apply (e.g., "jobs," "salary," "free")
- **Campaign-level**: category-specific exclusions
- **Ad group-level**: segment premium vs. budget product audiences

**Output**: Negative keyword upload CSV with term, match type, and apply-at level

### 3d. Brand/Non-Brand Split

See [references/match-type-overlap.md](references/match-type-overlap.md) for detection and fix workflow.

Most accounts have a hidden issue: campaigns labelled "generic" or "prospecting" secretly contain branded searches. Google routes branded traffic to these campaigns because it performs well and inflates blended metrics.

**How to detect**:
- Pull search terms from all non-brand campaigns
- Filter by brand name variants (including misspellings and model numbers)
- Calculate % of spend and conversions that are actually branded

**How to fix**:
1. Create dedicated branded campaigns
2. Add brand terms as negative keywords to all non-brand campaigns
3. Add non-branded categories as negatives in brand campaigns
4. Target budget split: 80-85% prospecting, 15-20% brand
5. Review search terms weekly; update negative lists monthly

**Output**: Brand leak % by campaign, negative keyword list for brand protection

### 4. Ads Evaluation

See [references/ads-evaluation.md](references/ads-evaluation.md) for detailed methodology.

**RSA Count Analysis**:
- Check RSA count per ad group (target: 1-2 max)
- Flag ad groups with 3+ RSAs (data dilution)

**Ad Strength Distribution**:
- Analyze spend % by Ad Strength rating
- Typical issue: 52% spend on Poor RSAs, only 5% on Excellent/Good
- Priority: Optimize RSAs with high spend + low strength

Check for each campaign/ad group:
- RSA adoption (best practice = RSA only, no legacy ETA)
- Ad Strength rating (Poor/Average/Good/Excellent)
- Number of headlines (target: 15) and descriptions (target: 4)
- Pin usage (excessive pinning = Bad)

**LLM Relevance Check**: Compare ad copy to ad group keywords:
- Headlines contain target keywords or close variants?
- Descriptions address user intent?
- CTAs present and clear?

**Recommendations**:
- Optimize Poor/Average RSAs to Good/Excellent
- Add more headlines/descriptions with keywords
- Reduce RSA count to 1-2 per ad group
- Keep high-performing legacy ETAs if data supports

### 4b. Bidding Strategy Audit

See [references/bidding-strategy.md](references/bidding-strategy.md) for full framework.

Two checks:

**Branded campaigns**: People searching for your brand already want to buy — avoid letting Google freely optimize and overcharge on this high-intent traffic. Check for unconstrained Target ROAS or Target CPA with no bid caps. Recommended: Manual CPC (set 20-50% below current avg CPC), Target Impression Share, or constrained ROAS.

**Non-branded campaigns**: Smart bidding requires data. Match strategy to actual monthly conversion volume:

| Monthly Conversions | Recommended Strategy |
|---------------------|---------------------|
| 0–15 | Enhanced CPC or Maximize Clicks |
| 15–30 | Target CPA |
| 30–50 | Target ROAS |
| 50+ | Maximize Conversion Value |

### 4c. Brand Keyword Match Types

See [references/match-type-overlap.md](references/match-type-overlap.md) for detection query.

Brand protection keywords must use controlled match types:
- **Exact match** `[brand name]` — primary, most control
- **Phrase match** `"brand name"` — for branded variants and typos
- **Never Broad match** — risks brand budget being spent on unrelated searches

Check all keywords in brand campaigns for any Broad match types and flag for immediate fix.

### 4d. Brand Ad Copy Performance

See [references/ads-evaluation.md](references/ads-evaluation.md) for quality checks and formatting standards.

**CTR benchmarks**:
- Branded Search: ≥5% CTR required
- Non-Branded Search: ≥2% CTR required
- Shopping: ≥2-3% CTR required

For ads below benchmark: create 2-3 new variations, test for minimum 2 weeks, pause consistently poor performers.

**Brand ad quality requirements**:
- Title Case formatting, consistent punctuation
- Include USPs (unique selling propositions)
- Feature key benefits: free shipping, guarantees, delivery speed
- Reflect current promotions — schedule ad copy aligned to promo calendar
- Headline structure: `Brand + Category | Main USP | Offer/Trust Signal`

### 5. Extensions Audit

See [references/extensions-placements.md](references/extensions-placements.md) for coverage matrix and best practices.

Required extensions per campaign type:

| Extension | Search | Display | PMax |
|-----------|--------|---------|------|
| Sitelinks | ✓ | - | ✓ |
| Callouts | ✓ | - | ✓ |
| Structured Snippets | ✓ | - | - |
| Call | Industry-dependent | - | - |
| Location | Local business | - | ✓ |
| Image | ✓ | - | - |

**Output**: Missing extensions matrix

### 6. Display Placements (if applicable)

See [references/extensions-placements.md](references/extensions-placements.md) for placement categorization.

Analyze placement distribution:
- % spend on apps vs websites vs YouTube
- High-spend low-converting placements
- Placement exclusion recommendations

### 7. Landing Pages

Evaluate:
- URL diversity (one URL vs personalized per ad group)
- HTTPS usage
- Page load indicators (if available)
- Keyword relevance to landing page (from URL/path analysis)

### 8. Rejected Items

List all disapproved:
- Ads
- Keywords
- Extensions

With rejection reasons and fix recommendations.

### 9. Anomaly Detection

Flag:
- Sudden spend spikes in search terms
- New high-volume search terms
- CTR anomalies (very high or very low)
- CPA outliers

### 9b. New Search Terms for Expansion

See [references/keyword-analysis.md](references/keyword-analysis.md) for filtering logic and 4-action framework.

Find search terms already converting that you are not directly targeting. These prove demand exists — double down on them.

**Filter criteria**: Conversions > 0, CPA below target, Clicks ≥ 3

**4 actions per qualifying term**:
1. **Add as keyword** — Phrase match for discovery terms, Exact match for proven high-volume terms; set bid 20% above average (proven converter)
2. **Optimize product feed title** — Place keywords in first 30-35 characters (most visible in search results); titles cut after ~70 chars so prioritize early placement
3. **Duplicate products with different keyword angles** — Use feed management tools to create variants for different intents (weight loss / muscle growth / women / etc.); update Item ID for each duplicate
4. **Build aligned landing pages** — Create pages matching the keyword theme and audience intent; match intent type (educational for Search, product-focused for Shopping)

### 10. Performance Max Signals

See [references/pmax-signals.md](references/pmax-signals.md) for configuration guidance.

Most PMax asset groups have empty signal fields — a missed optimization opportunity. Check each asset group's Signals section:

- **Search Themes**: Up to 50 per asset group; use medium-tail keywords describing products (not too broad, not too specific)
- **Customer Lists**: Add "All Purchases" for lookalike targeting, "High-Value Customers" as positive signal, recent purchasers as exclusion
- **Custom Segments**: Add relevant audience segments based on interests/behaviors for the product category

## Key Metrics Reference

| Metric | Good | Warning | Bad |
|--------|------|---------|-----|
| Quality Score | ≥7 | 5-6 | ≤4 |
| Search Impr. Share | >80% | 50-80% | <50% |
| CTR (Brand Search) | ≥5% | 3-5% | <3% |
| CTR (Non-Brand Search) | ≥2% | 1-2% | <1% |
| CTR (Shopping) | ≥2-3% | 1-2% | <1% |
| Ad Strength | Excellent/Good | Average | Poor |

## Output Generation

### 1. Executive Summary (Markdown/DOCX)

Structure:
```
# Google Ads Audit: [Account Name]
Date: [Date]

## Executive Summary
[2-3 sentence overview of account health]

## Priority Roadmap
### Immediate (This Week)
1. [Action] - [Impact] - [Effort]
...

### Short-term (This Month)
...

### Medium-term (This Quarter)
...

## Detailed Findings
[Section per analysis module]

## Appendix
[Methodology notes]
```

### 2. Excel Workbook

Create workbook with sheets:
- **Summary** - Key metrics dashboard
- **Structure** - Naming issues
- **Quality Score** - Weighted QS by campaign/ad group
- **Keywords** - Pause/scale recommendations
- **Search Terms** - Top spenders + relevance
- **Negative Keywords** - Suggested negatives with match type and apply-at level
- **Brand vs Non-Brand** - Brand leak % by campaign, traffic split
- **Bidding Strategy** - Current vs recommended strategy per campaign
- **Ads** - Ad Strength + recommendations
- **Extensions** - Coverage matrix
- **Placements** - If Display campaigns present
- **Search Term Expansion** - Converting terms with 4-action recommendations
- **PMax Signals** - Signal coverage per asset group
- **Roadmap** - Prioritized actions

See [references/excel-template.md](references/excel-template.md) for column specifications.

## Priority Scoring

Score each recommendation:
- **Impact**: High (3) / Medium (2) / Low (1)
- **Effort**: Low (3) / Medium (2) / High (1)
- **Priority Score** = Impact × Effort

Sort roadmap by priority score descending.
