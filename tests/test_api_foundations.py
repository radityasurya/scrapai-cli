"""API foundation endpoint tests with dependency overrides."""

import hashlib
import hmac
import json
import os
import tempfile
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api import deps
from api.main import app
from core.models import APIKey, Base, Spider, WebhookSubscription


@pytest.fixture
def api_client() -> Generator[tuple[TestClient, sessionmaker], None, None]:
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    engine = create_engine(f"sqlite:///{db_path}")
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    def override_api_key():
        return APIKey(
            id=1,
            name="test-key",
            key_hash="hash",
            project="demo",
            active=True,
        )

    app.dependency_overrides[deps.get_db_session] = override_db
    app.dependency_overrides[deps.get_api_key] = override_api_key

    client = TestClient(app)

    try:
        yield client, TestingSessionLocal
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
        os.close(db_fd)
        os.unlink(db_path)


def test_spider_analyze_endpoint(api_client, monkeypatch):
    client, _ = api_client

    async def fake_analyze_url(self, url, project, use_browser):
        return {
            "success": True,
            "url": url,
            "domain": "job-boards.greenhouse.io",
            "suggested_name": "stackblitz_greenhouse",
            "detected_platform": "greenhouse",
            "analysis_mode": "template",
            "confidence_score": 0.95,
            "warnings": [],
            "analysis": {"job_links_detected": 10},
            "suggested_config": {"name": "stackblitz_greenhouse", "project": project},
        }

    monkeypatch.setattr(
        "api.routers.spiders.SpiderAnalysisService.analyze_url",
        fake_analyze_url,
    )

    response = client.post(
        "/api/v1/spiders/analyze",
        json={
            "url": "https://job-boards.greenhouse.io/stackblitz",
            "project": "demo",
            "use_browser": False,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["detected_platform"] == "greenhouse"
    assert data["analysis_mode"] == "template"
    assert data["suggested_name"] == "stackblitz_greenhouse"


def test_spider_create_update_delete_flow(api_client, monkeypatch):
    client, SessionLocal = api_client

    from services.rate_limit_service import RateLimitService

    monkeypatch.setattr(
        RateLimitService,
        "check_rate_limit",
        lambda self, identifier, limit=100, window_seconds=60: {"allowed": True},
    )

    create_response = client.post(
        "/api/v1/spiders?project=demo",
        json={
            "name": "example_com",
            "source_url": "https://example.com/jobs",
            "allowed_domains": ["example.com"],
            "start_urls": ["https://example.com/jobs"],
            "rules": [],
            "settings": {"DOWNLOAD_DELAY": 1.0},
        },
    )

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["action"] == "created"
    spider_id = created["spider_id"]

    update_response = client.put(
        f"/api/v1/spiders/{spider_id}",
        json={
            "name": "example_com",
            "source_url": "https://example.com/jobs",
            "allowed_domains": ["example.com"],
            "start_urls": ["https://example.com/careers"],
            "rules": [],
            "settings": {"CONCURRENT_REQUESTS": 2},
        },
    )

    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["action"] == "updated"
    assert updated["start_urls"] == ["https://example.com/careers"]

    delete_response = client.delete(f"/api/v1/spiders/{spider_id}")
    assert delete_response.status_code == 200
    deleted = delete_response.json()
    assert deleted["active"] is False

    crawl_response = client.post(
        "/api/v1/crawls/",
        json={
            "spider_name": "example_com",
            "project": "demo",
            "output_mode": "db",
        },
    )
    assert crawl_response.status_code == 400
    assert "inactive" in crawl_response.json()["detail"]

    with SessionLocal() as db:
        spider = db.query(Spider).filter(Spider.id == spider_id).first()
        assert spider is not None
        assert spider.active is False


def test_webhook_subscription_crud(api_client):
    client, SessionLocal = api_client

    create_response = client.post(
        "/api/v1/webhooks/",
        json={
            "project": "demo",
            "target_url": "https://example.com/webhooks/scrapai",
            "event_types": ["crawl.completed", "crawl.failed"],
            "secret": "auto",
        },
    )

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["secret"]
    subscription_id = created["id"]

    list_response = client.get("/api/v1/webhooks/?project=demo")
    assert list_response.status_code == 200
    items = list_response.json()
    assert len(items) == 1
    assert items[0]["id"] == subscription_id

    delete_response = client.delete(f"/api/v1/webhooks/{subscription_id}")
    assert delete_response.status_code == 200
    assert delete_response.json()["success"] is True

    with SessionLocal() as db:
        subscription = (
            db.query(WebhookSubscription).filter(WebhookSubscription.id == subscription_id).first()
        )
        assert subscription is None


def test_webhook_worker_sends_documented_headers(api_client, monkeypatch):
    _, SessionLocal = api_client

    from core.models import WebhookDelivery, WebhookSubscription
    from apps.web_api.workers import webhook_worker

    with SessionLocal() as db:
        subscription = WebhookSubscription(
            project="demo",
            target_url="https://example.com/webhooks/scrapai",
            event_types=["crawl.completed"],
            secret="secret-value",
            active=True,
        )
        db.add(subscription)
        db.commit()
        db.refresh(subscription)

        payload = {
            "event": "crawl.completed",
            "event_type": "crawl.completed",
            "timestamp": "2026-06-24T00:00:00+00:00",
            "data": {"crawl_run_id": 123, "project": "demo"},
        }
        delivery = WebhookDelivery(
            subscription_id=subscription.id,
            event_type="crawl.completed",
            payload=payload,
            status="pending",
        )
        db.add(delivery)
        db.commit()
        db.refresh(delivery)
        delivery_id = int(getattr(delivery, "id"))

    captured = {}

    class FakeResponse:
        status_code = 204
        text = ""

    class FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, content, headers):
            captured["url"] = url
            captured["content"] = content
            captured["headers"] = headers
            return FakeResponse()

    monkeypatch.setattr(webhook_worker, "SessionLocal", SessionLocal)
    monkeypatch.setattr(webhook_worker.httpx, "Client", FakeClient)

    webhook_worker.webhook_actor.fn(delivery_id)

    body = json.dumps(payload, separators=(",", ":"))
    expected_signature = hmac.new(
        b"secret-value", body.encode(), hashlib.sha256
    ).hexdigest()

    assert captured["url"] == "https://example.com/webhooks/scrapai"
    assert captured["content"] == body
    assert captured["headers"]["X-Webhook-Signature"] == f"sha256={expected_signature}"
    assert captured["headers"]["X-Webhook-Event"] == "crawl.completed"
    assert captured["headers"]["X-Webhook-Timestamp"]
    assert captured["headers"]["X-ScrapAI-Signature"] == f"sha256={expected_signature}"

    with SessionLocal() as db:
        stored = db.query(WebhookDelivery).filter(WebhookDelivery.id == delivery_id).first()
        assert stored.status == "delivered"
