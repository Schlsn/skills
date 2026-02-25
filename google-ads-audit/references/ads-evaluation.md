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

## CTR Performance Benchmarks

Low CTR means ad copy isn't compelling enough or doesn't match search intent. Check CTR against campaign type benchmarks.

### Benchmarks

| Campaign Type | Good CTR | Warning | Action Needed |
|--------------|----------|---------|---------------|
| Brand Search | ≥5% | 3-5% | <3% |
| Non-Brand Search | ≥2% | 1-2% | <1% |
| Shopping | ≥2-3% | 1-2% | <1% |

### Detection

```python
def flag_low_ctr_ads(ads_df, campaigns_df, brand_campaign_pattern='brand'):
    """
    Flag ads below CTR benchmarks for their campaign type.

    Args:
        ads_df: Ads DataFrame with CTR and campaign name
        campaigns_df: Campaigns DataFrame (for campaign type)
        brand_campaign_pattern: Substring to identify brand campaigns

    Returns:
        DataFrame with below-benchmark ads and recommended actions
    """
    # Classify campaign type
    ads_df = ads_df.copy()
    ads_df['Campaign_Type'] = ads_df['Campaign'].apply(
        lambda c: 'Brand' if brand_campaign_pattern.lower() in c.lower() else 'Non-Brand'
    )

    # Apply benchmarks
    benchmarks = {'Brand': 5.0, 'Non-Brand': 2.0}
    ads_df['CTR_Benchmark'] = ads_df['Campaign_Type'].map(benchmarks)
    ads_df['Below_Benchmark'] = ads_df['CTR'] < ads_df['CTR_Benchmark']

    below = ads_df[ads_df['Below_Benchmark']].copy()
    below['Gap_Pct'] = ((below['CTR_Benchmark'] - below['CTR']) / below['CTR_Benchmark'] * 100).round(1)

    return below[[
        'Campaign', 'Ad Group', 'Campaign_Type', 'CTR',
        'CTR_Benchmark', 'Gap_Pct', 'Ad strength', 'Cost'
    ]].sort_values('Cost', ascending=False)
```

### Fix for Below-Benchmark Ads

1. Identify ads below CTR threshold
2. Create 2-3 new ad variations testing:
   - Different headlines (emphasize different benefits)
   - Stronger calls-to-action (Buy, Get, Start, Book)
   - Promotional messaging (% off, free shipping, limited time)
   - Trust signals (years in business, reviews, guarantees)
3. Let Google test combinations for **minimum 2 weeks**
4. Pause consistently poor performers after sufficient data

### Ad Copy Elements to Test

| Position | What to Test |
|----------|-------------|
| Headline 1 | Product name + key benefit |
| Headline 2 | Unique selling proposition |
| Headline 3 | Social proof or current promotion |
| Description 1 | Expand on benefits, address intent |
| Description 2 | Address objections + clear CTA |

## Brand Ad Copy Quality

Brand campaigns represent your brand at the highest-intent moment. Copy must be professional, consistent, and benefit-focused.

### Quality Checklist

```python
def check_brand_ad_quality(ads_df, brand_campaign_pattern='brand'):
    """
    Check brand ads against quality standards.

    Returns list of issues per ad.
    """
    brand_ads = ads_df[
        ads_df['Campaign'].str.lower().str.contains(brand_campaign_pattern)
    ].copy()

    issues_list = []

    for _, row in brand_ads.iterrows():
        issues = []
        headlines = [h for h in [row.get(f'Headline {i}', '') for i in range(1, 16)] if h]
        descs = [d for d in [row.get(f'Description {i}', '') for i in range(1, 5)] if d]
        all_text = ' '.join(headlines + descs)

        # Formatting checks
        for h in headlines:
            if h and h != h.title() and not any(word[0].isupper() for word in h.split()):
                issues.append('Headline not Title Case')
                break

        # USP check (look for key benefit terms)
        usp_indicators = [
            'free shipping', 'money back', 'guarantee', 'fast delivery',
            'same day', 'award', 'certified', 'official', 'since', 'trusted',
            '%', 'off', 'save'
        ]
        has_usp = any(u in all_text.lower() for u in usp_indicators)
        if not has_usp:
            issues.append('No clear USP or benefit in ad copy')

        # CTA check
        ctas = ['shop', 'buy', 'order', 'get', 'start', 'try', 'discover',
                'explore', 'learn', 'book', 'contact']
        has_cta = any(c in all_text.lower() for c in ctas)
        if not has_cta:
            issues.append('No clear CTA')

        # Headline count
        if len(headlines) < 10:
            issues.append(f'Only {len(headlines)} headlines (target: 15)')

        # Description count
        if len(descs) < 3:
            issues.append(f'Only {len(descs)} descriptions (target: 4)')

        issues_list.append({
            'Campaign': row['Campaign'],
            'Ad Group': row['Ad Group'],
            'Ad Strength': row.get('Ad strength', ''),
            'Issues': '; '.join(issues) if issues else 'OK',
            'Issue_Count': len(issues)
        })

    return pd.DataFrame(issues_list).sort_values('Issue_Count', ascending=False)
```

### Formatting Standards

| Element | Standard |
|---------|----------|
| Capitalization | Title Case for headlines |
| Punctuation | Consistent — no double punctuation, no ALL CAPS |
| Brand name | Consistent spelling in every ad |
| Promotional claims | Accurate, time-bound if applicable |

### Required Content Elements

- **USPs**: What makes you different (free shipping, guarantee, awards)
- **Key features**: Delivery speed, return policy, years in business
- **Trust signals**: Customer count, reviews, certifications
- **Current promotions**: Keep in sync with promo calendar

### Recommended Headline Structure

```
Headline 1: [Brand Name] + [Product Category]
Headline 2: [Main USP — e.g., Free Shipping on All Orders]
Headline 3: [Offer or Trust Signal — e.g., 30-Day Money Back Guarantee]
```

### Promotional Alignment

Brand ad copy must stay synchronized with the promotional calendar:
1. Schedule custom ad copy variations for each major promotion (Black Friday, seasonal sales, product launches)
2. Set start/end dates to auto-rotate promotional messaging
3. Prepare promotional ads **in advance** — do not scramble during campaign launch
4. Remove or pause expired promotional messaging promptly
5. Keep a "always on" non-promotional version as fallback

## Output Format

### Ad Summary Table

| Campaign | Ad Group | Type | Strength | CTR | CTR Benchmark | Headlines | Descriptions | Pins | Issues | Score |
|----------|----------|------|----------|-----|---------------|-----------|--------------|------|--------|-------|
| Brand | Core | RSA | Good | 6.2% | 5% | 12 | 4 | 0 | None | 8 |
| Generic | Supplements | RSA | Average | 1.1% | 2% | 6 | 2 | 2 | Low CTR, Low assets | 5 |

### Recommendations by Priority

1. **Critical**: Ad groups without RSA
2. **High**: Ad Strength = Poor; CTR below benchmark
3. **Medium**: < 10 headlines or < 3 descriptions; brand ads missing USPs
4. **Low**: Excessive pinning, minor copy improvements, promotional alignment
