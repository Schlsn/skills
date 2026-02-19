# Quality Score Analysis

## QS Distribution Analysis

Analyze spend and conversion distribution by Quality Score level.

### QS Distribution Report

```python
def analyze_qs_distribution(df):
    """
    Analyze cost and conversion distribution by QS level.
    
    Key insight: What % of spend goes to low QS keywords (< 7)?
    """
    # Filter keywords with QS
    df_qs = df[df['Quality Score'].notna() & (df['Quality Score'] != '--')].copy()
    df_qs['Quality Score'] = pd.to_numeric(df_qs['Quality Score'])
    
    summary = df_qs.groupby('Quality Score').agg({
        'Cost': 'sum',
        'Clicks': 'sum',
        'Conversions': 'sum'
    }).reset_index()
    
    total_cost = summary['Cost'].sum()
    total_clicks = summary['Clicks'].sum()
    total_conv = summary['Conversions'].sum()
    
    summary['Cost_Pct'] = (summary['Cost'] / total_cost * 100).round(2)
    summary['Clicks_Pct'] = (summary['Clicks'] / total_clicks * 100).round(2)
    summary['Conv_Pct'] = (summary['Conversions'] / total_conv * 100).round(2)
    summary['CPA'] = (summary['Cost'] / summary['Conversions'].replace(0, float('nan'))).round(2)
    
    return summary.sort_values('Quality Score')

def qs_efficiency_summary(df):
    """
    Summarize QS efficiency: low QS (1-6) vs high QS (7-10).
    
    Typical finding: 31% cost on QS < 7 yields only 19% conversions.
    """
    df_qs = df[df['Quality Score'].notna() & (df['Quality Score'] != '--')].copy()
    df_qs['Quality Score'] = pd.to_numeric(df_qs['Quality Score'])
    
    df_qs['QS_Group'] = df_qs['Quality Score'].apply(
        lambda x: 'Low (1-6)' if x <= 6 else 'High (7-10)'
    )
    
    summary = df_qs.groupby('QS_Group').agg({
        'Cost': 'sum',
        'Conversions': 'sum'
    })
    
    total_cost = summary['Cost'].sum()
    total_conv = summary['Conversions'].sum()
    
    summary['Cost_Pct'] = (summary['Cost'] / total_cost * 100).round(1)
    summary['Conv_Pct'] = (summary['Conversions'] / total_conv * 100).round(1)
    summary['Efficiency'] = (summary['Conv_Pct'] / summary['Cost_Pct']).round(2)
    
    return summary
```

### Typical QS Distribution (Problematic Account)

| QS | Cost % | Clicks % | Conv % | Issue |
|----|--------|----------|--------|-------|
| 1 | 4.3% | 2.3% | 2.0% | Critical - very inefficient |
| 2 | 0.6% | 0.3% | 0.5% | Critical |
| 3 | 12.1% | 14.8% | 6.8% | High spend, low return |
| 4 | 0.2% | 0.1% | 0.0% | Poor performer |
| 5 | 10.2% | 10.3% | 7.2% | Below average |
| 6 | 3.7% | 2.1% | 2.2% | Needs improvement |
| 7 | 10.9% | 8.9% | 11.7% | OK - baseline |
| 8 | 24.8% | 15.9% | 19.9% | Good performer |
| 9 | 1.0% | 1.1% | 2.1% | Excellent |
| 10 | 23.3% | 25.6% | 37.1% | Best performer |
| -- | 9.0% | 18.8% | 10.6% | Missing QS data |

**Summary**: Low QS (1-6) = 31% cost but only 19% conversions

### QS Improvement Priority

```python
def prioritize_qs_improvements(df, min_cost=100):
    """
    Prioritize keywords for QS improvement based on spend and potential.
    
    Focus on high-spend, low-QS keywords where improvement has biggest impact.
    """
    df_qs = df[
        (df['Quality Score'].notna()) & 
        (df['Quality Score'] != '--') &
        (df['Cost'] >= min_cost)
    ].copy()
    df_qs['Quality Score'] = pd.to_numeric(df_qs['Quality Score'])
    
    # Calculate potential savings
    df_qs['Potential_Savings'] = df_qs.apply(
        lambda r: estimate_savings(r['Cost'], r['Quality Score']), axis=1
    )
    
    # Sort by potential savings
    priority = df_qs[df_qs['Quality Score'] <= 6].sort_values(
        'Potential_Savings', ascending=False
    )
    
    return priority[[
        'Campaign', 'Ad Group', 'Keyword', 'Quality Score',
        'Expected CTR', 'Ad Relevance', 'Landing Page Exp',
        'Cost', 'Conversions', 'Potential_Savings', 'Priority_Action'
    ]]

def estimate_savings(cost, current_qs, target_qs=7):
    """Estimate savings from improving QS to target level."""
    # Approximate CPC multipliers by QS
    multipliers = {
        1: 4.0, 2: 3.5, 3: 3.0, 4: 2.5, 5: 2.0, 6: 1.5,
        7: 1.0, 8: 0.85, 9: 0.7, 10: 0.6
    }
    
    current_mult = multipliers.get(int(current_qs), 1.0)
    target_mult = multipliers.get(target_qs, 1.0)
    
    if current_mult > target_mult:
        savings = cost * (1 - target_mult / current_mult)
        return round(savings, 2)
    return 0
```

## Weighted Quality Score Calculation

QS at campaign/ad group level must be weighted by impressions or cost to be meaningful.

### Formula

```
Weighted QS = Σ(QS_i × Impressions_i) / Σ(Impressions_i)
```

Alternative (cost-weighted):
```
Weighted QS = Σ(QS_i × Cost_i) / Σ(Cost_i)
```

### Python Implementation

```python
import pandas as pd

def calculate_weighted_qs(df, group_by='Campaign'):
    """
    Calculate weighted Quality Score by campaign or ad group.
    
    Args:
        df: DataFrame with columns: Campaign, Ad Group, Keyword, QS, Impressions, Cost
        group_by: 'Campaign' or 'Ad Group'
    
    Returns:
        DataFrame with weighted QS per group
    """
    # Filter out keywords without QS (null or '--')
    df_qs = df[df['Quality Score'].notna() & (df['Quality Score'] != '--')].copy()
    df_qs['Quality Score'] = pd.to_numeric(df_qs['Quality Score'])
    
    # Calculate weighted QS
    df_qs['QS_weighted'] = df_qs['Quality Score'] * df_qs['Impressions']
    
    grouped = df_qs.groupby(group_by).agg({
        'QS_weighted': 'sum',
        'Impressions': 'sum',
        'Cost': 'sum',
        'Keyword': 'count'
    }).reset_index()
    
    grouped['Weighted_QS'] = (grouped['QS_weighted'] / grouped['Impressions']).round(2)
    grouped.rename(columns={'Keyword': 'Keyword_Count'}, inplace=True)
    
    return grouped[['Campaign', 'Weighted_QS', 'Impressions', 'Cost', 'Keyword_Count']]
```

## QS Opportunity Identification

### High-Spend Low-QS Keywords

Find keywords where investment in QS improvement yields best ROI:

```python
def find_qs_opportunities(df, min_cost=100, max_qs=5):
    """
    Find high-spend keywords with low QS (improvement opportunities).
    
    Args:
        df: Keywords DataFrame
        min_cost: Minimum cost threshold
        max_qs: Maximum QS to flag
    
    Returns:
        DataFrame sorted by Cost descending
    """
    df_opp = df[
        (df['Cost'] >= min_cost) & 
        (df['Quality Score'] <= max_qs) &
        (df['Quality Score'].notna())
    ].copy()
    
    return df_opp.sort_values('Cost', ascending=False)[[
        'Campaign', 'Ad Group', 'Keyword', 'Quality Score',
        'Expected CTR', 'Ad Relevance', 'Landing Page Exp',
        'Cost', 'Conversions', 'CPA'
    ]]
```

## QS Components Analysis

Quality Score has 3 components (each rated: Below Average, Average, Above Average):

| Component | Impact | Improvement Action |
|-----------|--------|-------------------|
| Expected CTR | Ad copy quality | Improve headlines, add keywords to copy |
| Ad Relevance | Keyword-ad match | Tighten ad groups, use keyword in ad |
| Landing Page Exp | Page quality | Improve load speed, relevance, mobile |

### Component Priority Matrix

```
If Expected CTR = Below Average → Focus on ad copy first
If Ad Relevance = Below Average → Restructure ad groups
If Landing Page = Below Average → Landing page optimization
```

## Reporting Format

### Campaign-Level Summary Table

| Campaign | Weighted QS | Keywords | Spend | QS < 5 Keywords | Est. Savings |
|----------|-------------|----------|-------|-----------------|--------------|
| Brand    | 8.2         | 45       | $5,000| 3               | $200         |
| Generic  | 5.1         | 120      | $15,000| 45             | $3,000       |

### Keyword-Level Detail

| Keyword | QS | Exp CTR | Ad Rel | LP Exp | Cost | Conv | Issue | Action |
|---------|-----|---------|--------|--------|------|------|-------|--------|
| "ivf treatment" | 4 | Below | Avg | Below | $500 | 5 | LP | Optimize LP |

### Estimated Impact

Low QS increases CPC by approximately:
- QS 1-4: +400% above benchmark
- QS 5-6: +50% above benchmark  
- QS 7: Benchmark
- QS 8-10: -20% to -50% below benchmark

```python
def estimate_qs_savings(df):
    """Estimate potential savings from QS improvements."""
    qs_multiplier = {
        1: 4.0, 2: 3.5, 3: 3.0, 4: 2.5,
        5: 1.5, 6: 1.25, 7: 1.0,
        8: 0.8, 9: 0.7, 10: 0.6
    }
    
    df['Current_Multiplier'] = df['Quality Score'].map(qs_multiplier)
    df['Target_Multiplier'] = 1.0  # QS 7 target
    df['Potential_Savings'] = df['Cost'] * (1 - df['Target_Multiplier'] / df['Current_Multiplier'])
    
    return df[df['Quality Score'] < 7]['Potential_Savings'].sum()
```
