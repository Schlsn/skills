# Match Type & Keyword Overlap Analysis

## Match Type Performance Analysis

Analyze cost vs conversion distribution by match type to identify optimization opportunities.

### Match Type Categories

| Match Type | Notation | Typical Behavior |
|------------|----------|------------------|
| Exact match | [keyword] | Highest relevance, lowest volume |
| Exact match (close variant) | Auto | Google's interpretation of exact |
| Phrase match | "keyword" | Medium relevance/volume |
| Phrase match (close variant) | Auto | Google's interpretation of phrase |
| Broad match | keyword | Highest volume, lowest relevance |

### Performance Analysis

```python
def analyze_match_type_performance(df):
    """
    Analyze performance by match type.
    
    Args:
        df: Keywords or Search Terms DataFrame with Match Type, Cost, Conversions
    
    Returns:
        DataFrame with match type performance breakdown
    """
    summary = df.groupby('Match type').agg({
        'Cost': 'sum',
        'Conversions': 'sum',
        'Clicks': 'sum',
        'Impressions': 'sum'
    }).reset_index()
    
    total_cost = summary['Cost'].sum()
    total_conv = summary['Conversions'].sum()
    
    summary['Cost_Pct'] = (summary['Cost'] / total_cost * 100).round(2)
    summary['Conv_Pct'] = (summary['Conversions'] / total_conv * 100).round(2)
    summary['CPA'] = (summary['Cost'] / summary['Conversions'].replace(0, float('nan'))).round(2)
    summary['CTR'] = (summary['Clicks'] / summary['Impressions'] * 100).round(2)
    
    # Efficiency ratio: Conv% / Cost%
    summary['Efficiency'] = (summary['Conv_Pct'] / summary['Cost_Pct']).round(2)
    
    return summary[[
        'Match type', 'Cost', 'Cost_Pct', 'Conversions', 'Conv_Pct', 
        'CPA', 'CTR', 'Efficiency'
    ]]
```

### Efficiency Interpretation

| Efficiency | Meaning | Action |
|------------|---------|--------|
| > 1.5 | Very efficient | Scale budget |
| 1.0 - 1.5 | Efficient | Maintain |
| 0.7 - 1.0 | Neutral | Monitor |
| < 0.7 | Inefficient | Reduce/restructure |

### Typical Findings Pattern

```
Exact match + Exact match (close variant) often deliver:
- 70% of conversions
- Only 45% of cost
→ High efficiency, should scale

Broad match often shows:
- 15% of conversions  
- 25% of cost
→ Low efficiency, needs negative keywords or restructuring
```

## Cross-Campaign Search Term Overlap

Identify when same search terms trigger ads from multiple campaigns (cannibalization).

### Detection Method

```python
def detect_search_term_overlap(st_df):
    """
    Find search terms appearing in multiple campaigns.
    
    Args:
        st_df: Search Terms report DataFrame
    
    Returns:
        DataFrame with overlapping terms and their distribution
    """
    # Group by search term
    overlap = st_df.groupby('Search term').agg({
        'Campaign': lambda x: list(x.unique()),
        'Cost': 'sum',
        'Conversions': 'sum',
        'Clicks': 'sum'
    }).reset_index()
    
    # Filter to terms in multiple campaigns
    overlap['Campaign_Count'] = overlap['Campaign'].apply(len)
    overlap = overlap[overlap['Campaign_Count'] > 1].copy()
    
    # Format campaigns list
    overlap['Campaigns'] = overlap['Campaign'].apply(lambda x: ' | '.join(x))
    
    return overlap[[
        'Search term', 'Campaigns', 'Campaign_Count',
        'Cost', 'Conversions', 'Clicks'
    ]].sort_values('Cost', ascending=False)


def analyze_overlap_by_campaign(st_df, overlap_terms):
    """
    Show which campaign "wins" each overlapping term.
    
    Returns per-campaign breakdown for overlapping terms.
    """
    # Filter to overlapping terms only
    overlap_detail = st_df[st_df['Search term'].isin(overlap_terms)]
    
    # Pivot to show cost/conv by campaign for each term
    pivot = overlap_detail.pivot_table(
        index='Search term',
        columns='Campaign',
        values=['Cost', 'Conversions'],
        aggfunc='sum',
        fill_value=0
    )
    
    return pivot
```

### Common Overlap Scenarios

| Scenario | Example | Issue | Fix |
|----------|---------|-------|-----|
| Brand in Generic | "brand name" triggers generic campaign | Wasted spend | Add brand as negative to generic |
| Location overlap | "service prague" in both CZ and EN campaigns | Budget split | Use location targeting or negatives |
| Service overlap | "ivf treatment" in multiple service campaigns | Cannibalization | Consolidate or use negatives |

### Brand Cannibalization Check

```python
def check_brand_cannibalization(st_df, brand_terms):
    """
    Check if brand terms appear in non-brand campaigns.
    
    Args:
        st_df: Search Terms DataFrame
        brand_terms: List of brand keywords (e.g., ['pronatal', 'brand name'])
    
    Returns:
        DataFrame with brand terms in wrong campaigns
    """
    # Identify brand campaigns (by naming convention)
    st_df['Is_Brand_Campaign'] = st_df['Campaign'].str.lower().str.contains('brand')
    
    # Check if search term contains brand
    brand_pattern = '|'.join([term.lower() for term in brand_terms])
    st_df['Contains_Brand'] = st_df['Search term'].str.lower().str.contains(brand_pattern)
    
    # Flag: brand term in non-brand campaign
    cannibalization = st_df[
        (st_df['Contains_Brand']) & 
        (~st_df['Is_Brand_Campaign'])
    ]
    
    return cannibalization[[
        'Campaign', 'Ad Group', 'Search term',
        'Cost', 'Conversions', 'CPA'
    ]].sort_values('Cost', ascending=False)
```

## Recommendations Generator

```python
def generate_match_type_recommendations(match_summary, overlap_df, brand_leak_df):
    """Generate actionable recommendations."""
    recommendations = []
    
    # Match type recommendations
    exact_efficiency = match_summary[
        match_summary['Match type'].str.contains('Exact')
    ]['Efficiency'].mean()
    
    broad_efficiency = match_summary[
        match_summary['Match type'] == 'Broad match'
    ]['Efficiency'].values
    
    if len(broad_efficiency) > 0 and broad_efficiency[0] < 0.8:
        recommendations.append({
            'Category': 'Match Type',
            'Issue': f"Broad match efficiency {broad_efficiency[0]:.2f} below threshold",
            'Action': 'Add negative keywords or convert to phrase match',
            'Impact': 'High',
            'Effort': 'Medium'
        })
    
    if exact_efficiency > 1.2:
        recommendations.append({
            'Category': 'Match Type',
            'Issue': f"Exact match highly efficient ({exact_efficiency:.2f})",
            'Action': 'Increase exact match keyword coverage and bids',
            'Impact': 'High',
            'Effort': 'Low'
        })
    
    # Overlap recommendations
    if len(overlap_df) > 0:
        total_overlap_cost = overlap_df['Cost'].sum()
        recommendations.append({
            'Category': 'Overlap',
            'Issue': f"{len(overlap_df)} search terms overlap campaigns (${total_overlap_cost:,.0f})",
            'Action': 'Add cross-campaign negative keywords',
            'Impact': 'Medium',
            'Effort': 'Medium'
        })
    
    # Brand leak recommendations
    if len(brand_leak_df) > 0:
        brand_leak_cost = brand_leak_df['Cost'].sum()
        recommendations.append({
            'Category': 'Brand Leak',
            'Issue': f"Brand terms in non-brand campaigns (${brand_leak_cost:,.0f})",
            'Action': 'Add brand terms as negatives to generic campaigns',
            'Impact': 'High',
            'Effort': 'Low'
        })
    
    return pd.DataFrame(recommendations)
```

## Output Tables

### Match Type Summary

| Match Type | Cost | Cost % | Conv | Conv % | CPA | Efficiency | Action |
|------------|------|--------|------|--------|-----|------------|--------|
| Exact match | $5,000 | 29.8% | 62 | 62.1% | $81 | 2.08 | Scale |
| Exact (close) | $2,500 | 15.1% | 8 | 8.0% | $313 | 0.53 | Monitor |
| Phrase match | $2,400 | 14.7% | 10 | 10.0% | $240 | 0.68 | Optimize |
| Phrase (close) | $4,300 | 26.2% | 9 | 9.0% | $478 | 0.34 | Review |
| Broad match | $2,300 | 14.2% | 11 | 11.0% | $209 | 0.77 | Add negatives |

### Search Term Overlap

| Search Term | Campaigns | Cost | Conv | Winner | Action |
|-------------|-----------|------|------|--------|--------|
| pronatal czech republic | Brand, Generic ENG | $800 | 15 | Brand | Add negative to Generic |
| ivf prague | IVF CZ, IVF EN | $500 | 8 | IVF EN | Location targeting |

### Brand Leak Report

| Campaign | Search Term | Cost | Conv | Action |
|----------|-------------|------|------|--------|
| ENG \| Generic \| Fertility | pronatal clinic | $300 | 5 | Add "pronatal" as negative |
