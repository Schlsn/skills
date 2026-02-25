# Performance Max Signals

## Overview

Performance Max campaigns serve ads across all Google channels (Search, Shopping, Display, YouTube, Gmail, Maps). Without signals, Google starts from scratch to determine who to target. Signals provide directional context — they tell Google which audiences and search themes to prioritize, dramatically speeding up optimization.

**Most accounts have empty signal fields.** This is a missed optimization that leaves Google without guidance.

## What to Check

Navigate to: Performance Max campaign → Asset groups → click into each asset group → **Signals** tab

Check whether each signal type is configured or empty.

## Detection Query

```python
PMAX_ASSET_GROUP_QUERY = """
    SELECT
        campaign.name,
        campaign.status,
        asset_group.name,
        asset_group.status,
        asset_group.ad_strength
    FROM asset_group
    WHERE campaign.advertising_channel_type = 'PERFORMANCE_MAX'
        AND campaign.status != 'REMOVED'
        AND asset_group.status != 'REMOVED'
"""

# Note: Signal details (search themes, audience signals) require
# the asset_group_signal resource — query separately if MCP/API supports it:
PMAX_SIGNALS_QUERY = """
    SELECT
        campaign.name,
        asset_group.name,
        asset_group_signal.audience.audience
    FROM asset_group_signal
    WHERE campaign.advertising_channel_type = 'PERFORMANCE_MAX'
        AND campaign.status != 'REMOVED'
"""
```

```python
def audit_pmax_signals(asset_groups_df, signals_df=None):
    """
    Check which PMax asset groups have signals configured.

    Args:
        asset_groups_df: Asset groups DataFrame
        signals_df: Optional signals DataFrame (if available from API)

    Returns:
        DataFrame flagging asset groups missing signals
    """
    asset_groups_df = asset_groups_df.copy()

    if signals_df is not None and not signals_df.empty:
        # Join signals to asset groups
        has_signals = signals_df.groupby('asset_group_name').size().reset_index(name='Signal_Count')
        asset_groups_df = asset_groups_df.merge(has_signals, on='asset_group_name', how='left')
        asset_groups_df['Signal_Count'] = asset_groups_df['Signal_Count'].fillna(0)
        asset_groups_df['Has_Signals'] = asset_groups_df['Signal_Count'] > 0
    else:
        # Cannot determine automatically — flag for manual check
        asset_groups_df['Has_Signals'] = None
        asset_groups_df['Signal_Count'] = None
        asset_groups_df['Manual_Check_Required'] = True

    return asset_groups_df[[
        'campaign_name', 'asset_group_name', 'asset_group_ad_strength',
        'Has_Signals', 'Signal_Count'
    ]]
```

## Three Signal Types

### 1. Search Themes

Search themes tell Google which search queries are relevant to this asset group.

**Configuration**:
- Up to **50 search themes** per asset group
- Use medium-tail keywords — not too broad, not too specific
- Focus on terms describing your products and customer intent

**Examples for a supplement brand**:
```
"organic protein powder"
"post workout recovery supplement"
"grass fed whey protein"
"creatine monohydrate for men"
"collagen peptides for women"
"pre workout natural"
"vegan protein powder"
"bcaa amino acids"
"magnesium glycinate supplement"
"omega 3 fish oil capsules"
```

**Rules**:
- Avoid single-word themes (too broad, Google already knows "protein")
- Avoid overly specific long-tail (5+ words) — defeats the purpose of PMax
- Aim for 2-3 word themes describing the product + a key qualifier (audience, benefit, variant)

### 2. Customer Lists

Customer lists as signals tell Google to find people similar to your existing customers.

**Recommended lists to add**:

| List | Signal Type | Purpose |
|------|-------------|---------|
| All Purchases (lifetime) | Positive | Lookalike: find people similar to all buyers |
| High-Value Customers (top 20% by LTV) | Positive | Lookalike: find people similar to best buyers |
| Recent Purchasers (last 30 days) | Exclusion | Avoid re-targeting customers who just bought |
| Email Subscribers | Positive | Lookalike: find people similar to engaged audience |
| Cart Abandoners | Positive | Retarget: warm audience who showed interest |

```python
# Customer lists must be created in Google Ads UI or via Customer Match API
# Once created, reference them by name in asset group signals

# Minimum list sizes for effective lookalike:
# - Seed list: 1,000+ members recommended
# - For Customer Match: 1,000+ matched emails

CUSTOMER_LIST_QUERY = """
    SELECT
        user_list.name,
        user_list.size_for_display,
        user_list.size_for_search,
        user_list.type,
        user_list.membership_status
    FROM user_list
    WHERE user_list.membership_status = 'OPEN'
        AND user_list.size_for_search > 0
"""
```

### 3. Custom Segments

Custom segments define audiences based on interests, behaviors, or in-market signals.

**Types of custom segments**:

| Type | Based On | Example |
|------|----------|---------|
| Interests & Habits | What people are interested in | "Health and wellness" |
| In-Market | Active buyers in category | "Sports nutrition buyers" |
| Apps | Apps people use | "MyFitnessPal users" |
| Websites | Websites people visit | "Visitors to competitor sites" |
| Search Terms | What people search on Google | "people who searched: protein powder buy" |

**Recommended approach**:
1. Create custom segment based on **competitor websites** (targets people browsing competitors)
2. Create custom segment based on **category search terms** (targets people actively searching)
3. Add both as positive signals to relevant asset groups

```
Custom Segment Example — Supplement Brand:
Name: "Supplement Shoppers"
Type: People who searched for any of:
  - "buy protein powder"
  - "creatine supplement online"
  - "best pre workout"
  - "vegan protein buy"
  - "supplement store near me"
```

## Fix Workflow

For each asset group missing signals:

1. **Add Search Themes first** — easiest, highest impact, do immediately
   - Brainstorm 20-50 medium-tail terms relevant to the asset group's products
   - Focus on commercial intent (buying, comparing, evaluating)

2. **Add Customer Lists** — requires CRM data or Google Ads remarketing lists
   - Export purchaser emails from CRM → upload via Customer Match
   - If no purchase lists exist, use website visitor remarketing lists

3. **Create Custom Segments** — 10 minutes to set up
   - Competitor domain targeting
   - Category search term targeting

4. **Review signal performance** after 30 days
   - Google Ads shows which signals contributed to conversions
   - Remove low-performing signals, add variants of high-performing ones

## Output Table

| Campaign | Asset Group | Ad Strength | Search Themes | Customer Lists | Custom Segments | Priority |
|----------|-------------|-------------|--------------|----------------|-----------------|----------|
| PMax - Supplements | All Products | Good | 0 | 0 | 0 | High |
| PMax - Protein | Women | Average | 12 | 1 | 0 | Medium |
| PMax - Creatine | Men | Excellent | 48 | 3 | 2 | OK |
