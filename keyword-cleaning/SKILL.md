---
name: keyword-cleaning
description: Sémantické čištění klíčových slov pomocí modelu umělé inteligence (Sentence Transformers). Porovnává hledaná slova vůči Seed Listu z databáze a vyřazuje nerelevantní výsledky (např. z našeptávače) na základě kalibrovatelné prahové hodnoty (Threshold).
---

# Keyword Cleaning (Sémantické čištění)

Při sběru dat z našeptávačů (Autocomplete) a z Related Queries vznikají stovky tisíc klíčových slov. Mnoho z nich může "ujet" od vašeho hlavního tématu (např. od *cyklistika* k *motocyklům* atd.). 

Tento skill slouží k **vyčištění tabulek před konečným klustrováním**, a to automatizovaně pomocí NLP modelu `paraphrase-multilingual-MiniLM-L12-v2` (špička pro češtinu).

---

## Pořadí kroků čistění (Keyword Analysis Workflow)

Tento skill je **Fáze H** v `keywords-analysis` workflow. Vždy provádět ve správném pořadí:

### H1. Nejdřív odstraň nulovou hledanost (SQL — rychlé)

Než spustíš model, odstraň KWs bez dat — ušetří výpočetní čas:

```sql
-- Označ KWs s nulovou hledaností jako nerelevantní
UPDATE {schema}.suggestions s
SET is_relevant = false
FROM {schema}.keyword_planner kp
WHERE LOWER(s.suggestion) = LOWER(kp.keyword)
  AND (kp.avg_monthly_searches IS NULL OR kp.avg_monthly_searches = 0);

-- Totéž pro related_queries
UPDATE {schema}.related_queries r
SET is_relevant = false
FROM {schema}.keyword_planner kp
WHERE LOWER(r.related_query) = LOWER(kp.keyword)
  AND (kp.avg_monthly_searches IS NULL OR kp.avg_monthly_searches = 0);

-- Kontrola kolik KWs zbývá ke zpracování modelem
SELECT COUNT(*) FROM {schema}.suggestions WHERE is_relevant IS NULL OR is_relevant = true;
```

### H2. Pak teprve sémantické čistění (model — pomalé)

Spusť model jen na KWs, která prošla H1 (není označena jako `is_relevant = false`).

---

## ⭐️ Zlatý standard Seed Listu

Algoritmus bere tabulku `seed_keywords` jako absolutní pravdu a středobod vašeho sémantického vesmíru.

1. **Velikost a granularita:** Zaměřte se na 50 až 100 frází.
2. **Zastoupení všech pilířů:** Pokud je web o cyklistice, Seed List nesmí obsahovat jen "jízdní kola". Musí pokrýt všechny vertikály: "cyklistické helmy", "náhradní díly na kolo", "servis kol", "výživa pro cyklisty".
3. **Vyhněte se příliš obecným pojmům:** Nepřidávejte slova jako "sport", "příroda" nebo "vybavení". Model by pak jako relevantní označil i "vybavení na hokej".

---

## Jak to funguje

Model matematicky převede slova na vektory (čísla) a vypočítá tzv. **kosínovou podobnost (Cosine Similarity)** mezi zkoumaným slovem a *všemi* slovy vašeho Seed Listu. Vybere se jen to **nejvyšší skóre** (pokud je slovo podobné alespoň jednomu semínku, je relevantní). Toto skóre (0.0 až 1.0) se uloží do sloupce `relevance_score` ve vaší databázi. 

Následně se na základě vámi zvolené hranice (Threshold, např. 0.28) nastaví sloupec `is_relevant = false` slovům, která už do tématu nepatří.

---

## Varianta A: Interaktivně v Google Colab (Doporučeno)

Skript je velmi náročný na paměť a výpočty, proto je ideální ho pouštět v Google Colab na T4 GPU. Umožní vám navíc snadno najít ideální práh (threshold) přímo v grafech a tabulkách.

1. Otevřete notebook z podsložky `notebooks/semantic_cleaning_colab.ipynb` ve vašem Google Colabu.
2. Vyplňte přístupové údaje do PostgreSQL (Hetzner), klienta (schéma) a tabulku k čištění (`suggestions` nebo `related_queries`).
3. Spusťte první polovinu notebooku a prohlédněte si distribuci skóre (histogram) a vzorky kolem hranic 0.6, 0.4, 0.3 a 0.25.
4. Najděte "bod zlomu", kde přestávají dávat slova byznysový smysl, a doplňte toto číslo do poslední buňky k uříznutí.

---

## Varianta B: Lokální CLI skript

Pro lokální běh (pokud máte Apple Silicon / výkonné CPU).

### 1. Průzkum a výpočet (Analyze Only)

Spočítá `relevance_score`, uloží do DB a vypíše na obrazovku vzorky na různých hranicích. Tento krok data **nemaže/nezneplatňuje**.

```bash
python3 scripts/semantic_cleaner.py --schema pronatal --table suggestions --analyze-only
```

### 2. Aplikace "Řezu" (Thresholding)

Jakmile zjistíte (z výstupu z bodu 1), na jaké hranici se už míchá odpad (např. 0.28), spusťte:

```bash
python3 scripts/semantic_cleaner.py --schema pronatal --table suggestions --apply-threshold 0.28
```
Tím se uškrtne vše pod touto hranicí a nastaví se tomu `is_relevant = false`.

---

Kategorizace a klustrování ze skillu `keyword-categorization` umí nadále načítat a brát v potaz jen slova, kde `is_relevant = true`.
