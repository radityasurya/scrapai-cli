"""
API router for scraped results.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.models import APIKey, ScrapedItem, Spider

from ..deps import ensure_project_access, get_api_key, get_db_session

logger = logging.getLogger(__name__)

router = APIRouter()


class ResultItemResponse(BaseModel):
    """Schema for a single scraped item."""

    id: int
    url: str
    title: Optional[str] = None
    content: Optional[str] = None
    author: Optional[str] = None
    published_date: Optional[datetime] = None
    scraped_at: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None
    spider_name: Optional[str] = None
    project: Optional[str] = None

    class Config:
        from_attributes = True


class ResultsListResponse(BaseModel):
    """Schema for paginated results list."""

    items: List[ResultItemResponse]
    total_count: int
    page: int
    page_size: int
    has_next: bool
    has_previous: bool


def _build_result_item_response(item: ScrapedItem) -> ResultItemResponse:
    record = cast(Any, item)
    spider = item.spider
    return ResultItemResponse(
        id=cast(int, getattr(record, "id")),
        url=cast(str, getattr(record, "url")),
        title=cast(Optional[str], getattr(record, "title")),
        content=cast(Optional[str], getattr(record, "content")),
        author=cast(Optional[str], getattr(record, "author")),
        published_date=cast(Optional[datetime], getattr(record, "published_date")),
        scraped_at=cast(Optional[datetime], getattr(record, "scraped_at")),
        metadata=cast(Optional[Dict[str, Any]], getattr(record, "metadata_json")),
        spider_name=cast(Optional[str], getattr(spider, "name", None)) if spider else None,
        project=cast(Optional[str], getattr(spider, "project", None)) if spider else None,
    )


@router.get("/", response_model=ResultsListResponse)
async def list_results(
    project: str,
    spider_name: Optional[str] = None,
    crawl_run_id: Optional[int] = None,
    limit: int = Query(50, le=100),
    offset: int = Query(0, ge=0),
    url_filter: Optional[str] = None,
    db: Session = Depends(get_db_session),
    api_key: APIKey = Depends(get_api_key),
):
    """List scraped items with filters."""
    ensure_project_access(api_key, project)

    query = db.query(ScrapedItem).join(Spider)

    query = query.filter(Spider.project == project)

    if spider_name:
        query = query.filter(Spider.name == spider_name)

    if crawl_run_id:
        query = query.filter(ScrapedItem.crawl_run_id == crawl_run_id)

    if url_filter:
        query = query.filter(ScrapedItem.url.ilike(f"%{url_filter}%"))

    total_count = query.count()

    items = query.order_by(ScrapedItem.scraped_at.desc()).offset(offset).limit(limit).all()

    result_items = [_build_result_item_response(item) for item in items]

    return ResultsListResponse(
        items=result_items,
        total_count=total_count,
        page=offset // limit if limit > 0 else 0,
        page_size=limit,
        has_next=offset + limit < total_count,
        has_previous=offset > 0,
    )


@router.get("/{item_id}", response_model=ResultItemResponse)
async def get_result(
    item_id: int,
    db: Session = Depends(get_db_session),
    api_key: APIKey = Depends(get_api_key),
):
    """Get a specific scraped item by ID."""
    item = db.query(ScrapedItem).filter(ScrapedItem.id == item_id).first()

    if not item:
        raise HTTPException(status_code=404, detail=f"Item {item_id} not found")

    if item.spider:
        ensure_project_access(api_key, cast(str, getattr(item.spider, "project")))

    return _build_result_item_response(item)


@router.get("/by-url/", response_model=ResultItemResponse)
async def get_result_by_url(
    url: str,
    project: Optional[str] = None,
    db: Session = Depends(get_db_session),
    api_key: APIKey = Depends(get_api_key),
):
    """Get a scraped item by URL."""
    if project:
        ensure_project_access(api_key, project)

    query = db.query(ScrapedItem).filter(ScrapedItem.url == url)

    if project:
        query = query.join(Spider).filter(Spider.project == project)

    item = query.first()

    if not item:
        raise HTTPException(status_code=404, detail=f"Item with URL '{url}' not found")

    if item.spider:
        ensure_project_access(api_key, cast(str, getattr(item.spider, "project")))

    return _build_result_item_response(item)
