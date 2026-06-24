# Workers Runbook

Operational guide for ScrapAI background workers (Dramatiq + Redis).

## Starting Workers

```bash
uv run workers
```

This launches Dramatiq with three actor modules: `crawl_worker`, `webhook_worker`, and `reaper`.

## Queue Names

Queue names follow the pattern `{REDIS_PREFIX_with_colons_replaced_by_underscores}_{queue_type}`.

With the default `REDIS_PREFIX=joinremotes:scrapai:prod`:

| Queue | Name |
|-------|------|
| Crawl | `joinremotes_scrapai_prod_crawl` |
| Webhook | `joinremotes_scrapai_prod_webhook` |

## Checking Queue Depths

```bash
redis-cli LLEN "joinremotes_scrapai_prod_crawl"
redis-cli LLEN "joinremotes_scrapai_prod_webhook"
```

## Checking Stale Runs in Postgres

Find crawl runs stuck in `running` state:

```bash
uv run python -c "
from core.db import SessionLocal
from core.models import CrawlRun
from datetime import datetime, timezone
db = SessionLocal()
runs = db.query(CrawlRun).filter(CrawlRun.status == 'running').all()
for r in runs:
    print(r.id, r.updated_at, r.spider_id)
db.close()
"
```

## Triggering the Reaper Manually

The reaper marks runs as failed when their heartbeat TTL (120 s × 2 = 240 s) has expired.
Trigger it on demand:

```bash
uv run python -c "from apps.web_api.workers.reaper import reap_stale_runs; reap_stale_runs.send()"
```

## Releasing a Stuck Redis Lock Manually

If a crawl run lock is stuck (e.g. after a forced kill), release it directly:

```bash
redis-cli DEL "joinremotes:scrapai:prod:lock:crawl:<crawl_run_id>"
```

Replace `joinremotes:scrapai:prod` with your `REDIS_PREFIX` value if different.

## Cancelling a Queued Crawl Run

Update the crawl run status to `cancelled` in the database:

```bash
uv run python -c "
from core.db import SessionLocal
from core.models import CrawlRun
db = SessionLocal()
run = db.query(CrawlRun).filter(CrawlRun.id == <crawl_run_id>).first()
if run:
    run.status = 'cancelled'
    db.commit()
    print('cancelled')
db.close()
"
```

If the worker picks it up after cancellation, `crawl_actor` will attempt to run it. To prevent this, also release the lock (see above) and remove the message from the queue before the worker consumes it.

## Worker Locking and Heartbeat

Each crawl run is protected by a Redis lock (`lock:crawl:<id>`) with a 120-second TTL. The worker refreshes this lock every 30 seconds while the crawl is active. If the worker dies, the lock expires after 120 seconds and the reaper will recover the run after 240 seconds (2 × TTL).

If two workers accidentally receive the same message, the second will log a warning and exit without processing.
