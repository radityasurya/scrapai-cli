"""
Spider analysis service for analyzing URLs and generating spider configurations.

Provides ATS platform detection and confidence scoring.
"""

import json
import logging
import os
import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from urllib.parse import urlparse

from utils.url_validation import validate_url_ssrf

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_ANALYZE_PROMPT = """You are an expert web scraping engineer.
Analyze the HTML below from a job board and generate a production-ready Scrapy spider config JSON.

URL: {url}
Domain: {domain}
Company name: {company_name}
Company slug: {company_slug}

HTML (condensed):
{html}

Return ONLY valid JSON with this exact structure:
{{
  "name": "{suggested_name}",
  "source_url": "{url}",
  "allowed_domains": ["{domain}"],
  "start_urls": ["{url}"],
  "rules": [
    {{
      "allow": ["<regex matching the listing page URL — must match {url}>"],
      "callback": "parse_listing",
      "follow": false
    }}
  ],
  "callbacks": {{
    "parse_listing": {{
      "extract": {{
        "source_job_id": {{
          "css": "a::attr(href)",
          "processors": [{{"type": "regex", "pattern": "<regex with one capture group extracting a stable job ID from job link hrefs — numeric ID, UUID, or last path segment>"}}]
        }}
      }},
      "iterate": {{
        "selector": "<CSS selector matching each repeating job card or row element on the listing page>",
        "follow": {{
          "url": {{"css": "a::attr(href)"}},
          "callback": "parse_job_detail"
        }},
        "url_context": {{
          "company_slug": {{"regex": "<regex with one capture group extracting the company identifier from the listing URL — e.g. subdomain or path segment>"}}
        }}
      }}
    }},
    "parse_job_detail": {{
      "extract": {{
        "title": {{"css": "<selector>::text", "processors": [{{"type": "strip"}}]}},
        "company": {{
          "xpath": "//no-match-placeholder",
          "processors": [{{"type": "default", "default": "{company_name}"}}]
        }},
        "description": {{"css": "<selector>"}},
        "location": {{"css": "<selector>::text", "processors": [{{"type": "strip"}}]}},
        "department": {{"css": "<selector>::text", "processors": [{{"type": "strip"}}]}}
      }}
    }}
  }},
  "settings": {{
    "DOWNLOAD_DELAY": 1.5,
    "CONCURRENT_REQUESTS": 1
  }},
  "_analysis": {{
    "confidence": <0.0-1.0>,
    "detected_platform": "<platform name or null>",
    "warnings": ["<any issues found>"],
    "job_links_detected": <count>
  }}
}}

Rules:
- iterate.selector: CSS selector for the repeating job card/row container on the listing page
- source_job_id: regex must have exactly ONE capture group; match numeric IDs, UUIDs, or the last non-empty path segment
- company_slug regex: must have exactly ONE capture group; match the company identifier in the listing URL
- Use ::text for text content, ::attr(href) for links
- If location or department are not visible in the HTML, use: {{"xpath": "//no-match-placeholder", "processors": [{{"type": "default", "default": ""}}]}}
- Only include fields you can actually observe in the HTML structure"""


# ATS Platform definitions — iterate-based configs with url_context for slug generation
ATS_PLATFORMS = {
    "greenhouse": {
        "url_patterns": [r"job-boards\.greenhouse\.io", r"boards\.greenhouse\.io"],
        "company_slug_regex": r"greenhouse\.io/([^/?]+)",
        "listing_allow": r"greenhouse\.io/{company_slug}$",
        "iterate_selector": "tr.job-post",
        "source_job_id_regex": r"/jobs/(\d+)",
        "url_context_regex": r"greenhouse\.io/([^/?]+)",
        "detail_selectors": {
            "title": {"css": "h1.section-header::text", "processors": [{"type": "strip"}]},
            "description": {"css": "div.job__description"},
            "location": {"css": "div.job__location div::text", "processors": [{"type": "strip"}]},
            "department": {"xpath": "//no-match-placeholder", "processors": [{"type": "default", "default": ""}]},
        },
        "settings": {"DOWNLOAD_DELAY": 1.0, "CONCURRENT_REQUESTS": 2},
    },
    "personio": {
        "url_patterns": [r"jobs\.personio\.com", r"\.jobs\.personio\.com"],
        "company_slug_regex": r"://([^.]+)\.jobs\.personio\.com",
        "listing_allow": r"{company_slug}\.jobs\.personio\.com",
        "iterate_selector": "a.job-box",
        "source_job_id_regex": r"/job/(\d+)",
        "url_context_regex": r"://([^.]+)\.jobs\.personio\.com",
        "detail_selectors": {
            "title": {"css": "h1.detail-title::text", "processors": [{"type": "strip"}]},
            "description": {"css": "div.detail-content-block-conditions"},
            "location": {"css": "div.JobAttributes_jobMetaItemLocation__MX4Xg span::text", "processors": [{"type": "strip"}]},
            "department": {"xpath": "//no-match-placeholder", "processors": [{"type": "default", "default": ""}]},
        },
        "settings": {"DOWNLOAD_DELAY": 1.0, "CONCURRENT_REQUESTS": 2},
    },
    "lever": {
        "url_patterns": [r"jobs\.lever\.co"],
        "company_slug_regex": r"lever\.co/([^/?]+)",
        "listing_allow": r"lever\.co/{company_slug}$",
        "iterate_selector": "div.posting",
        "source_job_id_regex": r"/postings/([a-f0-9-]{36})",
        "url_context_regex": r"lever\.co/([^/?]+)",
        "detail_selectors": {
            "title": {"css": "h2::text", "processors": [{"type": "strip"}]},
            "description": {"css": "div.posting-description"},
            "location": {"css": "div.location::text", "processors": [{"type": "strip"}]},
            "department": {"css": "div.team::text", "processors": [{"type": "strip"}]},
        },
        "settings": {"DOWNLOAD_DELAY": 1.0, "CONCURRENT_REQUESTS": 2},
    },
    "workable": {
        "url_patterns": [r"apply\.workable\.com"],
        "company_slug_regex": r"workable\.com/([^/?]+)",
        "listing_allow": r"workable\.com/{company_slug}",
        "iterate_selector": "li.jobs-list-section__item",
        "source_job_id_regex": r"/jobs/([^/?]+)",
        "url_context_regex": r"workable\.com/([^/?]+)",
        "detail_selectors": {
            "title": {"css": "h1::text", "processors": [{"type": "strip"}]},
            "description": {"css": "div.job-description"},
            "location": {"css": "span.location::text", "processors": [{"type": "strip"}]},
            "department": {"xpath": "//no-match-placeholder", "processors": [{"type": "default", "default": ""}]},
        },
        "settings": {"DOWNLOAD_DELAY": 1.0, "CONCURRENT_REQUESTS": 2},
    },
    "ashby": {
        "url_patterns": [r"jobs\.ashbyhq\.com"],
        "company_slug_regex": r"ashbyhq\.com/([^/?]+)",
        "listing_allow": r"ashbyhq\.com/{company_slug}$",
        "iterate_selector": "a[class*='_container_']",
        "source_job_id_regex": r"/[^/]+/([a-f0-9-]{36})",
        "url_context_regex": r"ashbyhq\.com/([^/?]+)",
        "detail_selectors": {
            "title": {"css": "h1.ashby-job-posting-heading::text", "processors": [{"type": "strip"}]},
            "description": {"css": "div.ashby-job-posting-brief-description"},
            "location": {"css": "div.ashby-job-posting-brief-details p::text", "processors": [{"type": "strip"}]},
            "department": {"xpath": "//no-match-placeholder", "processors": [{"type": "default", "default": ""}]},
        },
        "settings": {"DOWNLOAD_DELAY": 1.5, "CONCURRENT_REQUESTS": 1, "CLOUDFLARE_ENABLED": True},
    },
}


class SpiderAnalysisService:
    """Service for analyzing URLs and generating spider configurations."""

    async def analyze_url(
        self,
        url: str,
        project: str = "default",
        use_browser: bool = False,
        prompt_only: bool = False,
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
            result = await self._analyze_full(validated_url, project, suggested_name, use_browser, prompt_only=prompt_only)
            analysis_mode = "prompt_only" if prompt_only else "full-analysis"

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
        """Generate config using ATS template with iterate+url_context structure."""
        platform_config = ATS_PLATFORMS[platform]

        parsed = urlparse(url)
        domain = parsed.netloc.replace("www.", "")

        # Extract company slug from the URL
        company_slug_match = re.search(platform_config["company_slug_regex"], url)
        company_slug = company_slug_match.group(1) if company_slug_match else re.sub(r"[^a-z0-9]+", "-", domain.split(".")[0].lower()).strip("-")
        # Derive company name from the slug (e.g. "stripe" → "Stripe"), not the platform domain
        company_name = company_slug.replace("-", " ").title()

        listing_allow = platform_config["listing_allow"].replace("{company_slug}", re.escape(company_slug))

        config = {
            "name": suggested_name,
            "allowed_domains": [domain],
            "start_urls": [url],
            "source_url": url,
            "rules": [
                {"allow": [listing_allow], "callback": "parse_listing", "follow": False}
            ],
            "callbacks": {
                "parse_listing": {
                    "extract": {
                        "source_job_id": {
                            "css": "a::attr(href)",
                            "processors": [{"type": "regex", "pattern": platform_config["source_job_id_regex"]}],
                        }
                    },
                    "iterate": {
                        "selector": platform_config["iterate_selector"],
                        "follow": {"url": {"css": "a::attr(href)"}, "callback": "parse_job_detail"},
                        "url_context": {
                            "company_slug": {"regex": platform_config["url_context_regex"]}
                        },
                    },
                },
                "parse_job_detail": {
                    "extract": {
                        **platform_config["detail_selectors"],
                        "company": {
                            "xpath": "//no-match-placeholder",
                            "processors": [{"type": "default", "default": company_name}],
                        },
                    }
                },
            },
            "settings": platform_config.get("settings", {}),
        }

        return {
            "success": True,
            "url": url,
            "domain": domain,
            "suggested_name": suggested_name,
            "detected_platform": platform,
            "confidence_score": 0.95,
            "warnings": [],
            "analysis": {
                "title": f"{platform.title()} Job Board",
                "job_links_detected": 1,
                "company_slug": company_slug,
            },
            "suggested_config": config,
        }

    async def _analyze_full(
        self,
        url: str,
        project: str,
        suggested_name: str,
        use_browser: bool,
        prompt_only: bool = False,
    ) -> Dict[str, Any]:
        """Full analysis for unknown sites. Uses Claude AI if ANTHROPIC_API_KEY is set."""
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

        if prompt_only or os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENAI_API_KEY"):
            return await self._analyze_with_ai(url, domain, suggested_name, html_content, prompt_only=prompt_only)

        # Fallback: heuristic analysis
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html_content, "lxml")
        analysis = self._analyze_structure(soup, url)
        config = self._generate_basic_config(url, domain, suggested_name, soup, analysis)
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

    async def _analyze_with_ai(
        self,
        url: str,
        domain: str,
        suggested_name: str,
        html_content: str,
        prompt_only: bool = False,
    ) -> Dict[str, Any]:
        """Use Claude/GLM to analyze the page and generate a spider config."""
        try:
            from bs4 import BeautifulSoup

            # Condense HTML: strip scripts/styles, limit to 12k chars
            soup = BeautifulSoup(html_content, "lxml")
            for tag in soup(["script", "style", "noscript", "svg", "img"]):
                tag.decompose()
            condensed_html = soup.get_text(separator=" ", strip=True)[:4000]
            # Also include raw HTML structure (tags + classes) for selector discovery
            html_structure = str(soup)[:8000]
            combined = (
                f"=== TEXT CONTENT ===\n{condensed_html}\n\n"
                f"=== HTML STRUCTURE ===\n{html_structure}"
            )

            company_name, company_slug = self._derive_company_from_domain(domain)
            prompt = _ANALYZE_PROMPT.format(
                url=url,
                domain=domain,
                suggested_name=suggested_name,
                html=combined,
                company_name=company_name,
                company_slug=company_slug,
            )

            if prompt_only:
                return {
                    "success": True,
                    "url": url,
                    "domain": domain,
                    "suggested_name": suggested_name,
                    "detected_platform": None,
                    "confidence_score": 0.0,
                    "warnings": ["prompt_only mode — paste this prompt into any AI chat to get the config JSON"],
                    "analysis": {"title": domain, "job_links_detected": 0, "ai_powered": False},
                    "suggested_config": None,
                    "prompt": prompt,
                    "analysis_mode": "prompt_only",
                }

            model = os.getenv("SCRAPAI_ANALYZE_MODEL", "glm-4-flash")
            api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENAI_API_KEY")
            base_url = os.getenv("ANTHROPIC_BASE_URL") or os.getenv(
                "OPENAI_BASE_URL", "https://api.z.ai/api/paas/v4/"
            )

            from openai import OpenAI

            client = OpenAI(api_key=api_key, base_url=base_url)
            message = client.chat.completions.create(
                model=model,
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
            )

            raw = message.choices[0].message.content.strip()
            # Strip markdown code fences if present
            if raw.startswith("```"):
                raw = re.sub(r"^```[a-z]*\n?", "", raw)
                raw = re.sub(r"\n?```$", "", raw)

            config = json.loads(raw)
            ai_analysis = config.pop("_analysis", {})

            return {
                "success": True,
                "url": url,
                "domain": domain,
                "suggested_name": suggested_name,
                "detected_platform": ai_analysis.get("detected_platform"),
                "confidence_score": ai_analysis.get("confidence", 0.75),
                "warnings": ai_analysis.get("warnings", []),
                "analysis": {
                    "title": soup.title.text if soup.title else "Unknown",
                    "job_links_detected": ai_analysis.get("job_links_detected", 0),
                    "ai_powered": True,
                    "model": model,
                },
                "suggested_config": config,
                "analysis_mode": "ai",
            }

        except json.JSONDecodeError as e:
            logger.warning(f"AI returned invalid JSON, falling back to heuristic: {e}")
        except Exception as e:
            logger.warning(f"AI analysis failed, falling back to heuristic: {e}")

        # Fallback to heuristic on any AI failure
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html_content, "lxml")
        analysis = self._analyze_structure(soup, url)
        config = self._generate_basic_config(url, domain, suggested_name, soup, analysis)
        return {
            "success": True,
            "url": url,
            "domain": domain,
            "suggested_name": suggested_name,
            "detected_platform": None,
            "confidence_score": self._calculate_confidence(analysis),
            "warnings": self._generate_warnings(analysis)
            + ["AI analysis unavailable, using heuristic"],
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

        company_name, company_slug = self._derive_company_from_domain(domain)
        # Derive a generic source_job_id pattern: last non-empty path segment
        source_job_id_regex = r"/([^/?#]+)/?$"
        url_context_regex = re.escape(domain) + r"(?:/[^/?]+)?"

        return {
            "name": suggested_name,
            "allowed_domains": [domain],
            "start_urls": [url],
            "source_url": url,
            "rules": [
                {
                    "allow": [re.escape(urlparse(url).path.rstrip("/")) + r"$"],
                    "deny": [],
                    "callback": "parse_listing",
                    "follow": False,
                    "priority": 10,
                }
            ],
            "callbacks": {
                "parse_listing": {
                    "extract": {
                        "source_job_id": {
                            "css": "a::attr(href)",
                            "processors": [{"type": "regex", "pattern": source_job_id_regex}],
                        }
                    },
                    "iterate": {
                        "selector": "a[href]",
                        "follow": {"url": {"css": "::attr(href)"}, "callback": "parse_job_detail"},
                        "url_context": {
                            "company_slug": {"regex": url_context_regex.replace(re.escape(domain), re.escape(company_slug))}
                        },
                    },
                },
                "parse_job_detail": {
                    "extract": {
                        "title": {"css": "h1::text", "processors": [{"type": "strip"}]},
                        "company": {
                            "xpath": "//no-match-placeholder",
                            "processors": [{"type": "default", "default": company_name}],
                        },
                        "description": {"css": "body"},
                        "location": {"xpath": "//no-match-placeholder", "processors": [{"type": "default", "default": ""}]},
                        "department": {"xpath": "//no-match-placeholder", "processors": [{"type": "default", "default": ""}]},
                    }
                },
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

    @staticmethod
    def _derive_company_from_domain(domain: str) -> tuple:
        """Return (company_name, company_slug) derived from a domain.

        careers.bol.com → ("Bol", "bol")
        boards.greenhouse.io → ("Greenhouse", "greenhouse")
        """
        host = domain.lower()
        for prefix in ("careers.", "jobs.", "job.", "apply.", "work.", "boards.", "hiring."):
            if host.startswith(prefix):
                host = host[len(prefix):]
                break
        core = host.split(".")[0]
        slug = re.sub(r"[^a-z0-9]+", "-", core).strip("-") or "company"
        name = core.replace("-", " ").title()
        return name, slug
