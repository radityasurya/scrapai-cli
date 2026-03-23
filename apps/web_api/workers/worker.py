"""
Worker entry point for ScrapAI CLI.

Run with: dramatiq workers
"""

import logging
import sys

from .crawl_worker import crawl_actor
from .webhook_worker import webhook_actor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)

logger = logging.getLogger(__name__)

__all__ = ["crawl_actor", "webhook_actor"]
