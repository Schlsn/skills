---
name: meta-ads
description: Manage Meta (Facebook & Instagram) advertising from the terminal using the official Meta Ads CLI. Create, list, update and delete campaigns, ad sets, ads, ad creatives, datasets (Pixels) and product catalogs. Query performance insights with date ranges, breakdowns and custom metrics. Use when the user wants to manage Meta/Facebook/Instagram ads programmatically, automate ad workflows, build CI/CD pipelines around Meta Marketing API, audit Meta campaigns, prototype Marketing API calls before writing app code, or pull Meta ads insights from the command line.
triggers:
  - "meta ads"
  - "meta ads cli"
  - "facebook ads"
  - "facebook ads cli"
  - "instagram ads"
  - "marketing api"
  - "ads cli"
  - "meta pixel"
  - "advantage+ catalog"
  - "dynamic creative optimization"
  - "DCO"
---

# Meta Ads CLI

Official command-line tool for the **Meta Marketing API**. Wraps authentication, pagination, formatting and error handling so you can manage campaigns, ad sets, ads, ad creatives, datasets (Pixels) and product catalogs from the terminal — and pipe results into scripts.

> Source: [developers.facebook.com/documentation/ads-commerce/ads-ai-connectors/ads-cli](https://developers.facebook.com/documentation/ads-commerce/ads-ai-connectors/ads-cli/ads-cli-overview)

## What it does

- **Full lifecycle management** — Create, read, update, delete across the entire Meta ad hierarchy: campaigns → ad sets → ads → creatives.
- **Performance insights** — Query spend, impressions, CTR, CPC, ROAS, conversions etc. with custom date ranges and breakdowns (age, gender, placement, platform).
- **Catalogs & Pixels** — Manage Advantage+ product catalogs, create datasets/Pixels, connect them to ad accounts and catalogs, assign user permissions.
- **Automation-friendly** — Three output formats (`table` | `json` | `text`), non-interactive mode, exit codes 0–5, env-var credentials. CI/CD ready.
- **Safety by default** — New resources are created in `PAUSED` status; destructive ops require confirmation unless `--force` is passed.

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.12+ | Required runtime |
| Virtual environment | Recommended (`uv`, `venv`, or similar) |
| Meta system user access token | Admin system user, generated in Meta Business Suite |
| Ad account ID | Set as env var or per-command flag |
| Business ID | Required for `page list`, `dataset list`, `catalog list`. Set `BUSINESS_ID` env var (or pass `--business-id`). When only `AD_ACCOUNT_ID` is set, the CLI tries to resolve the business owner; otherwise these commands fail with `Error: No business ID available.` |
| Business Page (for ad creatives) | Every ad creative needs a Page identity |

### Required token scopes

At minimum the system user token needs `ads_management`, `business_management`, `pages_show_list`, `pages_read_engagement`. Add `catalog_management` for catalog work. Generate via **Meta Business Suite → System Users → Generate Token**.

## Setup

### 1. Install

The official PyPI package is **`meta-ads`** (binary: `meta`). Do **not** install `meta-ads-cli` — that is an unrelated YAML-based campaign creator with a different command surface.

```bash
# Using uv (recommended — installs as an isolated tool)
uv tool install meta-ads          # or: pip install meta-ads
```

After install, all commands are invoked as `meta ads ...`. Verify with `meta --version` (should print `meta, version 1.x.x`) and `meta ads --help` (should list `campaign`, `adset`, `ad`, `creative`, `insights`, …).

In a `uv`-managed project that depends on `meta-ads`, prefix commands with `uv run`: `uv run meta ads ...`.

### 2. Create a system user & generate a token

In **Meta Business Suite**:

1. **Business Settings → Users → System Users → Add** — create an **admin** system user.
2. **Assign assets** — give the system user access to the ad account(s), Pixel(s)/dataset(s), Business Page(s) and product catalog(s) you want to manage.
3. **App admin** — add the system user as an **app admin** of your Meta app.
4. **Generate Token** — pick the app, select scopes (`ads_management`, `business_management`, `pages_show_list`, `pages_read_engagement`, `catalog_management` if needed), and copy the token (it is shown only once).

### 3. Configure credentials

`Ads CLI` reads config in this precedence order (highest first):

1. Command-line flags (e.g. `--ad-account-id ...`)
2. Environment variables
3. `.env` file in the working directory
4. Persistent config file under `$XDG_CONFIG_HOME/meta-ads/` (override with `XDG_CONFIG_HOME`)

**Recommended — `.env` file in the project root:**

```bash
cat > .env << 'DOTENV'
ACCESS_TOKEN='<ACCESS_TOKEN>'
AD_ACCOUNT_ID='<AD_ACCOUNT_ID>'
BUSINESS_ID='<BUSINESS_ID>'
DOTENV
```

**Or export per-session:**

```bash
export ACCESS_TOKEN=<ACCESS_TOKEN>
export AD_ACCOUNT_ID=<AD_ACCOUNT_ID>
```

> **Note on `meta ads auth`:** the `auth login` / `auth status` subcommands described in some Meta documentation are not present in `meta-ads` v1.0.1 (verified 2026-04-30). Authentication is purely via `ACCESS_TOKEN` env var or `.env`. If a future version exposes `meta ads auth`, prefer it for persistent token storage.

### 4. Find your ad account ID

```bash
meta ads adaccount list            # list accessible ad accounts
meta ads adaccount current         # show currently configured account
```

### 5. Verify

```bash
meta ads campaign list                                        # should return [] or list of campaigns
meta ads insights get --fields spend,impressions,ctr,cpc      # last 30 days metrics
meta ads page list                                            # business pages (needed for creatives)
```

## Global options

Flag placement matters. The CLI has two flag groups: top-level flags on `meta` and `meta ads`-level flags. Top-level flags go **before** `ads`, ads-level flags go **after** `ads` and **before** the subcommand.

**Top-level (`meta ...`):**

| Flag | Description |
|---|---|
| `--output table\|json\|text` | Output format. Default: `table`. Use `json` in scripts. |
| `--no-color` | Disable colored output |
| `--non-interactive` | Disable interactive prompts (use in scripts/CI) |
| `--access-token <TOKEN>` | Override stored token (rarely needed) |

**Ads-level (`meta ads ...`):**

| Flag | Description |
|---|---|
| `--ad-account-id <ID>` | Override `AD_ACCOUNT_ID` for this call (e.g. `act_123456`) |
| `--business-id <ID>` | Override `BUSINESS_ID` for this call (used by `page`, `dataset`, `catalog`) |

Examples:
```bash
meta --output json ads campaign list                            # top-level flag before `ads`
meta ads --ad-account-id act_123 campaign list                  # ads-level flag after `ads`
meta --output json ads --ad-account-id act_123 campaign list    # both
```

⚠ `meta --ad-account-id act_123 ads campaign list` will fail with `Error: No such option: --ad-account-id` — `--ad-account-id` is not a top-level flag.

Exit codes: `0` success, `1–5` various error classes (auth, validation, API, network, internal). Reliable for scripting.

## Command reference

### Authentication

`meta-ads` v1.0.1 has **no `auth` subcommand**. Authentication is configured via `ACCESS_TOKEN` env var or `.env` (see Setup → Configure credentials). If a future version adds `meta ads auth login` / `auth status`, prefer it for persistent token storage.

### Ad accounts

```bash
meta ads adaccount list            # list accounts you have access to
meta ads adaccount list --limit 50
meta ads adaccount current         # show configured ACCOUNT_ID
```

### Business Pages

```bash
meta ads page list                 # list pages (needed for creatives)
meta ads page list --limit 50
```

### Campaigns

```bash
# List
meta ads campaign list
meta ads campaign list --limit 25

# Create (always created PAUSED)
meta ads campaign create --name "Summer Sale" --objective OUTCOME_TRAFFIC --daily-budget 5000
# budget unit = minor unit of the ad account currency (cents/haléře/öre/etc.)
# 5000 in a USD account = $50.00; 5000 in a CZK account = 50 CZK

# Without --start-time, the API stores 1970-01-01 as start_time (campaign still
# launches normally when activated). Pass --start-time to record a real timestamp:
meta ads campaign create --name "Summer Sale" --objective OUTCOME_TRAFFIC \
  --daily-budget 5000 --start-time 2026-06-01T00:00:00+0200

# Get / update / delete
meta ads campaign get <CAMPAIGN_ID>
meta ads campaign update <CAMPAIGN_ID> --status ACTIVE
meta ads campaign update <CAMPAIGN_ID> --daily-budget 10000
meta ads campaign delete <CAMPAIGN_ID> --force      # cascades to ad sets + ads
```

**Common objectives:** `OUTCOME_TRAFFIC`, `OUTCOME_AWARENESS`, `OUTCOME_ENGAGEMENT`, `OUTCOME_LEADS`, `OUTCOME_SALES`, `OUTCOME_APP_PROMOTION`.
**Status values:** `ACTIVE`, `PAUSED`, `ARCHIVED`.

### Ad sets

```bash
# List (optionally filter by campaign)
meta ads adset list                          # all in account
meta ads adset list <CAMPAIGN_ID>            # one campaign
meta ads adset list --limit 25

# Create — traffic ad set with country targeting
meta ads adset create <CAMPAIGN_ID> --name "US Traffic" \
  --optimization-goal LINK_CLICKS --billing-event IMPRESSIONS \
  --bid-amount 500 --targeting-countries US

# Conversion ad set (requires dataset/Pixel)
meta ads adset create <CAMPAIGN_ID> --name "US Purchases" \
  --optimization-goal OFFSITE_CONVERSIONS --billing-event IMPRESSIONS \
  --pixel-id <PIXEL_ID> --custom-event-type PURCHASE

# Get / update / delete
meta ads adset get <AD_SET_ID>
meta ads adset update <AD_SET_ID> --status ACTIVE
meta ads adset update <AD_SET_ID> --daily-budget 10000
meta ads adset delete <AD_SET_ID> --force
```

**Key ad set flags:**

| Flag | Notes |
|---|---|
| `--daily-budget` / `--lifetime-budget` | In cents. Omit if campaign uses CBO. `--lifetime-budget` requires `--end-time`. |
| `--start-time` / `--end-time` | ISO 8601 |
| `--targeting-countries` | Comma-separated ISO codes, e.g. `US,GB,CA` |
| `--optimization-goal` | `LINK_CLICKS`, `OFFSITE_CONVERSIONS`, `IMPRESSIONS`, `REACH`, ... |
| `--billing-event` | `IMPRESSIONS`, `LINK_CLICKS`, ... |
| `--bid-amount` | In cents |
| `--pixel-id` + `--custom-event-type` | For conversion ad sets |

### Ads

```bash
# List (optionally filter by ad set)
meta ads ad list
meta ads ad list <AD_SET_ID>
meta ads ad list --limit 25

# Create (an ad references a creative — create the creative first)
meta ads ad create <AD_SET_ID> --name "Summer Banner Ad" --creative-id <CREATIVE_ID>

# With tracking specs
meta ads ad create <AD_SET_ID> --name "Tracked Ad" --creative-id <CREATIVE_ID> \
  --tracking-specs '[{"action.type":["offsite_conversion"],"fb_pixel":["<PIXEL_ID>"]}]'

# Get / update / delete
meta ads ad get <AD_ID>
meta ads ad update <AD_ID> --status ACTIVE
meta ads ad update <AD_ID> --creative-id <NEW_CREATIVE_ID>
meta ads ad delete <AD_ID> --force
```

### Ad creatives

An ad creative is an **independent, reusable** object. Workflow: create creative → reference its ID when creating the ad. Every creative needs `--page-id` (Business Page identity).

#### Standard creative — link ad

```bash
meta ads creative create --name "Summer Banner" \
  --page-id <PAGE_ID> --image ./banner.jpg \
  --title "Summer Sale 50% Off" \
  --body "Limited time offer" \
  --link-url "https://example.com/sale" \
  --description "Free shipping" \
  --call-to-action SHOP_NOW
```

#### Standard creative — video ad

```bash
meta ads creative create --name "Brand Video" \
  --page-id <PAGE_ID> --video ./promo.mp4 \
  --title "See what's new" --link-url "https://example.com" \
  --call-to-action LEARN_MORE
```

#### Photo post (no link, posts to Page)

```bash
meta ads creative create --name "Photo Post" \
  --page-id <PAGE_ID> --image ./photo.jpg \
  --body "Behind the scenes at our Summer photoshoot"
```

#### Dynamic Creative Optimization (DCO)

Provide multiple variants of images/videos/headlines/bodies/CTAs and Meta auto-tests combinations. Uses **plural** flags (`--images`, `--titles`, `--bodies`, `--descriptions`, `--call-to-actions`) — repeat each per variant. Requires `--link-url` and at least one `--images` or `--videos`.

```bash
meta ads creative create --name "DCO Test" \
  --page-id <PAGE_ID> --link-url "https://example.com" \
  --images ./img1.jpg --images ./img2.jpg \
  --titles "Shop Now" --titles "Learn More" \
  --bodies "50% off everything!" --bodies "Free shipping today!" \
  --descriptions "Limited time offer" --descriptions "While supplies last" \
  --call-to-actions SHOP_NOW --call-to-actions LEARN_MORE
```

#### Update / delete creative

Updates change only the fields you specify (the API blocks updating some fields after creation — if it fails, create a new creative).

```bash
meta ads creative get <CREATIVE_ID>
meta ads creative update <CREATIVE_ID> --image ./new-banner.jpg
meta ads creative update <CREATIVE_ID> --body "New copy"
meta ads creative update <CREATIVE_ID> --status PAUSED
meta ads creative delete <CREATIVE_ID> --force
```

Available update fields: `--name`, `--body`, `--title`, `--link-url`, `--description`, `--call-to-action`, `--image`, `--video`, `--instagram-actor-id`, `--status`.

#### Call-to-action types

`SHOP_NOW`, `LEARN_MORE`, `SIGN_UP`, `DOWNLOAD`, `BOOK_TRAVEL`, `GET_QUOTE`, `CONTACT_US`, `APPLY_NOW`, `SUBSCRIBE`, `WATCH_MORE`.

#### Instagram placements

```bash
meta ads creative create --name "IG Ad" --page-id <PAGE_ID> \
  --instagram-actor-id <IG_ACCOUNT_ID> ...
```

### Datasets (Meta Pixels)

```bash
meta ads dataset list                                      # by business
meta ads dataset list --business-id <BUSINESS_ID>
meta ads dataset get <PIXEL_ID>

# Create — Ads CLI auto-assigns permissions
meta ads dataset create --name "Site Pixel" --business-id <BUSINESS_ID>

# Connect Pixel to an ad account and/or catalog
meta ads dataset connect <PIXEL_ID> --ad-account-id <AD_ACCOUNT_ID>
meta ads dataset connect <PIXEL_ID> --catalog-id <CATALOG_ID>
meta ads dataset connect <PIXEL_ID> --ad-account-id <AD_ACCOUNT_ID> --catalog-id <CATALOG_ID>

# Disconnect from ad account
meta ads dataset disconnect <PIXEL_ID> --ad-account-id <AD_ACCOUNT_ID> --force

# Assign user permissions
meta ads dataset assign-user <PIXEL_ID> --user-id <USER_ID> \
  --tasks ADVERTISE --tasks ANALYZE --tasks EDIT
```

### Product catalogs

```bash
meta ads catalog list                                       # business resolved from ad account
meta ads catalog list --business-id <BUSINESS_ID>
meta ads catalog get <CATALOG_ID>
meta ads catalog create --name "Main Catalog" --business-id <BUSINESS_ID>
meta ads catalog update <CATALOG_ID> --name "Renamed Catalog"
meta ads catalog delete <CATALOG_ID> --force
```

### Insights (performance reporting)

```bash
# Account-level, last 30 days (defaults)
meta ads insights get

# Custom metric set
meta ads insights get --fields spend,impressions,clicks,ctr,cpc,reach
meta ads insights get --fields spend,conversions,cost_per_conversion,purchase_roas

# Filter scope
meta ads insights get --campaign-id <CAMPAIGN_ID>
meta ads insights get --adset-id   <AD_SET_ID>
meta ads insights get --ad-id      <AD_ID>

# Date range — preset or custom
meta ads insights get --date-preset last_30d
meta ads insights get --date-preset yesterday
meta ads insights get --since 2024-01-01 --until 2024-01-31

# Time series
meta ads insights get --date-preset last_30d --time-increment daily --fields spend
meta ads insights get --campaign-id <CAMPAIGN_ID> --time-increment weekly

# Breakdowns (repeatable)
meta ads insights get --breakdown age --breakdown gender
meta ads insights get --breakdown publisher_platform --fields spend,impressions,ctr
# Other useful: country, region, dma, impression_device, platform_position

# Sort & limit
meta ads insights get --adset-id <AD_SET_ID> --sort spend_descending
meta ads insights get --adset-id <AD_SET_ID> --sort impressions_ascending
meta ads insights get --campaign-id <CAMPAIGN_ID> --limit 100         # default 50
```

**Useful metric fields:** `spend`, `impressions`, `clicks`, `reach`, `frequency`, `ctr`, `cpc`, `cpm`, `conversions`, `cost_per_conversion`, `purchase_roas`, `actions`.

**Date presets:** `today`, `yesterday`, `last_7d`, `last_14d`, `last_30d`, `last_90d`, `this_month`, `last_month`, `this_quarter`, `lifetime`.

## Recipes

### End-to-end campaign (PAUSED by default — review then activate)

```bash
# 0. Set credentials (if not in .env)
export ACCESS_TOKEN=<ACCESS_TOKEN>
export AD_ACCOUNT_ID=<AD_ACCOUNT_ID>

# 1. Find Page ID for the creative
meta ads page list

# 2. Campaign
meta ads campaign create --name "Summer Sale 2024" \
  --objective OUTCOME_TRAFFIC --daily-budget 5000
# → save the returned id as CAMPAIGN_ID

# 3. Ad set (CBO at campaign level → no budget here)
meta ads adset create <CAMPAIGN_ID> --name "US Adults 18-65" \
  --optimization-goal LINK_CLICKS --billing-event IMPRESSIONS \
  --targeting-countries US
# → save AD_SET_ID

# 4. Creative
meta ads creative create --name "Summer Banner" \
  --page-id <PAGE_ID> --image ./banner.jpg \
  --title "Summer Sale" --body "50% off everything" \
  --link-url "https://example.com/sale" --call-to-action SHOP_NOW
# → save CREATIVE_ID

# 5. Ad
meta ads ad create <AD_SET_ID> --name "Summer Banner Ad" \
  --creative-id <CREATIVE_ID>
# → save AD_ID

# 6. Activate the whole tree
meta ads campaign update <CAMPAIGN_ID> --status ACTIVE
meta ads adset update    <AD_SET_ID>   --status ACTIVE
meta ads ad update       <AD_ID>       --status ACTIVE
```

### Scripted automation — capture IDs from JSON output

```bash
CAMPAIGN_ID=$(meta --output json ads campaign create \
  --name "Auto Campaign" --objective OUTCOME_TRAFFIC --daily-budget 5000 \
  | jq -r '.id')

AD_SET_ID=$(meta --output json ads adset create $CAMPAIGN_ID \
  --name "Auto Ad Set" --optimization-goal LINK_CLICKS \
  --billing-event IMPRESSIONS --targeting-countries US \
  | jq -r '.id')

# Always pass --non-interactive in CI to suppress prompts
meta --output json --non-interactive ads campaign list | jq '.[] | {id, name, status}'
```

### Cleanup — cascade delete

Deleting a campaign cascades to its ad sets and ads. Deleting an ad set cascades to its ads.

```bash
meta ads ad delete       <AD_ID>       --force
meta ads adset delete    <AD_SET_ID>   --force      # + child ads
meta ads campaign delete <CAMPAIGN_ID> --force      # + child ad sets + ads
meta ads creative delete <CREATIVE_ID> --force      # only if no active ads use it
meta ads dataset disconnect <PIXEL_ID> --ad-account-id <AD_ACCOUNT_ID> --force
meta ads catalog delete  <CATALOG_ID>  --force
```

### Daily reporting cron

```bash
#!/usr/bin/env bash
set -euo pipefail
source /path/to/.env
meta --output json --non-interactive ads insights get \
  --date-preset yesterday \
  --fields spend,impressions,clicks,ctr,cpc,conversions,purchase_roas \
  --breakdown publisher_platform \
  > "/var/log/meta-ads/$(date +%F).json"
```

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `Authentication error` | Token expired, missing scopes, wrong app | Regenerate system user token; verify scopes (`ads_management`, `business_management`, `pages_show_list`, `pages_read_engagement`, `catalog_management`) |
| `Permission denied` on a Pixel/Page/Catalog | System user not assigned to the asset | Business Settings → System User → assign asset |
| `(#100) This application has not been approved to use this api` (catalog list / get) | The Meta **app** itself is not approved for the Catalog API (independent of token scope) | Request Catalog API access for the app in the App Dashboard, or use a different app that already has it. Token scope alone is not sufficient. |
| `Error: No business ID available.` on `page list` / `dataset list` / `catalog list` | `BUSINESS_ID` not set and ad account business cannot be auto-resolved | Set `BUSINESS_ID` env var or pass `meta ads --business-id <ID> ...` |
| `Error: No such option: --ad-account-id` | Flag placed before `ads` (top-level) instead of after | Use `meta ads --ad-account-id act_123 ...` (ads-level flag) |
| Creative update fails on a field | API blocks updating some fields after creation | Create a new creative instead |
| Cannot delete creative | Active ad still references it | Pause/delete the ad first |
| Created campaign shows `START_TIME = 1970-01-01` | `--start-time` not passed at create time | Pass `--start-time <ISO8601>` on create, or update afterward |

## Reference links

- [Overview](https://developers.facebook.com/documentation/ads-commerce/ads-ai-connectors/ads-cli/ads-cli-overview)
- [Get Started](https://developers.facebook.com/documentation/ads-commerce/ads-ai-connectors/ads-cli/setup/get-started)
- [Configuration](https://developers.facebook.com/documentation/ads-commerce/ads-ai-connectors/ads-cli/setup/configuration)
- [Command reference](https://developers.facebook.com/documentation/ads-commerce/ads-ai-connectors/ads-cli/command-reference)
- [Ad creatives](https://developers.facebook.com/documentation/ads-commerce/ads-ai-connectors/ads-cli/ad-creatives)
- [Insights](https://developers.facebook.com/documentation/ads-commerce/ads-ai-connectors/ads-cli/insights)
- [Tutorials & recipes](https://developers.facebook.com/documentation/ads-commerce/ads-ai-connectors/ads-cli/tutorials-and-recipes)
- [Launch announcement (2026-04-29)](https://developers.facebook.com/blog/post/2026/04/29/introducing-ads-cli)
