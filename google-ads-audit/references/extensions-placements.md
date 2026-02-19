# Extensions & Placements Analysis

## Extensions Audit

### Required Extensions by Campaign Type

| Extension Type | Search Brand | Search Generic | Display | PMax | Shopping |
|----------------|--------------|----------------|---------|------|----------|
| Sitelinks | Required | Required | N/A | Required | N/A |
| Callouts | Required | Required | N/A | Required | N/A |
| Structured Snippets | Recommended | Required | N/A | N/A | N/A |
| Call | If applicable | If applicable | N/A | If applicable | N/A |
| Location | If local | If local | N/A | If local | N/A |
| Image | Recommended | Required | N/A | N/A | N/A |
| Price | Optional | Recommended | N/A | N/A | N/A |
| Promotion | If promos | If promos | N/A | If promos | N/A |
| Lead Form | If lead gen | If lead gen | N/A | If lead gen | N/A |

### Extension Coverage Analysis

```python
def analyze_extension_coverage(ext_df, campaign_df):
    """Check extension coverage across campaigns."""
    
    # Determine campaign types
    campaign_types = campaign_df.set_index('Campaign')['Campaign type'].to_dict()
    
    # Pivot extensions by campaign
    ext_pivot = ext_df.pivot_table(
        index='Campaign',
        columns='Extension type',
        values='Status',
        aggfunc='count'
    ).fillna(0)
    
    # Convert to boolean
    ext_pivot = ext_pivot > 0
    
    # Check requirements
    results = []
    for campaign in ext_pivot.index:
        camp_type = campaign_types.get(campaign, 'Unknown')
        
        missing = []
        
        if camp_type == 'Search':
            if not ext_pivot.loc[campaign].get('Sitelink', False):
                missing.append('Sitelinks')
            if not ext_pivot.loc[campaign].get('Callout', False):
                missing.append('Callouts')
            if not ext_pivot.loc[campaign].get('Structured snippet', False):
                missing.append('Structured Snippets')
            if not ext_pivot.loc[campaign].get('Image', False):
                missing.append('Image')
        
        elif camp_type == 'Performance Max':
            if not ext_pivot.loc[campaign].get('Sitelink', False):
                missing.append('Sitelinks')
            if not ext_pivot.loc[campaign].get('Callout', False):
                missing.append('Callouts')
        
        results.append({
            'Campaign': campaign,
            'Type': camp_type,
            'Missing': ', '.join(missing) if missing else 'None',
            'Missing_Count': len(missing),
            'Priority': 'High' if len(missing) >= 2 else ('Medium' if len(missing) == 1 else 'Low')
        })
    
    return pd.DataFrame(results)
```

### Sitelink Best Practices

- Minimum: 4 sitelinks
- Target: 8+ sitelinks for rotation
- Include varied CTAs and landing pages
- Use description lines

### Callout Best Practices

- Minimum: 4 callouts
- Target: 8+ for variety
- Highlight unique selling points
- Keep under 25 characters

### Structured Snippets Best Practices

- Use relevant headers: Amenities, Brands, Services, Types, etc.
- Minimum 4 values per header
- Match to ad group themes

## Display Placement Analysis

### Placement Type Categories

```python
def categorize_placement(placement):
    """Categorize placement by type."""
    placement = str(placement).lower()
    
    if 'youtube.com' in placement:
        return 'YouTube'
    elif 'adsenseformobileapps.com' in placement or 'mobileapp::' in placement:
        return 'Mobile App'
    elif placement.startswith('http') or '.' in placement:
        return 'Website'
    else:
        return 'Other'

def analyze_placements(df):
    """Analyze placement distribution and performance."""
    df['Placement_Type'] = df['Placement'].apply(categorize_placement)
    
    # Aggregate by type
    summary = df.groupby('Placement_Type').agg({
        'Cost': 'sum',
        'Conversions': 'sum',
        'Clicks': 'sum',
        'Impressions': 'sum'
    }).reset_index()
    
    summary['CPA'] = summary['Cost'] / summary['Conversions'].replace(0, float('nan'))
    summary['CTR'] = summary['Clicks'] / summary['Impressions'] * 100
    summary['Cost_Pct'] = summary['Cost'] / summary['Cost'].sum() * 100
    
    return summary
```

### Placement Red Flags

Watch for:
- >50% spend on mobile apps (often low quality)
- High spend on single placements with no conversions
- YouTube placements without video ads

### Exclusion Recommendations

```python
def suggest_placement_exclusions(df, min_cost=50, max_cpa_multiplier=3):
    """Suggest placements to exclude."""
    avg_cpa = df[df['Conversions'] > 0]['CPA'].mean()
    
    # High cost, no conversions
    no_conv = df[(df['Cost'] >= min_cost) & (df['Conversions'] == 0)]
    
    # High CPA
    high_cpa = df[
        (df['Conversions'] > 0) & 
        (df['CPA'] > avg_cpa * max_cpa_multiplier)
    ]
    
    exclusions = pd.concat([no_conv, high_cpa]).drop_duplicates()
    exclusions['Reason'] = exclusions.apply(
        lambda r: 'No conversions' if r['Conversions'] == 0 else f"CPA {r['CPA']:.0f} > {avg_cpa * max_cpa_multiplier:.0f}",
        axis=1
    )
    
    return exclusions[[
        'Campaign', 'Placement', 'Placement_Type',
        'Cost', 'Conversions', 'CPA', 'Reason'
    ]].sort_values('Cost', ascending=False)
```

### App Category Exclusions

Common mobile app categories to consider excluding:
- Games (unless gaming advertiser)
- Parked domains
- Error pages
- Under construction

```python
app_exclusion_categories = [
    'Games',
    'adsenseformobileapps.com::1-xxx', # Specific low-quality apps
]
```

## Output Tables

### Extension Coverage Matrix

| Campaign | Type | Sitelinks | Callouts | Str. Snippets | Image | Call | Location | Missing | Priority |
|----------|------|-----------|----------|---------------|-------|------|----------|---------|----------|
| Brand CZ | Search | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | None | Low |
| Generic IVF | Search | ✓ | ✗ | ✗ | ✗ | ✗ | N/A | 3 | High |

### Placement Summary

| Type | Cost | % of Total | Conversions | CPA | Action |
|------|------|------------|-------------|-----|--------|
| Website | $5,000 | 60% | 50 | $100 | Monitor |
| Mobile App | $2,500 | 30% | 5 | $500 | Review |
| YouTube | $800 | 10% | 10 | $80 | Scale |

### Exclusion Recommendations

| Placement | Type | Cost | Conv | CPA | Reason | Priority |
|-----------|------|------|------|-----|--------|----------|
| game-app.com | App | $500 | 0 | - | No conv | High |
| random-site.com | Website | $300 | 0 | - | No conv | Medium |
