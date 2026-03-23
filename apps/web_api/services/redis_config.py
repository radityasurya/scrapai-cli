"""
Redis configuration for ScrapAI CLI.

Provides namespaced Redis access and Dramatiq broker setup.
"""

import logging
import os
from typing import Optional

import redis
from redis import Redis

logger = logging.getLogger(__name__)


class RedisConfig:
    """Redis configuration manager with namespace support."""

    def __init__(self):
        self.host = os.getenv("REDIS_HOST", "localhost")
        self.port = int(os.getenv("REDIS_PORT", "6379"))
        self.password = os.getenv("REDIS_PASSWORD", "")
        self.db = int(os.getenv("REDIS_DB", "0"))
        self.ssl = os.getenv("REDIS_SSL", "false").lower() == "true"
        self.prefix = os.getenv("REDIS_PREFIX", "joinremotes:scrapai:prod")

        self._client: Optional[Redis] = None
        self._broker = None

    def get_client(self) -> Redis:
        """Get Redis client with namespace support."""
        if self._client is None:
            self._client = redis.Redis(
                host=self.host,
                port=self.port,
                db=self.db,
                password=self.password if self.password else None,
                ssl=self.ssl,
                decode_responses=True,
            )
            try:
                self._client.ping()
                logger.info(f"Redis connection established: {self.host}:{self.port}")
            except Exception as e:
                logger.error(f"Redis connection failed: {e}")
                raise

        return self._client

    def get_namespaced_key(self, key: str) -> str:
        """Add prefix to Redis key."""
        return f"{self.prefix}:{key}"

    def get_queue_name(self, queue_type: str) -> str:
        """Get namespaced queue name for Dramatiq."""
        return f"{self.prefix.replace(':', '_')}_{queue_type}"

    def get_broker(self):
        """Get Dramatiq broker with namespaced queues."""
        import dramatiq
        from dramatiq.brokers.redis import RedisBroker
        from dramatiq.middleware import Retries

        if self._broker is None:
            try:
                self._broker = RedisBroker(
                    host=self.host,
                    port=self.port,
                    db=self.db,
                    password=self.password if self.password else None,
                    ssl=self.ssl,
                    middleware=[
                        Retries(max_retries=3, min_backoff=1000, max_backoff=60000),
                    ],
                )

                dramatiq.set_broker(self._broker)

                for queue_type in ["crawl", "scrape", "webhook", "validation"]:
                    queue_name = self.get_queue_name(queue_type)
                    self._broker.declare_queue(queue_name)

                logger.info(f"Dramatiq broker initialized with prefix: {self.prefix}")

            except Exception as e:
                logger.error(f"Failed to initialize Dramatiq broker: {e}")
                raise

        return self._broker

    def health_check(self) -> bool:
        """Check Redis connection health."""
        try:
            client = self.get_client()
            client.ping()
            return True
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return False

    def close(self):
        """Close Redis connections."""
        if self._client:
            try:
                self._client.close()
            except Exception as e:
                logger.error(f"Error closing Redis client: {e}")


_redis_config: Optional[RedisConfig] = None


def get_redis_config() -> RedisConfig:
    """Get or create Redis configuration singleton."""
    global _redis_config

    if _redis_config is None:
        _redis_config = RedisConfig()

    return _redis_config


def get_redis_client() -> Redis:
    """Get Redis client."""
    return get_redis_config().get_client()


def get_dramatiq_broker():
    """Get Dramatiq broker."""
    return get_redis_config().get_broker()
