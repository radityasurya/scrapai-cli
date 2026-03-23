"""
Spider service for creating and managing spiders.

Extracts logic from CLI for reuse in API endpoints.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from pydantic import ValidationError
from sqlalchemy.orm import Session

from core.models import Spider, SpiderRule, SpiderSetting
from core.schemas import SpiderConfigSchema

logger = logging.getLogger(__name__)


class SpiderService:
    """Service for spider CRUD operations."""

    def create_spider(
        self,
        db: Session,
        config: Dict[str, Any],
        project: str = "default",
        skip_validation: bool = False,
    ) -> Spider:
        """
        Create a new spider from configuration dict.

        Args:
            db: Database session
            config: Spider configuration dict (SpiderConfigSchema format)
            project: Project name
            skip_validation: Skip Pydantic validation

        Returns:
            Created Spider object

        Raises:
            ValueError: If validation fails or spider already exists with conflicts
        """
        # Validate with Pydantic schema
        if skip_validation:
            validated = None
            spider_name = config["name"]
            allowed_domains = config["allowed_domains"]
            start_urls = config["start_urls"]
            source_url = config.get("source_url")
            rules = config.get("rules", [])
            settings_dict = config.get("settings", {})
            callbacks_dict = config.get("callbacks")
        else:
            try:
                validated = SpiderConfigSchema(**config)
                spider_name = validated.name
                allowed_domains = validated.allowed_domains
                start_urls = validated.start_urls
                source_url = validated.source_url
                rules = [r.model_dump() for r in validated.rules]
                settings_dict = validated.settings.model_dump(exclude_none=True, exclude_unset=True)
                callbacks_dict = None
                if validated.callbacks:
                    callbacks_dict = {
                        name: cb.model_dump() for name, cb in validated.callbacks.items()
                    }
            except ValidationError as e:
                errors = []
                for error in e.errors():
                    field = " -> ".join(str(x) for x in error["loc"])
                    errors.append(f"{field}: {error['msg']}")
                raise ValueError(f"Validation failed: {'; '.join(errors)}")

        # Check for existing spider
        existing = (
            db.query(Spider).filter(Spider.name == spider_name, Spider.project == project).first()
        )
        if existing:
            raise ValueError(f"Spider '{spider_name}' already exists in project '{project}'")

        # Create new spider
        spider = Spider(
            name=spider_name,
            allowed_domains=allowed_domains,
            start_urls=start_urls,
            source_url=source_url,
            project=project,
            callbacks_config=callbacks_dict,
            active=True,
        )
        db.add(spider)
        db.flush()

        # Add rules
        for rule_data in rules:
            rule = SpiderRule(
                spider_id=spider.id,
                allow_patterns=rule_data.get("allow"),
                deny_patterns=rule_data.get("deny"),
                restrict_xpaths=rule_data.get("restrict_xpaths"),
                restrict_css=rule_data.get("restrict_css"),
                callback=rule_data.get("callback"),
                follow=rule_data.get("follow", True),
                priority=rule_data.get("priority", 0),
            )
            db.add(rule)

        # Add settings
        for k, v in settings_dict.items():
            if isinstance(v, (list, dict)):
                value_str = json.dumps(v)
                type_name = "json"
            else:
                value_str = str(v)
                type_name = type(v).__name__

            setting = SpiderSetting(spider_id=spider.id, key=k, value=value_str, type=type_name)
            db.add(setting)

        db.commit()
        db.refresh(spider)

        logger.info(f"Created spider '{spider_name}' in project '{project}'")
        return spider

    def update_spider(
        self,
        db: Session,
        spider_id: int,
        config: Dict[str, Any],
        skip_validation: bool = False,
    ) -> Spider:
        """
        Update an existing spider from configuration dict.

        Args:
            db: Database session
            spider_id: Spider ID to update
            config: Spider configuration dict (SpiderConfigSchema format)
            skip_validation: Skip Pydantic validation

        Returns:
            Updated Spider object

        Raises:
            ValueError: If validation fails or spider not found
        """
        spider = db.query(Spider).filter(Spider.id == spider_id).first()
        if not spider:
            raise ValueError(f"Spider {spider_id} not found")

        # Validate with Pydantic schema
        if skip_validation:
            validated = None
            spider_name = config.get("name", spider.name)
            allowed_domains = config.get("allowed_domains", spider.allowed_domains)
            start_urls = config.get("start_urls", spider.start_urls)
            source_url = config.get("source_url", spider.source_url)
            rules = config.get("rules", [])
            settings_dict = config.get("settings", {})
            callbacks_dict = config.get("callbacks")
        else:
            try:
                validated = SpiderConfigSchema(**config)
                spider_name = validated.name
                allowed_domains = validated.allowed_domains
                start_urls = validated.start_urls
                source_url = validated.source_url
                rules = [r.model_dump() for r in validated.rules]
                settings_dict = validated.settings.model_dump(exclude_none=True, exclude_unset=True)
                callbacks_dict = None
                if validated.callbacks:
                    callbacks_dict = {
                        name: cb.model_dump() for name, cb in validated.callbacks.items()
                    }
            except ValidationError as e:
                errors = []
                for error in e.errors():
                    field = " -> ".join(str(x) for x in error["loc"])
                    errors.append(f"{field}: {error['msg']}")
                raise ValueError(f"Validation failed: {'; '.join(errors)}")

        # Check name uniqueness if changing
        if spider_name != spider.name:
            existing = (
                db.query(Spider)
                .filter(
                    Spider.name == spider_name,
                    Spider.project == spider.project,
                    Spider.id != spider_id,
                )
                .first()
            )
            if existing:
                raise ValueError(
                    f"Spider '{spider_name}' already exists in project '{spider.project}'"
                )

        # Update spider fields
        spider.name = spider_name
        spider.allowed_domains = allowed_domains
        spider.start_urls = start_urls
        spider.source_url = source_url
        spider.callbacks_config = callbacks_dict

        # Delete old rules and settings
        db.query(SpiderRule).filter(SpiderRule.spider_id == spider.id).delete()
        db.query(SpiderSetting).filter(SpiderSetting.spider_id == spider.id).delete()

        # Add new rules
        for rule_data in rules:
            rule = SpiderRule(
                spider_id=spider.id,
                allow_patterns=rule_data.get("allow"),
                deny_patterns=rule_data.get("deny"),
                restrict_xpaths=rule_data.get("restrict_xpaths"),
                restrict_css=rule_data.get("restrict_css"),
                callback=rule_data.get("callback"),
                follow=rule_data.get("follow", True),
                priority=rule_data.get("priority", 0),
            )
            db.add(rule)

        # Add new settings
        for k, v in settings_dict.items():
            if isinstance(v, (list, dict)):
                value_str = json.dumps(v)
                type_name = "json"
            else:
                value_str = str(v)
                type_name = type(v).__name__

            setting = SpiderSetting(spider_id=spider.id, key=k, value=value_str, type=type_name)
            db.add(setting)

        db.commit()
        db.refresh(spider)

        logger.info(f"Updated spider '{spider_name}' (ID: {spider_id})")
        return spider

    def delete_spider(self, db: Session, spider_id: int) -> bool:
        """
        Soft delete a spider (set active=False).

        Args:
            db: Database session
            spider_id: Spider ID to delete

        Returns:
            True if deleted

        Raises:
            ValueError: If spider not found
        """
        spider = db.query(Spider).filter(Spider.id == spider_id).first()
        if not spider:
            raise ValueError(f"Spider {spider_id} not found")

        spider.active = False
        db.commit()

        logger.info(f"Soft deleted spider '{spider.name}' (ID: {spider_id})")
        return True

    def get_spider(self, db: Session, spider_id: int) -> Optional[Spider]:
        """Get a spider by ID."""
        return db.query(Spider).filter(Spider.id == spider_id).first()

    def get_spider_by_name(self, db: Session, name: str, project: str) -> Optional[Spider]:
        """Get a spider by name and project."""
        return db.query(Spider).filter(Spider.name == name, Spider.project == project).first()

    def list_spiders(
        self,
        db: Session,
        project: Optional[str] = None,
        active_only: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Spider]:
        """List spiders with optional filters."""
        query = db.query(Spider)

        if project:
            query = query.filter(Spider.project == project)

        if active_only:
            query = query.filter(Spider.active.is_(True))

        return query.order_by(Spider.name).offset(offset).limit(limit).all()
