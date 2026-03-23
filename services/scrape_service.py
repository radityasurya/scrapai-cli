"""
Single URL scraping service for ScrapAI CLI.

Handles scraping individual URLs using stored spider configurations.
"""

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


class ScrapeService:
    """Service for scraping individual URLs."""

    def scrape_url(self, spider_name: str, project: str, url: str) -> Dict[str, Any]:
        """Scrape a single URL using spider configuration."""
        from core.db import get_db
        from core.models import Spider

        db = next(get_db())
        try:
            spider = (
                db.query(Spider)
                .filter(Spider.name == spider_name, Spider.project == project)
                .first()
            )

            if not spider:
                raise ValueError(f"Spider '{spider_name}' not found in project '{project}'")

            logger.info(f"Scraping URL {url} with spider {spider_name}")

            return {
                "url": url,
                "spider": spider_name,
                "project": project,
                "status": "not_implemented",
            }

        except Exception as e:
            logger.error(f"Failed to scrape URL: {e}")
            raise
        finally:
            db.close()
