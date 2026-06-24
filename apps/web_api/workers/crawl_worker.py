"""
Crawl worker for ScrapAI CLI.

Dramatiq actor that executes crawl jobs in the background.
"""

import json
import logging
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import dramatiq

from core.db import SessionLocal

from ..services.crawl_service import CrawlService
from ..services.redis_config import (
    acquire_crawl_lock,
    get_dramatiq_broker,
    get_redis_client,
    get_redis_config,
    refresh_crawl_lock,
    release_crawl_lock,
)
from ..services.webhook_service import WebhookService

logger = logging.getLogger(__name__)

_broker = get_dramatiq_broker()
_redis_config = get_redis_config()
queue_name = _redis_config.get_queue_name("crawl")


def publish_sse_event(redis_client: Any, channel: str, event_type: str, data: dict) -> None:
    """Publish an SSE event to Redis for real-time progress updates."""
    try:
        message = json.dumps(
            {
                "event": event_type,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                **data,
            }
        )
        redis_client.publish(channel, message)
        logger.debug(f"Published SSE event {event_type} to {channel}")
    except Exception as e:
        logger.error(f"Failed to publish SSE event: {e}")


def _heartbeat_loop(crawl_run_id: int, stop_event: threading.Event) -> None:
    """Refresh the crawl lock TTL every 30s until stop_event is set."""
    while not stop_event.wait(timeout=30):
        if not refresh_crawl_lock(crawl_run_id):
            logger.warning(f"[run={crawl_run_id}] Heartbeat: lock key missing, another worker may have taken over")
            break


@dramatiq.actor(queue_name=queue_name, max_retries=3)
def crawl_actor(crawl_run_id: int) -> None:
    """
    Execute a crawl job.

    This actor runs the actual Scrapy spider for a crawl run.
    """
    log_prefix = f"[run={crawl_run_id}]"

    if not acquire_crawl_lock(crawl_run_id):
        logger.warning(f"{log_prefix} Lock already held — skipping duplicate execution")
        return

    stop_heartbeat = threading.Event()
    heartbeat_thread = threading.Thread(
        target=_heartbeat_loop,
        args=(crawl_run_id, stop_heartbeat),
        daemon=True,
        name=f"heartbeat-{crawl_run_id}",
    )
    heartbeat_thread.start()

    db = SessionLocal()
    redis_client = get_redis_client()
    channel = f"scrapai:crawl:{crawl_run_id}"
    crawl_service = None

    try:
        from core.models import Spider

        crawl_service = CrawlService()
        crawl_run = crawl_service.get_crawl_run(db, crawl_run_id)

        if not crawl_run:
            logger.error(f"{log_prefix} Crawl run not found")
            return

        spider = db.query(Spider).filter(Spider.id == crawl_run.spider_id).first()
        if not spider:
            logger.error(f"{log_prefix} Spider {crawl_run.spider_id} not found")
            crawl_service.update_crawl_run_status(
                db, crawl_run_id, "failed", error_message="Spider not found"
            )
            publish_sse_event(
                redis_client,
                channel,
                "crawl:failed",
                {"error": "Spider not found"},
            )
            return

        spider_name = spider.name
        project = crawl_run.project

        crawl_service.update_crawl_run_status(db, crawl_run_id, "running")
        publish_sse_event(
            redis_client,
            channel,
            "crawl:started",
            {
                "spider_name": spider_name,
                "project": project,
            },
        )
        crawl_service.emit_event(
            db, "crawl.started", "crawl_run", crawl_run_id,
            {"spider_name": spider_name, "project": project},
        )

        cmd = [
            sys.executable,
            "-m",
            "scrapy",
            "crawl",
            "database_spider",
            "-a",
            f"spider_name={spider_name}",
        ]

        if crawl_run.requested_limit and crawl_run.requested_limit > 0:
            cmd.extend(["-s", f"CLOSESPIDER_ITEMCOUNT={crawl_run.requested_limit}"])

        cwd = Path.cwd()
        env = os.environ.copy()
        env["SCRAPY_SETTINGS_MODULE"] = "settings"
        env["SCRAPAI_LOG_LEVEL"] = "INFO"
        env["SCRAPAI_CRAWL_RUN_ID"] = str(crawl_run_id)

        logger.info(f"{log_prefix} Starting crawl job: {' '.join(cmd)}")

        start_time = time.time()

        process = subprocess.Popen(
            cmd,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        last_progress_time = time.time()
        progress_interval = 2

        while process.poll() is None:
            current_time = time.time()

            if current_time - last_progress_time >= progress_interval:
                db.refresh(crawl_run)
                items_scraped = _count_scraped_items(db, crawl_run_id)

                publish_sse_event(
                    redis_client,
                    channel,
                    "crawl:progress",
                    {
                        "items_scraped": items_scraped,
                        "status": crawl_run.status,
                        "elapsed_seconds": int(current_time - start_time),
                    },
                )

                last_progress_time = current_time

            time.sleep(0.5)

        stdout, stderr = process.communicate()

        end_time = time.time()
        duration = int(end_time - start_time)

        if process.returncode != 0:
            error_msg = stderr.decode("utf-8", errors="replace")[-2000:]
            logger.error(f"{log_prefix} Crawl job failed: {error_msg}")
            assert crawl_service is not None
            crawl_run = crawl_service.update_crawl_run_status(
                db, crawl_run_id, "failed", error_message=error_msg
            )
            publish_sse_event(
                redis_client,
                channel,
                "crawl:failed",
                {
                    "error": error_msg,
                    "duration_seconds": duration,
                },
            )
            _trigger_webhooks(crawl_run, "crawl.failed")
            crawl_service.emit_event(
                db, "crawl.failed", "crawl_run", crawl_run_id,
                {"error": error_msg},
            )
            return

        items_scraped = _count_scraped_items(db, crawl_run_id)

        assert crawl_service is not None
        crawl_run = crawl_service.update_crawl_run_status(
            db, crawl_run_id, "completed", items_scraped=items_scraped
        )

        logger.info(f"{log_prefix} Crawl job completed in {duration}s, {items_scraped} items")

        publish_sse_event(
            redis_client,
            channel,
            "crawl:completed",
            {
                "items_scraped": items_scraped,
                "duration_seconds": duration,
            },
        )

        _trigger_webhooks(crawl_run, "crawl.completed")
        crawl_service.emit_event(
            db, "crawl.completed", "crawl_run", crawl_run_id,
            {"items_scraped": items_scraped, "duration_seconds": duration},
        )
        from ..services.validation_service import ValidationService
        ValidationService().generate_report(db, crawl_run_id)

    except Exception as e:
        logger.error(f"{log_prefix} Crawl job failed with exception: {e}")
        try:
            if crawl_service:
                crawl_service.update_crawl_run_status(
                    db, crawl_run_id, "failed", error_message=str(e)
                )
            publish_sse_event(
                redis_client,
                channel,
                "crawl:failed",
                {
                    "error": str(e),
                },
            )
        except Exception:
            pass
    finally:
        stop_heartbeat.set()
        heartbeat_thread.join(timeout=5)
        release_crawl_lock(crawl_run_id)
        db.close()


def _count_scraped_items(db: Any, crawl_run_id: int) -> int:
    """Count items scraped during this crawl run."""
    from sqlalchemy import func

    from core.models import ScrapedItem

    count = (
        db.query(func.count(ScrapedItem.id))
        .filter(ScrapedItem.crawl_run_id == crawl_run_id)
        .scalar()
    )

    return count or 0


def _trigger_webhooks(crawl_run: Any, event_type: str) -> None:
    """Trigger webhook notifications for a terminal crawl event."""
    try:
        webhook_service = WebhookService()
        db = SessionLocal()

        try:
            webhooks = webhook_service.get_active_webhooks(
                db, crawl_run.project, event_type=event_type
            )

            for webhook in webhooks:
                webhook_id = int(webhook.id) if webhook.id else None
                if webhook_id is None:
                    continue
                timestamp = datetime.now(timezone.utc).isoformat()
                data = {
                    "crawl_run_id": crawl_run.id,
                    "project": crawl_run.project,
                    "spider_name": crawl_run.spider.name if crawl_run.spider else None,
                    "status": crawl_run.status,
                    "items_scraped": crawl_run.items_scraped,
                    "duration_seconds": crawl_run.duration_seconds,
                    "error_message": crawl_run.error_message,
                }
                webhook_service.queue_webhook_delivery(
                    db,
                    webhook_id,
                    {
                        "event": event_type,
                        "event_type": event_type,
                        "timestamp": timestamp,
                        "data": data,
                        # Keep top-level fields for early integrations that consumed
                        # the pre-contract payload directly.
                        **data,
                    },
                )
        finally:
            db.close()

    except Exception as e:
        logger.error(f"Failed to trigger webhooks: {e}")


def enqueue_crawl_job(crawl_run_id: int) -> None:
    """
    Enqueue a crawl job for execution.

    This is called by the API to queue a crawl for background processing.
    """
    logger.info(f"Enqueueing crawl job {crawl_run_id}")
    crawl_actor.send(crawl_run_id)
