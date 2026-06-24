"""Crawl quality scoring and validation report generation."""

import logging
from typing import Optional

from sqlalchemy.orm import Session

from core.models import CrawlValidationReport, ScrapedItem

logger = logging.getLogger(__name__)

# A run is degraded if avg content < 200 chars OR >30% of items have no content
DEGRADED_AVG_CONTENT_THRESHOLD = 200
DEGRADED_MISSING_RATE_THRESHOLD = 0.30


class ValidationService:
    def generate_report(self, db: Session, crawl_run_id: int) -> Optional[CrawlValidationReport]:
        """Score crawl quality and persist a validation report."""
        try:
            items = db.query(ScrapedItem).filter(ScrapedItem.crawl_run_id == crawl_run_id).all()
            item_count = len(items)

            if item_count == 0:
                avg_content_length = None
                fields_missing_rate = 1.0
                degraded = True
            else:
                content_lengths = [len(i.content or "") for i in items]
                avg_content_length = sum(content_lengths) / item_count
                missing = sum(1 for i in items if not i.content or len(i.content) < 50)
                fields_missing_rate = missing / item_count
                degraded = (
                    avg_content_length < DEGRADED_AVG_CONTENT_THRESHOLD
                    or fields_missing_rate > DEGRADED_MISSING_RATE_THRESHOLD
                )

            report = CrawlValidationReport(
                crawl_run_id=crawl_run_id,
                item_count=item_count,
                avg_content_length=avg_content_length,
                fields_missing_rate=fields_missing_rate,
                degraded=degraded,
            )
            db.add(report)
            db.commit()
            db.refresh(report)
            logger.info(
                f"[run={crawl_run_id}] Validation report: {item_count} items, degraded={degraded}"
            )
            return report
        except Exception as e:
            logger.error(f"[run={crawl_run_id}] Failed to generate validation report: {e}")
            db.rollback()
            return None
