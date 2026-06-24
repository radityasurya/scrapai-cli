# ScrapAI Journeys and Cross-Check Matrix

Last updated: 2026-06-24

This document lists the intended journeys for ScrapAI, what each journey needs, what is already covered, and what remains to cross-check — with special focus on **joinremotes.com** as the first downstream client.

Status legend: ✅ covered, 🟡 partial, ❌ missing, ⏸️ deferred.

## Journey summary

Visual reference: [`joinremotes-scrapai-flow.html`](joinremotes-scrapai-flow.html) shows the layman product flow for the JoinRemotes Admin scraper UI.

| # | Journey | Primary actor | Status | Why it matters |
| --- | --- | --- | --- | --- |
| 1 | Operator sets up ScrapAI locally/private server | ScrapAI operator | 🟡 Partial | joinremotes needs a reachable API + worker stack before client sync can run. |
| 2 | Admin analyzes a job-board URL | joinremotes admin / AI agent | ✅ Covered | Admin enters a company careers/job-board URL and gets a draft scrape structure/spider config. |
| 3 | Admin tests selectors and spider output | joinremotes admin / AI agent | ✅ Covered | Prevents broken sources before they enter production sync. |
| 4 | Admin creates or updates a source spider | joinremotes admin | ✅ Covered | Persists a reusable scraper for each job source. |
| 5 | Admin triggers a crawl | joinremotes admin / cron | ✅ Covered | Produces fresh job listings on demand or on schedule. |
| 6 | Client observes crawl progress | joinremotes app | 🟡 Partial | Polling is straightforward; SSE needs client wrapper/proxy because of auth headers. |
| 7 | Client syncs crawl results into joinremotes jobs | joinremotes app | 🟡 Partial | API contract exists; needs live end-to-end verification. |
| 8 | ScrapAI notifies joinremotes by webhook | ScrapAI worker -> joinremotes app | ✅ Covered | Completed/failed terminal events now queue signed webhooks; live delivery still belongs in the E2E smoke test. |
| 9 | Operator monitors, fixes, and retries failures | ScrapAI operator | 🟡 Partial | Health/reporting exists, but production orchestration is still a next step. |
| 10 | Developer updates contract safely | ScrapAI + joinremotes devs | ❌ Missing | Generated TS types/OpenAPI checks are not implemented yet. |

---

## Product flow — JoinRemotes Admin scraper UI

**Layman goal:** use ScrapAI as the data-filling engine for JoinRemotes. The admin should paste a company job-board/careers URL, let ScrapAI discover the scrape structure, scrape company details and job listings, then preview and import that structured data into JoinRemotes.

| Step | What happens | Covered by | Implementation status |
| --- | --- | --- | --- |
| 1 | Admin opens JoinRemotes Admin → Scraper and enters a job-board URL. | Product flow diagram, Journey 2 | ✅ Documented; JoinRemotes UI implementation still needs verification/build. |
| 2 | JoinRemotes calls ScrapAI analyze API to detect platform/selectors and propose a scrape structure. | `POST /api/v1/spiders/analyze` | ✅ ScrapAI side covered. |
| 3 | Admin previews/tests sample extraction for company details and jobs. | Inspect/test-selector APIs, Journey 3 | ✅ ScrapAI side covered; UI preview is JoinRemotes-side work. |
| 4 | Admin saves the approved scrape structure as a reusable source spider. | Spider create/update API, Journey 4 | ✅ ScrapAI side covered. |
| 5 | Admin or cron starts a crawl. | Crawl API, Journey 5 | ✅ Covered. |
| 6 | ScrapAI scrapes company profile data and job post data from the source. | Database spider, job schema, result contract | ✅ Core covered; each real source still needs field-quality smoke test. |
| 7 | JoinRemotes receives clean JSON, previews it, and imports companies/jobs. | Results API/webhook contract, Journey 7/8 | 🟡 Contract covered; actual JoinRemotes import UI and DB sync need verification in JoinRemotes. |
| 8 | Public JoinRemotes shows fresh company pages and job listings. | JoinRemotes app | 🟡 Downstream implementation/verification. |

---

## Journey 1 — Operator sets up ScrapAI locally/private server

**Goal:** ScrapAI API is reachable from joinremotes.com, with DB, Redis, workers, and migrations in place.

### Desired feature coverage

| Need | Status | Covered by | Gap / cross-check |
| --- | --- | --- | --- |
| Install dependencies with uv | ✅ Covered | README, `docs/development.md` | Confirm target server has uv/Python/browser dependencies. |
| Database migration command | ✅ Covered | `scrapai db migrate`, Alembic | Run before API/worker start in deployment. |
| API process | ✅ Covered | `uvicorn apps.web_api.api.main:app` / README commands | Ensure bind host is private/local only. |
| Redis for rate limits, SSE, workers | 🟡 Partial | `.env.example`, `RedisConfig`, docs | Production Redis process and credentials need deployment wiring. |
| Dramatiq worker processes | 🟡 Partial | `apps/web_api/workers` | Crawl and webhook actors exist with retries; deployment still needs supervisor/Coolify process wiring. |
| Private exposure to joinremotes | 🟡 Partial | user deployment preference | Prefer localhost/Tailscale; avoid public ScrapAI endpoint unless intentionally secured. |
| API key for joinremotes project | ✅ Covered | `scrapai apikey create joinremotes --project joinremotes` | Store key only in joinremotes secrets. |
| CORS/origin policy | 🟡 Partial | Plane item #19 | Code currently uses wildcard CORS; replace with explicit joinremotes/private origins before production browser access. |

### Cross-check checklist

- [ ] `DATABASE_URL` points to production DB.
- [ ] Redis is reachable from API and workers.
- [ ] API `/health` passes.
- [ ] Worker can pick up a crawl job.
- [ ] joinremotes has `SCRAPAI_API_URL`, `SCRAPAI_API_KEY`, `SCRAPAI_PROJECT`, and optionally `SCRAPAI_WEBHOOK_SECRET`.

---

## Journey 2 — Admin analyzes a job-board URL

**Goal:** A joinremotes admin pastes a company careers/job-board URL and receives a suggested ScrapAI spider config.

### Desired feature coverage

| Need | Status | Covered by | Gap / cross-check |
| --- | --- | --- | --- |
| Analyze endpoint | ✅ Covered | `POST /api/v1/spiders/analyze` | Verify response shape in joinremotes client. |
| Optional browser mode | ✅ Covered | `use_browser` flag | Confirm server has browser deps for JS-heavy sites. |
| Project scoping | ✅ Covered | API key + `project` field | Use `joinremotes` project consistently. |
| SSRF protection | ✅ Covered | `utils/url_validation.py` | Verified by tests. |
| Job metadata awareness | ✅ Covered | `ScrapedJob`, `docs/joinremotes.md` | Ensure generated configs target `job_title`, `company`, `location`, `salary`, `description`, `tags`, `posted_date`. |

### Client contract

```http
POST /api/v1/spiders/analyze
Authorization: Bearer ***
Content-Type: application/json

{
  "url": "https://www.tomtom.com/careers/joboverview/",
  "project": "joinremotes",
  "use_browser": true
}
```

### Cross-check checklist

- [ ] joinremotes UI stores the original source URL.
- [ ] The generated spider name is stable and domain-based, e.g. `tomtom_com`.
- [ ] Callback name for job pages is `parse_job`.
- [ ] Generated result metadata matches the joinremotes required fields.

---

## Journey 3 — Admin tests selectors and spider output

**Goal:** Before saving a spider, the admin/agent can inspect HTML and test selectors against real pages.

### Desired feature coverage

| Need | Status | Covered by | Gap / cross-check |
| --- | --- | --- | --- |
| Inspect URL | ✅ Covered | `POST /api/v1/spiders/inspect` | Saves HTML metadata for analysis. |
| Test selector | ✅ Covered | `POST /api/v1/spiders/test-selector` | Useful for client-side validation loop. |
| Browser inspect mode | ✅ Covered | `use_browser` flag | Required for JS-heavy career sites. |
| Human-readable analysis artifact | 🟡 Partial | CLI analysis files, `docs/joinremotes.md` | API/UI should decide where to store/show analysis notes. |

### Cross-check checklist

- [ ] The joinremotes UI can show sample matches for each field.
- [ ] The admin can identify empty/malformed fields before saving.
- [ ] Test selectors do not require exposing raw server file paths to the client.

---

## Journey 4 — Admin creates or updates a source spider

**Goal:** The approved spider config is persisted in ScrapAI and can be reused by crawls.

### Desired feature coverage

| Need | Status | Covered by | Gap / cross-check |
| --- | --- | --- | --- |
| Upsert spider API | ✅ Covered | `POST /api/v1/spiders` | Creates or updates existing spider. |
| List spiders | ✅ Covered | `GET /api/v1/spiders` | joinremotes can show existing sources. |
| Get by name | ✅ Covered | `GET /api/v1/spiders/by-name/{project}/{name}` | Use for admin detail/edit page. |
| Delete/deactivate spider | ✅ Covered | `DELETE /api/v1/spiders/{id}` | Confirm UI labels as deactivate/soft delete if applicable. |
| Validation | ✅ Covered | Pydantic schemas, import service | Avoid `skip_validation` for client-supplied configs. |
| Reserved callback handling | ✅ Covered | `docs/joinremotes.md`, callback schema | Use `parse_job`; avoid Scrapy-reserved names. |

### Cross-check checklist

- [ ] joinremotes saves ScrapAI spider name alongside each external source.
- [ ] Updates preserve project scope.
- [ ] Validation errors are surfaced clearly in the joinremotes UI.

---

## Journey 5 — Admin or cron triggers a crawl

**Goal:** joinremotes starts a crawl for a source spider and gets a `crawl_run_id`.

### Desired feature coverage

| Need | Status | Covered by | Gap / cross-check |
| --- | --- | --- | --- |
| Create crawl run | ✅ Covered | `POST /api/v1/crawls` | Queues background job. |
| One active crawl per spider | ✅ Covered | 409 conflict guard | Client should handle conflict gracefully. |
| Requested item limit | ✅ Covered | `requested_limit` | Useful for smoke tests vs full sync. |
| Output mode | ✅ Covered | `db`, `file`, `jsonl` | joinremotes should use `db`. |
| Rate limiting | 🟡 Partial | `RateLimitService` | Confirm expected admin/cron frequency. |

### Client contract

```http
POST /api/v1/crawls
Authorization: Bearer ***
Content-Type: application/json

{
  "spider_name": "tomtom_com",
  "project": "joinremotes",
  "requested_limit": 500,
  "output_mode": "db"
}
```

### Cross-check checklist

- [ ] joinremotes stores `crawl_run_id` for audit/status display.
- [ ] 409 conflict maps to “crawl already running”, not generic failure.
- [ ] Scheduled crawls do not exceed rate limit.

---

## Journey 6 — Client observes crawl progress

**Goal:** joinremotes can tell whether a crawl is queued, running, completed, failed, or cancelled.

### Desired feature coverage

| Need | Status | Covered by | Gap / cross-check |
| --- | --- | --- | --- |
| Poll status | ✅ Covered | `GET /api/v1/crawls/{id}` | Safest/default client path. |
| List runs | ✅ Covered | `GET /api/v1/crawls?project=...` | Admin history table. |
| Cancel run | ✅ Covered | `POST /api/v1/crawls/{id}/cancel` | Admin stop button. |
| SSE stream | 🟡 Partial | `GET /api/v1/crawls/{id}/stream` | Native browser `EventSource` cannot send Authorization headers; use server-side proxy or fetch-event-source. |
| Progress events | 🟡 Partial | Redis pub/sub stream | Needs worker-to-Redis event verification in production. |

### Recommended joinremotes approach

Start with polling because it works with normal authenticated server-side fetches. Add SSE later through a joinremotes API route/proxy if live progress is important.

### Cross-check checklist

- [ ] Polling interval is reasonable, e.g. 2-5 seconds for admin UI.
- [ ] Failed status displays `error_message`.
- [ ] Completed status triggers result sync exactly once.

---

## Journey 7 — Client syncs crawl results into joinremotes jobs

**Goal:** joinremotes fetches scraped results and upserts Jobs and Companies.

### Desired feature coverage

| Need | Status | Covered by | Gap / cross-check |
| --- | --- | --- | --- |
| List results | ✅ Covered | `GET /api/v1/results` | Filter by project/spider/crawl run. |
| Result by URL | ✅ Covered | `GET /api/v1/results/by-url/` | Supports dedupe/debug checks. |
| Pagination | ✅ Covered | `limit`, `offset`, `total_count`, `has_next` | Client should loop until `has_next=false`. |
| Source URL dedupe | ✅ Covered | `url` in result contract | joinremotes uses `(sourceSpider, sourceUrl)`. |
| Required job metadata | ✅ Covered | `docs/joinremotes.md` | Needs live field-quality smoke test per spider. |
| Company matching/stub creation | 🟡 Partial | joinremotes-side behavior documented | Verify in joinremotes repo/app, not ScrapAI. |
| Salary/location/date normalization | 🟡 Partial | joinremotes-side behavior documented | Verify parser coverage in joinremotes. |

### Result shape expected by joinremotes

```json
{
  "id": 1,
  "url": "https://source.example/jobs/123",
  "title": "Senior Engineer at Acme",
  "scraped_at": "2026-03-29T10:15:00Z",
  "metadata": {
    "job_title": "Senior Engineer",
    "company": "Acme",
    "location": "Remote",
    "salary": "$120k-$160k",
    "description": "...",
    "tags": ["TypeScript", "Remote"],
    "posted_date": "2026-03-28"
  }
}
```

### Cross-check checklist

- [ ] Sync by `crawl_run_id` when possible to avoid reprocessing old results.
- [ ] If `job_title` is missing, fallback from top-level `title` is still acceptable.
- [ ] `company` missing should be treated as a bad extraction for production job sources.
- [ ] Description quality is checked before publishing jobs.

---

## Journey 8 — ScrapAI notifies joinremotes by webhook

**Goal:** When a crawl finishes/fails, ScrapAI calls joinremotes so the client can sync or alert without polling forever.

### Desired feature coverage

| Need | Status | Covered by | Gap / cross-check |
| --- | --- | --- | --- |
| Create subscription | ✅ Covered | `POST /api/v1/webhooks` | Secret is returned once; save in joinremotes env. |
| List subscriptions | ✅ Covered | `GET /api/v1/webhooks` | Admin/debug only. |
| Delete subscription | ✅ Covered | `DELETE /api/v1/webhooks/{id}` | Useful for rotating endpoints. |
| Completed/failed event queueing | ✅ Covered | `crawl_worker.py` | `crawl.completed` and `crawl.failed` terminal states queue webhook deliveries. |
| HMAC signature | ✅ Covered | `X-Webhook-Signature` | Active worker signs the exact compact JSON body it sends; legacy `X-ScrapAI-Signature` alias is also emitted. |
| Timestamp/event headers | ✅ Covered | `X-Webhook-Timestamp`, `X-Webhook-Event` | Use for replay/event routing. |
| Delivery retries | ✅ Covered | Dramatiq `Retries(max_retries=5)` | Worker retries failed/timeout deliveries through Dramatiq; live retry behavior still belongs in the E2E smoke test. |
| joinremotes endpoint | 🟡 Partial | Contract docs | Must exist as public HMAC-authenticated route. |

### Cross-check checklist

- [ ] joinremotes strips optional `sha256=` prefix before comparison.
- [ ] joinremotes verifies raw request body bytes, not re-serialized JSON.
- [ ] `crawl.completed` triggers sync; `crawl.failed` creates an admin-visible alert.
- [ ] Webhook replay protection decision is made (timestamp window or idempotent event handling).

---

## Journey 9 — Operator monitors, fixes, and retries failures

**Goal:** Broken spiders, API failures, or worker issues are visible and fixable.

### Desired feature coverage

| Need | Status | Covered by | Gap / cross-check |
| --- | --- | --- | --- |
| Health checks | 🟡 Partial | `docs/health.md`, CLI health command | API/worker deployment health checks need finalization. |
| Crawl status/error tracking | ✅ Covered | `CrawlRun.error_message`, status fields | Client can display run errors. |
| Queue visibility | 🟡 Partial | `CrawlQueue` model, `docs/queue.md` | API/admin queue UI is not complete. |
| Retry failed crawl | 🟡 Partial | trigger new crawl | No dedicated retry endpoint documented. |
| Fix/update spider config | ✅ Covered | `POST /spiders` upsert | Admin can update selectors/config. |
| Monthly/periodic health report | 🟡 Partial | README health-check workflow | Needs cron/deployment setup. |

### Cross-check checklist

- [ ] Failed crawl includes actionable `error_message`.
- [ ] joinremotes admin UI can rerun a failed source.
- [ ] Operator can identify whether failure is API, worker, source-site block, or extraction quality.

---

## Journey 10 — Developer updates contract safely

**Goal:** ScrapAI and joinremotes evolve without silently breaking the API/result contract.

### Desired feature coverage

| Need | Status | Covered by | Gap / cross-check |
| --- | --- | --- | --- |
| OpenAPI schema | ✅ Covered | FastAPI `/openapi.json` | Should be exported in CI/release. |
| TypeScript client/types | ❌ Missing | Plane item #20 | Generate and consume in joinremotes. |
| Contract tests | ❌ Missing | Not present | Add tests for joinremotes required fields/result shapes. |
| Example fixtures | 🟡 Partial | `docs/joinremotes.md` TomTom example | Add machine-readable fixture JSON for CI. |
| Versioning/deprecation policy | ❌ Missing | Not present | Needed once client integration stabilizes. |

### Recommended next checks

- [ ] Add `docs/examples/joinremotes-result.json` fixture.
- [ ] Export `openapi.json` and generate TypeScript types for joinremotes.
- [ ] Add contract tests that assert required result fields and webhook signature format.
- [ ] Add CI check that generated types are up to date.
