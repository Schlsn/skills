# Meta Ads — MCP Integration

Přímý přístup k Meta Ads API přes MCP server (clawhub). Umožňuje Claude spravovat kampaně, ad sety, kreativy a reporty přímo z chatu.

## Instalace

```bash
npx clawhub@latest install meta-ads
```

Tento příkaz automaticky:
1. Stáhne a nainstaluje Meta Ads MCP server
2. Přidá server do Claude Code konfigurace (`~/.claude/settings.json`)
3. Vyžádá propojení s Meta Business účtem (OAuth flow)

## Co MCP umožňuje

| Schopnost | Popis |
|-----------|-------|
| Čtení kampaní | Stažení struktury účtu, kampání, ad setů, reklam |
| Tvorba kampaní | Vytvoření nové kampaně, ad setu, kreativy |
| Úpravy | Změna rozpočtu, targeting, stav (aktivní/pauzovaný) |
| Reporting | Metriky za libovolné období (impressions, clicks, spend, ROAS, CPA) |
| Audience management | Tvorba custom a lookalike publik |
| Creative management | Upload a správa obrázků a videí |

## Setup po instalaci

### 1. Meta Business Manager přístup

Potřebuješ:
- Meta Business Manager účet s přístupem k ad účtu
- System User nebo osobní token s oprávněními `ads_management`, `ads_read`, `business_management`

### 2. Konfigurace tokenu

Po `npx clawhub@latest install meta-ads` tě průvodce vyzve k zadání:
- **Ad Account ID** — ve formátu `act_XXXXXXXXXX` (najdeš v Business Manager → Ad Accounts)
- **Access Token** — System User token (doporučeno) nebo uživatelský token

### 3. Ověření

```
Claude, show me my Meta Ads campaigns
```

## Přístupová práva (Meta App)

Token musí mít:
- `ads_management` — tvorba a úprava kampaní
- `ads_read` — čtení metrik a struktury
- `business_management` — přístup k Business Manager objektům
- `pages_read_engagement` — čtení page engagement dat (volitelné)

## Doporučené workflow

1. **Analýza** — "Show me campaign performance last 30 days, grouped by campaign"
2. **Diagnóza** — "Which ad sets have CPA above €X and what's causing it?"
3. **Tvorba** — "Create a new campaign for [produkt], budget €Y/day, audience [popis]"
4. **Optimalizace** — "Pause all ads with CTR below 1% and frequency above 4"

## Omezení

- Rate limity Meta API (obvykle 200 req/hodinu)
- Boosted posts a Instagram Shopping vyžadují extra oprávnění
- Změny ve struktuře kampaní mohou resetovat learning phase
