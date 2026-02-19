# Google Ads API Data Extraction

## Overview

For automated and comprehensive audits, use Google Ads API to extract data directly instead of manual CSV exports.

## Authentication Setup

```python
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

def get_google_ads_client(credentials_path='google-ads.yaml'):
    """
    Initialize Google Ads API client.
    
    Requires google-ads.yaml with:
    - developer_token
    - client_id
    - client_secret
    - refresh_token
    - login_customer_id (MCC if applicable)
    """
    return GoogleAdsClient.load_from_storage(credentials_path)
```

### Credentials File (google-ads.yaml)

```yaml
developer_token: YOUR_DEVELOPER_TOKEN
client_id: YOUR_CLIENT_ID
client_secret: YOUR_CLIENT_SECRET
refresh_token: YOUR_REFRESH_TOKEN
login_customer_id: YOUR_MCC_ID  # Optional, for MCC access
use_proto_plus: True
```

## GAQL Queries

### Campaign Performance

```python
CAMPAIGN_QUERY = """
    SELECT
        campaign.id,
        campaign.name,
        campaign.status,
        campaign.advertising_channel_type,
        campaign.bidding_strategy_type,
        metrics.cost_micros,
        metrics.conversions,
        metrics.conversions_value,
        metrics.clicks,
        metrics.impressions,
        metrics.search_impression_share,
        metrics.search_top_impression_share,
        metrics.ctr,
        metrics.average_cpc
    FROM campaign
    WHERE segments.date DURING LAST_30_DAYS
        AND campaign.status != 'REMOVED'
"""
```

### Ad Group Performance

```python
AD_GROUP_QUERY = """
    SELECT
        campaign.name,
        ad_group.id,
        ad_group.name,
        ad_group.status,
        metrics.cost_micros,
        metrics.conversions,
        metrics.clicks,
        metrics.impressions,
        metrics.search_impression_share,
        metrics.ctr,
        metrics.average_cpc
    FROM ad_group
    WHERE segments.date DURING LAST_30_DAYS
        AND ad_group.status != 'REMOVED'
"""
```

### Keywords with Quality Score

```python
KEYWORD_QUERY = """
    SELECT
        campaign.name,
        ad_group.name,
        ad_group_criterion.keyword.text,
        ad_group_criterion.keyword.match_type,
        ad_group_criterion.status,
        ad_group_criterion.quality_info.quality_score,
        ad_group_criterion.quality_info.creative_quality_score,
        ad_group_criterion.quality_info.post_click_quality_score,
        ad_group_criterion.quality_info.search_predicted_ctr,
        metrics.cost_micros,
        metrics.conversions,
        metrics.clicks,
        metrics.impressions,
        metrics.search_impression_share,
        metrics.ctr,
        metrics.average_cpc
    FROM keyword_view
    WHERE segments.date DURING LAST_30_DAYS
        AND ad_group_criterion.status != 'REMOVED'
"""
```

### Search Terms Report

```python
SEARCH_TERM_QUERY = """
    SELECT
        campaign.name,
        ad_group.name,
        search_term_view.search_term,
        search_term_view.status,
        segments.keyword.info.match_type,
        metrics.cost_micros,
        metrics.conversions,
        metrics.clicks,
        metrics.impressions,
        metrics.ctr
    FROM search_term_view
    WHERE segments.date DURING LAST_30_DAYS
"""
```

### Ads with Ad Strength

```python
AD_QUERY = """
    SELECT
        campaign.name,
        ad_group.name,
        ad_group_ad.ad.id,
        ad_group_ad.ad.type,
        ad_group_ad.ad.responsive_search_ad.headlines,
        ad_group_ad.ad.responsive_search_ad.descriptions,
        ad_group_ad.ad.final_urls,
        ad_group_ad.ad_strength,
        ad_group_ad.status,
        metrics.cost_micros,
        metrics.conversions,
        metrics.clicks,
        metrics.impressions,
        metrics.ctr
    FROM ad_group_ad
    WHERE segments.date DURING LAST_30_DAYS
        AND ad_group_ad.status != 'REMOVED'
"""
```

### Extensions (Assets)

```python
EXTENSION_QUERY = """
    SELECT
        campaign.name,
        asset.type,
        asset.name,
        campaign_asset.status,
        metrics.clicks,
        metrics.impressions
    FROM campaign_asset
    WHERE segments.date DURING LAST_30_DAYS
"""
```

### Display Placements

```python
PLACEMENT_QUERY = """
    SELECT
        campaign.name,
        group_placement_view.placement,
        group_placement_view.placement_type,
        metrics.cost_micros,
        metrics.conversions,
        metrics.clicks,
        metrics.impressions,
        metrics.ctr
    FROM group_placement_view
    WHERE segments.date DURING LAST_30_DAYS
        AND campaign.advertising_channel_type = 'DISPLAY'
"""
```

## Data Extraction Functions

```python
import pandas as pd

def run_query(client, customer_id, query):
    """
    Execute GAQL query and return results as DataFrame.
    
    Args:
        client: GoogleAdsClient instance
        customer_id: Google Ads customer ID (without dashes)
        query: GAQL query string
    
    Returns:
        DataFrame with query results
    """
    ga_service = client.get_service("GoogleAdsService")
    
    rows = []
    try:
        response = ga_service.search_stream(
            customer_id=customer_id,
            query=query
        )
        
        for batch in response:
            for row in batch.results:
                rows.append(row_to_dict(row))
    
    except GoogleAdsException as ex:
        print(f"Request failed: {ex.failure.errors[0].message}")
        raise
    
    return pd.DataFrame(rows)

def row_to_dict(row):
    """Convert API row to flat dictionary."""
    result = {}
    
    # Campaign fields
    if hasattr(row, 'campaign'):
        result['campaign_id'] = row.campaign.id
        result['campaign_name'] = row.campaign.name
        result['campaign_status'] = row.campaign.status.name
        result['campaign_type'] = row.campaign.advertising_channel_type.name
    
    # Ad group fields
    if hasattr(row, 'ad_group'):
        result['ad_group_id'] = row.ad_group.id
        result['ad_group_name'] = row.ad_group.name
        result['ad_group_status'] = row.ad_group.status.name
    
    # Keyword fields
    if hasattr(row, 'ad_group_criterion'):
        criterion = row.ad_group_criterion
        if hasattr(criterion, 'keyword'):
            result['keyword'] = criterion.keyword.text
            result['match_type'] = criterion.keyword.match_type.name
        if hasattr(criterion, 'quality_info'):
            qi = criterion.quality_info
            result['quality_score'] = qi.quality_score if qi.quality_score else None
            result['expected_ctr'] = qi.search_predicted_ctr.name if qi.search_predicted_ctr else None
            result['ad_relevance'] = qi.creative_quality_score.name if qi.creative_quality_score else None
            result['landing_page_exp'] = qi.post_click_quality_score.name if qi.post_click_quality_score else None
    
    # Search term fields
    if hasattr(row, 'search_term_view'):
        result['search_term'] = row.search_term_view.search_term
    
    # Ad fields
    if hasattr(row, 'ad_group_ad'):
        ad = row.ad_group_ad.ad
        result['ad_id'] = ad.id
        result['ad_type'] = ad.type_.name
        result['ad_strength'] = row.ad_group_ad.ad_strength.name
        if hasattr(ad, 'responsive_search_ad'):
            rsa = ad.responsive_search_ad
            result['headlines'] = [h.text for h in rsa.headlines]
            result['descriptions'] = [d.text for d in rsa.descriptions]
        if ad.final_urls:
            result['final_url'] = ad.final_urls[0]
    
    # Metrics (convert micros to currency)
    if hasattr(row, 'metrics'):
        m = row.metrics
        result['cost'] = m.cost_micros / 1_000_000
        result['conversions'] = m.conversions
        result['clicks'] = m.clicks
        result['impressions'] = m.impressions
        result['ctr'] = m.ctr * 100 if m.ctr else 0
        result['avg_cpc'] = m.average_cpc / 1_000_000 if m.average_cpc else 0
        result['search_impr_share'] = m.search_impression_share if m.search_impression_share else None
    
    return result
```

## Complete Data Extraction

```python
def extract_audit_data(client, customer_id, date_range='LAST_30_DAYS'):
    """
    Extract all data needed for comprehensive audit.
    
    Returns:
        Dict with DataFrames for each report type
    """
    data = {}
    
    queries = {
        'campaigns': CAMPAIGN_QUERY,
        'ad_groups': AD_GROUP_QUERY,
        'keywords': KEYWORD_QUERY,
        'search_terms': SEARCH_TERM_QUERY,
        'ads': AD_QUERY,
        'extensions': EXTENSION_QUERY,
        'placements': PLACEMENT_QUERY
    }
    
    for name, query in queries.items():
        print(f"Extracting {name}...")
        try:
            data[name] = run_query(client, customer_id, query)
            print(f"  → {len(data[name])} rows")
        except Exception as e:
            print(f"  → Error: {e}")
            data[name] = pd.DataFrame()
    
    return data
```

## Usage Example

```python
# Initialize client
client = get_google_ads_client('google-ads.yaml')

# Extract data
customer_id = '1234567890'  # Without dashes
audit_data = extract_audit_data(client, customer_id)

# Access individual reports
campaigns_df = audit_data['campaigns']
keywords_df = audit_data['keywords']
search_terms_df = audit_data['search_terms']

# Calculate metrics
keywords_df['cpa'] = keywords_df['cost'] / keywords_df['conversions'].replace(0, float('nan'))

# Run audit analyses
from quality_score import analyze_qs_distribution
qs_report = analyze_qs_distribution(keywords_df)
```

## Date Range Options

Available date ranges for GAQL:
- `TODAY`
- `YESTERDAY`
- `LAST_7_DAYS`
- `LAST_14_DAYS`
- `LAST_30_DAYS`
- `LAST_90_DAYS`
- `THIS_MONTH`
- `LAST_MONTH`
- `THIS_QUARTER`
- Custom: `segments.date BETWEEN '2024-01-01' AND '2024-01-31'`

## Error Handling

```python
from google.ads.googleads.errors import GoogleAdsException

def safe_query(client, customer_id, query, fallback=None):
    """Execute query with error handling."""
    try:
        return run_query(client, customer_id, query)
    except GoogleAdsException as ex:
        error = ex.failure.errors[0]
        print(f"API Error: {error.error_code} - {error.message}")
        return fallback if fallback is not None else pd.DataFrame()
    except Exception as e:
        print(f"Unexpected error: {e}")
        return fallback if fallback is not None else pd.DataFrame()
```

## Rate Limiting

Google Ads API has rate limits. For large accounts:

```python
import time

def extract_with_rate_limit(client, customer_id, queries, delay=1):
    """Extract data with rate limiting between queries."""
    data = {}
    
    for name, query in queries.items():
        data[name] = run_query(client, customer_id, query)
        time.sleep(delay)  # Avoid rate limits
    
    return data
```

## Output

API data can be:
1. Passed directly to audit analysis functions
2. Saved as CSV/Excel for manual review
3. Stored in database for historical comparison

```python
def save_audit_data(data, output_dir='./audit_data'):
    """Save extracted data to files."""
    import os
    os.makedirs(output_dir, exist_ok=True)
    
    for name, df in data.items():
        df.to_csv(f"{output_dir}/{name}.csv", index=False)
        print(f"Saved {name}.csv ({len(df)} rows)")
```
