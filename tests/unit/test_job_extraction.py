"""
Unit tests for job extraction.
"""

from datetime import datetime

import pytest

from core.extractors import JobExtractor
from core.schemas import ScrapedJob


class TestScrapedJob:
    """Test ScrapedJob schema validation."""

    @pytest.mark.unit
    def test_valid_job_with_minimal_fields(self):
        """Test that a job with title and company is valid."""
        job = ScrapedJob(
            url="https://example.com/job/123",
            title="Software Engineer",
            company="Example Corp",
            source="test",
        )
        assert job.title == "Software Engineer"
        assert job.company == "Example Corp"

    @pytest.mark.unit
    def test_valid_job_with_all_fields(self):
        """Test that a job with all fields is valid."""
        job = ScrapedJob(
            url="https://example.com/job/123",
            title="Senior Software Engineer",
            company="Tech Corp",
            location="San Francisco, CA",
            description="We are looking for a senior engineer...",
            employment_type="Full-time",
            posted_date=datetime(2024, 1, 15),
            closing_date=datetime(2024, 2, 15),
            remote=True,
            job_id="JOB-123",
            source="test",
        )
        assert job.title == "Senior Software Engineer"
        assert job.remote is True

    @pytest.mark.unit
    def test_title_too_short_raises_error(self):
        """Test that title too short raises validation error."""
        with pytest.raises(ValueError):
            ScrapedJob(
                url="https://example.com/job/123",
                title="AB",
                company="Example Corp",
                source="test",
            )

    @pytest.mark.unit
    def test_missing_identifying_field_raises_error(self):
        """Test that missing company/location/job_id/description raises error."""
        with pytest.raises(ValueError):
            ScrapedJob(
                url="https://example.com/job/123",
                title="Software Engineer",
                source="test",
            )

    @pytest.mark.unit
    def test_job_with_location_is_valid(self):
        """Test that a job with title and location is valid."""
        job = ScrapedJob(
            url="https://example.com/job/123",
            title="Software Engineer",
            location="Remote",
            source="test",
        )
        assert job.location == "Remote"

    @pytest.mark.unit
    def test_job_with_description_is_valid(self):
        """Test that a job with title and description is valid."""
        job = ScrapedJob(
            url="https://example.com/job/123",
            title="Software Engineer",
            description="A great job opportunity...",
            source="test",
        )
        assert job.description == "A great job opportunity..."

    @pytest.mark.unit
    def test_job_with_job_id_is_valid(self):
        """Test that a job with title and job_id is valid."""
        job = ScrapedJob(
            url="https://example.com/job/123",
            title="Software Engineer",
            job_id="JOB-456",
            source="test",
        )
        assert job.job_id == "JOB-456"


class TestJobExtractor:
    """Test JobExtractor class."""

    @pytest.fixture
    def extractor(self):
        return JobExtractor()

    @pytest.fixture
    def json_ld_job_html(self):
        """HTML with JobPosting JSON-LD structured data."""
        return """
        <html>
        <head>
        <script type="application/ld+json">
        {
            "@context": "https://schema.org",
            "@type": "JobPosting",
            "title": "Senior Python Developer",
            "description": "We are looking for a senior Python developer to join our team.",
            "hiringOrganization": {
                "@type": "Organization",
                "name": "Tech Company Inc"
            },
            "jobLocation": {
                "@type": "Place",
                "address": {
                    "@type": "PostalAddress",
                    "addressLocality": "San Francisco",
                    "addressRegion": "CA",
                    "addressCountry": "US"
                }
            },
            "employmentType": "FULL_TIME",
            "datePosted": "2024-01-15",
            "jobLocationType": "TELECOMMUTE"
        }
        </script>
        </head>
        <body>
        <h1>Senior Python Developer</h1>
        </body>
        </html>
        """

    @pytest.fixture
    def html_heuristic_job(self):
        """HTML without JSON-LD, relying on heuristics."""
        return """
        <html>
        <body>
        <h1 class="job-title">Full Stack Engineer</h1>
        <span class="company-name">Startup Co</span>
        <span class="location">New York, NY</span>
        <div class="job-description">
            We are looking for a talented full stack engineer.
            The ideal candidate will have experience with Python and JavaScript.
        </div>
        <span class="job-type">Full-time</span>
        </body>
        </html>
        """

    @pytest.mark.unit
    def test_extracts_from_json_ld(self, extractor, json_ld_job_html):
        """Test extraction from JSON-LD structured data."""
        result = extractor.extract(
            url="https://example.com/job/123",
            html=json_ld_job_html,
        )

        assert result is not None
        assert result.title == "Senior Python Developer"
        assert result.company == "Tech Company Inc"
        assert "San Francisco" in result.location
        assert result.employment_type == "FULL_TIME"
        assert result.remote is True

    @pytest.mark.unit
    def test_extracts_from_html_heuristics(self, extractor, html_heuristic_job):
        """Test extraction using HTML heuristics."""
        result = extractor.extract(
            url="https://example.com/job/456",
            html=html_heuristic_job,
        )

        assert result is not None
        assert result.title == "Full Stack Engineer"
        assert result.company == "Startup Co"
        assert "New York" in result.location

    @pytest.mark.unit
    def test_returns_none_for_non_job_page(self, extractor):
        """Test that extractor returns None for pages without job data."""
        html = """
        <html>
        <body>
        <h1>Welcome to our website</h1>
        <p>This is just a regular page.</p>
        </body>
        </html>
        """
        result = extractor.extract(
            url="https://example.com/about",
            html=html,
        )

        assert result is None

    @pytest.mark.unit
    def test_uses_title_hint(self, extractor):
        """Test that title_hint is used when title not found."""
        html = """
        <html>
        <body>
        <span class="company-name">Some Company</span>
        </body>
        </html>
        """
        result = extractor.extract(
            url="https://example.com/job/789",
            html=html,
            title_hint="Engineer Position",
        )

        assert result is not None
        assert result.title == "Engineer Position"

    @pytest.mark.unit
    def test_include_html_option(self, extractor, json_ld_job_html):
        """Test that include_html option preserves HTML."""
        result = extractor.extract(
            url="https://example.com/job/123",
            html=json_ld_job_html,
            include_html=True,
        )

        assert result is not None
        assert result.html is not None
        assert "Senior Python Developer" in result.html

    @pytest.mark.unit
    def test_handles_empty_html(self, extractor):
        """Test that extractor handles empty HTML gracefully."""
        result = extractor.extract(
            url="https://example.com/job/123",
            html="",
        )

        assert result is None

    @pytest.mark.unit
    def test_handles_malformed_json_ld(self, extractor):
        """Test that extractor handles malformed JSON-LD gracefully."""
        html = """
        <html>
        <head>
        <script type="application/ld+json">
        { invalid json }
        </script>
        </head>
        <body>
        <h1 class="job-title">Engineer</h1>
        <span class="company-name">Company</span>
        </body>
        </html>
        """
        result = extractor.extract(
            url="https://example.com/job/123",
            html=html,
        )

        # Should fall back to HTML heuristics
        assert result is not None
        assert result.title == "Engineer"

    @pytest.mark.unit
    def test_extracts_salary_from_json_ld(self, extractor):
        """Test salary extraction from JSON-LD."""
        html = """
        <html>
        <head>
        <script type="application/ld+json">
        {
            "@context": "https://schema.org",
            "@type": "JobPosting",
            "title": "Developer",
            "hiringOrganization": {"name": "Corp"},
            "baseSalary": {
                "@type": "MonetaryAmount",
                "currency": "USD",
                "value": {
                    "@type": "QuantitativeValue",
                    "value": 150000,
                    "unitText": "YEAR"
                }
            }
        }
        </script>
        </head>
        <body></body>
        </html>
        """
        result = extractor.extract(
            url="https://example.com/job/123",
            html=html,
        )

        assert result is not None
        assert result.metadata.get("salary_value") == 150000
        assert result.metadata.get("salary_currency") == "USD"

    @pytest.mark.unit
    def test_json_ld_in_graph_format(self, extractor):
        """Test extraction from JSON-LD in @graph format."""
        html = """
        <html>
        <head>
        <script type="application/ld+json">
        {
            "@context": "https://schema.org",
            "@graph": [
                {
                    "@type": "JobPosting",
                    "title": "Graph Job",
                    "hiringOrganization": {"name": "Graph Corp"}
                }
            ]
        }
        </script>
        </head>
        <body></body>
        </html>
        """
        result = extractor.extract(
            url="https://example.com/job/123",
            html=html,
        )

        assert result is not None
        assert result.title == "Graph Job"
        assert result.company == "Graph Corp"
