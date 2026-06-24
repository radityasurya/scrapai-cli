"""
Crawl execution service for ScrapAI CLI.

Handles creation, management, and execution of crawl runs.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, cast

from sqlalchemy.orm import Session

from core.models import CrawlRun, Spider

logger = logging.getLogger(__name__)


class CrawlService:
    """Service for managing and executing crawl runs."""

    def create_crawl_run(
        self,
        db: Session,
        project: str,
        spider_name: str,
        trigger_source: str = "api",
        trigger_actor: Optional[str] = None,
        requested_limit: Optional[int] = None,
        output_mode: str = "db",
        **kwargs,
    ) -> CrawlRun:
        """Create a new crawl run record."""
        try:
            spider = (
                db.query(Spider)
                .filter(Spider.name == spider_name, Spider.project == project)
                .first()
            )

            if not spider:
                raise ValueError(f"Spider '{spider_name}' not found in project '{project}'")
            if not cast(bool, getattr(spider, "active")):
                raise ValueError(f"Spider '{spider_name}' in project '{project}' is inactive")

            crawl_run = CrawlRun(
                project=project,
                spider_id=spider.id,
                trigger_source=trigger_source,
                trigger_actor=trigger_actor,
                status="queued",
                requested_limit=requested_limit,
                output_mode=output_mode,
                **kwargs,
            )

            db.add(crawl_run)
            db.commit()
            db.refresh(crawl_run)

            logger.info(f"Created crawl run {crawl_run.id} for spider {spider_name}")
            return crawl_run

        except Exception as e:
            db.rollback()
            logger.error(f"Failed to create crawl run: {e}")
            raise

    def get_crawl_run(self, db: Session, crawl_run_id: int) -> Optional[CrawlRun]:
        """Get a crawl run by ID."""
        try:
            return db.query(CrawlRun).filter(CrawlRun.id == crawl_run_id).first()
        except Exception as e:
            logger.error(f"Failed to get crawl run {crawl_run_id}: {e}")
            raise

    def get_crawl_runs_by_project(
        self,
        db: Session,
        project: str,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[CrawlRun]:
        """Get crawl runs for a project with optional status filter."""
        try:
            query = db.query(CrawlRun).filter(CrawlRun.project == project)

            if status:
                if status not in [
                    "queued",
                    "running",
                    "completed",
                    "failed",
                    "cancelled",
                ]:
                    raise ValueError(f"Invalid status: {status}")
                query = query.filter(CrawlRun.status == status)

            return query.order_by(CrawlRun.created_at.desc()).offset(offset).limit(limit).all()
        except Exception as e:
            logger.error(f"Failed to get crawl runs for project {project}: {e}")
            raise

    def get_crawl_runs_by_spider(
        self,
        db: Session,
        project: str,
        spider_name: str,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[CrawlRun]:
        """Get crawl runs for a specific spider."""
        try:
            spider = (
                db.query(Spider)
                .filter(Spider.name == spider_name, Spider.project == project)
                .first()
            )

            if not spider:
                raise ValueError(f"Spider '{spider_name}' not found in project '{project}'")

            query = db.query(CrawlRun).filter(CrawlRun.spider_id == spider.id)

            if status:
                if status not in [
                    "queued",
                    "running",
                    "completed",
                    "failed",
                    "cancelled",
                ]:
                    raise ValueError(f"Invalid status: {status}")
                query = query.filter(CrawlRun.status == status)

            return query.order_by(CrawlRun.created_at.desc()).offset(offset).limit(limit).all()
        except Exception as e:
            logger.error(f"Failed to get crawl runs for spider {spider_name}: {e}")
            raise

    def update_crawl_run_status(
        self,
        db: Session,
        crawl_run_id: int,
        status: str,
        error_message: Optional[str] = None,
        items_scraped: Optional[int] = None,
    ) -> CrawlRun:
        """Update the status of a crawl run."""
        try:
            if status not in ["queued", "running", "completed", "failed", "cancelled"]:
                raise ValueError(f"Invalid status: {status}")

            crawl_run = self.get_crawl_run(db, crawl_run_id)
            if not crawl_run:
                raise ValueError(f"Crawl run {crawl_run_id} not found")

            run: Any = crawl_run

            run.status = status
            run.updated_at = datetime.now(timezone.utc)

            if status == "running" and not getattr(run, "started_at", None):
                run.started_at = datetime.now(timezone.utc)

            if status in ["completed", "failed", "cancelled"]:
                run.finished_at = datetime.now(timezone.utc)

            if error_message:
                run.error_message = error_message

            if items_scraped is not None:
                run.items_scraped = items_scraped

            db.commit()
            db.refresh(crawl_run)

            logger.info(f"Updated crawl run {crawl_run_id} status to {status}")
            return crawl_run

        except Exception as e:
            db.rollback()
            logger.error(f"Failed to update crawl run status: {e}")
            raise

    def get_crawl_run_stats(self, db: Session, crawl_run_id: int) -> Optional[Dict[str, Any]]:
        """Get statistics for a crawl run."""
        try:
            crawl_run = self.get_crawl_run(db, crawl_run_id)
            if not crawl_run:
                return None

            run: Any = crawl_run

            return {
                "id": run.id,
                "project": run.project,
                "spider_id": run.spider_id,
                "spider_name": run.spider.name if run.spider else None,
                "status": run.status,
                "trigger_source": run.trigger_source,
                "trigger_actor": run.trigger_actor,
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "finished_at": run.finished_at.isoformat() if run.finished_at else None,
                "error_message": run.error_message,
                "items_scraped": run.items_scraped,
                "duration_seconds": run.duration_seconds,
                "created_at": run.created_at.isoformat() if run.created_at else None,
                "updated_at": run.updated_at.isoformat() if run.updated_at else None,
            }
        except Exception as e:
            logger.error(f"Failed to get crawl run stats: {e}")
            raise

    def get_active_runs_for_spider(
        self, db: Session, project: str, spider_name: str
    ) -> List[CrawlRun]:
        """Get active (queued or running) crawl runs for a spider."""
        try:
            spider = (
                db.query(Spider)
                .filter(Spider.name == spider_name, Spider.project == project)
                .first()
            )

            if not spider:
                return []

            return (
                db.query(CrawlRun)
                .filter(
                    CrawlRun.spider_id == spider.id,
                    CrawlRun.status.in_(["queued", "running"]),
                )
                .all()
            )
        except Exception as e:
            logger.error(f"Failed to get active runs for spider {spider_name}: {e}")
            raise

    def emit_event(
        self,
        db: Session,
        event_type: str,
        aggregate_type: str,
        aggregate_id: int,
        payload: dict,
    ) -> None:
        """Write a lifecycle event to the outbox."""
        try:
            from core.models import EventOutbox

            entry = EventOutbox(
                event_type=event_type,
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                payload=payload,
            )
            db.add(entry)
            db.commit()
        except Exception as e:
            logger.error(f"Failed to write event to outbox: {e}")
            db.rollback()
