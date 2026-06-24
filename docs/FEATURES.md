# ScrapAI Features and Coverage

Last updated: 2026-06-24

This file is the cross-check sheet for what ScrapAI is intended to provide, what is already implemented in the repository, and what still needs work for downstream consumers such as **joinremotes.com**.

Related docs:

- [`API.md`](API.md) — full REST API reference
- [`joinremotes.md`](joinremotes.md) — joinremotes.com integration contract and examples
- [`JOURNEYS.md`](JOURNEYS.md) — journey-by-journey feature coverage
- [`joinremotes-scrapai-flow.html`](joinremotes-scrapai-flow.html) — visual layman flow for the admin scraper UI
- [`development.md`](development.md) — local development workflow
- [`deployment.md`](deployment.md) — deployment notes

## Status legend

| Status | Meaning |
| --- | --- |
| ✅ Covered | Implemented and documented/tested enough to rely on |
| 🟡 Partial | Core exists, but missing polish, automation, production hardening, or full client coverage |
| ❌ Missing | Desired feature is not implemented yet |
| ⏸️ Deferred | Known but not in the current integration scope |

## Current validated baseline

- Last audited against repository code, docs, tests, and Plane on 2026-06-24.
- API route inventory was verified from the live FastAPI app (`api.main:app`).
- Test suite baseline: `281 passed, 3 skipped` via `uv run pytest -q`.
- API/client integration work is primarily for **joinremotes.com**, with ScrapAI expected locally/privately behind `localhost` or Tailscale, not as a public SaaS.

## Feature matrix

| Area | Feature | Status | Evidence / source | Notes / gaps |
| --- | --- | --- | --- | --- |
| Core scraping | Database-backed spiders | ✅ Covered | `core/models.py`, `spiders/database_spider.py`, `docs/projects.md` | Spiders are stored as DB rows with rules, settings, callbacks, and project scope. |
| Core scraping | JSON spider config import/export | ✅ Covered | `cli/spiders.py`, `services/spider_import_service.py`, `docs/API.md` | Used by CLI and API create/update. |
| Core scraping | Custom callbacks with CSS/XPath selectors | ✅ Covered | `core/schemas.py`, `spiders/base.py`, `docs/callbacks.md` | Supports `extract`, processors, nested lists, URL context, and iterate/follow patterns. |
| Core scraping | Job extraction schema | ✅ Covered | `core/schemas.py::ScrapedJob`, tests, Plane item #4 Done | Required for job-board/client scenarios. |
| Core scraping | Article extraction | ✅ Covered | `core/extractors.py`, README | Newspaper/trafilatura extraction remains available for content/news use cases. |
| Core scraping | Incremental crawling / DeltaFetch | 🟡 Partial | `docs/deltafetch.md`, README | Documented; verify production behavior per site when enabling. |
| Core scraping | Checkpoint pause/resume | 🟡 Partial | `docs/checkpoint.md`, README | Documented; use for long production crawls. |
| Core scraping | Sitemap crawling | 🟡 Partial | `spiders/sitemap_spider.py`, `docs/sitemap.md` | Code exists; coverage is lighter than core database spider. |
| Anti-bot | Cloudflare bypass with browser/cookie cache | 🟡 Partial | `handlers/cloudflare_handler.py`, `docs/cloudflare.md` | Core exists; production environment needs browser dependencies and periodic verification. |
| Anti-bot | Proxy escalation | 🟡 Partial | `middlewares.py`, `docs/proxies.md` | Good for blocked domains; residential proxy behavior should remain explicit opt-in. |
| Security | SSRF validation | ✅ Covered | `utils/url_validation.py`, tests, Plane item #7 Done | Blocks localhost/private/reserved/sensitive ranges while allowing RFC 5737 doc ranges for tests/examples. |
| Security | Secret/API key redaction | ✅ Covered | `utils/secret_redaction.py`, API docs | Never expose API keys in docs or logs. |
| Security | API key auth and project scoping | ✅ Covered | `apps/web_api/api/deps.py`, `core/models.py`, `docs/API.md` | API keys can be project-scoped; joinremotes should use a project-scoped key. |
| REST API | API service foundation | ✅ Covered | Plane item #10 Done, `apps/web_api/api` | FastAPI app with routers for spiders/crawls/results/webhooks/auth. |
| REST API | Analyze URL endpoint | ✅ Covered | `POST /api/v1/spiders/analyze`, Plane item #12 Done | Consumer/admin can ask ScrapAI for a suggested spider config. |
| REST API | Inspect URL endpoint | ✅ Covered | `POST /api/v1/spiders/inspect` | Useful before selector testing and spider generation. |
| REST API | Test selector endpoint | ✅ Covered | `POST /api/v1/spiders/test-selector` | Helps client UI validate selectors before save. |
| REST API | Create/update spider endpoint | ✅ Covered | `POST /api/v1/spiders`, Plane item #13 Done | Upserts spider config by project/name. |
| REST API | Delete spider endpoint | ✅ Covered | `DELETE /api/v1/spiders/{id}`, Plane item #16 Done | Soft delete behavior is documented in API reference. |
| REST API | List/get spiders | ✅ Covered | `GET /spiders`, `GET /spiders/by-name/{project}/{name}` | Needed by joinremotes admin UI to show existing source configs. |
| REST API | Create crawl run | ✅ Covered | `POST /api/v1/crawls` | Queues background crawl job via Dramatiq/Redis. |
| REST API | List/get crawl status | ✅ Covered | `GET /api/v1/crawls`, `GET /api/v1/crawls/{id}` | Polling flow is covered. |
| REST API | Cancel crawl run | ✅ Covered | `POST /api/v1/crawls/{id}/cancel` | Client can stop queued/running jobs. |
| REST API | Crawl progress stream | ✅ Covered | `GET /api/v1/crawls/{id}/stream` | SSE exists; client compatibility should be checked because native `EventSource` cannot send `Authorization` headers without a wrapper/proxy. |
| REST API | Results list/query | ✅ Covered | `GET /api/v1/results` | Supports project, spider, crawl run, pagination, URL filter. |
| REST API | Result by URL | ✅ Covered | `GET /api/v1/results/by-url/` | Useful for dedupe checks. |
| Webhooks | Webhook subscription API | ✅ Covered | `apps/web_api/api/routers/webhooks.py`, Plane item #17 Done | Create/list/delete subscriptions. |
| Webhooks | HMAC signed delivery | ✅ Covered | `apps/web_api/workers/webhook_worker.py`, `services/webhook_service.py`, `docs/joinremotes.md` | Active worker sends documented `X-Webhook-*` headers and backward-compatible `X-ScrapAI-*` aliases. |
| Webhooks | Completed/failed crawl events | ✅ Covered | `apps/web_api/workers/crawl_worker.py` | Terminal crawl events queue `crawl.completed` and `crawl.failed` deliveries with the documented nested payload plus flat compatibility fields. |
| Workers | Redis-backed queue/worker execution | 🟡 Partial | Plane item #1 Backlog, `apps/web_api/workers` | Code has Redis/Dramatiq crawl + webhook workers with retries; production process orchestration and ops runbook remain backlog. |
| Rate limiting | API/crawl rate limiting | 🟡 Partial | `RateLimitService`, `docs/API.md`, Plane item #2 Backlog | Redis-backed limits exist; advanced quality/events plan still backlog. |
| Deployment | Coolify deployment | ❌ Missing | Plane item #15 Todo | Needs production compose/build config, secrets, health checks, workers, and migration step. |
| Config | API env vars and CORS | 🟡 Partial | `.env.example`, `docs/API.md`, Plane item #19 Backlog | Env vars exist; code currently uses permissive wildcard CORS; production allowed-origin policy should be finalized for joinremotes. |
| DX | TypeScript type generation | ❌ Missing | Plane item #20 Backlog | Useful for joinremotes typed client; currently manual contract docs only. |
| DX | JoinRemotes integration docs | ✅ Covered | `docs/joinremotes.md`, this file, `docs/JOURNEYS.md`, `docs/joinremotes-scrapai-flow.html`, Plane item #21 Done | Repo docs, cross-check matrices, and visual layman flow are present. |
| Client integration | joinremotes consumer contract | ✅ Covered | `docs/joinremotes.md` | Required metadata fields and webhook contract documented. |
| Client integration | joinremotes admin scraper UI concept | ✅ Covered as product/docs, 🟡 implementation | `docs/joinremotes-scrapai-flow.html`, `docs/JOURNEYS.md` | Product idea is documented: paste job-board URL, analyze, preview company/jobs, approve import. Actual JoinRemotes UI still needs implementation/verification in the JoinRemotes repo. |
| Client integration | joinremotes admin source/spider management | 🟡 Partial | API endpoints exist | Need verify actual joinremotes UI routes/client code against this contract. |
| Client integration | joinremotes crawl/sync flow | 🟡 Partial | `docs/joinremotes.md` | Trigger/poll/webhook/result sync documented; end-to-end production run still needed. |

## Plane cross-check snapshot

| Plane item | Live state | Documentation interpretation |
| --- | --- | --- |
| #1 Redis Worker Orchestration Plan | Backlog | Code has Redis/Dramatiq workers, retries, and SSE publishing; production orchestration/runbook is still not done. |
| #2 Advanced API Quality and Events Plan | Backlog | Rate limiting and basic events exist; advanced quality gates/event coverage remain backlog. |
| #4 Job Extraction Plan | Done | Job schema and extraction tests are covered. |
| #7 SSRF validation test coverage plan | Done | URL validation and tests are covered. |
| #10 API Service Foundation Plan | Done | FastAPI app, auth dependencies, and route foundation are covered. |
| #12 Add Spider Analysis API Endpoint | Done | Analyze endpoint exists and is tested. |
| #13 Add Spider Create/Update API Endpoint | Done | Create/update endpoint exists and is tested. |
| #14 Apply Database Migrations and Create JoinRemotes API Key | Done | Setup/API key path is documented; actual secrets stay outside docs. |
| #15 Coolify Deployment Configuration | Todo | Deployment remains missing from implementation docs. |
| #16 Add Spider Delete API Endpoint | Done | Delete/deactivate endpoint exists and is tested. |
| #17 Add Webhook Subscription API | Done | Subscription CRUD exists and is tested. |
| #18 Test Initial Job Board Spiders via CLI | Backlog | Still requires a real source smoke test. |
| #19 Add API Environment Variables & CORS Configuration | Backlog | Env vars exist; CORS is still wildcard and needs production policy. |
| #20 Create TypeScript Type Generator with Git Hooks | Backlog | Missing. |
| #21 Create JoinRemotes Integration Documentation | Done | Repo docs and cross-check matrices are present. |

## joinremotes.com required result contract

For a scraped job result to be consumable by joinremotes.com, ScrapAI should emit the source URL plus metadata fields below. See [`joinremotes.md`](joinremotes.md) for the full contract.

| Field | Required for good sync? | Current coverage | Notes |
| --- | --- | --- | --- |
| `url` | Yes | ✅ Covered | Used by joinremotes as the source dedupe key. |
| `metadata.job_title` | Yes | ✅ Covered | Falls back to top-level `title` when missing. |
| `metadata.company` | Yes | ✅ Covered | JoinRemotes can create/match stub Company records. |
| `metadata.location` | Strongly recommended | ✅ Covered | Free-form string. |
| `metadata.salary` | Optional but desired | ✅ Covered | Free-form; joinremotes parses ranges/currency where possible. |
| `metadata.description` | Yes | ✅ Covered | HTML or plain text. |
| `metadata.tags` | Optional but desired | ✅ Covered | String array; joinremotes normalizes casing/whitespace. |
| `metadata.posted_date` | Optional but desired | ✅ Covered | ISO date preferred; fallback to `scraped_at`. |

## What's next

Recommended next implementation order:

1. **Finish production orchestration** — Redis, Dramatiq worker process management, queue visibility, retries, and health checks. Maps to Plane item #1 and Plane item #2.
2. **Finalize joinremotes environment/CORS contract** — exact private API URL, allowed origins, local/Tailscale behavior, timeout policy. Maps to Plane item #19.
3. **Add generated client/types** — OpenAPI export plus TypeScript generator or checked-in types for joinremotes. Maps to Plane item #20.
4. **Complete Coolify deployment path** — API + worker + Redis + DB + migrations + health checks. Maps to Plane item #15.
5. **Run a real joinremotes end-to-end smoke test** — create/import one job-board spider, trigger crawl through API, wait for completion, fetch results, and sync into joinremotes. Maps to Plane item #18 and Plane item #21.
