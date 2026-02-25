# Bidding Strategy Audit

## Overview

Correct bidding strategy depends on two factors:
1. **Campaign type** (branded vs non-branded) — different goals, different risks
2. **Conversion volume** — smart bidding needs data to work; too little data = poor optimization

## Branded Campaign Bidding

### The Problem

People searching for your brand already want to buy from you. You should control costs — not let Google freely optimize and overcharge on this high-intent, easy-to-convert traffic.

**Red flag**: Unconstrained Target ROAS or Target CPA on brand campaigns with no bid caps. Google will bid up aggressively on branded queries because they convert well, driving up your CPCs unnecessarily.

### Detection

```python
BRAND_BIDDING_QUERY = """
    SELECT
        campaign.name,
        campaign.bidding_strategy_type,
        campaign.target_cpa.target_cpa_micros,
        campaign.target_roas.target_roas,
        campaign.maximize_conversions.target_cpa_micros,
        campaign.maximize_conversion_value.target_roas,
        metrics.average_cpc,
        metrics.conversions,
        metrics.cost_micros
    FROM campaign
    WHERE segments.date DURING LAST_30_DAYS
        AND campaign.status = 'ENABLED'
"""


def check_brand_bidding(campaigns_df, brand_pattern='brand'):
    """
    Flag brand campaigns using unconstrained smart bidding.

    Args:
        campaigns_df: Campaigns DataFrame from GAQL query above
        brand_pattern: Substring identifying brand campaigns

    Returns:
        DataFrame with flagged campaigns and recommended changes
    """
    brand = campaigns_df[
        campaigns_df['campaign_name'].str.lower().str.contains(brand_pattern)
    ].copy()

    unconstrained_strategies = ['TARGET_CPA', 'TARGET_ROAS', 'MAXIMIZE_CONVERSIONS',
                                 'MAXIMIZE_CONVERSION_VALUE']

    brand['Is_Unconstrained'] = (
        brand['campaign_bidding_strategy_type'].isin(unconstrained_strategies) &
        brand['campaign_target_cpa_target_cpa_micros'].isna() &   # No CPA target = unconstrained
        brand['campaign_target_roas_target_roas'].isna()           # No ROAS target = unconstrained
    )

    return brand[[
        'campaign_name', 'campaign_bidding_strategy_type',
        'Is_Unconstrained', 'metrics_average_cpc', 'metrics_conversions'
    ]]
```

### Recommended Bidding Strategies for Brand Campaigns

| Strategy | Configuration | Best For |
|----------|--------------|---------|
| **Manual CPC** | Start 20-50% below current avg CPC | Maximum control; test incrementally |
| **Target Impression Share** | Set IS target (e.g., 90%) with max CPC cap | Control visibility while capping costs |
| **Target ROAS with constraints** | Set challenging ROAS target + bid cap | When you need some automation but with guardrails |

**Never use**: Unconstrained Target ROAS or Target CPA without bid caps on brand campaigns.

### Manual CPC Implementation

```
1. Note current avg CPC for brand campaign
2. Switch to Manual CPC
3. Set initial bids at 60-80% of current avg CPC
4. Monitor impression share (aim to maintain >90%)
5. Increase bids in 10% increments if impression share drops below target
6. Adjust based on position and conversion data
```

---

## Non-Branded Campaign Bidding

### The Problem

Google's smart bidding algorithms need sufficient conversion data to optimize. Without enough data, they make poor decisions — you either overpay for conversions or miss opportunities.

### Conversion Volume Framework

Match bidding strategy to monthly conversion volume in the campaign:

| Monthly Conversions | Recommended Strategy | Rationale |
|---------------------|---------------------|-----------|
| **0–15** | Enhanced CPC or Maximize Clicks | Too little data for smart bidding; focus on gathering data first |
| **15–30** | Target CPA | Enough data for basic optimization; focus on controlling cost per acquisition |
| **30–50** | Target ROAS | Sufficient for revenue-based optimization; set target near your breakeven ROAS |
| **50+** | Maximize Conversion Value | Enough data for Google to find optimal bids within constraints |

### Detection

```python
def audit_nonbrand_bidding(campaigns_df, brand_pattern='brand'):
    """
    Check non-brand campaigns for appropriate bidding strategy
    based on actual conversion volume.

    Args:
        campaigns_df: Campaigns DataFrame with bidding strategy and conversion data
        brand_pattern: Substring to exclude brand campaigns

    Returns:
        DataFrame with current vs recommended strategy per campaign
    """
    non_brand = campaigns_df[
        ~campaigns_df['campaign_name'].str.lower().str.contains(brand_pattern)
    ].copy()

    def recommend_strategy(monthly_conversions):
        if monthly_conversions < 15:
            return 'Enhanced CPC or Maximize Clicks'
        elif monthly_conversions < 30:
            return 'Target CPA'
        elif monthly_conversions < 50:
            return 'Target ROAS'
        else:
            return 'Maximize Conversion Value'

    def is_mismatch(row):
        current = row['campaign_bidding_strategy_type']
        recommended = row['Recommended_Strategy']
        # Check if current strategy is appropriate for conversion volume
        if row['metrics_conversions'] < 15:
            return current not in ['ENHANCED_CPC', 'MAXIMIZE_CLICKS', 'MANUAL_CPC']
        elif row['metrics_conversions'] < 30:
            return 'TARGET_CPA' not in current
        elif row['metrics_conversions'] < 50:
            return 'TARGET_ROAS' not in current
        else:
            return 'MAXIMIZE_CONVERSION_VALUE' not in current

    non_brand['Recommended_Strategy'] = non_brand['metrics_conversions'].apply(recommend_strategy)
    non_brand['Strategy_Mismatch'] = non_brand.apply(is_mismatch, axis=1)

    return non_brand[[
        'campaign_name', 'campaign_bidding_strategy_type',
        'metrics_conversions', 'Recommended_Strategy', 'Strategy_Mismatch'
    ]].sort_values('Strategy_Mismatch', ascending=False)
```

### Implementation Steps

**Moving from manual/eCPC to smart bidding (when ready)**:
1. Verify 30+ conversions in last 30 days before switching
2. Set initial Target CPA at 10-20% above current CPA (give Google room to learn)
3. Expect 2-4 week learning period — don't evaluate performance during learning
4. After learning: adjust target CPA in 10-15% increments based on performance
5. Upgrade to Target ROAS only after consistent 30+ conv/month for 2+ consecutive months

**Downgrading when conversion volume drops**:
- If a campaign drops below its threshold for 2+ consecutive months, downgrade to the appropriate strategy
- This commonly happens with seasonal products or after landing page changes

### Output Table

| Campaign | Current Strategy | Monthly Conv | Recommended Strategy | Mismatch? | Priority |
|----------|-----------------|-------------|---------------------|-----------|----------|
| Generic - Supplements | TARGET_ROAS | 8 | Enhanced CPC | Yes | High |
| Generic - Protein | TARGET_CPA | 35 | Target ROAS | Yes | Medium |
| Generic - Creatine | ENHANCED_CPC | 65 | Maximize Conv Value | Yes | Medium |
| Brand - Core | MAXIMIZE_CONVERSIONS | 120 | Manual CPC | Yes (brand) | High |
