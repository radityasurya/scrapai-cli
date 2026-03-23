"""
Spider analysis service for analyzing URLs and generating spider configurations.

Provides ATS platform detection and confidence scoring.
"""

import logging
import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from urllib.parse import urlparse

from utils.url_validation import validate_url_ssrf

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


# ATS Platform definitions with URL patterns and template configs
ATS_PLATFORMS = {
    "greenhouse": {
        "url_patterns": [r"job-boards\.greenhouse\.io", r"greenhouse\.io"],
        "job_url_pattern": r"/jobs/(\d+)",
        "template": {
            "rules": [
                {
                    "allow": [r"/jobs/\d+$"],
                    "deny": [],
                    "callback": "parse_job",
                    "follow": False,
                    "priority": 10,
                }
            ],
            "callbacks": {
                "parse_job": {
                    "extract": {
                        "title": {"css": "h1.job-title::text"},
                        "location": {"css": "span.location::text"},
                        "department": {"css": "span.department::text"},
                        "description": {"css": "div#content", "get_all": True},
                        "apply_url": {"css": "a.apply-button::attr(href)"},
                    }
                }
            },
            "settings": {"DOWNLOAD_DELAY": 1.0, "CONCURRENT_REQUESTS": 2},
        },
        "fields": ["title", "location", "department", "description", "apply_url"],
    },
    "personio": {
        "url_patterns": [r"jobs\.personio\.com", r"\.jobs\.personio\.com"],
        "job_url_pattern": r"job_id=([^&]+)",
        "template": {
            "rules": [
                {
                    "allow": [r"\?job_id="],
                    "deny": [],
                    "callback": "parse_job",
                    "follow": False,
                    "priority": 10,
                }
            ],
            "callbacks": {
                "parse_job": {
                    "extract": {
                        "title": {"css": "h1::text"},
                        "location": {"css": "span.job-location::text"},
                        "department": {"css": "span.job-department::text"},
                        "description": {"css": "div.job-description", "get_all": True},
                        "employment_type": {"css": "span.employment-type::text"},
                    }
                }
            },
            "settings": {"DOWNLOAD_DELAY": 1.0, "CONCURRENT_REQUESTS": 2},
        },
        "fields": ["title", "location", "department", "description", "employment_type"],
    },
    "lever": {
        "url_patterns": [r"lever\.co", r"\.lever\.co"],
        "job_url_pattern": r"/postings/([^/?]+)",
        "template": {
            "rules": [
                {
                    "allow": [r"/postings/[\w-]+$"],
                    "deny": [],
                    "callback": "parse_job",
                    "follow": False,
                    "priority": 10,
                }
            ],
            "callbacks": {
                "parse_job": {
                    "extract": {
                        "title": {"css": "h1::text"},
                        "location": {"css": "span.location::text"},
                        "department": {"css": "span.department::text"},
                        "description": {"css": "div.job-description", "get_all": True},
                        "apply_url": {"css": "a.apply-button::attr(href)"},
                    }
                }
            },
            "settings": {"DOWNLOAD_DELAY": 1.0, "CONCURRENT_REQUESTS": 2},
        },
        "fields": ["title", "location", "department", "description", "apply_url"],
    },
    "workable": {
        "url_patterns": [r"workable\.com", r"\.workable\.com"],
        "job_url_pattern": r"/jobs/([^/?]+)",
        "template": {
            "rules": [
                {
                    "allow": [r"/jobs/[\w-]+$"],
                    "deny": [],
                    "callback": "parse_job",
                    "follow": False,
                    "priority": 10,
                }
            ],
            "callbacks": {
                "parse_job": {
                    "extract": {
                        "title": {"css": "h1::text"},
                        "location": {"css": "span.location::text"},
                        "description": {"css": "div.job-description", "get_all": True},
                    }
                }
            },
            "settings": {"DOWNLOAD_DELAY": 1.0, "CONCURRENT_REQUESTS": 2},
        },
        "fields": ["title", "location", "description"],
    },
    "ashby": {
        "url_patterns": [r"ashbyhq\.com", r"\.ashbyhq\.com"],
        "job_url_pattern": r"/jobs/([^/?]+)",
        "template": {
            "rules": [
                {
                    "allow": [r"/jobs/[\w-]+$"],
                    "deny": [],
                    "callback": "parse_job",
                    "follow": False,
                    "priority": 10,
                }
            ],
            "callbacks": {
                "parse_job": {
                    "extract": {
                        "title": {"css": "h1::text"},
                        "location": {"css": "span.location::text"},
                        "description": {"css": "div.job-description", "get_all": True},
                    }
                }
            },
            "settings": {"DOWNLOAD_DELAY": 1.0, "CONCURRENT_REQUESTS": 2},
        },
        "fields": ["title", "location", "description"],
    },
}


class SpiderAnalysisService:
    """Service for analyzing URLs and generating spider configurations."""

    async def analyze_url(
        self,
        url: str,
        project: str = "default",
        use_browser: bool = False,
    ) -> Dict[str, Any]:
        """
        Analyze a URL and return a suggested spider configuration.

        Args:
            url: URL to analyze
            project: Project name
            use_browser: Whether to use browser mode for JS-rendered sites

        Returns:
            Analysis result with suggested config and confidence score
        """
        # Validate URL
        try:
            validated_url = validate_url_ssrf(url)
        except ValueError as e:
            return {"error": str(e), "success": False}

        parsed = urlparse(validated_url)
        domain = parsed.netloc.replace("www.", "")
        suggested_name = domain.replace(".", "_")

        # Try to detect ATS platform
        detected_platform = self._detect_platform(validated_url)
        analysis_mode = "template" if detected_platform else "full-analysis"

        if detected_platform:
            # Use template for known ATS platforms
            result = await self._analyze_with_template(
                validated_url, project, suggested_name, detected_platform
            )
        else:
            # Full analysis for unknown sites
            result = await self._analyze_full(validated_url, project, suggested_name, use_browser)
            analysis_mode = "full-analysis"

        result["analysis_mode"] = analysis_mode
        return result

    def _detect_platform(self, url: str) -> Optional[str]:
        """Detect ATS platform from URL patterns."""
        url_lower = url.lower()

        for platform, config in ATS_PLATFORMS.items():
            for pattern in config["url_patterns"]:
                if re.search(pattern, url_lower):
                    return platform

        return None

    async def _analyze_with_template(
        self,
        url: str,
        project: str,
        suggested_name: str,
        platform: str,
    ) -> Dict[str, Any]:
        """Generate config using ATS template."""
        platform_config = ATS_PLATFORMS[platform]
        template = platform_config["template"]

        parsed = urlparse(url)
        domain = parsed.netloc.replace("www.", "")

        # Build suggested config from template
        config = {
            "name": suggested_name,
            "allowed_domains": [domain],
            "start_urls": [url],
            "source_url": url,
            "rules": template.get("rules", []),
            "callbacks": template.get("callbacks", {}),
            "settings": template.get("settings", {}),
        }

        # Count job links (basic estimate)
        job_links_detected = 1  # Template assumes job listing page

        # Calculate confidence
        confidence_score = 0.95  # High confidence for known ATS
        warnings = []

        return {
            "success": True,
            "url": url,
            "domain": domain,
            "suggested_name": suggested_name,
            "detected_platform": platform,
            "confidence_score": confidence_score,
            "warnings": warnings,
            "analysis": {
                "title": f"{platform.title()} Job Board",
                "job_links_detected": job_links_detected,
                "expected_fields": platform_config.get("fields", []),
                "job_url_pattern": platform_config.get("job_url_pattern"),
            },
            "suggested_config": config,
        }

    async def _analyze_full(
        self,
        url: str,
        project: str,
        suggested_name: str,
        use_browser: bool,
    ) -> Dict[str, Any]:
        """Full analysis for unknown sites."""
        # Fetch HTML
        html_content = await self._fetch_html(url, use_browser)

        if not html_content:
            return {
                "success": False,
                "url": url,
                "error": "Failed to fetch page content",
                "confidence_score": 0.0,
                "warnings": ["Could not fetch page content"],
                "suggested_config": None,
            }

        parsed = urlparse(url)
        domain = parsed.netloc.replace("www.", "")

        # Parse HTML
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html_content, "lxml")

        # Analyze page structure
        analysis = self._analyze_structure(soup, url)

        # Generate basic config
        config = self._generate_basic_config(url, domain, suggested_name, soup, analysis)

        # Calculate confidence based on what we found
        confidence_score = self._calculate_confidence(analysis)
        warnings = self._generate_warnings(analysis)

        return {
            "success": True,
            "url": url,
            "domain": domain,
            "suggested_name": suggested_name,
            "detected_platform": None,
            "confidence_score": confidence_score,
            "warnings": warnings,
            "analysis": analysis,
            "suggested_config": config,
        }

    async def _fetch_html(self, url: str, use_browser: bool) -> Optional[str]:
        """Fetch HTML content from URL."""
        try:
            if use_browser:
                from utils.cf_browser import CloudflareBrowserClient

                async with CloudflareBrowserClient(headless=False) as browser:
                    return await browser.fetch(url)
            else:
                import aiohttp

                from settings import USER_AGENT

                timeout = aiohttp.ClientTimeout(total=30)
                headers = {"User-Agent": USER_AGENT}

                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=headers, timeout=timeout) as response:
                        if response.status == 200:
                            return await response.text()
                        return None
        except Exception as e:
            logger.error(f"Failed to fetch {url}: {e}")
            return None

    def _analyze_structure(self, soup: "BeautifulSoup", url: str) -> Dict[str, Any]:
        """Analyze HTML structure to find job listing patterns."""
        analysis = {
            "title": soup.title.text if soup.title else "Unknown",
            "total_links": len(soup.find_all("a")),
            "job_links_detected": 0,
            "possible_job_selectors": [],
            "possible_title_selectors": [],
            "possible_description_selectors": [],
        }

        # Look for common job listing patterns
        job_link_patterns = [
            r"/job/",
            r"/jobs/",
            r"/career",
            r"/careers",
            r"/position",
            r"/posting",
            r"\?job_id=",
        ]

        job_links = 0
        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            for pattern in job_link_patterns:
                if re.search(pattern, href, re.IGNORECASE):
                    job_links += 1
                    break

        analysis["job_links_detected"] = job_links

        # Try to find job listing containers
        job_containers = soup.find_all(
            ["div", "li", "article"],
            class_=re.compile(r"job|position|career|opening|listing", re.IGNORECASE),
        )
        if job_containers:
            analysis["possible_job_selectors"] = [
                f"div.{c.get('class', [''])[0]}" for c in job_containers[:3] if c.get("class")
            ]

        # Find title patterns
        titles = soup.find_all(
            ["h1", "h2", "h3"], class_=re.compile(r"title|heading", re.IGNORECASE)
        )
        if titles:
            analysis["possible_title_selectors"] = [
                f"{t.name}.{'.'.join(t.get('class', []))}" for t in titles[:3] if t.get("class")
            ]

        return analysis

    def _generate_basic_config(
        self,
        url: str,
        domain: str,
        suggested_name: str,
        soup: "BeautifulSoup",
        analysis: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Generate basic spider config from analysis."""
        # Extract job URL patterns from links
        job_patterns = []
        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            if "/job" in href.lower() or "/career" in href.lower():
                # Try to extract pattern
                pattern = re.sub(r"\d+", r"\\d+", href.split("?")[0])
                if pattern not in job_patterns and len(pattern) < 200:
                    job_patterns.append(pattern)

        if not job_patterns:
            job_patterns = ["/job/.*"]

        return {
            "name": suggested_name,
            "allowed_domains": [domain],
            "start_urls": [url],
            "source_url": url,
            "rules": [
                {
                    "allow": job_patterns[:3],  # Limit to top 3 patterns
                    "deny": [],
                    "callback": "parse_job",
                    "follow": True,
                    "priority": 10,
                }
            ],
            "callbacks": {
                "parse_job": {
                    "extract": {
                        "title": {"css": "h1::text"},
                        "description": {"css": "body", "get_all": True},
                    }
                }
            },
            "settings": {"DOWNLOAD_DELAY": 1.5, "CONCURRENT_REQUESTS": 1},
        }

    def _calculate_confidence(self, analysis: Dict[str, Any]) -> float:
        """Calculate confidence score based on analysis results."""
        score = 0.5  # Base score

        # Job links detected
        job_links = analysis.get("job_links_detected", 0)
        if job_links > 0:
            score += 0.1
        if job_links > 5:
            score += 0.1
        if job_links > 10:
            score += 0.1

        # Good selectors found
        if analysis.get("possible_job_selectors"):
            score += 0.1
        if analysis.get("possible_title_selectors"):
            score += 0.1

        return min(score, 0.99)

    def _generate_warnings(self, analysis: Dict[str, Any]) -> List[str]:
        """Generate warnings based on analysis."""
        warnings = []

        if analysis.get("job_links_detected", 0) == 0:
            warnings.append("No job links detected - may need manual URL pattern configuration")

        if not analysis.get("possible_job_selectors"):
            warnings.append("No clear job listing containers found - selectors may need adjustment")

        if analysis.get("confidence_score", 0) < 0.6:
            warnings.append("Low confidence - manual review and adjustment required")

        return warnings
