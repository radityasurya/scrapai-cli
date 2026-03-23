"""
Analyzer service for HTML inspection and selector discovery.

Extracts reusable logic from the CLI analyze command.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List

if TYPE_CHECKING:
    from bs4 import BeautifulSoup


class AnalyzerService:
    """Service for analyzing HTML files and selectors."""

    async def analyze_html(self, html_path: str) -> Dict[str, Any]:
        """Analyze an HTML file and return structured discovery data."""
        try:
            html = self._read_html(html_path)
        except FileNotFoundError:
            return {
                "success": False,
                "html_file": html_path,
                "error": f"File not found: {html_path}",
            }

        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")

        return {
            "success": True,
            "html_file": html_path,
            "html_size": len(html),
            "headers": self._collect_headers(soup),
            "content_containers": self._collect_content_containers(soup),
            "dates": self._collect_dates(soup),
            "authors": self._collect_authors(soup),
        }

    async def test_selector(self, html_path: str, selector: str) -> Dict[str, Any]:
        """Test a CSS selector against an HTML file."""
        try:
            html = self._read_html(html_path)
        except FileNotFoundError:
            return {
                "success": False,
                "html_file": html_path,
                "selector": selector,
                "error": f"File not found: {html_path}",
            }

        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")
        elements = soup.select(selector)

        return {
            "success": len(elements) > 0,
            "html_file": html_path,
            "selector": selector,
            "count": len(elements),
            "matches": [self._element_match(el, include_classes=True) for el in elements[:3]],
            "error": None if elements else "No elements found",
        }

    async def find_by_keyword(self, html_path: str, keyword: str) -> Dict[str, Any]:
        """Find elements whose class or id contains a keyword."""
        try:
            html = self._read_html(html_path)
        except FileNotFoundError:
            return {
                "success": False,
                "html_file": html_path,
                "keyword": keyword,
                "error": f"File not found: {html_path}",
            }

        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")
        matches: List[Dict[str, Any]] = []

        for el in soup.find_all():
            classes = el.get("class", [])
            class_str = " ".join(classes) if classes else ""
            el_id = el.get("id", "")

            if keyword.lower() not in class_str.lower() and keyword.lower() not in el_id.lower():
                continue

            text = el.get_text(strip=True)
            if text and len(text) < 200:
                matches.append(
                    {
                        "tag": el.name,
                        "selector": self._selector_for(el),
                        "text": text[:100],
                    }
                )

            if len(matches) >= 10:
                break

        return {
            "success": len(matches) > 0,
            "html_file": html_path,
            "keyword": keyword,
            "count": len(matches),
            "matches": matches,
            "error": None if matches else f"No elements found with keyword '{keyword}'",
        }

    def _read_html(self, html_path: str) -> str:
        path = Path(html_path)
        return path.read_text(encoding="utf-8")

    def _collect_headers(self, soup: "BeautifulSoup") -> List[Dict[str, Any]]:
        headers: List[Dict[str, Any]] = []
        for tag in ["h1", "h2"]:
            elements = soup.find_all(tag)
            for el in elements[:5]:
                headers.append(
                    {
                        "tag": tag,
                        "selector": self._selector_for(el, tag_name=tag),
                        "text": el.get_text(strip=True)[:80],
                    }
                )
        return headers

    def _collect_content_containers(self, soup: "BeautifulSoup") -> List[Dict[str, Any]]:
        content_keywords = ["article", "content", "body", "text", "post", "entry"]
        found = []

        for el in soup.find_all(["article", "div", "section", "main"]):
            classes = el.get("class", [])
            class_str = " ".join(classes) if classes else ""
            if el.name == "article" or any(kw in class_str.lower() for kw in content_keywords):
                text = el.get_text(strip=True)
                if len(text) > 200:
                    found.append(
                        {
                            "tag": el.name,
                            "selector": self._selector_for(el),
                            "size": len(text),
                            "preview": text[:80],
                        }
                    )

        found.sort(key=lambda item: item["size"], reverse=True)
        return found[:5]

    def _collect_dates(self, soup: "BeautifulSoup") -> List[Dict[str, Any]]:
        date_keywords = ["date", "time", "published", "posted", "updated"]
        matches: List[Dict[str, Any]] = []

        for el in soup.find_all(["time", "span", "div", "p"]):
            classes = el.get("class", [])
            class_str = " ".join(classes) if classes else ""
            if el.name == "time" or any(kw in class_str.lower() for kw in date_keywords):
                text = el.get_text(strip=True)
                if text and len(text) < 50:
                    matches.append(
                        {
                            "tag": el.name,
                            "selector": self._selector_for(el),
                            "text": text,
                        }
                    )
                if len(matches) >= 5:
                    break

        return matches

    def _collect_authors(self, soup: "BeautifulSoup") -> List[Dict[str, Any]]:
        author_keywords = ["author", "byline", "writer", "by"]
        matches: List[Dict[str, Any]] = []

        for el in soup.find_all(["span", "div", "a", "p"]):
            classes = el.get("class", [])
            class_str = " ".join(classes) if classes else ""
            if any(kw in class_str.lower() for kw in author_keywords):
                text = el.get_text(strip=True)
                if text and len(text) < 100:
                    matches.append(
                        {
                            "tag": el.name,
                            "selector": self._selector_for(el),
                            "text": text,
                        }
                    )
                if len(matches) >= 5:
                    break

        return matches

    def _element_match(self, element, include_classes: bool = False) -> Dict[str, Any]:
        result = {
            "tag": element.name,
            "text": element.get_text(strip=True)[:150],
            "selector": self._selector_for(element),
        }
        if include_classes:
            result["classes"] = element.get("class", [])
        return result

    def _selector_for(self, element, tag_name: str = "") -> str:
        if element.get("id"):
            return f"#{element.get('id')}"

        classes = element.get("class", [])
        class_suffix = "." + ".".join(classes) if classes else ""
        return f"{tag_name or element.name}{class_suffix}"
