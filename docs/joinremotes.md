# ScrapAI Integration Guide for joinremotes.com

This document is for the AI agent and developers working on the joinremotes.com project. It explains how to set up and use the ScrapAI API to scrape job listings from joinremotes.com and keep them in sync.

For coverage tracking and next steps, also see:

- [`FEATURES.md`](FEATURES.md) — what ScrapAI already covers vs. what remains
- [`JOURNEYS.md`](JOURNEYS.md) — journey-by-journey cross-check matrix for joinremotes.com

---

## What is ScrapAI?

ScrapAI is a web scraping service that runs spiders, stores results in a database, and exposes them via a REST API. It handles the crawling infrastructure — you just trigger crawls and fetch results.

---

## Consumer Contract (joinremotes-side expectations)

joinremotes' sync (`lib/scrapai/sync.ts`) reads each scraped result and upserts a Job + Company. To be consumable, every scraped item must satisfy:

**1. URL pattern.** Any URL is fine — joinremotes uses it as the dedup key (composite unique on `(sourceSpider, sourceUrl)` in JR's `Job` table) but doesn't impose any shape on it. Spiders yield their native source URLs untouched.

> Slugs on the joinremotes side are derived from job content (title + company), not from the source URL. So Workday's `/careers/job/12345/` becomes a slug like `senior-engineer-acme` after sync — same for Greenhouse, Personio, etc.

**2. `metadata` fields** (in the `metadata` JSON object on each result):

| Field | Type | Notes |
|-------|------|-------|
| `job_title` | string | Falls back to `result.title` (with " at <company>" stripped) if missing |
| `company` | string | Case-insensitive name match; stub Company created if not found |
| `location` | string | |
| `salary` | string | Free-form; joinremotes parses `$`, `€`, `£`, `k` suffix, ranges |
| `description` | string | HTML or plain text |
| `tags` | string[] | Lowercased + trimmed before storage |
| `posted_date` | string | ISO date; falls back to `scraped_at` if missing |

**3. Callback name.** Use `parse_job` (the canonical name). joinremotes does **not** reserve `parse_job` — it round-trips unchanged. The names joinremotes does rename (because they collide with Scrapy internals or article extractor): `closed`, `from_crawler`, `parse`, `parse_article`, `parse_start_url`, `start_requests`. Keep this list in sync with `CLAUDE.md`.

---

## One-Time Setup (do this once)

### 1. Build the spider

The `joinremotes_com` spider must be created before the API can be used. An operator needs to run the ScrapAI CLI to analyze joinremotes.com and generate the spider config.

On the ScrapAI server:

```bash
# Phase 1: inspect homepage and document site structure
scrapai inspect https://joinremotes.com/ --project joinremotes
scrapai extract-urls --file data/joinremotes/joinremotes_com/analysis/page.html \
  --output data/joinremotes/joinremotes_com/analysis/all_urls.txt
# → write sections.md documenting URL patterns for each section

# Phase 2: inspect a sample job page and discover CSS selectors
scrapai inspect https://joinremotes.com/jobs/EXAMPLE-JOB --project joinremotes --browser
scrapai analyze data/joinremotes/joinremotes_com/analysis/page.html
# → write final_spider.json with rules + callbacks for: job_title, company,
#   location, salary, description, tags, posted_date

# Phase 3: create test_spider.json (5 URLs, follow: false) and final_spider.json

# Phase 4: test, verify, then import
scrapai spiders import test_spider.json --project joinremotes
scrapai crawl joinremotes_com --limit 5 --project joinremotes
scrapai show joinremotes_com --limit 5 --project joinremotes
# if output looks good:
scrapai spiders import final_spider.json --project joinremotes
```

Spider name: **`joinremotes_com`** (must match this exactly — domain with dots as underscores).

### 2. Create an API key

```bash
scrapai apikey create joinremotes-app --project joinremotes
# → outputs: sk_xxxxxxxxxxxxxxxxxxxx
```

Store this key securely — it cannot be retrieved again.

---

## Environment Variables (joinremotes.com)

Add these to your `.env` / secrets manager:

```bash
SCRAPAI_API_URL=https://your-scrapai-server   # Base URL only — joinremotes' client appends /api/v1
SCRAPAI_API_KEY=sk_xxxxxxxxxxxxxxxxxxxx
SCRAPAI_PROJECT=joinremotes
SCRAPAI_SPIDER=joinremotes_com
SCRAPAI_WEBHOOK_SECRET=your-webhook-secret  # only if using webhooks
```

---

## Integration Flow

```
┌─────────────────────────────────────────────────────┐
│  Trigger (cron / manual)                            │
│    POST /crawls                                     │
│         │                                           │
│         ▼                                           │
│  Wait for completion                                │
│    Option A: Subscribe to SSE stream                │
│    Option B: Poll GET /crawls/{id}                  │
│    Option C: Receive webhook callback               │
│         │                                           │
│         ▼                                           │
│  Fetch new results                                  │
│    GET /results?project=joinremotes&...             │
│         │                                           │
│         ▼                                           │
│  Upsert into joinremotes.com database               │
└─────────────────────────────────────────────────────┘
```

---

## API Reference

All requests require:
```
Authorization: Bearer sk_YOUR_API_KEY
Content-Type: application/json
```

### Trigger a crawl

```
POST /crawls
```

Request body:
```json
{
  "spider_name": "joinremotes_com",
  "project": "joinremotes",
  "requested_limit": 500
}
```

Response:
```json
{
  "id": 42,
  "spider_name": "joinremotes_com",
  "project": "joinremotes",
  "status": "queued",
  "items_scraped": 0,
  "created_at": "2026-03-29T10:00:00Z"
}
```

Returns `409 Conflict` if a crawl is already running for this spider.

---

### Check crawl status (polling)

```
GET /crawls/{crawl_run_id}
```

Poll until `status` is one of: `completed`, `failed`, `cancelled`.

---

### Stream crawl progress (SSE — recommended)

```
GET /crawls/{crawl_run_id}/stream
Accept: text/event-stream
```

Example with `EventSource`:
```js
const es = new EventSource(
  `${SCRAPAI_API_URL}/crawls/${crawlRunId}/stream`,
  { headers: { Authorization: `Bearer ${SCRAPAI_API_KEY}` } }
)

es.addEventListener('crawl:progress', (e) => {
  const data = JSON.parse(e.data)
  console.log(`Items scraped: ${data.items_scraped}`)
})

es.addEventListener('crawl:completed', (e) => {
  es.close()
  syncResults()
})

es.addEventListener('crawl:failed', (e) => {
  es.close()
  const data = JSON.parse(e.data)
  console.error('Crawl failed:', data.error_message)
})
```

Events: `crawl:init`, `crawl:progress`, `crawl:completed`, `crawl:failed`, `crawl:cancelled`, `crawl:timeout`

---

### List crawl runs

```
GET /crawls?project=joinremotes&spider_name=joinremotes_com&limit=20
```

---

### Cancel a crawl

```
POST /crawls/{crawl_run_id}/cancel
```

---

### Fetch scraped results

```
GET /results?project=joinremotes&spider_name=joinremotes_com&limit=50&offset=0
```

Response:
```json
{
  "items": [
    {
      "id": 1,
      "url": "https://joinremotes.com/jobs/senior-engineer-at-acme",
      "title": "Senior Engineer at Acme",
      "scraped_at": "2026-03-29T10:15:00Z",
      "metadata": {
        "company": "Acme Corp",
        "location": "Remote",
        "salary": "$120k–$160k",
        "tags": ["Python", "AWS"],
        "posted_date": "2026-03-28"
      }
    }
  ],
  "total_count": 450,
  "has_next": true
}
```

Custom spider fields (company, salary, location, tags, etc.) are in the `metadata` object.

---

### Get a result by URL

```
GET /results/by-url/?url=https://joinremotes.com/jobs/xyz&project=joinremotes
```

Useful for checking if a specific listing was already scraped.

---

### Register a webhook (recommended for production)

Register once so joinremotes.com is notified automatically when crawls finish:

```
POST /webhooks
```

Request body:
```json
{
  "project": "joinremotes",
  "target_url": "https://joinremotes.com/api/admin/scrapai/webhook",
  "event_types": ["crawl.completed", "crawl.failed"],
  "secret": "auto"
}
```

The response includes a `secret` — save it as `SCRAPAI_WEBHOOK_SECRET`. It is never returned again.

---

## Webhook Endpoint (implement in joinremotes.com)

Your app needs to expose a POST endpoint that ScrapAI will call:

```
POST /api/admin/scrapai/webhook
```

> The `/admin/` segment is a URL-organisation choice on the joinremotes side — the route is **public, HMAC-authenticated**, no admin session required.

Verify the signature:
```python
import hmac, hashlib

def verify_webhook(body: bytes, signature: str, secret: str) -> bool:
    # Strip the optional "sha256=" prefix that ScrapAI sends
    provided = signature.removeprefix("sha256=")
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, provided)

# In your handler:
sig = request.headers.get("X-Webhook-Signature")
if not verify_webhook(request.body, sig, SCRAPAI_WEBHOOK_SECRET):
    return 401

payload = request.json()
if payload["event_type"] == "crawl.completed":
    sync_jobs_from_scrapai()
```

Webhook payload:
```json
{
  "event_type": "crawl.completed",
  "timestamp": "2026-03-29T10:20:00Z",
  "data": {
    "crawl_run_id": 42,
    "spider_name": "joinremotes_com",
    "project": "joinremotes",
    "items_scraped": 450,
    "duration_seconds": 320
  }
}
```

Headers sent by ScrapAI:
- `X-Webhook-Signature` — `sha256=<hex>` where `<hex>` is HMAC-SHA256 of the **raw request body** (the bytes on the wire, not a re-serialised payload)
- `X-Webhook-Timestamp` — Unix timestamp
- `X-Webhook-Event` — event type string

joinremotes accepts both `sha256=<hex>` and bare-hex forms (the prefix is stripped before comparison).

---

## Full Endpoint Reference

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `POST` | `/crawls` | Trigger a new crawl |
| `GET` | `/crawls` | List crawl runs |
| `GET` | `/crawls/{id}` | Get crawl status |
| `POST` | `/crawls/{id}/cancel` | Cancel a crawl |
| `GET` | `/crawls/{id}/stream` | Stream progress (SSE) |
| `GET` | `/results` | List scraped items (paginated) |
| `GET` | `/results/{id}` | Get a single item |
| `GET` | `/results/by-url/` | Get item by URL |
| `GET` | `/spiders` | List spiders |
| `GET` | `/spiders/by-name/{project}/{name}` | Get spider by name |
| `POST` | `/spiders` | Create or update spider |
| `PUT` | `/spiders/{id}` | Update spider |
| `DELETE` | `/spiders/{id}` | Soft-delete spider |
| `POST` | `/webhooks` | Register webhook |
| `GET` | `/webhooks` | List webhooks |
| `DELETE` | `/webhooks/{id}` | Delete webhook |

---

## Error Codes

| Status | Meaning |
|--------|---------|
| `400` | Bad request / validation error |
| `401` | Missing or invalid API key |
| `403` | API key doesn't have access to this project |
| `404` | Resource not found |
| `409` | Crawl already running for this spider |
| `429` | Rate limit exceeded (10 req / 60s per key) |
| `500` | Server error |

---

## Worked Example: TomTom Careers

When the joinremotes admin pastes `https://www.tomtom.com/careers/joboverview/` into the admin UI, the analyze endpoint should produce a config like:

```json
{
  "name": "tomtom_com",
  "allowed_domains": ["tomtom.com"],
  "start_urls": ["https://www.tomtom.com/careers/joboverview/"],
  "settings": {
    "BROWSER_ENABLED": true,
    "EXTRACTOR_ORDER": ["custom"]
  },
  "rules": [
    { "allow": ["/careers/job/.*"], "callback": "parse_job", "follow": true },
    { "allow": ["/careers/joboverview"], "callback": "parse_listing", "follow": true }
  ],
  "callbacks": {
    "parse_job": {
      "extract": {
        "job_title":   { "css": "h1::text", "processors": [{ "type": "strip" }] },
        "company":     { "default": "TomTom" },
        "location":    { "css": "[data-field='location']::text" },
        "salary":      { "css": "[data-field='salary']::text" },
        "description": { "css": "section.job-description", "get_all": true,
                         "processors": [{ "type": "join", "sep": "\n" }] },
        "tags":        { "css": "ul.skills li::text", "get_all": true },
        "posted_date": { "css": "time::attr(datetime)" }
      }
    }
  }
}
```

The spider yields each job with `url = "https://www.tomtom.com/careers/job/<id>/"` — joinremotes accepts that URL as-is, uses it as the `(sourceSpider, sourceUrl)` dedup key, and generates a content-derived slug like `senior-engineer-tomtom` from the job title + company name. No URL rewriting needed.

---

## Infrastructure Requirements (ScrapAI server)

For the API to function the ScrapAI server must have:
- Redis running (SSE streaming, rate limiting, job queue)
- Dramatiq workers running:
  ```bash
  dramatiq apps.web_api.workers.crawl_worker
  dramatiq apps.web_api.workers.webhook_worker
  ```
- `joinremotes_com` spider imported in the database
- API key created for the `joinremotes` project
