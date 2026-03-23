import asyncio
import json
import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

import newspaper
import trafilatura
from bs4 import BeautifulSoup

from .schemas import ScrapedArticle, ScrapedJob

logger = logging.getLogger(__name__)


class BaseExtractor(ABC):
    """Abstract base class for content extractors"""

    @abstractmethod
    def extract(
        self, url: str, html: str, title_hint: str = None, include_html: bool = False
    ) -> Optional[ScrapedArticle]:
        """
        Extract content from HTML.

        Args:
            url: The URL of the page
            html: The raw HTML content
            title_hint: Optional title extracted from other sources (e.g. metadata)
            include_html: Whether to include raw HTML in output (for JSONL exports)

        Returns:
            ScrapedArticle object or None if extraction fails
        """
        pass


class NewspaperExtractor(BaseExtractor):
    """Extractor using newspaper4k"""

    def extract(
        self, url: str, html: str, title_hint: str = None, include_html: bool = False
    ) -> Optional[ScrapedArticle]:
        try:
            # newspaper4k usually fetches itself, but we can pass html
            article = newspaper.Article(url)
            article.download(input_html=html)
            article.parse()

            # Use hint if newspaper failed to find title
            title = article.title
            if not title and title_hint:
                title = title_hint.strip()

            # Basic validation before creating model
            if not title or not article.text:
                text_len = len(article.text) if article.text else 0
                logger.warning(
                    f"NewspaperExtractor validation failed: title='{title}', text_len={text_len}"
                )
                return None

            return ScrapedArticle(
                url=url,
                title=title,
                content=article.text,
                author=", ".join(article.authors) if article.authors else None,
                published_date=article.publish_date,
                source="newspaper4k",
                metadata={
                    "top_image": article.top_image,
                    "keywords": article.keywords,
                    "summary": article.summary,
                },
                html=html if include_html else None,
            )
        except Exception as e:
            logger.debug(f"NewspaperExtractor failed for {url}: {e}")
            return None


class TrafilaturaExtractor(BaseExtractor):
    """Extractor using trafilatura"""

    def extract(
        self, url: str, html: str, title_hint: str = None, include_html: bool = False
    ) -> Optional[ScrapedArticle]:
        try:
            # trafilatura.bare_extraction returns a Document object or dict
            extracted = trafilatura.bare_extraction(html, url=url)

            if not extracted:
                return None

            # Convert to dict if it's a Document object
            if hasattr(extracted, "as_dict"):
                data = extracted.as_dict()
            elif isinstance(extracted, dict):
                data = extracted
            else:
                return None

            if not data.get("text"):
                return None

            # Use hint if trafilatura failed to find title
            title = data.get("title")
            if not title and title_hint:
                title = title_hint.strip()

            return ScrapedArticle(
                url=url,
                title=title or "",
                content=data.get("text"),
                author=data.get("author"),
                published_date=data.get("date"),
                source="trafilatura",
                metadata={
                    "description": data.get("description"),
                    "sitename": data.get("sitename"),
                    "categories": data.get("categories"),
                    "tags": data.get("tags"),
                    "fingerprint": data.get("fingerprint"),
                    "license": data.get("license"),
                },
                html=html if include_html else None,
            )
        except Exception as e:
            logger.debug(f"TrafilaturaExtractor failed for {url}: {e}")
            return None


class CustomExtractor(BaseExtractor):
    """Extractor using custom CSS selectors"""

    def __init__(self, selectors: Dict[str, str]):
        """
        Initialize with custom selectors.

        Args:
            selectors: Dict mapping field names to CSS selectors
                      e.g., {"title": "h1.title", "content": "div.article"}
        """
        self.selectors = selectors

    def extract(
        self, url: str, html: str, title_hint: str = None, include_html: bool = False
    ) -> Optional[ScrapedArticle]:
        """
        Extract content using custom CSS selectors.

        Standard fields: title, author, content, date
        Custom fields: anything else goes into metadata
        """
        try:
            soup = BeautifulSoup(html, "lxml")

            # Extract standard fields
            title = self._extract_text(soup, self.selectors.get("title"))
            logger.debug(
                f"Extracted title: '{title}' using selector '{self.selectors.get('title')}'"
            )
            if not title and title_hint:
                title = title_hint.strip()
                logger.debug(f"Using title hint: '{title}'")

            author = self._extract_text(soup, self.selectors.get("author"))
            logger.debug(
                f"Extracted author: '{author}' using selector '{self.selectors.get('author')}'"
            )

            content = self._extract_text(soup, self.selectors.get("content"))
            content_len = len(content) if content else 0
            logger.debug(
                "Extracted content: %s chars using selector '%s'",
                content_len,
                self.selectors.get("content"),
            )
            if content and content_len < 200:
                logger.debug(f"Content preview: '{content[:200]}'")

            date_str = self._extract_text(soup, self.selectors.get("date"))
            logger.debug(
                f"Extracted date: '{date_str}' using selector '{self.selectors.get('date')}'"
            )

            # Validation: at minimum need title and content
            if not title or not content:
                logger.warning(
                    f"CustomExtractor validation failed: title='{title}', content_len={content_len}"
                )
                return None

            # Parse date if present
            published_date = None
            if date_str:
                try:
                    from dateutil import parser

                    published_date = parser.parse(date_str)
                except Exception as e:
                    logger.debug(f"Failed to parse date '{date_str}': {e}")

            # Extract custom fields into metadata
            metadata = {}
            for field_name, selector in self.selectors.items():
                # Skip standard fields
                if field_name in ["title", "author", "content", "date"]:
                    continue

                # Extract custom field
                value = self._extract_text(soup, selector)
                if value:
                    metadata[field_name] = value

            return ScrapedArticle(
                url=url,
                title=title,
                content=content,
                author=author,
                published_date=published_date,
                source="custom",
                metadata=metadata,
                html=html if include_html else None,
            )

        except Exception as e:
            logger.error(f"CustomExtractor failed for {url}: {e}")
            return None

    def _extract_text(self, soup: BeautifulSoup, selector: Optional[str]) -> Optional[str]:
        """
        Extract text from HTML using CSS selector.

        Args:
            soup: BeautifulSoup object
            selector: CSS selector string

        Returns:
            Extracted text or None
        """
        if not selector:
            return None

        try:
            # Find element
            element = soup.select_one(selector)
            if not element:
                logger.debug(f"Selector '{selector}' found no elements")
                return None

            # Get text and clean it
            text = element.get_text(separator=" ", strip=True)
            return text if text else None

        except Exception as e:
            logger.debug(f"Error extracting with selector '{selector}': {e}")
            return None


class SmartExtractor:
    """
    Intelligent extractor that tries multiple strategies in order.
    Strategies:
    1. 'custom': Use custom CSS selectors if provided
    2. 'newspaper': Use newspaper4k on provided HTML
    3. 'trafilatura': Use trafilatura on provided HTML
    4. 'playwright': Fetch rendered HTML via browser, then try trafilatura
    """

    def __init__(self, strategies: List[str] = None, custom_selectors: Dict[str, str] = None):
        self.strategies = strategies or ["newspaper", "trafilatura", "playwright"]
        self.custom_selectors = custom_selectors

    async def extract(
        self,
        url: str,
        html: str,
        title_hint: str = None,
        include_html: bool = False,
        wait_for_selector: str = None,
        additional_delay: float = 0,
        enable_scroll: bool = False,
        max_scrolls: int = 5,
        scroll_delay: float = 1.0,
    ) -> Optional[ScrapedArticle]:
        """
        Async version of extract method with Playwright support.

        Tries each strategy in order, including Playwright for JS-rendered content.
        Falls back to next strategy if one fails.

        Args:
            url: The URL of the page
            html: The raw HTML content
            title_hint: Optional title extracted from other sources
            include_html: Whether to include raw HTML in output
            wait_for_selector: CSS selector to wait for when using Playwright
            additional_delay: Additional seconds to wait after page load when using Playwright
            enable_scroll: Whether to perform infinite scroll when using Playwright
            max_scrolls: Maximum number of scrolls to perform
            scroll_delay: Delay between scrolls in seconds
        """
        # Try each strategy in order
        for strategy in self.strategies:
            if strategy == "custom":
                if self.custom_selectors:
                    logger.info(f"Trying custom extractor for {url}")
                    try:
                        result = await asyncio.to_thread(
                            CustomExtractor(self.custom_selectors).extract,
                            url,
                            html,
                            title_hint,
                            include_html,
                        )
                        if result:
                            logger.info(f"Successfully extracted {url} using custom")
                            return result
                        else:
                            logger.debug(f"Custom extractor returned no result for {url}")
                    except Exception as e:
                        logger.debug(f"Custom extractor failed for {url}: {e}")
                else:
                    logger.debug("Skipping 'custom' strategy - no custom selectors provided")

            elif strategy == "newspaper":
                logger.info(f"Trying newspaper extractor for {url}")
                try:
                    result = await asyncio.to_thread(
                        NewspaperExtractor().extract,
                        url,
                        html,
                        title_hint,
                        include_html,
                    )
                    if result:
                        logger.info(f"Successfully extracted {url} using newspaper")
                        return result
                    else:
                        logger.debug(f"Newspaper extractor returned no result for {url}")
                except Exception as e:
                    logger.debug(f"Newspaper extractor failed for {url}: {e}")

            elif strategy == "trafilatura":
                logger.info(f"Trying trafilatura extractor for {url}")
                try:
                    result = await asyncio.to_thread(
                        TrafilaturaExtractor().extract,
                        url,
                        html,
                        title_hint,
                        include_html,
                    )
                    if result:
                        logger.info(f"Successfully extracted {url} using trafilatura")
                        return result
                    else:
                        logger.debug(f"Trafilatura extractor returned no result for {url}")
                except Exception as e:
                    logger.debug(f"Trafilatura extractor failed for {url}: {e}")

            elif strategy == "playwright":
                logger.info(f"Trying playwright extractor for {url}")
                try:
                    result = await self._extract_with_playwright_async(
                        url,
                        title_hint,
                        include_html,
                        wait_for_selector,
                        additional_delay,
                        enable_scroll,
                        max_scrolls,
                        scroll_delay,
                    )
                    if result:
                        logger.info(f"Successfully extracted {url} using playwright")
                        return result
                    else:
                        logger.debug(f"Playwright extractor returned no result for {url}")
                except Exception as e:
                    logger.debug(f"Playwright extractor failed for {url}: {e}")

        # All extractors failed
        logger.error(f"All extractors failed for {url}")
        return None

    async def _extract_with_playwright_async(
        self,
        url: str,
        title_hint: str = None,
        include_html: bool = False,
        wait_for_selector: str = None,
        additional_delay: float = 0,
        enable_scroll: bool = False,
        max_scrolls: int = 5,
        scroll_delay: float = 1.0,
    ) -> Optional[ScrapedArticle]:
        """
        Fetch via Playwright (async) and extract using Trafilatura

        Args:
            url: The URL to fetch
            title_hint: Optional title hint
            include_html: Whether to include raw HTML in output
            wait_for_selector: CSS selector to wait for after navigation
            additional_delay: Additional seconds to wait after page load
            enable_scroll: Whether to perform infinite scroll
            max_scrolls: Maximum number of scrolls to perform
            scroll_delay: Delay between scrolls in seconds
        """
        try:
            logger.info(f"Starting Playwright fetch for {url}")
            if wait_for_selector:
                logger.info(f"Will wait for selector: {wait_for_selector}")
            if additional_delay > 0:
                logger.info(f"Will wait additional {additional_delay} seconds")
            if enable_scroll:
                logger.info(
                    "Will perform infinite scroll: %s scrolls with %ss delay",
                    max_scrolls,
                    scroll_delay,
                )

            from utils.cf_browser import CloudflareBrowserClient

            async with CloudflareBrowserClient(headless=False) as browser:
                logger.info("CloudflareBrowserClient started")

                # Navigate to URL
                await browser.page.goto(url, wait_until="networkidle", timeout=60000)
                logger.info(f"Navigated to {url}")

                # Wait for selector if specified
                if wait_for_selector:
                    await browser.page.wait_for_selector(wait_for_selector, timeout=30000)
                    logger.info(f"Selector found: {wait_for_selector}")

                # Additional delay if specified
                if additional_delay > 0:
                    await asyncio.sleep(additional_delay)

                # Infinite scroll if enabled
                if enable_scroll:
                    for i in range(max_scrolls):
                        await browser.page.evaluate(
                            "window.scrollTo(0, document.body.scrollHeight)"
                        )
                        await asyncio.sleep(scroll_delay)
                        logger.info(f"Scroll {i + 1}/{max_scrolls}")

                logger.info("Browser navigated")
                html = await browser.page.content()
                logger.info(f"Got HTML from browser: {len(html)} bytes")
                if html:
                    # Try Trafilatura on rendered HTML
                    return await asyncio.to_thread(
                        TrafilaturaExtractor().extract,
                        url,
                        html,
                        title_hint,
                        include_html,
                    )
                else:
                    logger.warning("Browser navigation failed")
        except Exception as e:
            logger.error(f"Playwright fetch failed: {e}")
            import traceback

            logger.error(traceback.format_exc())
        return None


class JobExtractor:
    """Extractor for job posting pages using JSON-LD and HTML heuristics."""

    def extract(
        self, url: str, html: str, title_hint: str = None, include_html: bool = False
    ) -> Optional[ScrapedJob]:
        """
        Extract job data from HTML.

        Extraction order:
        1. JSON-LD JobPosting schema
        2. HTML heuristics for common job fields
        3. Fallback to title_hint and minimal data

        Args:
            url: The URL of the page
            html: The raw HTML content
            title_hint: Optional title extracted from other sources
            include_html: Whether to include raw HTML in output

        Returns:
            ScrapedJob object or None if extraction fails
        """
        try:
            soup = BeautifulSoup(html, "lxml")

            job_data = {}

            json_ld_data = self._extract_json_ld(soup)
            if json_ld_data:
                logger.info(f"Found JSON-LD JobPosting data for {url}")
                job_data.update(json_ld_data)

            html_data = self._extract_html_heuristics(soup)
            if html_data:
                for key, value in html_data.items():
                    if key not in job_data or not job_data.get(key):
                        job_data[key] = value

            if title_hint and ("title" not in job_data or not job_data.get("title")):
                job_data["title"] = title_hint.strip()

            if not job_data.get("title"):
                logger.warning(f"JobExtractor: No title found for {url}")
                return None

            has_identifying_field = any(
                [
                    job_data.get("company"),
                    job_data.get("location"),
                    job_data.get("job_id"),
                    job_data.get("description"),
                ]
            )

            if not has_identifying_field:
                logger.warning(f"JobExtractor: No identifying fields found for {url}")
                return None

            return ScrapedJob(
                url=url,
                title=job_data.get("title", ""),
                company=job_data.get("company"),
                location=job_data.get("location"),
                description=job_data.get("description"),
                employment_type=job_data.get("employment_type"),
                posted_date=job_data.get("posted_date"),
                closing_date=job_data.get("closing_date"),
                remote=job_data.get("remote"),
                job_id=job_data.get("job_id"),
                source="job_extractor",
                metadata=job_data.get("metadata", {}),
                html=html if include_html else None,
            )

        except Exception as e:
            logger.error(f"JobExtractor failed for {url}: {e}")
            return None

    def _extract_json_ld(self, soup: BeautifulSoup) -> Optional[Dict]:
        """Extract JobPosting data from JSON-LD structured data."""
        try:
            scripts = soup.find_all("script", type="application/ld+json")

            for script in scripts:
                try:
                    data = json.loads(script.string)

                    if data.get("@type") == "JobPosting":
                        return self._parse_job_posting_json_ld(data)

                    graph = data.get("@graph", [])
                    if isinstance(graph, list):
                        for item in graph:
                            if isinstance(item, dict) and item.get("@type") == "JobPosting":
                                return self._parse_job_posting_json_ld(item)

                except (json.JSONDecodeError, TypeError):
                    continue

            return None

        except Exception as e:
            logger.debug(f"Error extracting JSON-LD: {e}")
            return None

    def _parse_job_posting_json_ld(self, data: Dict) -> Dict:
        """Parse JobPosting JSON-LD data into job fields."""
        job_data = {}

        title = data.get("title")
        if title:
            job_data["title"] = str(title)

        description = data.get("description")
        if description:
            job_data["description"] = str(description)

        organization = data.get("hiringOrganization") or data.get("employer")
        if organization:
            if isinstance(organization, dict):
                job_data["company"] = organization.get("name", "")
            else:
                job_data["company"] = str(organization)

        location = data.get("jobLocation")
        if location:
            if isinstance(location, dict):
                address = location.get("address", {})
                parts = [
                    address.get("addressLocality", ""),
                    address.get("addressRegion", ""),
                    address.get("addressCountry", ""),
                ]
                parts = [p for p in parts if p]
                job_data["location"] = ", ".join(parts) if parts else None
            else:
                job_data["location"] = str(location)

        employment_type = data.get("employmentType")
        if employment_type:
            job_data["employment_type"] = str(employment_type)

        date_posted = data.get("datePosted")
        if date_posted:
            try:
                from dateutil import parser

                job_data["posted_date"] = parser.parse(str(date_posted))
            except Exception:
                job_data["posted_date"] = None

        valid_through = data.get("validThrough")
        if valid_through:
            try:
                from dateutil import parser

                job_data["closing_date"] = parser.parse(str(valid_through))
            except Exception:
                job_data["closing_date"] = None

        job_location_type = data.get("jobLocationType")
        if job_location_type:
            location_type = str(job_location_type).lower()
            job_data["remote"] = any(token in location_type for token in ["remote", "telecommute"])

        identifier = data.get("identifier")
        if identifier:
            job_data["job_id"] = str(identifier)

        base_salary = data.get("baseSalary")
        estimated_salary = data.get("estimatedSalary")
        salary_data = base_salary or estimated_salary
        if salary_data:
            metadata = job_data.setdefault("metadata", {})
            if isinstance(salary_data, dict):
                value = salary_data.get("value")
                currency = salary_data.get("currency", "USD")
                unit_text = salary_data.get("unitText", "")
                if isinstance(value, dict):
                    unit_text = value.get("unitText", unit_text)
                    value = value.get("value")
                if value:
                    metadata["salary_value"] = value
                    metadata["salary_currency"] = currency
                    metadata["salary_period"] = unit_text
            else:
                metadata["salary_text"] = str(salary_data)

        return job_data

    def _extract_html_heuristics(self, soup: BeautifulSoup) -> Optional[Dict]:
        """Extract job data using common HTML patterns and selectors."""
        job_data = {}

        title_selectors = [
            "h1[class*='job']",
            "h1[class*='title']",
            ".job-title",
            ".job-title",
            "[class*='job-title']",
            "[class*='jobTitle']",
            "h1",
        ]
        for selector in title_selectors:
            element = soup.select_one(selector)
            if element:
                text = element.get_text(strip=True)
                if text and len(text) > 5:
                    job_data["title"] = text
                    break

        company_selectors = [
            "[class*='company']",
            "[class*='employer']",
            "[class*='organization']",
            ".company-name",
            ".employer-name",
            "a[href*='company']",
        ]
        for selector in company_selectors:
            element = soup.select_one(selector)
            if element:
                text = element.get_text(strip=True)
                if text and len(text) > 1:
                    job_data["company"] = text
                    break

        location_selectors = [
            "[class*='location']",
            "[class*='where']",
            "[class*='place']",
            ".job-location",
            ".location",
        ]
        for selector in location_selectors:
            element = soup.select_one(selector)
            if element:
                text = element.get_text(strip=True)
                if text and len(text) > 1:
                    job_data["location"] = text
                    break

        desc_selectors = [
            "[class*='description']",
            "[class*='detail']",
            "[class*='content']",
            ".job-description",
            ".description",
            "article",
            "[role='main']",
            "main",
        ]
        for selector in desc_selectors:
            element = soup.select_one(selector)
            if element:
                text = element.get_text(separator=" ", strip=True)
                if text and len(text) > 100:
                    job_data["description"] = text
                    break

        type_selectors = [
            "[class*='type']",
            "[class*='employment']",
            "[class*='commitment']",
            ".employment-type",
            ".job-type",
        ]
        for selector in type_selectors:
            element = soup.select_one(selector)
            if element:
                text = element.get_text(strip=True)
                if text:
                    job_data["employment_type"] = text
                    break

        remote_indicators = [
            ("[class*='remote']", True),
            ("[class*='work-from-home']", True),
            ("[class*='hybrid']", None),
            ("[class*='on-site']", False),
        ]
        for selector, is_remote in remote_indicators:
            element = soup.select_one(selector)
            if element:
                text = element.get_text(strip=True).lower()
                if is_remote is True or "remote" in text or "work from home" in text:
                    job_data["remote"] = True
                elif is_remote is False or "on-site" in text or "onsite" in text:
                    job_data["remote"] = False
                break

        time_elements = soup.find_all("time")
        for time_elem in time_elements:
            datetime_attr = time_elem.get("datetime")
            if datetime_attr:
                try:
                    from dateutil import parser

                    parsed_date = parser.parse(datetime_attr)
                    text = time_elem.get_text(strip=True).lower()
                    if any(word in text for word in ["posted", "published", "date"]):
                        job_data["posted_date"] = parsed_date
                    elif any(
                        word in text for word in ["closing", "deadline", "expires", "through"]
                    ):
                        job_data["closing_date"] = parsed_date
                    elif "posted_date" not in job_data:
                        job_data["posted_date"] = parsed_date
                    break
                except Exception:
                    pass

        return job_data
