# Ad Evaluation Guide

## Ad Type Check

### RSA Count per Ad Group

Best practice: 1-2 RSA per ad group. More RSAs dilute data and slow optimization.

```python
def check_rsa_count_per_adgroup(df):
    """
    Check RSA count per ad group.
    
    Issue: Many ad groups have 2+ RSAs, diluting performance data.
    Target: 1-2 RSAs per ad group maximum.
    """
    rsa_df = df[df['Ad type'] == 'Responsive search ad']
    
    rsa_count = rsa_df.groupby(['Campaign', 'Ad Group']).agg({
        'Ad': 'count',
        'Cost': 'sum',
        'Conversions': 'sum'
    }).reset_index()
    
    rsa_count.columns = ['Campaign', 'Ad Group', 'RSA_Count', 'Cost', 'Conversions']
    
    # Flag ad groups with too many RSAs
    rsa_count['Issue'] = rsa_count['RSA_Count'].apply(
        lambda x: 'Too many RSAs' if x > 2 else ('OK' if x > 0 else 'No RSA')
    )
    
    return rsa_count

def rsa_count_summary(df):
    """Summary of RSA count distribution."""
    rsa_count = df.groupby(['Campaign', 'Ad Group'])['Ad'].count()
    
    summary = {
        '1 RSA': (rsa_count == 1).sum(),
        '2 RSAs': (rsa_count == 2).sum(),
        '3+ RSAs': (rsa_count >= 3).sum()
    }
    
    return pd.DataFrame([summary])
```

### Ad Strength Distribution Analysis

Analyze spend distribution by Ad Strength rating.

```python
def ad_strength_spend_analysis(df):
    """
    Analyze cost distribution by Ad Strength.
    
    Common finding: 50%+ spend goes to Poor/Average rated RSAs.
    Target: Majority spend on Good/Excellent RSAs.
    """
    # Filter to RSA only
    rsa_df = df[df['Ad type'] == 'Responsive search ad'].copy()
    
    summary = rsa_df.groupby('Ad strength').agg({
        'Cost': 'sum',
        'Conversions': 'sum',
        'Clicks': 'sum'
    }).reset_index()
    
    total_cost = summary['Cost'].sum()
    total_conv = summary['Conversions'].sum()
    
    summary['Cost_Pct'] = (summary['Cost'] / total_cost * 100).round(2)
    summary['Conv_Pct'] = (summary['Conversions'] / total_conv * 100).round(2)
    summary['CPA'] = (summary['Cost'] / summary['Conversions'].replace(0, float('nan'))).round(2)
    
    # Order by strength
    strength_order = ['Excellent', 'Good', 'Average', 'Poor', 'Pending', '--']
    summary['Ad strength'] = pd.Categorical(summary['Ad strength'], categories=strength_order, ordered=True)
    summary = summary.sort_values('Ad strength')
    
    return summary

def identify_poor_strength_high_spend(df, threshold_pct=20):
    """
    Flag RSAs with Poor strength but high spend.
    
    These are priority optimization targets.
    """
    rsa_df = df[df['Ad type'] == 'Responsive search ad'].copy()
    total_cost = rsa_df['Cost'].sum()
    
    poor_rsa = rsa_df[rsa_df['Ad strength'].isin(['Poor', 'Average'])]
    poor_rsa['Cost_Pct'] = poor_rsa['Cost'] / total_cost * 100
    
    # High spend poor performers
    priority = poor_rsa[poor_rsa['Cost_Pct'] >= 1].sort_values('Cost', ascending=False)
    
    return priority[[
        'Campaign', 'Ad Group', 'Ad strength', 
        'Cost', 'Cost_Pct', 'Conversions',
        'Headline_Count', 'Description_Count'
    ]]
```

### Typical Ad Strength Distribution (Problematic)

| Rating | Cost % | Conv % | Issue |
|--------|--------|--------|-------|
| Excellent | 2% | 5% | Underutilized |
| Good | 3% | 8% | Underutilized |
| Average | 43% | 40% | Needs improvement |
| Poor | 52% | 47% | Critical - priority fix |

**Target Distribution:**

| Rating | Cost % Target |
|--------|---------------|
| Excellent | 30%+ |
| Good | 40%+ |
| Average | 20% max |
| Poor | 10% max |

### RSA Optimization Recommendations

```python
def generate_rsa_recommendations(df):
    """Generate specific RSA improvement recommendations."""
    recommendations = []
    
    rsa_df = df[df['Ad type'] == 'Responsive search ad'].copy()
    
    for _, row in rsa_df.iterrows():
        issues = []
        actions = []
        
        # Check Ad Strength
        if row['Ad strength'] in ['Poor', 'Average']:
            issues.append(f"Ad Strength: {row['Ad strength']}")
            
            # Check specific issues
            if row.get('Headline_Count', 0) < 10:
                actions.append(f"Add {10 - row.get('Headline_Count', 0)} more headlines")
            
            if row.get('Description_Count', 0) < 3:
                actions.append(f"Add {3 - row.get('Description_Count', 0)} more descriptions")
            
            actions.append("Include target keywords in headlines")
            actions.append("Add clear CTAs")
        
        if issues:
            recommendations.append({
                'Campaign': row['Campaign'],
                'Ad Group': row['Ad Group'],
                'Current_Strength': row['Ad strength'],
                'Cost': row['Cost'],
                'Issues': '; '.join(issues),
                'Actions': '; '.join(actions),
                'Priority': 'High' if row['Ad strength'] == 'Poor' else 'Medium'
            })
    
    return pd.DataFrame(recommendations)
```

### RSA Adoption

Best practice: All ad groups should have RSA (Responsive Search Ads) only.

```python
def check_ad_types(df):
    """Check ad type distribution by ad group."""
    summary = df.groupby(['Campaign', 'Ad Group', 'Ad type']).size().unstack(fill_value=0)
    
    # Flag ad groups without RSA
    if 'Responsive search ad' in summary.columns:
        summary['Has_RSA'] = summary['Responsive search ad'] > 0
    else:
        summary['Has_RSA'] = False
    
    # Flag legacy ETAs
    eta_columns = [c for c in summary.columns if 'Expanded text ad' in c]
    summary['Has_Legacy_ETA'] = summary[eta_columns].sum(axis=1) > 0 if eta_columns else False
    
    return summary
```

### Ad Strength Distribution

| Rating | Interpretation | Action |
|--------|---------------|--------|
| Excellent | Optimal | Maintain |
| Good | Acceptable | Minor improvements possible |
| Average | Needs work | Add more assets |
| Poor | Critical | Immediate attention |

```python
def ad_strength_summary(df):
    """Summarize Ad Strength across account."""
    strength_order = ['Excellent', 'Good', 'Average', 'Poor', '--']
    
    summary = df['Ad strength'].value_counts()
    summary = summary.reindex(strength_order, fill_value=0)
    
    # Calculate percentages
    total = summary.sum()
    summary_pct = (summary / total * 100).round(1)
    
    return pd.DataFrame({
        'Count': summary,
        'Percentage': summary_pct
    })
```

## RSA Asset Analysis

### Headline Requirements

| Metric | Target | Minimum |
|--------|--------|---------|
| Headlines | 15 | 3 |
| Headline length | Varied | - |
| Keyword inclusion | Yes | - |

### Description Requirements

| Metric | Target | Minimum |
|--------|--------|---------|
| Descriptions | 4 | 2 |
| Description length | Varied | - |
| CTA inclusion | Yes | - |

```python
def analyze_rsa_assets(df):
    """Analyze RSA headline and description counts."""
    rsa_df = df[df['Ad type'] == 'Responsive search ad'].copy()
    
    # Count headlines (Headlines are in columns like 'Headline 1', 'Headline 2', etc.)
    headline_cols = [c for c in rsa_df.columns if c.startswith('Headline')]
    desc_cols = [c for c in rsa_df.columns if c.startswith('Description')]
    
    rsa_df['Headline_Count'] = rsa_df[headline_cols].notna().sum(axis=1)
    rsa_df['Description_Count'] = rsa_df[desc_cols].notna().sum(axis=1)
    
    # Flag issues
    rsa_df['Headlines_Issue'] = rsa_df['Headline_Count'] < 10
    rsa_df['Descriptions_Issue'] = rsa_df['Description_Count'] < 3
    
    return rsa_df[[
        'Campaign', 'Ad Group', 'Ad strength',
        'Headline_Count', 'Description_Count',
        'Headlines_Issue', 'Descriptions_Issue'
    ]]
```

## Pinning Analysis

Excessive pinning reduces RSA effectiveness:

```python
def check_pinning(df):
    """Check for excessive pinning in RSAs."""
    # Look for position indicators in headlines/descriptions
    # Format: "Headline text {position:1}"
    
    rsa_df = df[df['Ad type'] == 'Responsive search ad'].copy()
    
    # Count pinned assets
    headline_cols = [c for c in rsa_df.columns if c.startswith('Headline')]
    
    def count_pins(row):
        pins = 0
        for col in headline_cols:
            val = str(row.get(col, ''))
            if '{position:' in val.lower() or '(pinned' in val.lower():
                pins += 1
        return pins
    
    rsa_df['Pin_Count'] = rsa_df.apply(count_pins, axis=1)
    rsa_df['Excessive_Pinning'] = rsa_df['Pin_Count'] > 3
    
    return rsa_df
```

## LLM Relevance Check

Use LLM to evaluate ad-keyword alignment:

### Prompt Template

```
Evaluate this Google Ads RSA for relevance to the target keywords.

Ad Group Keywords: {keywords}

Headlines:
{headlines}

Descriptions:
{descriptions}

Landing Page URL: {url}

Evaluate on a scale of 1-10:
1. Keyword Inclusion (are keywords/variants in headlines?): 
2. Intent Match (do descriptions address user intent?): 
3. CTA Clarity (is call-to-action clear?): 
4. Value Proposition (is benefit clear?): 
5. URL Relevance (does URL match keywords?): 

Overall Score: 
Key Issues:
Recommendations:
```

### Scoring Interpretation

| Score | Meaning | Action |
|-------|---------|--------|
| 8-10 | Excellent | Maintain |
| 6-7 | Good | Minor tweaks |
| 4-5 | Needs work | Rewrite copy |
| 1-3 | Poor | Complete overhaul |

## Ad Copy Best Practices Checklist

```python
def check_ad_best_practices(headlines, descriptions, keywords):
    """Check ad copy against best practices."""
    issues = []
    
    # Combine all text
    all_text = ' '.join(headlines + descriptions).lower()
    
    # Check keyword inclusion
    keyword_found = any(kw.lower() in all_text for kw in keywords)
    if not keyword_found:
        issues.append("No keywords in ad copy")
    
    # Check for CTA
    ctas = ['call', 'click', 'buy', 'get', 'start', 'learn', 'discover', 
            'try', 'sign up', 'book', 'schedule', 'contact']
    has_cta = any(cta in all_text for cta in ctas)
    if not has_cta:
        issues.append("No clear CTA")
    
    # Check headline variety
    headline_lengths = [len(h) for h in headlines if h]
    if headline_lengths and max(headline_lengths) - min(headline_lengths) < 10:
        issues.append("Headlines too similar in length")
    
    # Check for numbers/stats
    has_numbers = any(char.isdigit() for char in all_text)
    if not has_numbers:
        issues.append("Consider adding numbers/stats")
    
    return issues
```

## Output Format

### Ad Summary Table

| Campaign | Ad Group | Type | Strength | Headlines | Descriptions | Pins | Issues | Score |
|----------|----------|------|----------|-----------|--------------|------|--------|-------|
| Brand | Core | RSA | Good | 12 | 4 | 0 | None | 8 |
| Generic | IVF | RSA | Average | 6 | 2 | 2 | Low assets, pinning | 5 |

### Recommendations by Priority

1. **Critical**: Ad groups without RSA
2. **High**: Ad Strength = Poor
3. **Medium**: < 10 headlines or < 3 descriptions
4. **Low**: Excessive pinning, minor copy improvements
