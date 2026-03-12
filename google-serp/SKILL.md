---
name: google-serp
description: Scrape Google Search results using local Playwright (headless Chromium). Returns organic results, People Also Ask, and Related Searches as formatted tables and CSV files. Use when the user asks to scrape Google, get SERP results, check rankings, or analyze search results for any keyword.
---

# Google SERP Scraper

Two modes of operation:
1. **n8n workflow (preferred for batch)** — queues keywords into PostgreSQL (`seo_kws.tasks`), SearxNG scrapes asynchronously and saves directly to the client's schema (e.g. `client_slug.serp`).
2. **Direct SearxNG via SSH (fallback)** — synchronous, no queue, no DB storage

---

## Mode 1: n8n Workflow (Batch Scraping)

Workflows are on Hetzner n8n at `https://s.smuz.cz` (tag: **SERP**).
Workflow JSONs are stored in `workflows/` (relative to this skill).

### Step 1 — Ingest keywords (create job)

```bash
curl -s -X POST "https://s.smuz.cz/webhook/wGSmmWIGdUcnf2i4/webhook/serp/ingest" \
  -H "Content-Type: application/json" \
  -d '{
    "client": "my_project",
    "client_name": "My Project Name",
    "job_name": "SERP 2026-03-07",
    "keywords": ["ivf klinika", "umělé oplodnění", "fertilita"],
    "lang": "cs",
    "country": "cz",
    "num": 10
  }'
```

**Response:** `{ "job_id": 5, "task_count": 3, "client_id": 1, "status": "queued" }`

**Parameters:**

| Field | Default | Description |
|-------|---------|-------------|
| `client` | required | Client slug (alphanumeric) |
| `client_name` | = client | Human-readable client name |
| `job_name` | "SERP YYYY-MM-DD" | Job label |
| `keywords` | required | Array of keywords to scrape |
| `lang` | `cs` | Language code |
| `country` | `cz` | Country / Google TLD |
| `num` | `10` | Results per keyword (max 10) |

### Step 2 — Monitor progress

```bash
curl -s "https://s.smuz.cz/webhook/riBJdxE0JMR49vFM/webhook/serp/status?job_id=5"
```

**Response fields:** `id`, `name`, `status` (pending/running/completed/failed), `total_keywords`, `completed_keywords`, `failed_keywords`, `progress_pct`, `pending`, `running`, `completed`, `failed`

Poll every 30–60 seconds until `status == "completed"`.

### Step 3 — Query results from PostgreSQL

Connect via SSH to Hetzner:
```bash
ssh hetzner-n8n "docker exec n8n-stack-postgres-1 psql -U n8n -d seo -c \"<SQL>\""
```

**Database:** `seo` on `78.46.190.162:5432`, schema `seo_kws`

#### Organic results
```sql
SELECT keyword, position, title, url, description, engine, scraped_at
FROM seo_kws.serp_organic
WHERE job_id = 5
ORDER BY keyword, position;
```

#### People Also Ask
```sql
SELECT keyword, position, question, engine
FROM seo_kws.serp_paa
WHERE job_id = 5
ORDER BY keyword, position;
```

#### Related Searches
```sql
SELECT keyword, position, query, engine
FROM seo_kws.serp_related
WHERE job_id = 5
ORDER BY keyword, position;
```

#### Job overview (all jobs)
```sql
SELECT j.id, j.name, j.status, j.lang, j.country,
       j.total_keywords, j.completed_keywords, j.failed_keywords,
       c.slug as client, j.created_at::date
FROM seo_kws.jobs j
JOIN seo_kws.clients c ON c.id = j.client_id
ORDER BY j.id DESC
LIMIT 20;
```

#### Final Results in Client Schema
```sql
-- Client schemas and tables are automatically created by the worker, e.g. "pronatal", "my_project"
SELECT keyword, position, title, url, description, language, country, imported_at
FROM "my_project".serp
ORDER BY keyword, position;

-- PAA results
SELECT seed_keyword, question, position FROM "my_project".people_also_ask;

-- Related searches
SELECT seed_keyword, related_query, position FROM "my_project".related_queries;
```

#### Task-level detail (errors)
```sql
SELECT keyword, status, attempts, last_error, scraped_at
FROM seo_kws.tasks
WHERE job_id = 5
ORDER BY keyword;
```

#### Top results across a job
```sql
SELECT keyword, position, title, url
FROM seo_kws.serp_organic
WHERE job_id = 5 AND position <= 3
ORDER BY keyword, position;
```

### Database schema

```
seo_kws.clients     — id, slug, name
seo_kws.jobs        — id, client_id, name, lang, country, num_results,
                       total_keywords, completed_keywords, failed_keywords,
                       status, created_at, started_at, completed_at
seo_kws.tasks       — id, job_id, keyword, status, scraped_at, last_error, attempts
seo_kws.serp_organic — task_id, job_id, client_id, keyword, position, title,
                        description, url, engine, scraped_at
seo_kws.serp_paa    — task_id, job_id, client_id, keyword, position,
                        question, engine, scraped_at
seo_kws.serp_related — task_id, job_id, client_id, keyword, position,
                         query, engine, scraped_at
```

### Notes on SERP Worker
- Runs automatically every 30 seconds, processes one task per cycle
- Engine fallback is **per-attempt**: attempt 1 → google, 2 → bing, 3 → duckduckgo, 4 → brave
- Each attempt calls SearxNG via a dedicated HTTP Request node (not Code node — `$helpers` unavailable in n8n sandbox)
- Language is auto-formatted: `lang=cs` + `country=cz` → `cs-CZ` (required for correct Bing/Google locale)
- If all engines fail (CAPTCHA/blocked): task retries up to 3×, then marks `failed`
- PAA (`serp_paa`) is not populated — SearxNG standard JSON response does not extract People Also Ask boxes

---

## Mode 2: Direct SearxNG (Fallback)

Bypasses n8n queue — synchronous single query, results not stored in DB.
SearxNG runs in Docker on Hetzner (`172.18.0.10:8080`, internal network only).

### CLI — single keyword

```bash
ssh hetzner-n8n \
  "docker exec searxng wget -qO- \
  'http://localhost:8080/search?q=ivf+klinika&format=json&engines=google,bing&language=cs-CZ&safesearch=0'" \
  | python3 -m json.tool
```

### Python — parse organic results

```python
import subprocess, json, urllib.parse

def searxng_search(keyword, lang="cs-CZ", engines="google,bing,duckduckgo", num=10):
    """Query SearxNG directly via SSH — fast, synchronous, no DB."""
    q = urllib.parse.quote(keyword)
    cmd = (
        f"docker exec searxng wget -qO- "
        f"'http://localhost:8080/search?q={q}&format=json"
        f"&engines={engines}&language={lang}&safesearch=0'"
    )
    result = subprocess.run(
        ["ssh", "hetzner-n8n", cmd],
        capture_output=True, text=True, timeout=30
    )
    data = json.loads(result.stdout)
    return {
        "organic": data.get("results", [])[:num],
        "suggestions": data.get("suggestions", []),
        "answers": data.get("answers", []),
        "unresponsive": data.get("unresponsive_engines", []),
    }

# Usage
data = searxng_search("ivf klinika")
for r in data["organic"]:
    print(f"[{r['positions'][0]}] {r['title']}")
    print(f"    {r['url']}")
    print(f"    {r.get('content','')[:120]}")
```

### SearxNG response fields

| Field | Description |
|-------|-------------|
| `results[].url` | Result URL |
| `results[].title` | Page title |
| `results[].content` | Snippet / description |
| `results[].engine` | Which engine returned it |
| `results[].positions` | List of positions (can appear in multiple engines) |
| `results[].score` | Relevance score (1.0 = top) |
| `suggestions` | Related search suggestions |
| `answers` | Direct answer boxes |
| `unresponsive_engines` | Engines that failed (CAPTCHA / empty) |

### SSH tunnel (for local access)

```bash
# Expose SearxNG locally on port 8080 (run once, in background)
ssh -L 8080:172.18.0.10:8080 hetzner-n8n -f -N

# Then query from localhost
curl -s "http://localhost:8080/search?q=ivf+klinika&format=json&engines=google,bing&language=cs-CZ&safesearch=0"
```

---

## Credentials

- **n8n API token**: `/Users/adam/Documents/credentials/api/N8N-API`
- **Hetzner SSH**: `ssh hetzner-n8n` (alias in `~/.ssh/config`)
- **PostgreSQL**: host `78.46.190.162`, port `5432`, user `n8n`, db `seo`, schema `seo_kws`
- **n8n UI**: `https://s.smuz.cz` (workflows tagged **SERP**)
- **SearxNG**: internal Docker `172.18.0.10:8080` (access via SSH)

## Workflow files

| File | Purpose |
|------|---------|
| `workflows/serp_ingest.json` | POST webhook — creates job + tasks |
| `workflows/serp_worker.json` | Scheduled (30s) — processes tasks via SearxNG |
| `workflows/serp_status.json` | GET webhook — returns job progress |
| `workflows/google_autocomplete.json` | Sub-workflow for Google Autocomplete |
| `workflows/google_serp_old.json` | Legacy Google SERP workflow (not active) |
