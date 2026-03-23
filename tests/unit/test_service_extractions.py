"""Unit tests for extracted reusable services."""

import asyncio
import json

from core.models import Spider, SpiderRule, SpiderSetting
from services.analyzer_service import AnalyzerService
from services.inspector_service import InspectorService
from services.spider_import_service import SpiderImportService


class TestAnalyzerService:
    def test_analyze_html_returns_structured_discovery(self, tmp_path):
        html_file = tmp_path / "sample.html"
        html_file.write_text(
            """
            <html><head><title>Example</title></head><body>
            <h1 class="page-title">Main Title</h1>
            <div class="article-content">%s</div>
            <time>2026-03-09</time>
            <span class="author-name">Jane Doe</span>
            </body></html>
            """ % ("A" * 260),
            encoding="utf-8",
        )

        result = asyncio.run(AnalyzerService().analyze_html(str(html_file)))

        assert result["success"] is True
        assert result["html_size"] > 0
        assert any(item["selector"] == "h1.page-title" for item in result["headers"])
        assert result["content_containers"]
        assert result["dates"][0]["text"] == "2026-03-09"
        assert result["authors"][0]["text"] == "Jane Doe"

    def test_test_selector_and_find_by_keyword(self, tmp_path):
        html_file = tmp_path / "sample.html"
        html_file.write_text(
            """
            <html><body>
            <div id="job-card">Backend Engineer</div>
            <div class="job-meta">Remote</div>
            </body></html>
            """,
            encoding="utf-8",
        )

        service = AnalyzerService()
        selector_result = asyncio.run(service.test_selector(str(html_file), "#job-card"))
        keyword_result = asyncio.run(service.find_by_keyword(str(html_file), "job"))

        assert selector_result["success"] is True
        assert selector_result["count"] == 1
        assert keyword_result["success"] is True
        assert keyword_result["count"] >= 2


class TestInspectorService:
    def test_inspect_url_returns_wrapped_result(self, monkeypatch):
        async def fake_inspect_page_async(**kwargs):
            return {
                "success": True,
                "url": kwargs["url"],
                "project": kwargs["project"],
                "mode": kwargs["mode"],
                "title": "Example",
            }

        monkeypatch.setattr(
            "services.inspector_service.inspect_page_async",
            fake_inspect_page_async,
        )

        result = asyncio.run(
            InspectorService().inspect_url(
                "https://example.com/jobs",
                project="demo",
                mode="http",
            )
        )

        assert result["success"] is True
        assert result["url"] == "https://example.com/jobs"
        assert result["project"] == "demo"


class TestSpiderImportService:
    def test_import_spider_creates_records(self, temp_db, tmp_path):
        config_file = tmp_path / "spider.json"
        config_file.write_text(
            json.dumps(
                {
                    "name": "example_com",
                    "source_url": "https://example.com/jobs",
                    "allowed_domains": ["example.com"],
                    "start_urls": ["https://example.com/jobs"],
                    "rules": [{"allow": ["/jobs/.*"], "callback": "parse_listing"}],
                    "settings": {"DOWNLOAD_DELAY": 1.0},
                    "callbacks": {
                        "parse_listing": {
                            "extract": {
                                "title": {"css": "h1::text"},
                                "description": {"css": "body", "get_all": True},
                            }
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

        result = asyncio.run(
            SpiderImportService().import_spider(
                db=temp_db,
                file_path=str(config_file),
                project="jobs",
            )
        )

        spider = temp_db.query(Spider).filter(Spider.name == "example_com").first()

        assert result["success"] is True
        assert result["action"] == "created"
        assert spider is not None
        assert spider.project == "jobs"
        assert temp_db.query(SpiderRule).filter(SpiderRule.spider_id == spider.id).count() == 1
        assert (
            temp_db.query(SpiderSetting).filter(SpiderSetting.spider_id == spider.id).count() == 1
        )

    def test_import_spider_updates_existing_spider(self, temp_db, tmp_path):
        spider = Spider(
            name="example_com",
            allowed_domains=["example.com"],
            start_urls=["https://example.com/jobs"],
            source_url="https://example.com/jobs",
            project="old",
            callbacks_config=None,
        )
        temp_db.add(spider)
        temp_db.commit()

        config_file = tmp_path / "spider.json"
        config_file.write_text(
            json.dumps(
                {
                    "name": "example_com",
                    "source_url": "https://example.com/jobs",
                    "allowed_domains": ["example.com"],
                    "start_urls": ["https://example.com/careers"],
                    "rules": [],
                    "settings": {"CONCURRENT_REQUESTS": 2},
                }
            ),
            encoding="utf-8",
        )

        result = asyncio.run(
            SpiderImportService().import_spider(
                db=temp_db,
                file_path=str(config_file),
                project="new-project",
            )
        )

        temp_db.refresh(spider)

        assert result["success"] is True
        assert result["action"] == "updated"
        assert spider.project == "new-project"
        assert spider.start_urls == ["https://example.com/careers"]
