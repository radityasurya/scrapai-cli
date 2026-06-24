"""
Stale crawl run reaper for ScrapAI CLI.

Periodic Dramatiq actor that recovers crawl runs left in 'running' state
after their worker died (heartbeat TTL expired).
"""

import logging
from datetime import datetime, timedelta, timezone

import dramatiq

from core.db import SessionLocal
from core.models import CrawlRun

from ..services.redis_config import get_dramatiq_broker, get_redis_config

logger = logging.getLogger(__name__)

_broker = get_dramatiq_broker()
_redis_config = get_redis_config()

# A crawl run is considered stale if it has been "running" for longer than
# 2× the lock TTL without a heartbeat refresh (i.e. the worker died).
STALE_THRESHOLD_SECONDS = _redis_config.CRAWL_LOCK_TTL_SECONDS * 2


@dramatiq.actor(queue_name=_redis_config.get_queue_name("crawl"), max_retries=0)
def reap_stale_runs() -> None:
    """
    Mark stale crawl runs as failed and release their Redis locks.

    A run is stale when it has status='running' and updated_at is older
    than STALE_THRESHOLD_SECONDS (meaning no heartbeat has refreshed the
    Postgres record in that window).
    """
    db = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=STALE_THRESHOLD_SECONDS)

        stale_runs = (
            db.query(CrawlRun)
            .filter(CrawlRun.status == "running", CrawlRun.updated_at < cutoff)
            .all()
        )

        if not stale_runs:
            logger.debug("Reaper: no stale crawl runs found")
            return

        for run in stale_runs:
            run_id = int(run.id)
            logger.warning(f"[reaper] Stale run detected: run_id={run_id}, last_updated={run.updated_at}")
            run.status = "failed"
            run.error_message = "Worker heartbeat lost — auto-recovered by reaper"
            run.finished_at = datetime.now(timezone.utc)
            run.updated_at = datetime.now(timezone.utc)
            _redis_config.release_crawl_lock(run_id)

        db.commit()
        logger.info(f"[reaper] Recovered {len(stale_runs)} stale crawl run(s)")

    except Exception as e:
        logger.error(f"[reaper] Failed during stale run recovery: {e}")
        db.rollback()
    finally:
        db.close()
