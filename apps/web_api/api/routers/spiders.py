"""API router for spider operations."""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, cast

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.models import APIKey, Spider
from services.analyzer_service import AnalyzerService
from services.inspector_service import InspectorService
from services.spider_analysis_service import SpiderAnalysisService
from services.spider_import_service import SpiderImportService
from services.spider_service import SpiderService

from ..deps import ensure_project_access, get_api_key, get_db_session, resolve_project

logger = logging.getLogger(__name__)

router = APIRouter()


class SpiderResponse(BaseModel):
    """Schema for spider response."""

    id: int
    name: str
    project: str
    active: bool
    source_url: Optional[str] = None
    allowed_domains: Optional[List[str]] = None
    start_urls: Optional[List[str]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SpiderDetailResponse(SpiderResponse):
    """Schema for detailed spider response."""

    rules_count: int = 0
    settings_count: int = 0
    items_count: int = 0


class SpiderAnalyzeRequest(BaseModel):
    """Request payload for spider analysis."""

    url: str
    project: Optional[str] = None
    use_browser: bool = False


class SpiderInspectRequest(BaseModel):
    """Request payload for fetching a page's HTML."""

    url: str
    project: Optional[str] = None
    use_browser: bool = False


class SpiderInspectResponse(BaseModel):
    """Response for page inspection."""

    success: bool
    url: str
    project: str
    mode: str
    html_file: Optional[str] = None
    title: Optional[str] = None
    html_size: Optional[int] = None
    error: Optional[str] = None


class SpiderTestSelectorRequest(BaseModel):
    """Request payload for testing a CSS selector against a page."""

    url: str
    selector: str
    project: Optional[str] = None
    use_browser: bool = False


class SpiderMutationResponse(BaseModel):
    """Structured response for create/update spider mutations."""

    success: bool
    action: str
    spider_id: int
    spider_name: str
    project: str
    active: bool
    allowed_domains: List[str]
    start_urls: List[str]
    rules_count: int
    callbacks: List[str] = Field(default_factory=list)


class SpiderDeleteResponse(BaseModel):
    """Response for spider delete operations."""

    success: bool
    spider_id: int
    spider_name: str
    project: str
    active: bool
    message: str


def _build_spider_detail(spider: Spider) -> SpiderDetailResponse:
    item = cast(Any, spider)
    return SpiderDetailResponse(
        id=item.id,
        name=item.name,
        project=item.project,
        active=item.active,
        source_url=item.source_url,
        allowed_domains=item.allowed_domains,
        start_urls=item.start_urls,
        created_at=item.created_at,
        updated_at=item.updated_at,
        rules_count=len(item.rules) if item.rules else 0,
        settings_count=len(item.settings) if item.settings else 0,
        items_count=len(item.items) if item.items else 0,
    )


def _build_spider_response(spider: Spider) -> SpiderResponse:
    item = cast(Any, spider)
    return SpiderResponse(
        id=item.id,
        name=item.name,
        project=item.project,
        active=item.active,
        source_url=item.source_url,
        allowed_domains=item.allowed_domains,
        start_urls=item.start_urls,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.post("/analyze")
async def analyze_spider(
    payload: SpiderAnalyzeRequest,
    db: Session = Depends(get_db_session),
    api_key: APIKey = Depends(get_api_key),
):
    """Analyze a source URL and return a suggested spider configuration."""
    del db
    project = resolve_project(payload.project, api_key)
    service = SpiderAnalysisService()

    result = await service.analyze_url(
        url=payload.url,
        project=project,
        use_browser=payload.use_browser,
    )

    if not result.get("success", True):
        raise HTTPException(status_code=400, detail=result.get("error", "Analysis failed"))

    return result


@router.get("/", response_model=List[SpiderResponse])
async def list_spiders(
    project: Optional[str] = None,
    active_only: bool = True,
    limit: int = Query(50, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db_session),
    api_key: APIKey = Depends(get_api_key),
):
    """List spiders with optional project filtering."""
    spider_service = SpiderService()
    scoped_project: Optional[str] = (
        project if project is not None else cast(Optional[str], getattr(api_key, "project", None))
    )
    if scoped_project is not None:
        ensure_project_access(api_key, scoped_project)

    spiders = spider_service.list_spiders(
        db=db,
        project=scoped_project,
        active_only=active_only,
        limit=limit,
        offset=offset,
    )

    return [_build_spider_response(spider) for spider in spiders]


@router.post("/", response_model=SpiderMutationResponse)
async def create_or_update_spider(
    response: Response,
    config: Dict[str, Any] = Body(...),
    project: Optional[str] = Query(default=None),
    skip_validation: bool = Query(default=False),
    db: Session = Depends(get_db_session),
    api_key: APIKey = Depends(get_api_key),
):
    """Create a spider, or update it when the same name already exists."""
    scoped_project = resolve_project(project, api_key)
    import_service = SpiderImportService()

    result = await import_service.import_spider_data(
        db=db,
        data=config,
        project=scoped_project,
        skip_validation=skip_validation,
    )

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])

    if result["action"] == "created":
        response.status_code = status.HTTP_201_CREATED

    return result


@router.get("/by-name/{project}/{spider_name}", response_model=SpiderDetailResponse)
async def get_spider_by_name(
    project: str,
    spider_name: str,
    db: Session = Depends(get_db_session),
    api_key: APIKey = Depends(get_api_key),
):
    """Get details of a spider by project and name."""
    ensure_project_access(api_key, project)
    spider = (
        db.query(Spider)
        .filter(
            Spider.project == project,
            Spider.name == spider_name,
        )
        .first()
    )

    if not spider:
        raise HTTPException(
            status_code=404,
            detail=f"Spider '{spider_name}' not found in project '{project}'",
        )

    return _build_spider_detail(spider)


@router.post("/inspect", response_model=SpiderInspectResponse)
async def inspect_url(
    payload: SpiderInspectRequest,
    api_key: APIKey = Depends(get_api_key),
):
    """Fetch and save a page's HTML for selector testing."""
    project = resolve_project(payload.project, api_key)
    ensure_project_access(api_key, project)

    service = InspectorService()
    result = await service.inspect_url(
        url=payload.url,
        project=project,
        mode="browser" if payload.use_browser else "http",
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Inspection failed"))

    return result


@router.post("/test-selector")
async def test_selector(
    payload: SpiderTestSelectorRequest,
    api_key: APIKey = Depends(get_api_key),
):
    """Fetch a page and test a CSS selector against it. Returns matched elements."""
    project = resolve_project(payload.project, api_key)
    ensure_project_access(api_key, project)

    inspector = InspectorService()
    inspect_result = await inspector.inspect_url(
        url=payload.url,
        project=project,
        mode="browser" if payload.use_browser else "http",
    )

    if not inspect_result.get("success"):
        raise HTTPException(
            status_code=400,
            detail=inspect_result.get("error", "Failed to fetch page"),
        )

    html_file = inspect_result.get("html_file")
    if not html_file:
        raise HTTPException(status_code=400, detail="No HTML file saved during inspection")

    analyzer = AnalyzerService()
    result = await analyzer.test_selector(html_path=html_file, selector=payload.selector)
    result["html_file"] = html_file
    result["url"] = payload.url
    return result


@router.get("/{spider_id}/config")
async def get_spider_config(
    spider_id: int,
    db: Session = Depends(get_db_session),
    api_key: APIKey = Depends(get_api_key),
):
    """Return the full raw JSON config for a spider, ready for editing and re-importing."""
    import json as _json

    spider = db.query(Spider).filter(Spider.id == spider_id).first()
    if not spider:
        raise HTTPException(status_code=404, detail=f"Spider {spider_id} not found")

    ensure_project_access(api_key, cast(Any, spider).project)
    item = cast(Any, spider)

    rules = []
    for rule in item.rules or []:
        r = cast(Any, rule)
        rule_dict: Dict[str, Any] = {}
        if r.allow_patterns:
            rule_dict["allow"] = r.allow_patterns
        if r.deny_patterns:
            rule_dict["deny"] = r.deny_patterns
        if r.callback:
            rule_dict["callback"] = r.callback
        if r.follow is not None:
            rule_dict["follow"] = r.follow
        rules.append(rule_dict)

    settings: Dict[str, Any] = {}
    for setting in item.settings or []:
        s = cast(Any, setting)
        settings[s.key] = _json.loads(s.value) if s.type == "json" else s.value

    config: Dict[str, Any] = {
        "name": item.name,
        "source_url": item.source_url,
        "allowed_domains": item.allowed_domains or [],
        "start_urls": item.start_urls or [],
        "rules": rules,
        "settings": settings,
    }
    if item.callbacks_config:
        config["callbacks"] = item.callbacks_config

    return config


@router.get("/{spider_id}", response_model=SpiderDetailResponse)
async def get_spider(
    spider_id: int,
    db: Session = Depends(get_db_session),
    api_key: APIKey = Depends(get_api_key),
):
    """Get details of a specific spider."""
    spider = db.query(Spider).filter(Spider.id == spider_id).first()

    if not spider:
        raise HTTPException(status_code=404, detail=f"Spider {spider_id} not found")

    ensure_project_access(api_key, cast(Any, spider).project)
    return _build_spider_detail(spider)


@router.put("/{spider_id}", response_model=SpiderMutationResponse)
async def update_spider(
    spider_id: int,
    config: Dict[str, Any] = Body(...),
    skip_validation: bool = Query(default=False),
    db: Session = Depends(get_db_session),
    api_key: APIKey = Depends(get_api_key),
):
    """Update an existing spider from JSON configuration."""
    existing = db.query(Spider).filter(Spider.id == spider_id).first()
    if not existing:
        raise HTTPException(status_code=404, detail=f"Spider {spider_id} not found")

    ensure_project_access(api_key, cast(Any, existing).project)

    result = await SpiderImportService().update_spider_data(
        db=db,
        spider_id=spider_id,
        data=config,
        skip_validation=skip_validation,
    )

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])

    return result


@router.delete("/{spider_id}", response_model=SpiderDeleteResponse)
async def delete_spider(
    spider_id: int,
    db: Session = Depends(get_db_session),
    api_key: APIKey = Depends(get_api_key),
):
    """Soft-delete a spider by setting active=false."""
    spider_service = SpiderService()
    spider = spider_service.get_spider(db, spider_id)
    if not spider:
        raise HTTPException(status_code=404, detail=f"Spider {spider_id} not found")

    ensure_project_access(api_key, cast(Any, spider).project)
    spider_service.delete_spider(db, spider_id)
    db.refresh(spider)

    return SpiderDeleteResponse(
        success=True,
        spider_id=cast(Any, spider).id,
        spider_name=cast(Any, spider).name,
        project=cast(Any, spider).project,
        active=cast(Any, spider).active,
        message="Spider deactivated",
    )
