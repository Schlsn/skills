---
name: google-docs
description: >
  Vytváří a upravuje Google Dokumenty přes Google Workspace CLI (`gws`) se správným firemním formátováním (Proxima Nova, zelené H2, named styles).
  Použij tento skill VŽDY, když uživatel chce:
  - vytvořit Google dokument / Google Doc / doc na Drive
  - napsat dokument do Google Drive
  - udělat/připravit/sepsat dokument (pokud není specifikován jiný formát jako .docx nebo PDF)
  - vytvořit SEO brief, audit, analýzu, report nebo jiný strukturovaný dokument
  - upravit formátování existujícího Google dokumentu / aplikovat styly na existující doc
  - přeformátovat dokument, opravit styly, přidat nadpisy nebo odrážky do existujícího dokumentu
  Skill se postará o výběr složky, zkopírování šablony stylů, vložení obsahu a přesunutí do správné složky.
---

# Google Docs Skill

Vytváří Google Dokumenty přes `gws` CLI se správným firemním formátováním.

## Prerekvizity

- `gws` CLI musí být přihlášeno (`gws auth login`)
- Šablona stylů existuje na Drive (ID: `1yBKmQKVaX738JwDQ1IDGnPHEyETUIZJrjuxxOKxEyTc`)

## Postup

### 1. Zjisti název a obsah

Pokud uživatel nespecifikoval název nebo obsah dokumentu, zeptej se. Obsah může být:
- Konkrétní text (uživatel ho diktuje)
- Osnova/struktura (vygeneruj obsah sám)
- Prázdný dokument (jen vytvořit se správnými styly)

### 2. Zjisti cílovou složku

Nabídni uživateli výběr složky. Nejdřív zobraz složky v rootu:

```bash
gws drive files list --params '{
  "q": "mimeType = \"application/vnd.google-apps.folder\" and \"root\" in parents and trashed = false",
  "fields": "files(id,name)",
  "pageSize": 50
}'
```

Pokud uživatel chce složku v podsložce nebo zná název, prohledej:

```bash
gws drive files list --params '{
  "q": "mimeType = \"application/vnd.google-apps.folder\" and name contains \"NÁZEV\" and trashed = false",
  "fields": "files(id,name,parents)"
}'
```

Pokud uživatel chce nechat dokument v rootu, přesun ho přeskoč.

### 3. Zkopíruj šablonu stylů

Kopírování zachová named styles (Proxima Nova, zelená H2, atd.) — to je klíčové.

```bash
gws drive files copy \
  --params '{"fileId": "1yBKmQKVaX738JwDQ1IDGnPHEyETUIZJrjuxxOKxEyTc"}' \
  --json '{"name": "NÁZEV DOKUMENTU"}'
```

Ulož `id` nového dokumentu jako `DOC_ID`.

### 4. Smaž obsah šablony

```bash
# Nejdřív zjisti délku dokumentu
gws docs documents get --params '{"documentId": "DOC_ID"}' > /tmp/doc.json

# Zjisti endIndex (poslední element v body.content)
END_INDEX=$(python3 -c "
import json
d = json.load(open('/tmp/doc.json'))
content = d['body']['content']
print(content[-1]['endIndex'])
")

# Smaž obsah (ponech poslední \n)
gws docs documents batchUpdate \
  --params '{"documentId": "DOC_ID"}' \
  --json "{\"requests\": [{\"deleteContentRange\": {\"range\": {\"startIndex\": 1, \"endIndex\": $((END_INDEX - 1))}}}]}"
```

### 5. Vlož obsah

Používej Python skript pro správné výpočty indexů:

```bash
python3 /Users/adam/Documents/AI/Skills/google-docs/scripts/insert_content.py \
  --doc-id "DOC_ID" \
  --content '[
    {"style": "TITLE", "text": "Název dokumentu"},
    {"style": "SUBTITLE", "text": "Podtitulek nebo popis"},
    {"style": "HEADING_1", "text": "Hlavní sekce"},
    {"style": "NORMAL_TEXT", "text": "Obsah odstavce..."},
    {"style": "HEADING_2", "text": "Podsekce"},
    {"style": "NORMAL_TEXT", "text": "Další text..."},
    {"style": "LIST_BULLET", "text": "První odrážka"},
    {"style": "LIST_BULLET", "text": "Druhá odrážka"},
    {"style": "LIST_NUMBERED", "text": "První bod číslovaného seznamu"},
    {"style": "LIST_NUMBERED", "text": "Druhý bod číslovaného seznamu"}
  ]'
```

**Dostupné styly včetně listů:**
- `TITLE`, `SUBTITLE`, `HEADING_1`–`HEADING_6`, `NORMAL_TEXT` — viz Named styles níže
- `LIST_BULLET` — odrážkový seznam (•)
- `LIST_NUMBERED` — číslovaný seznam (1. 2. 3.)

Skript přijímá i volitelné pole `bold_parts` a `links` pro inline formátování (viz sekci níže).

### 6. Přesuň do složky

```bash
gws drive files update \
  --params '{"fileId": "DOC_ID", "addParents": "FOLDER_ID", "removeParents": "root"}' \
  --json '{}'
```

### 7. Vrať odkaz

Vždy vrať přímý odkaz na dokument:
```
https://docs.google.com/document/d/DOC_ID/edit
```

---

## Named styles (šablona stylů)

| Style type | Vzhled |
|------------|--------|
| `TITLE` | Proxima Nova, 36pt, tmavá `#353744` |
| `SUBTITLE` | 13pt, šedá `#666666` |
| `HEADING_1` | Proxima Nova, 14pt, tučné, tmavá `#353744`, mezera nahoře 24pt |
| `HEADING_2` | 14pt, tučné, zelená `#00AB44`, mezera nahoře 16pt |
| `HEADING_3` | 13pt, lineSpacing 100% |
| `HEADING_4` / `HEADING_5` / `HEADING_6` | Trebuchet MS, 11pt, šedá `#666666` |
| `NORMAL_TEXT` | Proxima Nova, 11pt, tmavá, lineSpacing 130%, spaceAbove 10pt |

---

## Listy (odrážky a číslování)

Skript `insert_content.py` podporuje dva typy listů přes speciální hodnoty `style`:

| Style | Typ | Vzhled |
|-------|-----|--------|
| `LIST_BULLET` | Odrážkový | • položka |
| `LIST_NUMBERED` | Číslovaný | 1. položka |

Každá položka seznamu = jeden dict s `"style": "LIST_BULLET"` nebo `"LIST_NUMBERED"` a `"text"`. Skript automaticky vloží text jako `NORMAL_TEXT` a pak aplikuje `createParagraphBullets` s příslušným glyphem.

```bash
python3 /Users/adam/Documents/AI/Skills/google-docs/scripts/insert_content.py \
  --doc-id "DOC_ID" \
  --content '[
    {"style": "HEADING_2", "text": "Výhody"},
    {"style": "LIST_BULLET", "text": "Rychlé zpracování"},
    {"style": "LIST_BULLET", "text": "Snadná integrace"},
    {"style": "LIST_BULLET", "text": "Nízké náklady"},
    {"style": "HEADING_2", "text": "Kroky implementace"},
    {"style": "LIST_NUMBERED", "text": "Nainstaluj závislosti"},
    {"style": "LIST_NUMBERED", "text": "Nakonfiguruj prostředí"},
    {"style": "LIST_NUMBERED", "text": "Spusť testy"}
  ]'
```

Pokud potřebuješ list vytvořit přímo přes `gws` (bez skriptu):
```bash
# Nejdřív vlož text jako NORMAL_TEXT, pak aplikuj bullet
gws docs documents batchUpdate \
  --params '{"documentId": "DOC_ID"}' \
  --json '{"requests": [
    {"createParagraphBullets": {
      "range": {"startIndex": START, "endIndex": END},
      "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE"
    }}
  ]}'
# Pro číslovaný seznam: "NUMBERED_DECIMAL_ALPHA_ROMAN"
```

---

## Úprava formátování existujícího dokumentu

Použij tento postup, když uživatel chce přeformátovat nebo opravit styly v existujícím dokumentu — **bez mazání obsahu**.

### 1. Načti strukturu dokumentu

```bash
gws docs documents get --params '{"documentId": "DOC_ID"}' > /tmp/doc.json
```

### 2. Analyzuj odstavce

```python
import json

d = json.load(open('/tmp/doc.json'))
for el in d['body']['content']:
    if 'paragraph' in el:
        start = el['startIndex']
        end = el['endIndex']
        text = ''.join(
            r.get('textRun', {}).get('content', '')
            for r in el['paragraph'].get('elements', [])
        ).strip()
        current_style = el['paragraph'].get('paragraphStyle', {}).get('namedStyleType', '?')
        print(f"[{start}-{end}] {current_style}: {text[:60]}")
```

### 3. Aplikuj nové styly

Vytvoř seznam `updateParagraphStyle` requestů pro odstavce, které chceš přeformátovat:

```bash
gws docs documents batchUpdate \
  --params '{"documentId": "DOC_ID"}' \
  --json '{"requests": [
    {
      "updateParagraphStyle": {
        "range": {"startIndex": 1, "endIndex": 25},
        "paragraphStyle": {"namedStyleType": "HEADING_1"},
        "fields": "namedStyleType"
      }
    },
    {
      "updateParagraphStyle": {
        "range": {"startIndex": 25, "endIndex": 80},
        "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
        "fields": "namedStyleType"
      }
    }
  ]}'
```

### Tipy pro úpravu existujícího dokumentu

- **Named styles zdědíš kopírováním šablony** — pokud dokument nemá správné styly (špatné fonty, barvy), nestačí jen změnit `namedStyleType`. Musíš přesunout obsah do nové kopie šablony (kroky 3–5 hlavního postupu). Pokud ale dokument už byl vytvořen ze šablony, `updateParagraphStyle` stačí.
- **Nemazej obsah** — `updateParagraphStyle` mění jen styl odstavce, text zůstává beze změny.
- **Hromadná úprava** — pokud chceš přeformátovat celý dokument, iteruj přes `body.content` a vytvoř batch requestů pro všechny odstavce najednou. Jeden `batchUpdate` s mnoha requesty je mnohem rychlejší než volat API opakovaně.
- **Bold/italic inline** — pro inline formátování použij `updateTextStyle` s `fields: "bold"` nebo `"italic"`.

---

## Chybové scénáře

**`gws` není přihlášeno:**
```bash
gws auth login  # provede OAuth flow v prohlížeči
```

**Docs API není povolené:**
Uživatel musí zapnout Google Docs API na: https://console.developers.google.com/apis/api/docs.googleapis.com/overview?project=287944530746

**Drive API není povolené:**
https://console.developers.google.com/apis/api/drive.googleapis.com/overview?project=287944530746

**Šablona nedostupná:**
Pokud šablona (ID `1yBKmQKVaX738JwDQ1IDGnPHEyETUIZJrjuxxOKxEyTc`) není přístupná, vytvoř dokument bez šablony:
```bash
gws docs documents create --json '{"title": "NÁZEV"}'
```
V tom případě budou styly výchozí Google styly (bez Proxima Nova).
