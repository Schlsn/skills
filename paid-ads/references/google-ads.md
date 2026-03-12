# Google Ads — Přístup a Credentials

Přehled credentials a způsobů přístupu ke Google Ads pro různé use case.

## Credentials — umístění

| Soubor | Cesta | Použití |
|--------|-------|---------|
| OAuth YAML (hlavní) | `/Users/adam/Documents/credentials/google-ads.yaml` | Python SDK, Keyword Planner, Search Terms |
| Service Account YAML | `/Users/adam/Documents/credentials/google-ads-service-account.yaml` | Server-side, bez interaktivního OAuth |
| GCP Service Accounts | `/Users/adam/Documents/credentials/gcp-service-accounts/` | BigQuery export, GSC API |

## google-ads.yaml — formát

```yaml
developer_token: XXXXXXXXXXXXXXXX
client_id: XXXXXXXXXX.apps.googleusercontent.com
client_secret: XXXXXXXXXXXXXXXX
refresh_token: XXXXXXXXXXXXXXXX
login_customer_id: XXXXXXXXXX   # Manager (MCC) account ID, bez pomlček
```

Nastavit cestu v kódu:
```python
from google.ads.googleads.client import GoogleAdsClient
client = GoogleAdsClient.load_from_storage("/Users/adam/Documents/credentials/google-ads.yaml")
```

## Skills využívající Google Ads credentials

### `google-ads-keyword-planner`

Keyword ideas a search volumes přes `KeywordPlanIdeaService`.

```bash
# Viz skill SKILL.md pro plné použití
python3 scripts/get_keyword_ideas.py --keywords "pronatal" --language cs --location 2203
```

### `google-ads-audit`

Kompletní audit Google Ads účtu — Quality Score, search terms, struktura, waste analysis.

```bash
# Export search terms z Google Ads UI a předej do skillu
# nebo použij GAQL přes Python SDK
```

### `gsc-ads-keyword-data`

Stažení Google Ads search terms (co lidé zadali) za posledních 90 dní.

```bash
python3 scripts/fetch_ads_search_terms_api.py \
  --schema klient \
  --project klient \
  --customer-id 123-456-7890 \
  --days 90
```

## Customer ID

- Formát v URL: `123-456-7890`
- Formát v kódu/YAML: `1234567890` (bez pomlček)
- MCC (manager) ID do `login_customer_id` v YAML

## Nalezení správného customer ID

```
Claude, list my Google Ads accounts
```
nebo v Google Ads UI: vpravo nahoře ikona → Správce → přehled účtů.

## Lokace a jazyk kódy (CZ)

| Parametr | Hodnota |
|----------|---------|
| Location CZ | `2203` |
| Location SK | `2703` |
| Language CS | `cs` nebo `1021` |
| Language SK | `sk` nebo `1033` |

## Typické problémy

**`AuthenticationError: OAUTH_TOKEN_EXPIRED`**
→ Spusť znovu OAuth flow: `python3 scripts/setup_credentials.py` (ve skillu `google-ads-keyword-planner`)

**`AuthorizationError: USER_PERMISSION_DENIED`**
→ Token nemá přístup k danému customer ID — zkontroluj `login_customer_id` v YAML

**`ResourceExhausted`**
→ Překročen denní limit API — počkej na reset (půlnoc UTC)
