"""
Crawl worker for ScrapAI CLI.

Dramatiq actor that executes crawl jobs in the background.
"""

import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import dramatiq
from dramatiq.brokers.redis import RedisBroker
from dramatiq.middleware import Retries

from core.db import SessionLocal

from ..services.crawl_service import CrawlService
from ..services.redis_config import get_redis_client, get_redis_config
from ..services.webhook_service import WebhookService

logger = logging.getLogger(__name__)

_redis_config = get_redis_config()
broker = RedisBroker(
    host=_redis_config.host,
    port=_redis_config.port,
    db=_redis_config.db,
    password=_redis_config.password if _redis_config.password else None,
    ssl=_redis_config.ssl,
    middleware=[
        Retries(max_retries=3, min_backoff=1000, max_backoff=60000),
    ],
)
dramatiq.set_broker(broker)

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


@dramatiq.actor(queue_name=queue_name, max_retries=3)
def crawl_actor(crawl_run_id: int) -> None:
    """
    Execute a crawl job.

    This actor runs the actual Scrapy spider for a crawl run.
    """
    db = SessionLocal()
    redis_client = get_redis_client()
    channel = f"scrapai:crawl:{crawl_run_id}"
    crawl_service = None

    try:
        from core.models import Spider

        crawl_service = CrawlService()
        crawl_run = crawl_service.get_crawl_run(db, crawl_run_id)

        if not crawl_run:
            logger.error(f"Crawl run {crawl_run_id} not found")
            return

        spider = db.query(Spider).filter(Spider.id == crawl_run.spider_id).first()
        if not spider:
            logger.error(f"Spider {crawl_run.spider_id} not found")
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

        logger.info(f"Starting crawl job {crawl_run_id}: {' '.join(cmd)}")

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
            logger.error(f"Crawl job {crawl_run_id} failed: {error_msg}")
            assert crawl_service is not None
            crawl_service.update_crawl_run_status(
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
            return

        items_scraped = _count_scraped_items(db, crawl_run_id)

        assert crawl_service is not None
        crawl_run = crawl_service.update_crawl_run_status(
            db, crawl_run_id, "completed", items_scraped=items_scraped
        )

        logger.info(f"Crawl job {crawl_run_id} completed in {duration}s, {items_scraped} items")

        publish_sse_event(
            redis_client,
            channel,
            "crawl:completed",
            {
                "items_scraped": items_scraped,
                "duration_seconds": duration,
            },
        )

        _trigger_webhooks(crawl_run)

    except Exception as e:
        logger.error(f"Crawl job {crawl_run_id} failed with exception: {e}")
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


def _trigger_webhooks(crawl_run: Any) -> None:
    """Trigger webhook notifications for completed crawl."""
    try:
        webhook_service = WebhookService()
        db = SessionLocal()

        try:
            webhooks = webhook_service.get_active_webhooks(
                db, crawl_run.project, event_type="crawl.completed"
            )

            for webhook in webhooks:
                webhook_id = int(webhook.id) if webhook.id else None
                if webhook_id is None:
                    continue
                webhook_service.queue_webhook_delivery(
                    db,
                    webhook_id,
                    {
                        "event": "crawl.completed",
                        "crawl_run_id": crawl_run.id,
                        "project": crawl_run.project,
                        "spider_name": crawl_run.spider.name if crawl_run.spider else None,
                        "status": crawl_run.status,
                        "items_scraped": crawl_run.items_scraped,
                        "duration_seconds": crawl_run.duration_seconds,
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
