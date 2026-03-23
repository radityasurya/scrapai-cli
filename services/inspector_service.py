"""
Inspector service for reusable page inspection.

Wraps utils.inspector.inspect_page_async() for API and CLI reuse.
"""

from typing import Any, Dict, Optional

from utils.inspector import inspect_page_async


class InspectorService:
    """Service wrapper around the inspector utility."""

    async def inspect_url(
        self,
        url: str,
        output_dir: Optional[str] = None,
        proxy_type: str = "auto",
        save_html: bool = True,
        mode: str = "http",
        project: str = "default",
    ) -> Dict[str, Any]:
        """Inspect a URL and return a structured response."""
        result = await inspect_page_async(
            url=url,
            output_dir=output_dir,
            proxy_type=proxy_type,
            save_html=save_html,
            mode=mode,
            project=project,
        )

        if result is None:
            return {
                "success": False,
                "url": url,
                "project": project,
                "mode": mode,
                "error": "Inspection failed",
            }

        return result
