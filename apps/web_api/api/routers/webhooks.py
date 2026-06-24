"""API router for webhook subscription management."""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import AnyHttpUrl, BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from core.models import APIKey, WebhookDelivery, WebhookSubscription

from ...services.webhook_service import WebhookService
from ..deps import get_api_key, get_db_session, resolve_project

router = APIRouter()

ALLOWED_EVENTS = {"crawl.completed", "crawl.failed", "crawl.cancelled", "crawl.started"}


class WebhookCreateRequest(BaseModel):
    """Request payload for webhook creation."""

    project: Optional[str] = None
    target_url: AnyHttpUrl
    event_types: List[str] = Field(min_length=1)
    secret: Optional[str] = None

    @field_validator("event_types")
    @classmethod
    def validate_event_types(cls, values: List[str]) -> List[str]:
        invalid = sorted({value for value in values if value not in ALLOWED_EVENTS})
        if invalid:
            raise ValueError(f"Unsupported event types: {', '.join(invalid)}")
        return values


class WebhookResponse(BaseModel):
    """Webhook subscription response."""

    id: int
    project: str
    target_url: str
    event_types: List[str]
    active: bool
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class WebhookCreateResponse(WebhookResponse):
    """Webhook creation response with returned secret."""

    secret: str


class WebhookDeleteResponse(BaseModel):
    """Response for webhook deletion."""

    success: bool
    subscription_id: int
    message: str


@router.post("/", response_model=WebhookCreateResponse, status_code=201)
async def create_webhook_subscription(
    payload: WebhookCreateRequest,
    db: Session = Depends(get_db_session),
    api_key: APIKey = Depends(get_api_key),
):
    """Create a webhook subscription."""
    project = resolve_project(payload.project, api_key)
    service = WebhookService()

    try:
        subscription = service.create_subscription(
            db=db,
            project=project,
            target_url=str(payload.target_url),
            event_types=payload.event_types,
            secret=None if payload.secret == "auto" else payload.secret,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return WebhookCreateResponse(
        id=subscription.id,
        project=subscription.project,
        target_url=subscription.target_url,
        event_types=subscription.event_types,
        active=subscription.active,
        created_at=subscription.created_at,
        secret=subscription.secret,
    )


@router.get("/", response_model=List[WebhookResponse])
async def list_webhook_subscriptions(
    project: Optional[str] = None,
    active_only: bool = True,
    db: Session = Depends(get_db_session),
    api_key: APIKey = Depends(get_api_key),
):
    """List webhook subscriptions for a project."""
    scoped_project = resolve_project(project, api_key)
    subscriptions = WebhookService().list_subscriptions(
        db=db,
        project=scoped_project,
        active_only=active_only,
    )

    return [
        WebhookResponse(
            id=item.id,
            project=item.project,
            target_url=item.target_url,
            event_types=item.event_types,
            active=item.active,
            created_at=item.created_at,
        )
        for item in subscriptions
    ]


@router.delete("/{subscription_id}", response_model=WebhookDeleteResponse)
async def delete_webhook_subscription(
    subscription_id: int,
    db: Session = Depends(get_db_session),
    api_key: APIKey = Depends(get_api_key),
):
    """Delete a webhook subscription."""
    service = WebhookService()
    subscription = service.get_subscription(db, subscription_id)
    if not subscription:
        raise HTTPException(
            status_code=404,
            detail=f"Webhook subscription {subscription_id} not found",
        )

    if api_key.project and api_key.project != subscription.project:
        raise HTTPException(status_code=403, detail="Not authorized for this project")

    deleted = service.delete_subscription(db, subscription_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Webhook subscription {subscription_id} not found",
        )

    return WebhookDeleteResponse(
        success=True,
        subscription_id=subscription_id,
        message="Webhook subscription deleted",
    )


class WebhookDeliveryResponse(BaseModel):
    """Webhook delivery record response."""

    id: int
    subscription_id: int
    event_type: str
    status: str
    attempt: Optional[int] = None
    response_status: Optional[int] = None
    delivered_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


@router.get("/deliveries", response_model=List[WebhookDeliveryResponse])
async def list_webhook_deliveries(
    project: Optional[str] = None,
    status: Optional[str] = None,
    event_type: Optional[str] = None,
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db_session),
    api_key: APIKey = Depends(get_api_key),
):
    """List recent webhook delivery records, filterable by status and event_type."""
    scoped_project = resolve_project(project, api_key)

    query = (
        db.query(WebhookDelivery)
        .join(WebhookSubscription, WebhookDelivery.subscription_id == WebhookSubscription.id)
        .filter(WebhookSubscription.project == scoped_project)
    )

    if status:
        query = query.filter(WebhookDelivery.status == status)
    if event_type:
        query = query.filter(WebhookDelivery.event_type == event_type)

    deliveries = (
        query.order_by(WebhookDelivery.created_at.desc()).offset(offset).limit(limit).all()
    )

    return [
        WebhookDeliveryResponse(
            id=delivery.id,
            subscription_id=delivery.subscription_id,
            event_type=delivery.event_type,
            status=delivery.status,
            attempt=delivery.attempt,
            response_status=delivery.response_status,
            delivered_at=delivery.delivered_at,
            created_at=delivery.created_at,
        )
        for delivery in deliveries
    ]
