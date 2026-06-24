"""Entry points for uv run api / uv run workers."""

import subprocess
import sys
from pathlib import Path

# Ensure project root is on sys.path so local packages (apps, cli, core, etc.) are importable
ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Load .env so subprocesses (workers) inherit the correct env vars
try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=False)
except ImportError:
    pass


def scrapai_cli():
    from cli import cli

    cli()


def api():
    import uvicorn

    uvicorn.run(
        "apps.web_api.api.main:app",
        reload=True,
        host="0.0.0.0",
        port=8481,
    )


def workers():
    subprocess.run(
        [
            sys.executable,
            "-m",
            "dramatiq",
            "apps.web_api.workers.crawl_worker",
            "apps.web_api.workers.webhook_worker",
            "apps.web_api.workers.reaper",
        ],
        check=True,
    )
