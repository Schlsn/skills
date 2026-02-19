# Keyword & Search Term Analysis

## Keyword Performance Segmentation

### Pause Candidates

Keywords to consider pausing based on performance:

```python
def find_pause_candidates(df, lookback_days=30, min_cost=50):
    """
    Identify keywords that should be paused.
    
    Criteria:
    - High cost with zero conversions
    - CPA > 3x account average
    - No impressions in lookback period
    """
    avg_cpa = df[df['Conversions'] > 0]['CPA'].mean()
    
    # Zero conversion high spenders
    zero_conv = df[(df['Cost'] >= min_cost) & (df['Conversions'] == 0)]
    
    # Expensive converters
    expensive = df[
        (df['Conversions'] > 0) & 
        (df['CPA'] > avg_cpa * 3)
    ]
    
    # Combine and dedupe
    pause_candidates = pd.concat([zero_conv, expensive]).drop_duplicates()
    
    return pause_candidates[[
        'Campaign', 'Ad Group', 'Keyword', 'Match Type',
        'Cost', 'Clicks', 'Conversions', 'CPA', 'Recommendation'
    ]]
```

### Scale Candidates

Keywords with room to grow:

```python
def find_scale_candidates(df, max_cpa_ratio=0.8, max_impr_share=0.5):
    """
    Find keywords that can be scaled.
    
    Criteria:
    - CPA below account average
    - Impression share below threshold
    - Has conversions
    """
    avg_cpa = df[df['Conversions'] > 0]['CPA'].mean()
    
    scale = df[
        (df['Conversions'] > 0) &
        (df['CPA'] < avg_cpa * max_cpa_ratio) &
        (df['Impr. (Top) %'] < max_impr_share)
    ]
    
    # Calculate scaling potential
    scale['Scale_Potential'] = (1 - scale['Impr. (Top) %']) * scale['Conversions']
    
    return scale.sort_values('Scale_Potential', ascending=False)[[
        'Campaign', 'Ad Group', 'Keyword', 'CPA', 
        'Impr. (Top) %', 'Scale_Potential', 'Recommendation'
    ]]
```

## Zero Impression Keywords

```python
def find_zero_impression_keywords(df):
    """Find keywords with no impressions."""
    zero_imp = df[df['Impressions'] == 0]
    
    # Categorize reasons
    zero_imp['Likely_Reason'] = zero_imp.apply(categorize_zero_imp, axis=1)
    
    return zero_imp[[
        'Campaign', 'Ad Group', 'Keyword', 'Match Type',
        'Status', 'Likely_Reason', 'Recommendation'
    ]]

def categorize_zero_imp(row):
    if row['Status'] != 'Enabled':
        return 'Paused/Removed'
    if row.get('Quality Score', 0) < 3:
        return 'Low QS - rarely shown'
    return 'Low search volume or bid'
```

## Keyword Overlap Detection

Find same keywords in multiple ad groups (cannibalization):

```python
def find_keyword_overlaps(df):
    """Detect keyword overlap across ad groups."""
    # Normalize keywords for comparison
    df['Keyword_Normalized'] = df['Keyword'].str.lower().str.strip()
    
    # Find duplicates
    overlaps = df.groupby('Keyword_Normalized').filter(
        lambda x: x['Ad Group'].nunique() > 1
    )
    
    # Format output
    overlap_summary = overlaps.groupby('Keyword_Normalized').agg({
        'Ad Group': lambda x: ' | '.join(x.unique()),
        'Campaign': lambda x: ' | '.join(x.unique()),
        'Cost': 'sum',
        'Conversions': 'sum'
    }).reset_index()
    
    return overlap_summary
```

## Search Term Analysis

### Relevance Scoring

```python
from difflib import SequenceMatcher

def score_search_term_relevance(search_term, keywords):
    """
    Score how relevant a search term is to target keywords.
    
    Returns: 0-1 score (1 = exact match)
    """
    search_term = search_term.lower()
    
    scores = []
    for kw in keywords:
        kw = kw.lower().replace('+', '').replace('"', '').replace('[', '').replace(']', '')
        
        # Check if keyword in search term
        if kw in search_term:
            scores.append(1.0)
        else:
            # Fuzzy match
            ratio = SequenceMatcher(None, search_term, kw).ratio()
            scores.append(ratio)
    
    return max(scores) if scores else 0

def analyze_search_terms(st_df, kw_df):
    """Analyze search term relevance to keywords."""
    # Get keywords per ad group
    kw_by_adgroup = kw_df.groupby('Ad Group')['Keyword'].apply(list).to_dict()
    
    st_df['Relevance_Score'] = st_df.apply(
        lambda row: score_search_term_relevance(
            row['Search term'],
            kw_by_adgroup.get(row['Ad Group'], [])
        ), axis=1
    )
    
    # Flag low relevance
    st_df['Relevance_Flag'] = st_df['Relevance_Score'].apply(
        lambda x: 'Low' if x < 0.5 else ('Medium' if x < 0.8 else 'High')
    )
    
    return st_df
```

### High-Spend Search Terms

```python
def top_search_terms(df, n=50):
    """Get top spending search terms with metrics."""
    return df.nlargest(n, 'Cost')[[
        'Campaign', 'Ad Group', 'Search term',
        'Cost', 'Conversions', 'CPA', 'CTR',
        'Relevance_Score', 'Added/Excluded'
    ]]
```

### Anomaly Detection

```python
def detect_search_term_anomalies(df_current, df_previous):
    """Find new high-volume search terms."""
    # Merge periods
    merged = df_current.merge(
        df_previous[['Search term', 'Cost', 'Impressions']],
        on='Search term',
        how='left',
        suffixes=('', '_prev')
    )
    
    # Flag new terms with significant spend
    merged['Is_New'] = merged['Cost_prev'].isna()
    merged['Spend_Spike'] = (
        (merged['Cost'] > merged['Cost_prev'] * 2) & 
        (merged['Cost'] > 50)
    )
    
    anomalies = merged[merged['Is_New'] | merged['Spend_Spike']]
    
    return anomalies[[
        'Search term', 'Cost', 'Cost_prev', 
        'Conversions', 'Is_New', 'Spend_Spike'
    ]]
```

## Negative Keyword Recommendations

```python
def suggest_negatives(st_df, relevance_threshold=0.4, min_cost=20):
    """Suggest search terms to add as negatives."""
    negatives = st_df[
        (st_df['Relevance_Score'] < relevance_threshold) &
        (st_df['Cost'] >= min_cost) &
        (st_df['Conversions'] == 0)
    ]
    
    return negatives[[
        'Search term', 'Cost', 'Clicks', 
        'Relevance_Score', 'Suggested_Match_Type'
    ]]
```

## Output Tables

### Keyword Summary

| Status | Count | Cost | Conv | CPA | Action |
|--------|-------|------|------|-----|--------|
| Pause | 45 | $2,500 | 0 | - | Review & pause |
| Scale | 23 | $3,000 | 85 | $35 | Increase bids |
| Zero Impr | 120 | $0 | 0 | - | Evaluate relevance |
| Overlap | 15 | $800 | 12 | $67 | Consolidate |

### Search Term Summary

| Category | Count | Cost | Conv | Action |
|----------|-------|------|------|--------|
| High relevance | 250 | $8,000 | 120 | Monitor |
| Low relevance | 85 | $1,500 | 3 | Add negatives |
| New high-spend | 12 | $600 | 5 | Evaluate |
