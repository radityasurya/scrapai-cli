"""
Authentication service for ScrapAI CLI.

Handles API key management and verification.
"""

import hashlib
import logging
import secrets
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from core.models import APIKey

logger = logging.getLogger(__name__)


class AuthService:
    """Service for API key authentication and management."""

    @staticmethod
    def generate_api_key() -> str:
        """Generate a new API key."""
        return f"sk_{secrets.token_hex(32)}"

    @staticmethod
    def hash_key(key: str) -> str:
        """Hash an API key for storage."""
        return hashlib.sha256(key.encode()).hexdigest()

    def create_api_key(
        self,
        db: Session,
        name: str,
        project: Optional[str] = None,
        scopes: Optional[List[str]] = None,
    ) -> tuple[str, APIKey]:
        """Create a new API key. Returns (key, api_key_object)."""
        try:
            key = self.generate_api_key()
            key_hash = self.hash_key(key)

            existing = db.query(APIKey).filter(APIKey.name == name).first()
            if existing:
                if project and existing.project != project:
                    raise ValueError(
                        f"API key with name '{name}' already exists in project '{existing.project}'"
                    )
                raise ValueError(f"API key with name '{name}' already exists")

            api_key = APIKey(
                name=name,
                key_hash=key_hash,
                project=project,
                scopes=scopes or [],
                active=True,
            )

            db.add(api_key)
            db.commit()
            db.refresh(api_key)

            logger.info(f"Created API key '{name}' for project {project or 'global'}")
            return key, api_key

        except Exception as e:
            db.rollback()
            logger.error(f"Failed to create API key: {e}")
            raise

    def verify_key(self, db: Session, key: str, project: Optional[str] = None) -> Optional[APIKey]:
        """Verify an API key and optionally check project scope."""
        try:
            key_hash = self.hash_key(key)
            query = db.query(APIKey).filter(
                APIKey.key_hash == key_hash,
                APIKey.active.is_(True),
            )

            api_key = query.first()

            if not api_key:
                return None

            if project:
                if api_key.project and api_key.project != project:
                    return None

            api_key.last_used_at = datetime.now(timezone.utc)
            db.commit()

            return api_key

        except Exception as e:
            logger.error(f"Failed to verify API key: {e}")
            raise

    def revoke_key(self, db: Session, key_id: int, project: Optional[str] = None) -> bool:
        """Revoke an API key."""
        try:
            api_key = db.query(APIKey).filter(APIKey.id == key_id).first()

            if not api_key:
                return False

            if project and api_key.project != project:
                return False

            api_key.active = False
            api_key.revoked_at = datetime.now(timezone.utc)

            db.commit()

            logger.info(f"Revoked API key {key_id}")
            return True

        except Exception as e:
            db.rollback()
            logger.error(f"Failed to revoke API key: {e}")
            raise

    def list_keys(
        self, db: Session, project: Optional[str] = None, active_only: bool = True
    ) -> List[APIKey]:
        """List API keys with optional filters."""
        try:
            query = db.query(APIKey)

            if project:
                query = query.filter(APIKey.project == project)

            if active_only:
                query = query.filter(APIKey.active.is_(True))

            return query.order_by(APIKey.created_at.desc()).all()

        except Exception as e:
            logger.error(f"Failed to list API keys: {e}")
            raise

    def get_key_by_id(self, db: Session, key_id: int) -> Optional[APIKey]:
        """Get an API key by ID."""
        try:
            return db.query(APIKey).filter(APIKey.id == key_id).first()
        except Exception as e:
            logger.error(f"Failed to get API key: {e}")
            raise
