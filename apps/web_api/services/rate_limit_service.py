"""
Rate limiting service for ScrapAI CLI.

Provides Redis-backed rate limiting for API endpoints.
"""

import logging
import time
from typing import Any, Dict

from .redis_config import get_redis_client, get_redis_config

logger = logging.getLogger(__name__)


class RateLimitService:
    """Service for rate limiting API requests using Redis."""

    def __init__(self):
        self.redis_client = get_redis_client()
        self.prefix = get_redis_config().prefix

    def check_rate_limit(
        self, identifier: str, limit: int = 100, window_seconds: int = 60
    ) -> Dict[str, Any]:
        """
        Check if an identifier has exceeded rate limit.

        Args:
            identifier: Unique identifier (e.g., API key, IP address)
            limit: Maximum requests allowed in window
            window_seconds: Time window in seconds

        Returns:
            Dict with rate limit status
        """
        key = self._get_rate_limit_key(identifier)

        try:
            current = self.redis_client.get(key)

            if current is None:
                current = 0
                self.redis_client.setex(key, window_seconds, current)
            else:
                current = int(current)

            if current >= limit:
                ttl = self.redis_client.ttl(key)
                return {
                    "allowed": False,
                    "remaining": 0,
                    "reset_at": time.time() + ttl if ttl else None,
                    "limit": limit,
                    "window_seconds": window_seconds,
                }

            pipe = self.redis_client.pipeline()
            pipe.incr(key)
            pipe.expire(key, window_seconds)
            pipe.execute()

            return {
                "allowed": True,
                "remaining": limit - current,
                "reset_at": time.time() + window_seconds,
                "limit": limit,
                "window_seconds": window_seconds,
            }

        except Exception as e:
            logger.error(f"Rate limit check failed: {e}")
            return {
                "allowed": True,
                "remaining": limit,
                "reset_at": None,
                "limit": limit,
                "window_seconds": window_seconds,
            }

    def reset_rate_limit(self, identifier: str) -> bool:
        """Reset rate limit for an identifier."""
        key = self._get_rate_limit_key(identifier)

        try:
            self.redis_client.delete(key)
            return True
        except Exception as e:
            logger.error(f"Failed to reset rate limit: {e}")
            return False

    def get_rate_limit_status(self, identifier: str) -> Dict[str, Any]:
        """Get current rate limit status for an identifier."""
        key = self._get_rate_limit_key(identifier)

        try:
            current = self.redis_client.get(key)
            ttl = self.redis_client.ttl(key)

            if current is None:
                return {
                    "identifier": identifier,
                    "current_usage": 0,
                    "limit": 100,
                    "remaining": 100,
                    "reset_at": None,
                }

            return {
                "identifier": identifier,
                "current_usage": int(current),
                "limit": 100,
                "remaining": 100 - int(current),
                "reset_at": time.time() + ttl if ttl else None,
            }

        except Exception as e:
            logger.error(f"Failed to get rate limit status: {e}")
            return {
                "identifier": identifier,
                "current_usage": 1,
                "limit": 100,
                "remaining": 100,
                "reset_at": None,
            }

    def _get_rate_limit_key(self, identifier: str) -> str:
        """Generate Redis key for rate limiting."""
        return f"{self.prefix}:rate_limit:{identifier}"
