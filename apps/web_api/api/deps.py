"""Shared API dependencies and access helpers."""

from typing import Generator, Optional

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from core.db import SessionLocal
from core.models import APIKey

from ..services.auth_service import AuthService


def get_db_session() -> Generator[Session, None, None]:
    """Provide a database session for API requests."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_api_key(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db_session),
) -> APIKey:
    """Validate the bearer token from the Authorization header."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization format")

    key = authorization[7:]
    api_key = AuthService().verify_key(db, key)
    if not api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return api_key


def resolve_project(
    requested_project: Optional[str], api_key: APIKey, default: str = "default"
) -> str:
    """Resolve project scoping from request and API key."""
    if requested_project:
        ensure_project_access(api_key, requested_project)
        return requested_project

    return api_key.project or default


def ensure_project_access(api_key: APIKey, project: str) -> None:
    """Ensure a project-scoped API key cannot access other projects."""
    if api_key.project and api_key.project != project:
        raise HTTPException(
            status_code=403,
            detail=f"API key is not authorized for project '{project}'",
        )
