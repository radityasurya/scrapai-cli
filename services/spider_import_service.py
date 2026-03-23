"""
Spider import service for reusable CLI and API spider imports.
"""

import json
from typing import Any, Dict, Optional, cast
from urllib.parse import urlparse

from pydantic import ValidationError
from sqlalchemy.orm import Session

from core.models import Spider, SpiderRule, SpiderSetting
from core.schemas import SpiderConfigSchema


class SpiderImportService:
    """Service for importing spider configs from JSON sources."""

    async def import_spider_data(
        self,
        db: Session,
        data: Dict[str, Any],
        project: str = "default",
        skip_validation: bool = False,
    ) -> Dict[str, Any]:
        """Import or upsert a spider from a configuration dictionary."""
        try:
            parsed = self._parse_config(data, skip_validation)
            name_error = self._validate_spider_name(
                parsed["spider_name"], parsed["source_url"], project
            )
            if name_error:
                return {
                    "success": False,
                    "error": name_error,
                    "spider_name": parsed["spider_name"],
                    "project": project,
                }

            existing = db.query(Spider).filter(Spider.name == parsed["spider_name"]).first()
            return self._save_spider(
                db=db,
                parsed=parsed,
                project=project,
                spider=existing,
                action="updated" if existing else "created",
            )
        except ValueError as exc:
            db.rollback()
            return {"success": False, "error": str(exc), "project": project}
        except Exception as exc:
            db.rollback()
            return {
                "success": False,
                "error": f"Error importing spider: {exc}",
                "project": project,
            }

    async def update_spider_data(
        self,
        db: Session,
        spider_id: int,
        data: Dict[str, Any],
        skip_validation: bool = False,
    ) -> Dict[str, Any]:
        """Update a spider by ID from a configuration dictionary."""
        spider = db.query(Spider).filter(Spider.id == spider_id).first()
        if not spider:
            return {"success": False, "error": f"Spider {spider_id} not found"}

        try:
            parsed = self._parse_config(data, skip_validation)
            name_error = self._validate_spider_name(
                parsed["spider_name"],
                parsed["source_url"],
                cast(str, getattr(spider, "project")),
            )
            if name_error:
                return {
                    "success": False,
                    "error": name_error,
                    "project": cast(str, getattr(spider, "project")),
                }

            conflicting = (
                db.query(Spider)
                .filter(Spider.name == parsed["spider_name"], Spider.id != spider_id)
                .first()
            )
            if conflicting:
                return {
                    "success": False,
                    "error": f"Spider '{parsed['spider_name']}' already exists",
                    "project": cast(str, getattr(spider, "project")),
                }

            return self._save_spider(
                db=db,
                parsed=parsed,
                project=cast(str, getattr(spider, "project")),
                spider=spider,
                action="updated",
            )
        except ValueError as exc:
            db.rollback()
            return {
                "success": False,
                "error": str(exc),
                "project": cast(str, getattr(spider, "project")),
            }
        except Exception as exc:
            db.rollback()
            return {
                "success": False,
                "error": f"Error importing spider: {exc}",
                "project": cast(str, getattr(spider, "project")),
            }

    async def import_spider(
        self,
        db: Session,
        file_path: str,
        project: str = "default",
        skip_validation: bool = False,
        stdin_data: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Import or update a spider from a JSON file or stdin payload."""
        try:
            data = self._load_json(file_path, stdin_data)
            return await self.import_spider_data(
                db=db,
                data=data,
                project=project,
                skip_validation=skip_validation,
            )
        except FileNotFoundError:
            return {
                "success": False,
                "error": f"File not found: {file_path}",
                "project": project,
            }
        except json.JSONDecodeError as exc:
            return {
                "success": False,
                "error": f"Invalid JSON file: {exc}",
                "project": project,
            }
        except ValueError as exc:
            db.rollback()
            return {
                "success": False,
                "error": str(exc),
                "project": project,
            }
        except Exception as exc:
            db.rollback()
            return {
                "success": False,
                "error": f"Error importing spider: {exc}",
                "project": project,
            }

    def _load_json(self, file_path: str, stdin_data: Optional[str]) -> Dict[str, Any]:
        if file_path == "-":
            if stdin_data is None:
                raise ValueError("stdin_data is required when file_path is '-'")
            return json.loads(stdin_data)

        with open(file_path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    def _parse_config(self, data: Dict[str, Any], skip_validation: bool) -> Dict[str, Any]:
        if skip_validation:
            return {
                "spider_name": data["name"],
                "allowed_domains": data["allowed_domains"],
                "start_urls": data["start_urls"],
                "source_url": data.get("source_url"),
                "rules": data.get("rules", []),
                "settings_dict": data.get("settings", {}),
                "callbacks_dict": data.get("callbacks"),
            }

        try:
            validated = SpiderConfigSchema(**data)
        except ValidationError as exc:
            errors = []
            for error in exc.errors():
                field = " -> ".join(str(item) for item in error["loc"])
                errors.append(f"{field}: {error['msg']}")
            raise ValueError(
                "Spider configuration validation failed: " + "; ".join(errors)
            ) from exc

        callbacks_dict = None
        if validated.callbacks:
            callbacks_dict = {
                name: callback.model_dump() for name, callback in validated.callbacks.items()
            }

        return {
            "spider_name": validated.name,
            "allowed_domains": validated.allowed_domains,
            "start_urls": validated.start_urls,
            "source_url": validated.source_url,
            "rules": [rule.model_dump() for rule in validated.rules],
            "settings_dict": validated.settings.model_dump(exclude_none=True, exclude_unset=True),
            "callbacks_dict": callbacks_dict,
        }

    def _validate_spider_name(
        self, spider_name: str, source_url: Optional[str], project: str
    ) -> Optional[str]:
        if not source_url:
            return None

        parsed_url = urlparse(source_url)
        domain = parsed_url.netloc.replace("www.", "")
        expected_name = domain.replace(".", "_")

        if spider_name == expected_name:
            return None

        return (
            "Spider name mismatch detected! "
            f"Inspector created folder: data/{project}/{expected_name}/analysis/; "
            f"but spider name is '{spider_name}'; "
            f"crawls will save to: data/{project}/{spider_name}/crawls/. "
            f"Fix: change spider name to '{expected_name}' in the JSON config."
        )

    def _add_rules(self, db: Session, spider_id: int, rules: list[Dict[str, Any]]) -> None:
        for rule_data in rules:
            db.add(
                SpiderRule(
                    spider_id=spider_id,
                    allow_patterns=rule_data.get("allow"),
                    deny_patterns=rule_data.get("deny"),
                    restrict_xpaths=rule_data.get("restrict_xpaths"),
                    restrict_css=rule_data.get("restrict_css"),
                    callback=rule_data.get("callback"),
                    follow=rule_data.get("follow", True),
                    priority=rule_data.get("priority", 0),
                )
            )

    def _add_settings(self, db: Session, spider_id: int, settings_dict: Dict[str, Any]) -> None:
        for key, value in settings_dict.items():
            if isinstance(value, (list, dict)):
                value_str = json.dumps(value)
                type_name = "json"
            else:
                value_str = str(value)
                type_name = type(value).__name__

            db.add(
                SpiderSetting(
                    spider_id=spider_id,
                    key=key,
                    value=value_str,
                    type=type_name,
                )
            )

    def _save_spider(
        self,
        db: Session,
        parsed: Dict[str, Any],
        project: str,
        spider: Optional[Spider],
        action: str,
    ) -> Dict[str, Any]:
        if spider:
            item: Any = spider
            item.name = parsed["spider_name"]
            item.allowed_domains = parsed["allowed_domains"]
            item.start_urls = parsed["start_urls"]
            item.source_url = parsed["source_url"]
            item.project = project
            item.callbacks_config = parsed["callbacks_dict"]
            item.active = True

            db.query(SpiderRule).filter(SpiderRule.spider_id == item.id).delete()
            db.query(SpiderSetting).filter(SpiderSetting.spider_id == item.id).delete()
        else:
            spider = Spider(
                name=parsed["spider_name"],
                allowed_domains=parsed["allowed_domains"],
                start_urls=parsed["start_urls"],
                source_url=parsed["source_url"],
                project=project,
                callbacks_config=parsed["callbacks_dict"],
                active=True,
            )
            db.add(spider)
            db.flush()

        spider_id = cast(int, getattr(spider, "id"))

        self._add_rules(db, spider_id, parsed["rules"])
        self._add_settings(db, spider_id, parsed["settings_dict"])

        db.commit()
        db.refresh(spider)

        return {
            "success": True,
            "action": action,
            "spider_id": cast(int, getattr(spider, "id")),
            "spider_name": cast(str, getattr(spider, "name")),
            "project": cast(str, getattr(spider, "project")),
            "active": cast(bool, getattr(spider, "active")),
            "allowed_domains": parsed["allowed_domains"],
            "start_urls": parsed["start_urls"],
            "rules_count": len(parsed["rules"]),
            "callbacks": sorted((parsed["callbacks_dict"] or {}).keys()),
        }
