from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import relationship

from .db import Base


def _utcnow():
    """Return current UTC time."""
    return datetime.now(timezone.utc)


class Spider(Base):
    __tablename__ = "spiders"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    allowed_domains = Column(JSON, nullable=False)
    start_urls = Column(JSON, nullable=False)
    source_url = Column(String, nullable=True)
    active = Column(Boolean, default=True)
    project = Column(String(255), default="default")
    callbacks_config = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    rules = relationship("SpiderRule", back_populates="spider", cascade="all, delete-orphan")
    settings = relationship("SpiderSetting", back_populates="spider", cascade="all, delete-orphan")
    items = relationship("ScrapedItem", back_populates="spider", cascade="all, delete-orphan")


class SpiderRule(Base):
    __tablename__ = "spider_rules"

    id = Column(Integer, primary_key=True, index=True)
    spider_id = Column(Integer, ForeignKey("spiders.id"), nullable=False)

    allow_patterns = Column(JSON, nullable=True)
    deny_patterns = Column(JSON, nullable=True)
    restrict_xpaths = Column(JSON, nullable=True)
    restrict_css = Column(JSON, nullable=True)

    callback = Column(String, nullable=True, default=None)
    follow = Column(Boolean, default=True)
    priority = Column(Integer, default=0)

    spider = relationship("Spider", back_populates="rules")


class SpiderSetting(Base):
    __tablename__ = "spider_settings"

    id = Column(Integer, primary_key=True, index=True)
    spider_id = Column(Integer, ForeignKey("spiders.id"), nullable=False)

    key = Column(String, nullable=False)
    value = Column(String, nullable=False)
    type = Column(String, default="string")

    spider = relationship("Spider", back_populates="settings")


class ScrapedItem(Base):
    __tablename__ = "scraped_items"

    id = Column(Integer, primary_key=True, index=True)
    spider_id = Column(Integer, ForeignKey("spiders.id"), nullable=False)
    crawl_run_id = Column(Integer, ForeignKey("crawl_runs.id"), nullable=True, index=True)

    url = Column(String, index=True, nullable=False)
    title = Column(String, nullable=True)
    content = Column(Text, nullable=True)
    published_date = Column(DateTime, nullable=True)
    author = Column(String, nullable=True)
    scraped_at = Column(DateTime, default=_utcnow)
    metadata_json = Column(JSON, nullable=True)

    spider = relationship("Spider", back_populates="items")
    crawl_run = relationship("CrawlRun", backref="items")


class CrawlQueue(Base):
    __tablename__ = "crawl_queue"

    id = Column(Integer, primary_key=True, index=True)
    project_name = Column(String(255), nullable=False, default="default")
    website_url = Column(Text, nullable=False)
    custom_instruction = Column(Text, nullable=True)
    status = Column(String(50), nullable=False, default="pending")
    priority = Column(Integer, nullable=False, default=5)
    processing_by = Column(String(255), nullable=True)
    locked_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)
    completed_at = Column(DateTime, nullable=True)


class CrawlRun(Base):
    __tablename__ = "crawl_runs"

    id = Column(Integer, primary_key=True, index=True)
    project = Column(String(255), nullable=False, default="default")
    spider_id = Column(Integer, ForeignKey("spiders.id"), nullable=False)
    trigger_source = Column(String(50), nullable=False, default="cli")
    trigger_actor = Column(String(255), nullable=True)
    status = Column(String(50), nullable=False, default="queued")
    requested_limit = Column(Integer, nullable=True)
    output_mode = Column(String(50), nullable=False, default="db")
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    items_scraped = Column(Integer, nullable=True, default=0)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    spider = relationship("Spider", backref="crawl_runs")
    validation_report = relationship("CrawlValidationReport", back_populates="crawl_run", uselist=False)

    @property
    def duration_seconds(self) -> int:
        if self.started_at and self.finished_at:
            delta = self.finished_at - self.started_at
            return int(delta.total_seconds())
        return 0


class CrawlValidationReport(Base):
    __tablename__ = "crawl_validation_reports"

    id = Column(Integer, primary_key=True, index=True)
    crawl_run_id = Column(Integer, ForeignKey("crawl_runs.id"), nullable=False, index=True)
    item_count = Column(Integer, nullable=False, default=0)
    avg_content_length = Column(Float, nullable=True)
    fields_missing_rate = Column(Float, nullable=True)  # 0.0-1.0
    degraded = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    crawl_run = relationship("CrawlRun", back_populates="validation_report")


class EventOutbox(Base):
    __tablename__ = "event_outbox"

    id = Column(Integer, primary_key=True, index=True)
    event_type = Column(String, nullable=False, index=True)
    aggregate_type = Column(String, nullable=False)
    aggregate_id = Column(Integer, nullable=False, index=True)
    payload = Column(JSON, nullable=False)
    published = Column(Boolean, nullable=False, default=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    published_at = Column(DateTime(timezone=True), nullable=True)


class APIKey(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    key_hash = Column(String(64), unique=True, nullable=False, index=True)
    project = Column(String(255), nullable=True)
    scopes = Column(JSON, nullable=True, default=list)
    active = Column(Boolean, default=True, nullable=False)
    last_used_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    revoked_by = Column(String(50), nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)


class WebhookSubscription(Base):
    __tablename__ = "webhook_subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    project = Column(String(255), nullable=False)
    target_url = Column(String(500), nullable=False)
    event_types = Column(JSON, nullable=False)
    secret = Column(String(255), nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"

    id = Column(Integer, primary_key=True, index=True)
    subscription_id = Column(Integer, ForeignKey("webhook_subscriptions.id"), nullable=False)
    event_type = Column(String(100), nullable=False)
    payload = Column(JSON, nullable=False)
    status = Column(String(50), nullable=False, default="pending")
    attempt = Column(Integer, default=0)
    delivered_at = Column(DateTime, nullable=True)
    response_status = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    subscription = relationship("WebhookSubscription", backref="deliveries")
