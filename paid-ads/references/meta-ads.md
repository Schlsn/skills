# Meta Ads API

Full read/write integration with Meta (Facebook) Ads API for managing campaigns, ad sets, ads, and accessing performance insights/metrics.

## Setup

### Instalace MCP

```bash
npx clawhub@latest install meta-ads
```

### Environment Variables

- `META_ACCESS_TOKEN` — Meta access token (User Access Token or System User Token)
- `META_AD_ACCOUNT_ID` — Your ad account ID (numeric, without `act_` prefix)

### Required Permissions

- `ads_read` — Read access to ads data
- `ads_management` — Create, edit, and delete ads

### Token Types

**User Access Token**
- Short-lived: ~2 hours
- Can be extended to 60-90 days
- Obtained via OAuth flow or Graph API Explorer

**System User Token** *(doporučeno)*
- No expiration
- Recommended for production/automated access
- Created in Business Manager

### Authentication

```
Authorization: Bearer $META_ACCESS_TOKEN
Content-Type: application/json
```

Or as query parameter: `?access_token=$META_ACCESS_TOKEN`

---

## API Reference

Base URL: `https://graph.facebook.com/v25.0/`

> **Important:** Ad account IDs must be prefixed with `act_` in API calls (e.g., `act_123456789`).

---

## Ad Account

#### Get Ad Account Info

```bash
curl "https://graph.facebook.com/v25.0/act_$META_AD_ACCOUNT_ID?fields=name,account_status,currency,timezone_name,amount_spent" \
  -H "Authorization: Bearer $META_ACCESS_TOKEN"
```

---

## Campaigns

#### List Campaigns

```bash
curl "https://graph.facebook.com/v25.0/act_$META_AD_ACCOUNT_ID/campaigns?fields=id,name,status,objective,daily_budget,lifetime_budget,created_time" \
  -H "Authorization: Bearer $META_ACCESS_TOKEN"
```

#### Get Single Campaign

```bash
curl "https://graph.facebook.com/v25.0/{CAMPAIGN_ID}?fields=id,name,status,objective,daily_budget,lifetime_budget,created_time,updated_time" \
  -H "Authorization: Bearer $META_ACCESS_TOKEN"
```

#### Create Campaign

```bash
curl -X POST "https://graph.facebook.com/v25.0/act_$META_AD_ACCOUNT_ID/campaigns" \
  -H "Authorization: Bearer $META_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Campaign",
    "objective": "OUTCOME_TRAFFIC",
    "status": "PAUSED",
    "special_ad_categories": []
  }'
```

#### Update Campaign

```bash
curl -X POST "https://graph.facebook.com/v25.0/{CAMPAIGN_ID}" \
  -H "Authorization: Bearer $META_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Updated Campaign Name", "status": "ACTIVE"}'
```

#### Pause / Delete Campaign

```bash
# Pause
curl -X POST "https://graph.facebook.com/v25.0/{CAMPAIGN_ID}" \
  -H "Authorization: Bearer $META_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"status": "PAUSED"}'

# Delete
curl -X DELETE "https://graph.facebook.com/v25.0/{CAMPAIGN_ID}" \
  -H "Authorization: Bearer $META_ACCESS_TOKEN"
```

---

## Ad Sets

#### List Ad Sets

```bash
curl "https://graph.facebook.com/v25.0/act_$META_AD_ACCOUNT_ID/adsets?fields=id,name,status,campaign_id,daily_budget,lifetime_budget,targeting,optimization_goal" \
  -H "Authorization: Bearer $META_ACCESS_TOKEN"
```

#### Get Single Ad Set

```bash
curl "https://graph.facebook.com/v25.0/{ADSET_ID}?fields=id,name,status,campaign_id,daily_budget,lifetime_budget,targeting,optimization_goal,bid_amount,billing_event" \
  -H "Authorization: Bearer $META_ACCESS_TOKEN"
```

#### Create Ad Set

```bash
curl -X POST "https://graph.facebook.com/v25.0/act_$META_AD_ACCOUNT_ID/adsets" \
  -H "Authorization: Bearer $META_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Ad Set",
    "campaign_id": "{CAMPAIGN_ID}",
    "daily_budget": 5000,
    "billing_event": "IMPRESSIONS",
    "optimization_goal": "LINK_CLICKS",
    "bid_amount": 200,
    "targeting": {
      "geo_locations": {"countries": ["US"]},
      "age_min": 18,
      "age_max": 65
    },
    "status": "PAUSED"
  }'
```

> **Note:** Budget values are in cents (e.g., `5000` = $50.00).

#### Update / Pause / Delete Ad Set

```bash
# Update
curl -X POST "https://graph.facebook.com/v25.0/{ADSET_ID}" \
  -H "Authorization: Bearer $META_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"daily_budget": 10000, "status": "ACTIVE"}'

# Pause
curl -X POST "https://graph.facebook.com/v25.0/{ADSET_ID}" \
  -H "Authorization: Bearer $META_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"status": "PAUSED"}'

# Delete
curl -X DELETE "https://graph.facebook.com/v25.0/{ADSET_ID}" \
  -H "Authorization: Bearer $META_ACCESS_TOKEN"
```

---

## Ads

#### List Ads

```bash
curl "https://graph.facebook.com/v25.0/act_$META_AD_ACCOUNT_ID/ads?fields=id,name,status,adset_id,campaign_id,creative,created_time" \
  -H "Authorization: Bearer $META_ACCESS_TOKEN"
```

#### Create Ad (with existing creative)

```bash
curl -X POST "https://graph.facebook.com/v25.0/act_$META_AD_ACCOUNT_ID/ads" \
  -H "Authorization: Bearer $META_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Ad",
    "adset_id": "{ADSET_ID}",
    "creative": {"creative_id": "{CREATIVE_ID}"},
    "status": "PAUSED"
  }'
```

#### Create Ad with Inline Creative

```bash
curl -X POST "https://graph.facebook.com/v25.0/act_$META_AD_ACCOUNT_ID/ads" \
  -H "Authorization: Bearer $META_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Ad",
    "adset_id": "{ADSET_ID}",
    "creative": {
      "object_story_spec": {
        "page_id": "{PAGE_ID}",
        "link_data": {
          "link": "https://example.com",
          "message": "Check out our website!",
          "name": "Example Site",
          "call_to_action": {"type": "LEARN_MORE"}
        }
      }
    },
    "status": "PAUSED"
  }'
```

---

## Ad Creatives

#### List / Create Ad Creatives

```bash
# List
curl "https://graph.facebook.com/v25.0/act_$META_AD_ACCOUNT_ID/adcreatives?fields=id,name,object_story_spec,thumbnail_url" \
  -H "Authorization: Bearer $META_ACCESS_TOKEN"

# Create
curl -X POST "https://graph.facebook.com/v25.0/act_$META_AD_ACCOUNT_ID/adcreatives" \
  -H "Authorization: Bearer $META_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Creative",
    "object_story_spec": {
      "page_id": "{PAGE_ID}",
      "link_data": {
        "link": "https://example.com",
        "message": "Ad copy text here",
        "name": "Headline",
        "description": "Description text",
        "call_to_action": {"type": "SHOP_NOW"}
      }
    }
  }'
```

---

## Insights (Performance Metrics)

#### Account / Campaign / Ad Set / Ad Level

```bash
# Account
curl "https://graph.facebook.com/v25.0/act_$META_AD_ACCOUNT_ID/insights?fields=spend,impressions,clicks,reach,cpc,cpm,ctr&date_preset=last_30d" \
  -H "Authorization: Bearer $META_ACCESS_TOKEN"

# Campaign
curl "https://graph.facebook.com/v25.0/{CAMPAIGN_ID}/insights?fields=spend,impressions,clicks,reach,frequency,cpc,cpm,ctr,actions&date_preset=last_7d" \
  -H "Authorization: Bearer $META_ACCESS_TOKEN"
```

#### Custom Date Range

```bash
curl "https://graph.facebook.com/v25.0/act_$META_AD_ACCOUNT_ID/insights?fields=spend,impressions,clicks,cpc,cpm,ctr&time_range={\"since\":\"2026-01-01\",\"until\":\"2026-01-31\"}" \
  -H "Authorization: Bearer $META_ACCESS_TOKEN"
```

#### With Breakdowns / By Day / Attribution Window

```bash
# Breakdowns (age, gender)
curl "https://graph.facebook.com/v25.0/act_$META_AD_ACCOUNT_ID/insights?fields=spend,impressions,clicks,cpc&breakdowns=age,gender&date_preset=last_7d" \
  -H "Authorization: Bearer $META_ACCESS_TOKEN"

# Daily
curl "https://graph.facebook.com/v25.0/act_$META_AD_ACCOUNT_ID/insights?fields=spend,impressions,clicks&time_increment=1&date_preset=last_7d" \
  -H "Authorization: Bearer $META_ACCESS_TOKEN"

# Attribution window
curl "https://graph.facebook.com/v25.0/{CAMPAIGN_ID}/insights?fields=spend,actions,action_values&action_attribution_windows=[\"7d_click\",\"1d_view\"]&date_preset=last_7d" \
  -H "Authorization: Bearer $META_ACCESS_TOKEN"
```

---

## Reference Tables

### Campaign Objectives

| Objective | Description |
|-----------|-------------|
| `OUTCOME_AWARENESS` | Brand awareness and reach |
| `OUTCOME_ENGAGEMENT` | Post engagement, page likes |
| `OUTCOME_TRAFFIC` | Drive traffic to website or app |
| `OUTCOME_LEADS` | Lead generation |
| `OUTCOME_APP_PROMOTION` | App installs and engagement |
| `OUTCOME_SALES` | Conversions and catalog sales |

### Available Metrics

| Metric | Description |
|--------|-------------|
| `spend` | Total amount spent |
| `impressions` | Times ads were shown |
| `clicks` | Number of clicks |
| `reach` | Unique people who saw ads |
| `frequency` | Avg. times each person saw your ad |
| `cpc` | Cost per click |
| `cpm` | Cost per 1,000 impressions |
| `ctr` | Click-through rate |
| `actions` | Conversions broken down by type |
| `action_values` | Value of conversions |
| `cost_per_action_type` | Cost per action by type |

### Attribution Windows

| Window | Description |
|--------|-------------|
| `1d_click` | 1-day click attribution |
| `7d_click` | 7-day click attribution (default) |
| `28d_click` | 28-day click attribution |
| `1d_view` | 1-day view-through attribution |

> **Note (Jan 2026):** `7d_view` and `28d_view` have been removed. Only `1d_view` remains for view-through.

### Breakdowns

| Breakdown | Description |
|-----------|-------------|
| `age` | Age ranges (18-24, 25-34…) |
| `gender` | Male, Female, Unknown |
| `placement` | Where ad was shown |
| `device_platform` | Mobile, desktop |
| `publisher_platform` | Facebook, Instagram, Audience Network |
| `country` | Country of viewer |

### Date Presets

`today`, `yesterday`, `this_month`, `last_month`, `last_7d`, `last_14d`, `last_28d`, `last_30d`, `last_90d`

### Status Values

| Status | Description |
|--------|-------------|
| `ACTIVE` | Currently running |
| `PAUSED` | Manually paused |
| `DELETED` | Soft deleted |
| `ARCHIVED` | Archived, not running |

---

## Targeting Options

```json
{
  "geo_locations": {
    "countries": ["US", "CA"],
    "cities": [{"key": "2420379", "radius": 25, "distance_unit": "mile"}]
  },
  "age_min": 25,
  "age_max": 54,
  "genders": [1, 2],
  "flexible_spec": [{
    "interests": [{"id": "6003139266461", "name": "Technology"}]
  }]
}
```

Gender values: `1` = Male, `2` = Female

---

## Pagination

Responses include cursor-based paging:

```json
{
  "data": [...],
  "paging": {
    "cursors": {"before": "abc123", "after": "xyz789"},
    "next": "https://graph.facebook.com/v25.0/..."
  }
}
```

```bash
curl "https://graph.facebook.com/v25.0/act_$META_AD_ACCOUNT_ID/campaigns?fields=id,name&after={AFTER_CURSOR}" \
  -H "Authorization: Bearer $META_ACCESS_TOKEN"
```

- Default: 25 records/page
- Maximum: 5000 records/page (use `limit` parameter)

---

## Rate Limits

```
Call Limit = 60 + (400 × Active Ads) - (0.001 × API Errors)
```

- Minimum: 60 calls/hour
- Check `X-Business-Use-Case-Usage` header for current usage
- On `429`: exponential backoff (start 1s, double each retry, max 5 retries)

---

## Token Management

#### Extend User Token (short-lived → 60-90 days)

```bash
curl "https://graph.facebook.com/v25.0/oauth/access_token?grant_type=fb_exchange_token&client_id={APP_ID}&client_secret={APP_SECRET}&fb_exchange_token={SHORT_LIVED_TOKEN}"
```

#### Debug Token

```bash
curl "https://graph.facebook.com/v25.0/debug_token?input_token={TOKEN_TO_CHECK}&access_token={APP_ID}|{APP_SECRET}"
```

#### System User Token (doporučeno pro produkci)

1. Business Settings → Users → System Users
2. Create System User with "Admin" role
3. Assign ad account to the System User
4. Generate token with `ads_read` + `ads_management`

System User tokens **do not expire**.
