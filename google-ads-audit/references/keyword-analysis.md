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

## Negative Keywords Audit (Full Workflow)

### Identification Methods

**Method 1: Zero-conversion search terms (data-driven)**

```python
def find_negative_candidates(st_df, min_cost=20, min_clicks=3):
    """
    Find search terms that spent budget but never converted.

    Filters by minimum spend and clicks to avoid flagging low-signal terms.
    """
    candidates = st_df[
        (st_df['Conversions'] == 0) &
        (st_df['Cost'] >= min_cost) &
        (st_df['Clicks'] >= min_clicks)
    ].copy()

    candidates['Suggested_Level'] = candidates.apply(assign_negative_level, axis=1)
    candidates['Suggested_Match_Type'] = candidates['Search term'].apply(suggest_match_type)

    return candidates[[
        'Campaign', 'Ad Group', 'Search term', 'Cost', 'Clicks',
        'Suggested_Match_Type', 'Suggested_Level'
    ]].sort_values('Cost', ascending=False)


def assign_negative_level(row):
    """Suggest account / campaign / ad group level for negative."""
    term = row['Search term'].lower()
    # Universal terms → account level
    universal = ['free', 'cheap', 'diy', 'jobs', 'salary', 'career', 'how to make',
                 'what is', 'wikipedia', 'youtube', 'amazon', 'ebay']
    if any(u in term for u in universal):
        return 'Account'
    # High-spend, cross-campaign → campaign level
    if row['Cost'] > 100:
        return 'Campaign'
    # Low-spend, isolated → ad group level
    return 'Ad Group'


def suggest_match_type(search_term):
    """Suggest negative match type based on term length."""
    word_count = len(search_term.split())
    if word_count == 1:
        return 'Broad'   # Single word: block all combinations
    if word_count <= 3:
        return 'Phrase'  # Short phrase: block exact phrase in any query
    return 'Exact'       # Long phrase: block only this exact query
```

**Method 2: Category-based exclusion (e-commerce)**

Common negative keyword categories for e-commerce accounts:

```python
ECOMMERCE_NEGATIVE_CATEGORIES = {
    'free_cheap': [
        'free', 'gratis', 'free shipping', 'cheap', 'cheapest', 'budget',
        'low cost', 'inexpensive', 'discount code', 'coupon', 'promo code',
        'voucher'
    ],
    'diy_homemade': [
        'diy', 'homemade', 'make your own', 'how to make', 'recipe',
        'make at home', 'build your own', 'instructions'
    ],
    'educational': [
        'what is', 'how does', 'definition', 'meaning', 'wikipedia',
        'explained', 'guide', 'tutorial', 'learn', 'course', 'certification'
    ],
    'job_related': [
        'jobs', 'job', 'career', 'careers', 'salary', 'hiring',
        'employment', 'work from home', 'remote job', 'internship',
        'apprenticeship', 'vacancy', 'vacancies'
    ],
    'research_not_buying': [
        'review', 'reviews', 'vs', 'versus', 'comparison', 'compare',
        'best', 'top 10', 'forum', 'reddit', 'side effects'
    ],
    'wrong_product_type': [
        # Populate based on your specific category
        # Example for supplement brand:
        'seed', 'plant', 'pet', 'animal', 'dog', 'cat', 'horse',
        'baby formula', 'baby food'
    ]
}


def flag_category_negatives(st_df, categories=None):
    """
    Flag search terms matching known negative categories.

    Args:
        st_df: Search Terms DataFrame
        categories: Dict of category → keyword list (defaults to ECOMMERCE_NEGATIVE_CATEGORIES)

    Returns:
        DataFrame with category flags
    """
    if categories is None:
        categories = ECOMMERCE_NEGATIVE_CATEGORIES

    st_df = st_df.copy()
    term_lower = st_df['Search term'].str.lower()

    for category, terms in categories.items():
        pattern = '|'.join([re.escape(t) for t in terms])
        st_df[f'Cat_{category}'] = term_lower.str.contains(pattern)

    # Any category match = negative candidate
    cat_cols = [c for c in st_df.columns if c.startswith('Cat_')]
    st_df['Is_Category_Negative'] = st_df[cat_cols].any(axis=1)
    st_df['Matched_Category'] = st_df[cat_cols].apply(
        lambda row: ', '.join([c.replace('Cat_', '') for c in cat_cols if row[c]]),
        axis=1
    )

    return st_df[st_df['Is_Category_Negative']][[
        'Search term', 'Cost', 'Clicks', 'Conversions',
        'Matched_Category', 'Campaign', 'Ad Group'
    ]]
```

### Three-Tier Implementation

```python
def build_negative_upload_list(negative_df):
    """
    Format negative keyword recommendations for Google Ads bulk upload.

    Output CSV columns match Google Ads Editor format:
    Campaign, Ad Group, Keyword, Match Type, Status
    (Leave Campaign/Ad Group blank for account-level shared list)
    """
    rows = []
    for _, row in negative_df.iterrows():
        level = row.get('Suggested_Level', 'Campaign')
        term = row['Search term']
        match_type = row.get('Suggested_Match_Type', 'Exact')

        if level == 'Account':
            rows.append({
                'List Name': 'Account Negatives - Universal',
                'Campaign': '',
                'Ad Group': '',
                'Keyword': term,
                'Match Type': match_type
            })
        elif level == 'Campaign':
            rows.append({
                'List Name': '',
                'Campaign': row['Campaign'],
                'Ad Group': '',
                'Keyword': term,
                'Match Type': match_type
            })
        else:
            rows.append({
                'List Name': '',
                'Campaign': row['Campaign'],
                'Ad Group': row['Ad Group'],
                'Keyword': term,
                'Match Type': match_type
            })

    return pd.DataFrame(rows)
```

### GAQL Query for Existing Negative Lists

```python
NEGATIVE_LISTS_QUERY = """
    SELECT
        shared_set.name,
        shared_set.type,
        shared_set.member_count,
        shared_set.status
    FROM shared_set
    WHERE shared_set.type = 'NEGATIVE_KEYWORDS'
        AND shared_set.status != 'REMOVED'
"""

NEGATIVE_LIST_KEYWORDS_QUERY = """
    SELECT
        shared_set.name,
        shared_criterion.keyword.text,
        shared_criterion.keyword.match_type
    FROM shared_criterion
    WHERE shared_set.type = 'NEGATIVE_KEYWORDS'
"""
```

## New Search Terms for Expansion

Find search terms already converting that you are not directly targeting. These prove demand exists — add them to your targeting strategy to capture more of this proven traffic.

### Filter Criteria

```python
def find_expansion_candidates(st_df, target_cpa=None):
    """
    Find converting search terms not yet targeted as keywords.

    Filters:
    - Conversions > 0
    - CPA at or below target (or below account average if no target set)
    - Clicks >= 3 (enough data to be reliable)
    - Not already added as a keyword (Added/Excluded != 'Added')
    """
    if target_cpa is None:
        target_cpa = st_df[st_df['Conversions'] > 0]['CPA'].mean()

    candidates = st_df[
        (st_df['Conversions'] > 0) &
        (st_df['CPA'] <= target_cpa) &
        (st_df['Clicks'] >= 3) &
        (st_df.get('Added/Excluded', '') != 'Added')
    ].copy()

    # Sort by conversion volume descending
    return candidates[[
        'Campaign', 'Ad Group', 'Search term', 'Cost',
        'Conversions', 'CPA', 'Clicks'
    ]].sort_values('Conversions', ascending=False)
```

### 4-Action Framework per Converting Term

For each qualifying search term, apply as many of these actions as relevant:

**Action 1: Add as Keyword**
```python
def recommend_keyword_addition(search_term, existing_keywords, avg_cpc):
    """
    Recommend keyword addition strategy based on term characteristics.

    Returns suggested match type and bid.
    """
    term_lower = search_term.lower()
    word_count = len(term_lower.split())

    # Check if already targeted
    for kw in existing_keywords:
        kw_clean = kw.lower().replace('[', '').replace(']', '').replace('"', '')
        if kw_clean == term_lower:
            return {'action': 'Already targeted', 'match_type': None, 'bid_adj': None}

    # Suggest match type based on specificity
    if word_count >= 4:
        match_type = 'Exact'   # Proven high-intent long tail
    else:
        match_type = 'Phrase'  # Discovery term, capture variants too

    # Set bid 20% above average (proven converter)
    suggested_bid = round(avg_cpc * 1.2, 2)

    return {
        'action': f'Add as {match_type} match keyword',
        'match_type': match_type,
        'suggested_bid': suggested_bid
    }
```

**Action 2: Optimize Product Feed Title**
- Place the converting search term keywords in the **first 30-35 characters** of the product title (most visible in Shopping results)
- Product titles are cut after ~70 characters in search results — prioritize early placement
- Example: Search term "grass fed protein powder women" → Title: `Grass Fed Protein Powder Women | Organic Collagen...`

**Action 3: Duplicate Products with Keyword Angles**
Use feed management tools (e.g., DataFeedWatch, Channable) to create multiple product variants targeting different keyword angles:

```
Original: "Creatine Monohydrate Supplement"
→ Duplicate 1 (Item ID: 401-weightloss): "Creatine Monohydrate for Weight Loss"
→ Duplicate 2 (Item ID: 401-muscle): "Creatine Monohydrate for Muscle Growth"
→ Duplicate 3 (Item ID: 401-women): "Creatine Monohydrate for Women"
```

Rules:
- Each duplicate needs a **unique Item ID** (append angle suffix)
- Update title, and optionally image + landing page per angle
- Don't duplicate for angles with no proven search demand

**Action 4: Build Aligned Landing Pages**
Create a dedicated page matching the keyword theme and user intent:
- **Search campaigns**: Educational intent → informational/comparison page
- **Shopping campaigns**: Product intent → product-focused page with matching title and imagery
- Example: Search term "protein powder for mature women" → dedicated landing page for that audience segment

### Output

```python
def build_expansion_report(candidates, existing_keywords_df, avg_cpc):
    """Build expansion action report."""
    results = []

    for _, row in candidates.iterrows():
        existing = existing_keywords_df[
            existing_keywords_df['Campaign'] == row['Campaign']
        ]['Keyword'].tolist()

        kw_rec = recommend_keyword_addition(row['Search term'], existing, avg_cpc)

        results.append({
            'Search Term': row['Search term'],
            'Campaign': row['Campaign'],
            'Ad Group': row['Ad Group'],
            'Conversions': row['Conversions'],
            'CPA': row['CPA'],
            'Action 1 - Keyword': kw_rec['action'],
            'Suggested Match Type': kw_rec.get('match_type', ''),
            'Suggested Bid': kw_rec.get('suggested_bid', ''),
            'Action 2 - Feed Title': 'Add to product title (first 30-35 chars)',
            'Action 3 - Product Duplicate': 'Create angle variant if 3+ keyword angles exist',
            'Action 4 - Landing Page': 'Build dedicated page if search volume justifies it'
        })

    return pd.DataFrame(results)
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
