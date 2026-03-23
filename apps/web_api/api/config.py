"""
API configuration for ScrapAI API.

Uses Pydantic BaseSettings for environment variable loading with validation.
"""

import logging
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class APISettings(BaseSettings):
    """API server configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    api_host: str = Field(default="0.0.0.0", description="API server host")
    api_port: int = Field(default=8000, description="API server port")
    api_workers: int = Field(default=4, description="Number of API workers")
    secret_key: str = Field(
        default="change-me-in-production",
        description="Secret key for JWT signing",
    )

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        if v == "change-me-in-production" or v == "your-secret-key-here-change-in-production":
            logger.warning(
                "Using default SECRET_KEY. Generate a secure key with: "
                'python -c "import secrets; print(secrets.token_urlsafe(32))"'
            )
        if len(v) < 16:
            raise ValueError("SECRET_KEY must be at least 16 characters")
        return v


class RedisSettings(BaseSettings):
    """Redis configuration for API rate limiting and queues."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    redis_host: str = Field(default="localhost", description="Redis host")
    redis_port: int = Field(default=6379, description="Redis port")
    redis_password: str = Field(default="", description="Redis password")
    redis_db: int = Field(default=0, description="Redis database number")
    redis_ssl: bool = Field(default=False, description="Use SSL for Redis connection")
    redis_prefix: str = Field(
        default="scrapai:api",
        description="Key namespace prefix",
    )

    @field_validator("redis_prefix")
    @classmethod
    def validate_prefix(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("REDIS_PREFIX cannot be empty")
        return v.strip()


class DatabaseSettings(BaseSettings):
    """Database configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = Field(
        default="sqlite:///scrapai.db",
        description="Database connection URL",
    )


class Settings(BaseSettings):
    """Combined application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    api: APISettings = Field(default_factory=APISettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


def get_api_settings() -> APISettings:
    """Get API settings."""
    return get_settings().api


def get_redis_settings() -> RedisSettings:
    """Get Redis settings."""
    return get_settings().redis


def get_database_settings() -> DatabaseSettings:
    """Get database settings."""
    return get_settings().database
