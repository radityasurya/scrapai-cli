"""
Results querying service for ScrapAI CLI.

Handles querying and filtering of scraped items.
"""

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from core.models import ScrapedItem, Spider

logger = logging.getLogger(__name__)


class ResultsService:
    """Service for querying scraped results."""

    def get_items(
        self,
        db: Session,
        spider_name: str,
        project: str,
        limit: int = 10,
        offset: int = 0,
        url_filter: Optional[str] = None,
        title_filter: Optional[str] = None,
        text_filter: Optional[str] = None,
        order_by: str = "scraped_at",
        order_desc: bool = True,
    ) -> List[ScrapedItem]:
        """Get scraped items with optional filters."""
        try:
            spider = (
                db.query(Spider)
                .filter(Spider.name == spider_name, Spider.project == project)
                .first()
            )

            if not spider:
                raise ValueError(f"Spider '{spider_name}' not found in project '{project}'")

            query = db.query(ScrapedItem).filter(ScrapedItem.spider_id == spider.id)

            if url_filter:
                query = query.filter(ScrapedItem.url.ilike(f"%{url_filter}%"))

            if title_filter:
                query = query.filter(ScrapedItem.title.ilike(f"%{title_filter}%"))

            if text_filter:
                query = query.filter(
                    or_(
                        ScrapedItem.title.ilike(f"%{text_filter}%"),
                        ScrapedItem.content.ilike(f"%{text_filter}%"),
                    )
                )

            order_column = getattr(ScrapedItem, order_by, ScrapedItem.scraped_at)
            if order_desc:
                query = query.order_by(order_column.desc())
            else:
                query = query.order_by(order_column.asc())

            return query.offset(offset).limit(limit).all()

        except Exception as e:
            logger.error(f"Failed to get items: {e}")
            raise

    def get_item_by_url(
        self, db: Session, url: str, project: Optional[str] = None
    ) -> Optional[ScrapedItem]:
        """Get a specific item by URL."""
        try:
            query = db.query(ScrapedItem).filter(ScrapedItem.url == url)

            if project:
                query = query.join(Spider).filter(Spider.project == project)

            return query.first()
        except Exception as e:
            logger.error(f"Failed to get item by URL: {e}")
            raise

    def get_item_count(self, db: Session, spider_name: str, project: str) -> int:
        """Get count of items for a spider."""
        try:
            spider = (
                db.query(Spider)
                .filter(Spider.name == spider_name, Spider.project == project)
                .first()
            )

            if not spider:
                return 0

            return db.query(ScrapedItem).filter(ScrapedItem.spider_id == spider.id).count()
        except Exception as e:
            logger.error(f"Failed to get item count: {e}")
            raise

    def get_latest_items(self, db: Session, project: str, limit: int = 10) -> List[ScrapedItem]:
        """Get latest items across all spiders in a project."""
        try:
            return (
                db.query(ScrapedItem)
                .join(Spider)
                .filter(Spider.project == project)
                .order_by(ScrapedItem.scraped_at.desc())
                .limit(limit)
                .all()
            )
        except Exception as e:
            logger.error(f"Failed to get latest items: {e}")
            raise

    def export_items(
        self,
        db: Session,
        spider_name: str,
        project: str,
        format: str = "json",
        url_filter: Optional[str] = None,
        title_filter: Optional[str] = None,
        text_filter: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Export items in specified format."""
        try:
            query_limit = limit if limit else None
            items = self.get_items(
                db,
                spider_name,
                project,
                limit=query_limit or 1000,
                url_filter=url_filter,
                title_filter=title_filter,
                text_filter=text_filter,
            )

            results = []
            spider = (
                db.query(Spider)
                .filter(Spider.name == spider_name, Spider.project == project)
                .first()
            )

            if not spider:
                return results

            callbacks_config = spider.callbacks_config or {}

            for item in items:
                row = {
                    "id": item.id,
                    "url": item.url,
                    "scraped_at": item.scraped_at.isoformat() if item.scraped_at else None,
                }

                callback_name = None
                if item.metadata_json and isinstance(item.metadata_json, dict):
                    callback_name = item.metadata_json.get("_callback")

                if callback_name and callback_name in callbacks_config:
                    extract_config = callbacks_config[callback_name].get("extract", {})
                    row["callback"] = callback_name

                    for field_name in extract_config.keys():
                        if field_name == "title":
                            row[field_name] = item.title
                        elif field_name == "content":
                            row[field_name] = item.content
                        elif field_name == "author":
                            row[field_name] = item.author
                        elif field_name == "published_date":
                            row[field_name] = (
                                item.published_date.isoformat() if item.published_date else None
                            )
                        else:
                            row[field_name] = (
                                item.metadata_json.get(field_name) if item.metadata_json else None
                            )

                    if item.metadata_json and isinstance(item.metadata_json, dict):
                        skip_keys = set(extract_config.keys()) | {"_callback"}
                        for key, value in item.metadata_json.items():
                            if key not in skip_keys and key not in row:
                                row[key] = value
                else:
                    row["title"] = item.title
                    row["content"] = item.content
                    row["author"] = item.author
                    row["published_date"] = (
                        item.published_date.isoformat() if item.published_date else None
                    )
                    if item.metadata_json:
                        row["metadata"] = item.metadata_json

                results.append(row)

            return results

        except Exception as e:
            logger.error(f"Failed to export items: {e}")
            raise
