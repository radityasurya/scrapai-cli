# Development Guide

Architecture, debugging, and extending ScrapAI.

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Core Components](#core-components)
- [Data Flow](#data-flow)
- [Database Schema](#database-schema)
- [Adding New Features](#adding-new-features)
- [Debugging](#debugging)
- [Performance Profiling](#performance-profiling)
- [Extension Points](#extension-points)

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLI Layer                                │
│  scrapai → cli/ → commands (crawl, analyze, health, etc.)       │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Core Layer                                │
│  core/spider.py (DatabaseSpider)  core/db.py (SQLAlchemy)       │
└─────────────────────────────────────────────────────────────────┘
                                │
                ┌───────────────┴───────────────┐
                ▼                               ▼
┌───────────────────────────┐   ┌───────────────────────────┐
│     Scrapy Framework      │   │     API Layer (FastAPI)   │
│  - middlewares.py         │   │  - api/routers/           │
│  - pipelines.py           │   │  - api/main.py            │
│  - settings.py            │   │  - api/config.py          │
└───────────────────────────┘   └───────────────────────────┘
                │                               │
                └───────────────┬───────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Storage Layer                                │
│  SQLite/PostgreSQL (spiders, crawl_logs)   Redis (queues, cache)│
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Background Workers                             │
│  workers/crawl_worker.py (Dramatiq + Redis)                     │
└─────────────────────────────────────────────────────────────────┘
```

## Core Components

### DatabaseSpider (`core/spider.py`)

The single generic spider that loads configs from the database:

```python
class DatabaseSpider(Spider):
    """
    Generic spider that loads configuration from database.

    Key methods:
    - from_database(name): Load spider config from DB
    - parse_item(response): Extract data using config selectors
    - parse_*(): Custom callbacks defined in config
    """

    @classmethod
    def from_database(cls, spider_name: str) -> "DatabaseSpider":
        """Load spider configuration from database."""
        config = get_spider_config(spider_name)
        return cls(
            name=config.name,
            allowed_domains=config.allowed_domains,
            start_urls=config.start_urls,
            rules=build_rules(config.rules),
        )

    def parse_item(self, response):
        """Extract fields using config selectors."""
        for field, selector in self.config.fields.items():
            # Use newspaper, trafilatura, or CSS selectors
            ...
```

### Database Models (`core/db.py`)

SQLAlchemy models for the database:

```python
class SpiderConfig(Base):
    """Spider configuration stored in database."""
    __tablename__ = "spider_configs"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    project = Column(String, index=True)
    allowed_domains = Column(JSON)
    start_urls = Column(JSON)
    rules = Column(JSON)
    fields = Column(JSON)
    settings = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)

class CrawlLog(Base):
    """Log of crawl runs."""
    __tablename__ = "crawl_logs"

    id = Column(Integer, primary_key=True)
    spider_name = Column(String, index=True)
    status = Column(String)  # running, completed, failed
    items_scraped = Column(Integer)
    pages_crawled = Column(Integer)
    started_at = Column(DateTime)
    finished_at = Column(DateTime)
    error_message = Column(Text)
```

### Middlewares (`middlewares.py`)

```python
class SmartProxyMiddleware:
    """
    Intelligent proxy middleware.

    - Only uses proxy when needed (403/429 errors)
    - Learns which domains require proxy
    - Supports datacenter and residential proxies
    """

    def process_request(self, request, spider):
        if self._needs_proxy(request.url):
            request.meta["proxy"] = self._get_proxy_url()

    def process_response(self, request, response, spider):
        if response.status in [403, 429]:
            self._mark_domain_as_blocked(request.url)
            return request.replace(dont_filter=True)  # Retry with proxy
        return response
```

### Pipelines (`pipelines.py`)

```python
class DatabasePipeline:
    """Store scraped items in database."""

    def process_item(self, item, spider):
        # Validate item
        # Store in database
        # Return item for next pipeline

class S3UploadPipeline:
    """Upload results to S3."""

    def close_spider(self, spider):
        if is_s3_configured():
            upload_to_s3(spider.output_file)
```

## Data Flow

### Crawl Flow

```
1. CLI Command
   ./scrapai crawl myspider

2. Load Config
   DatabaseSpider.from_database("myspider")
   → Query spider_configs table
   → Build Scrapy spider with rules

3. Start Crawl
   CrawlerProcess.crawl(spider)
   → Scrapy engine starts
   → Downloads pages

4. Extract Data
   parse_item(response)
   → Apply selectors from config
   → Use newspaper/trafilatura/custom

5. Process Items
   ItemPipeline.process_item()
   → Validate
   → Store in DB
   → Upload to S3

6. Output
   data/projects/myproject/outputs/myspider.jsonl
```

### API Flow

```
1. Request
   POST /api/v1/crawls
   {"spider": "myspider", "urls": [...]}

2. Queue Job
   Dramatiq actor.enqueue()
   → Redis queue

3. Worker Picks Up
   crawl_worker.run_crawl()
   → Runs Scrapy crawl

4. Store Results
   → Database (crawl_logs)
   → File system (JSONL)

5. Return Response
   {"crawl_id": "...", "status": "queued"}

6. Poll Status
   GET /api/v1/crawls/{id}/status
   → {"status": "completed", "items": 150}
```

## Database Schema

### ER Diagram

```
spider_configs
├── id (PK)
├── name (unique)
├── project
├── allowed_domains (JSON)
├── start_urls (JSON)
├── rules (JSON)
├── fields (JSON)
├── settings (JSON)
└── timestamps

crawl_logs
├── id (PK)
├── spider_name (FK → spider_configs.name)
├── status
├── items_scraped
├── pages_crawled
├── started_at
├── finished_at
└── error_message

crawl_results
├── id (PK)
├── crawl_id (FK → crawl_logs.id)
├── url
├── data (JSON)
└── scraped_at
```

### Migrations

```bash
# Create migration
alembic revision --autogenerate -m "Add new table"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

## Adding New Features

### Add a New CLI Command

```python
# cli/mycommand_cmd.py
import click
from core.db import get_session

@click.command()
@click.option("--project", "-p", required=True)
def mycommand(project: str):
    """My new command."""
    session = get_session()
    # Implementation
    click.echo(f"Done: {project}")

# cli/__init__.py
from cli.mycommand_cmd import mycommand

commands.add_command(mycommand, "mycommand")
```

### Add a New Extractor

```python
# utils/extractors.py
def extract_with_my_extractor(html: str, url: str) -> dict:
    """Extract content using my custom extractor."""
    # Implementation
    return {
        "title": "...",
        "content": "...",
        "author": "...",
    }

# In spider config
{
    "extractor": "my_extractor",
    "fields": {...}
}

# In DatabaseSpider.parse_item()
if self.config.extractor == "my_extractor":
    item = extract_with_my_extractor(response.text, response.url)
```

### Add a New API Endpoint

```python
# api/routers/myrouter.py
from fastapi import APIRouter, Depends

router = APIRouter()

@router.get("/myendpoint")
async def my_endpoint():
    """My new endpoint."""
    return {"status": "ok"}

# api/main.py
from api.routers import myrouter
app.include_router(myrouter.router, prefix="/api/v1/my", tags=["my"])
```

### Add a New Middleware

```python
# middlewares.py
class MyMiddleware:
    """My custom middleware."""

    def __init__(self):
        self.stats = {}

    def process_request(self, request, spider):
        # Before request is sent
        request.meta["start_time"] = time.time()

    def process_response(self, request, response, spider):
        # After response is received
        duration = time.time() - request.meta["start_time"]
        self.stats[request.url] = duration
        return response

# settings.py
DOWNLOADER_MIDDLEWARES = {
    "middlewares.MyMiddleware": 400,
}
```

## Debugging

### Enable Debug Logging

```bash
# Environment variable
LOG_LEVEL=DEBUG

# CLI flag
./scrapai crawl myspider --verbose --log-level DEBUG

# In code
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Interactive Debugging

```python
# Add breakpoint
import pdb; pdb.set_trace()

# Or with IPython
import IPython; IPython.embed()

# Or with debugpy (VS Code)
import debugpy
debugpy.listen(5678)
debugpy.wait_for_client()
```

### Scrapy Shell

```bash
# Test selectors interactively
scrapy shell "https://example.com/article"

# In shell:
>>> response.css("h1::text").get()
>>> response.xpath("//div[@class='content']").get()
```

### Database Queries

```python
# Interactive session
from core.db import get_session, SpiderConfig

session = get_session()
configs = session.query(SpiderConfig).all()
for config in configs:
    print(f"{config.name}: {config.start_urls}")
```

### Redis Debugging

```bash
# Connect to Redis
redis-cli

# List all keys
KEYS *

# Get value
GET scrapai:api:some_key

# Monitor commands
MONITOR
```

## Performance Profiling

### Profile Spider

```python
import cProfile
import pstats

# Profile crawl
profiler = cProfile.Profile()
profiler.enable()

# Run crawl
profiler.disable()

# View results
stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')
stats.print_stats(20)
```

### Memory Profiling

```python
# Install memory_profiler
pip install memory-profiler

# Add decorator
from memory_profiler import profile

@profile
def parse_item(self, response):
    # Your code
    pass

# Run with
python -m memory_profiler your_script.py
```

### Database Query Profiling

```python
# Enable SQLAlchemy echo
engine = create_engine(DATABASE_URL, echo=True)

# Or use query logging
import logging
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)
```

## Extension Points

### Plugin System

```python
# plugins/base.py
from abc import ABC, abstractmethod

class SpiderPlugin(ABC):
    """Base class for spider plugins."""

    @abstractmethod
    def before_crawl(self, spider):
        """Called before crawl starts."""
        pass

    @abstractmethod
    def after_crawl(self, spider, stats):
        """Called after crawl finishes."""
        pass

    @abstractmethod
    def process_item(self, item, spider):
        """Process each scraped item."""
        return item

# plugins/my_plugin.py
class MyPlugin(SpiderPlugin):
    def before_crawl(self, spider):
        print(f"Starting {spider.name}")

    def after_crawl(self, spider, stats):
        print(f"Finished: {stats}")

    def process_item(self, item, spider):
        item["plugin_processed"] = True
        return item

# Register plugin
# In settings.py
SPIDER_PLUGINS = ["plugins.my_plugin.MyPlugin"]
```

### Custom Selectors

```python
# Add custom selector type
def extract_json_ld(response):
    """Extract JSON-LD structured data."""
    scripts = response.css('script[type="application/ld+json"]::text').getall()
    for script in scripts:
        data = json.loads(script)
        if data.get("@type") == "NewsArticle":
            return {
                "title": data.get("headline"),
                "author": data.get("author", {}).get("name"),
                "date": data.get("datePublished"),
            }
    return {}

# Use in spider config
{
    "fields": {
        "title": {"type": "json_ld", "path": "headline"},
        "author": {"type": "json_ld", "path": "author.name"}
    }
}
```

### Event Hooks

```python
# hooks.py
from typing import Callable, Dict, Any

class EventHooks:
    """Event hook system."""

    def __init__(self):
        self._hooks: Dict[str, list[Callable]] = {
            "spider.opened": [],
            "spider.closed": [],
            "item.scraped": [],
            "request.scheduled": [],
            "response.received": [],
        }

    def register(self, event: str, callback: Callable):
        """Register a callback for an event."""
        self._hooks[event].append(callback)

    def trigger(self, event: str, *args, **kwargs):
        """Trigger all callbacks for an event."""
        for callback in self._hooks.get(event, []):
            callback(*args, **kwargs)

# Usage
hooks = EventHooks()

@hooks.register("spider.closed")
def log_completion(spider, reason, stats):
    print(f"Spider {spider.name} closed: {reason}")
```

## Testing Extensions

```python
# tests/test_my_extension.py
import pytest
from unittest.mock import Mock

def test_my_plugin():
    plugin = MyPlugin()
    spider = Mock(name="test_spider")

    plugin.before_crawl(spider)

    item = {"title": "Test"}
    result = plugin.process_item(item, spider)

    assert result["plugin_processed"] is True
```

## Contributing Extensions

1. Create feature branch
2. Add extension in appropriate directory
3. Add tests
4. Update documentation
5. Submit pull request

See [CONTRIBUTING.md](../CONTRIBUTING.md) for details.
