"""
API router for managing crawl runs.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import AsyncGenerator, List, Optional, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, validator
from sqlalchemy import func
from sqlalchemy.orm import Session

from core.models import APIKey, CrawlRun, ScrapedItem

from ...services.crawl_service import CrawlService
from ...services.rate_limit_service import RateLimitService
from ...services.redis_config import get_redis_client
from ...workers.crawl_worker import enqueue_crawl_job
from ..deps import ensure_project_access, get_api_key, get_db_session

logger = logging.getLogger(__name__)

router = APIRouter()


class CrawlRunCreate(BaseModel):
    """Schema for creating a crawl run."""

    spider_name: str
    project: str
    trigger_actor: Optional[str] = None
    requested_limit: Optional[int] = Field(None, gt=0, description="Maximum items to scrape")
    output_mode: str = Field("db", description="Output mode: db, file, or jsonl")

    @validator("output_mode")
    def validate_output_mode(cls, v):
        if v not in ["db", "file", "jsonl"]:
            raise ValueError("output_mode must be one of: db, file, jsonl")
        return v


class CrawlRunResponse(BaseModel):
    """Schema for crawl run response."""

    id: int
    spider_name: Optional[str] = None
    project: str
    status: str
    trigger_source: str
    trigger_actor: Optional[str]
    requested_limit: Optional[int]
    output_mode: str
    created_at: Optional[datetime]
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    error_message: Optional[str]
    items_scraped: Optional[int]
    duration_seconds: Optional[int]

    class Config:
        from_attributes = True


def _build_crawl_run_response(crawl_run: CrawlRun) -> CrawlRunResponse:
    item = cast(object, crawl_run)
    spider = crawl_run.spider
    spider_name = cast(Optional[str], getattr(spider, "name", None)) if spider else None

    return CrawlRunResponse(
        id=cast(int, getattr(item, "id")),
        spider_name=spider_name,
        project=cast(str, getattr(item, "project")),
        status=cast(str, getattr(item, "status")),
        trigger_source=cast(str, getattr(item, "trigger_source")),
        trigger_actor=cast(Optional[str], getattr(item, "trigger_actor")),
        requested_limit=cast(Optional[int], getattr(item, "requested_limit")),
        output_mode=cast(str, getattr(item, "output_mode")),
        created_at=cast(Optional[datetime], getattr(item, "created_at")),
        started_at=cast(Optional[datetime], getattr(item, "started_at")),
        finished_at=cast(Optional[datetime], getattr(item, "finished_at")),
        error_message=cast(Optional[str], getattr(item, "error_message")),
        items_scraped=cast(Optional[int], getattr(item, "items_scraped")),
        duration_seconds=crawl_run.duration_seconds,
    )


class BatchCrawlCreate(BaseModel):
    """Schema for creating multiple crawl runs in one request."""

    spider_names: List[str] = Field(min_length=1)
    project: str
    requested_limit: Optional[int] = Field(None, gt=0, description="Maximum items to scrape per spider")


class BatchCrawlRunItem(BaseModel):
    """Single crawl run entry in a batch response."""

    id: int
    spider_name: Optional[str] = None
    status: str


class BatchCrawlResponse(BaseModel):
    """Response for a batch crawl creation."""

    crawl_runs: List[BatchCrawlRunItem]


@router.post("/batch", response_model=BatchCrawlResponse)
async def create_batch_crawl_runs(
    batch: BatchCrawlCreate,
    db: Session = Depends(get_db_session),
    api_key: APIKey = Depends(get_api_key),
):
    """Create multiple crawl runs in a single request (max 10 spiders)."""
    ensure_project_access(api_key, batch.project)

    if len(batch.spider_names) > 10:
        raise HTTPException(
            status_code=400,
            detail="Batch request cannot exceed 10 spiders",
        )

    crawl_service = CrawlService()
    created_runs = []

    for spider_name in batch.spider_names:
        try:
            crawl_run = crawl_service.create_crawl_run(
                db=db,
                spider_name=spider_name,
                project=batch.project,
                trigger_source="api",
                trigger_actor=cast(str, getattr(api_key, "name")),
                requested_limit=batch.requested_limit,
                output_mode="db",
            )
            enqueue_crawl_job(cast(int, getattr(crawl_run, "id")))
            created_runs.append(
                BatchCrawlRunItem(
                    id=cast(int, getattr(crawl_run, "id")),
                    spider_name=spider_name,
                    status="queued",
                )
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error(f"Failed to create crawl run for spider {spider_name}: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to create crawl run for spider '{spider_name}': {str(e)}",
            )

    return BatchCrawlResponse(crawl_runs=created_runs)


@router.post("/", response_model=CrawlRunResponse)
async def create_crawl_run(
    crawl: CrawlRunCreate,
    db: Session = Depends(get_db_session),
    api_key: APIKey = Depends(get_api_key),
):
    """Create a new crawl run and queue it for execution."""
    ensure_project_access(api_key, crawl.project)

    rate_limit_service = RateLimitService()
    rate_limit_key = f"crawl:{api_key.project or 'global'}:{api_key.id}"
    rate_status = rate_limit_service.check_rate_limit(rate_limit_key, limit=10, window_seconds=60)

    if not rate_status["allowed"]:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    crawl_service = CrawlService()

    active_runs = crawl_service.get_active_runs_for_spider(db, crawl.project, crawl.spider_name)
    if active_runs:
        raise HTTPException(
            status_code=409,
            detail=f"Spider {crawl.spider_name} already has active run(s)",
        )

    try:
        crawl_run = crawl_service.create_crawl_run(
            db=db,
            spider_name=crawl.spider_name,
            project=crawl.project,
            trigger_source="api",
            trigger_actor=cast(str, getattr(api_key, "name")),
            requested_limit=crawl.requested_limit,
            output_mode=crawl.output_mode,
        )

        enqueue_crawl_job(cast(int, getattr(crawl_run, "id")))

        return _build_crawl_run_response(crawl_run)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create crawl run: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create crawl run: {str(e)}")


@router.get("/{crawl_run_id}", response_model=CrawlRunResponse)
async def get_crawl_run_status(
    crawl_run_id: int,
    db: Session = Depends(get_db_session),
    api_key: APIKey = Depends(get_api_key),
):
    """Get the status of a specific crawl run."""
    crawl_service = CrawlService()
    crawl_run = crawl_service.get_crawl_run(db, crawl_run_id)

    if not crawl_run:
        raise HTTPException(status_code=404, detail=f"Crawl run {crawl_run_id} not found")

    ensure_project_access(api_key, cast(str, getattr(crawl_run, "project")))

    return _build_crawl_run_response(crawl_run)


@router.get("/", response_model=List[CrawlRunResponse])
async def list_crawl_runs(
    project: str,
    spider_name: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(50, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db_session),
    api_key: APIKey = Depends(get_api_key),
):
    """List crawl runs for a project."""
    ensure_project_access(api_key, project)

    if status and status not in [
        "queued",
        "running",
        "completed",
        "failed",
        "cancelled",
    ]:
        raise HTTPException(status_code=400, detail="Invalid status")

    crawl_service = CrawlService()

    if spider_name:
        runs = crawl_service.get_crawl_runs_by_spider(
            db, project, spider_name, status, limit, offset
        )
    else:
        runs = crawl_service.get_crawl_runs_by_project(db, project, status, limit, offset)

    return [_build_crawl_run_response(run) for run in runs]


@router.post("/{crawl_run_id}/cancel")
async def cancel_crawl_run(
    crawl_run_id: int,
    db: Session = Depends(get_db_session),
    api_key: APIKey = Depends(get_api_key),
):
    """Cancel a crawl run."""
    crawl_service = CrawlService()
    crawl_run = crawl_service.get_crawl_run(db, crawl_run_id)

    if not crawl_run:
        raise HTTPException(status_code=404, detail=f"Crawl run {crawl_run_id} not found")

    ensure_project_access(api_key, cast(str, getattr(crawl_run, "project")))

    if cast(str, getattr(crawl_run, "status")) == "completed":
        raise HTTPException(status_code=400, detail="Cannot cancel completed crawl run")

    try:
        crawl_service.update_crawl_run_status(db, crawl_run_id, "cancelled")
        return {"status": "cancelled", "message": "Crawl run cancelled"}
    except Exception as e:
        logger.error(f"Failed to cancel crawl run: {e}")
        raise HTTPException(status_code=500, detail="Failed to cancel crawl run")


@router.get("/{crawl_run_id}/stream")
async def stream_crawl_progress(
    crawl_run_id: int,
    db: Session = Depends(get_db_session),
    api_key: APIKey = Depends(get_api_key),
):
    """Stream crawl progress via Server-Sent Events (SSE)."""
    crawl_service = CrawlService()
    crawl_run = crawl_service.get_crawl_run(db, crawl_run_id)

    if not crawl_run:
        raise HTTPException(status_code=404, detail=f"Crawl run {crawl_run_id} not found")

    ensure_project_access(api_key, cast(str, getattr(crawl_run, "project")))

    redis_client = get_redis_client()
    channel = f"scrapai:crawl:{crawl_run_id}"
    pubsub = redis_client.pubsub()
    pubsub.subscribe(channel)

    async def event_generator() -> AsyncGenerator[str, None]:
        last_status = cast(str, getattr(crawl_run, "status"))
        last_count = 0

        init_event = {"status": last_status, "crawl_run_id": crawl_run_id}
        yield f"event: crawl:init\ndata: {json.dumps(init_event)}\n\n"

        timeout = 300
        elapsed = 0
        poll_interval = 0.5

        while elapsed < timeout:
            message = pubsub.get_message(
                ignore_subscribe_messages=True,
                timeout=poll_interval,
            )

            if message and message["type"] == "message":
                data = message["data"]
                if isinstance(data, str):
                    yield f"data: {data}\n\n"
                    try:
                        event = json.loads(data)
                        if event.get("status") in ["completed", "failed", "cancelled"]:
                            return
                    except json.JSONDecodeError:
                        pass

            db.refresh(crawl_run)
            current_count = (
                db.query(func.count(ScrapedItem.id))
                .filter(ScrapedItem.crawl_run_id == crawl_run_id)
                .scalar()
                or 0
            )

            current_status = cast(str, getattr(crawl_run, "status"))

            if current_count != last_count or current_status != last_status:
                last_count = current_count
                last_status = current_status

                progress_event = {
                    "status": current_status,
                    "items_scraped": current_count,
                    "crawl_run_id": crawl_run_id,
                }
                yield f"event: crawl:progress\ndata: {json.dumps(progress_event)}\n\n"

                if current_status in ["completed", "failed", "cancelled"]:
                    return

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        timeout_event = {"status": "timeout", "crawl_run_id": crawl_run_id}
        yield f"event: crawl:timeout\ndata: {json.dumps(timeout_event)}\n\n"
        pubsub.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
