"""
Main FastAPI application entry point for ScrapAI CLI.

Provides REST API for programmatic access to spiders and crawls.
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .routers import crawls, results, spiders, webhooks

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    logger.info("ScrapAI API starting up...")
    db_url = os.getenv("DATABASE_URL", "sqlite:///scrapai.db")
    logger.info(f"Using database: {db_url}")
    yield
    logger.info("ScrapAI API shutting down...")


app = FastAPI(
    title="ScrapAI API",
    description="REST API for ScrapAI spiders and crawls",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

cors_origins = [o.strip() for o in os.getenv("API_CORS_ORIGINS", "http://localhost:3000").split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Handle unhandled exceptions."""
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions."""
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.get("/")
async def root():
    """Root endpoint - API information."""
    return {
        "name": "ScrapAI API",
        "version": "0.1.0",
        "docs": "/docs",
        "status": "operational",
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    from ..services.redis_config import get_redis_config  # local import to avoid startup failure
    redis_ok = False
    try:
        redis_ok = get_redis_config().health_check()
    except Exception:
        pass
    status = "healthy" if redis_ok else "degraded"
    return {"status": status, "redis": "ok" if redis_ok else "unavailable"}


app.include_router(crawls.router, prefix="/api/v1/crawls", tags=["crawls"])
app.include_router(spiders.router, prefix="/api/v1/spiders", tags=["spiders"])
app.include_router(results.router, prefix="/api/v1/results", tags=["results"])
app.include_router(webhooks.router, prefix="/api/v1/webhooks", tags=["webhooks"])


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
