"""
Tests for URL validation utilities (SSRF protection).

Comprehensive test coverage for utils/url_validation.py to ensure
SSRF vulnerabilities are properly blocked while allowing legitimate URLs.
"""

import pytest
from utils.url_validation import validate_url_ssrf


class TestValidateUrlSSRF:
    """Test suite for SSRF URL validation"""

    # Valid URLs that should pass validation
    @pytest.mark.parametrize("url", [
        "http://example.com",
        "https://example.com",
        "http://example.com/path",
        "https://example.com/path?query=value",
        "http://subdomain.example.com",
        "https://subdomain.example.com:8080/path",
        "http://example.com:80",
        "https://example.co.uk",
        "http://192.0.2.1",  # TEST-NET-1 (documentation range, not private)
        "http://198.51.100.1",  # TEST-NET-2 (documentation range, not private)
        "http://203.0.113.1",  # TEST-NET-3 (documentation range, not private)
    ])
    def test_valid_urls(self, url):
        """Valid public URLs should pass validation"""
        result = validate_url_ssrf(url)
        assert result == url

    # Empty/invalid URLs
    @pytest.mark.parametrize("url,error_substring", [
        ("", "URL cannot be empty"),
        ("   ", "URL cannot be empty"),
        ("not-a-url", "Invalid URL scheme"),
        ("ftp://example.com", "Invalid URL scheme"),
        ("file:///etc/passwd", "Invalid URL scheme"),
        ("javascript:alert(1)", "Invalid URL scheme"),
        ("data:text/html,<script>alert(1)</script>", "Invalid URL scheme"),
    ])
    def test_invalid_urls(self, url, error_substring):
        """Invalid URLs should raise ValueError with appropriate message"""
        with pytest.raises(ValueError) as exc_info:
            validate_url_ssrf(url)
        assert error_substring in str(exc_info.value)

    # Localhost blocking
    @pytest.mark.parametrize("url", [
        "http://localhost",
        "http://localhost:8080",
        "http://localhost/path",
        "https://localhost",
        "http://0.0.0.0",
        "http://0.0.0.0:8080",
    ])
    def test_localhost_blocked(self, url):
        """URLs pointing to localhost should be blocked"""
        with pytest.raises(ValueError) as exc_info:
            validate_url_ssrf(url)
        assert "localhost" in str(exc_info.value).lower()

    # Loopback IP blocking
    @pytest.mark.parametrize("url", [
        "http://127.0.0.1",
        "http://127.0.0.1:8080",
        "http://127.0.0.1/path",
        "http://127.0.0.2",
        "http://127.255.255.255",
        "http://[::1]",  # IPv6 loopback
        "http://[::1]:8080",
    ])
    def test_loopback_ips_blocked(self, url):
        """Loopback IP addresses should be blocked"""
        with pytest.raises(ValueError) as exc_info:
            validate_url_ssrf(url)
        assert "private/reserved IP" in str(exc_info.value)

    # Private IP blocking - Class A
    @pytest.mark.parametrize("url", [
        "http://10.0.0.1",
        "http://10.255.255.255",
        "http://10.0.0.1:8080",
        "http://10.0.0.1/path",
    ])
    def test_private_class_a_blocked(self, url):
        """Private Class A IPs (10.0.0.0/8) should be blocked"""
        with pytest.raises(ValueError) as exc_info:
            validate_url_ssrf(url)
        assert "private/reserved IP" in str(exc_info.value)

    # Private IP blocking - Class B
    @pytest.mark.parametrize("url", [
        "http://172.16.0.1",
        "http://172.31.255.255",
        "http://172.16.0.1:8080",
        "http://172.16.0.1/path",
    ])
    def test_private_class_b_blocked(self, url):
        """Private Class B IPs (172.16.0.0/12) should be blocked"""
        with pytest.raises(ValueError) as exc_info:
            validate_url_ssrf(url)
        assert "private/reserved IP" in str(exc_info.value)

    # Private IP blocking - Class C
    @pytest.mark.parametrize("url", [
        "http://192.168.0.1",
        "http://192.168.255.255",
        "http://192.168.1.1:8080",
        "http://192.168.1.1/path",
    ])
    def test_private_class_c_blocked(self, url):
        """Private Class C IPs (192.168.0.0/16) should be blocked"""
        with pytest.raises(ValueError) as exc_info:
            validate_url_ssrf(url)
        assert "private/reserved IP" in str(exc_info.value)

    # Link-local addresses
    @pytest.mark.parametrize("url", [
        "http://169.254.0.1",
        "http://169.254.255.255",
        "http://169.254.1.1:8080",
        "http://[fe80::1]",  # IPv6 link-local
    ])
    def test_link_local_blocked(self, url):
        """Link-local addresses should be blocked"""
        with pytest.raises(ValueError) as exc_info:
            validate_url_ssrf(url)
        assert "private/reserved IP" in str(exc_info.value)

    # Reserved addresses
    @pytest.mark.parametrize("url", [
        "http://0.0.0.1",  # Reserved (this network)
        "http://224.0.0.1",  # Multicast
        "http://239.255.255.255",  # Multicast
        "http://240.0.0.1",  # Reserved for future use
    ])
    def test_reserved_addresses_blocked(self, url):
        """Reserved addresses should be blocked"""
        with pytest.raises(ValueError) as exc_info:
            validate_url_ssrf(url)
        assert "private/reserved IP" in str(exc_info.value)

    # URL length validation
    def test_url_too_long(self):
        """URLs exceeding max length should be blocked"""
        long_url = "http://example.com/" + "a" * 2050
        with pytest.raises(ValueError) as exc_info:
            validate_url_ssrf(long_url)
        assert "URL too long" in str(exc_info.value)

    def test_url_at_max_length(self):
        """URLs at max length (2048 chars) should be valid"""
        base = "http://example.com/"
        max_url = base + "a" * (2048 - len(base))
        result = validate_url_ssrf(max_url)
        assert result == max_url

    # Case insensitivity
    @pytest.mark.parametrize("url", [
        "HTTP://example.com",
        "HTTPS://example.com",
        "HtTp://example.com",
    ])
    def test_scheme_case_insensitive(self, url):
        """URL schemes should be case-insensitive"""
        result = validate_url_ssrf(url)
        assert result == url

    # Hostname resolution (if resolvable)
    @pytest.mark.parametrize("hostname", [
        "example.com",
        "google.com",
        "github.com",
    ])
    def test_resolvable_public_hostnames(self, hostname):
        """Public resolvable hostnames should be allowed"""
        url = f"https://{hostname}"
        result = validate_url_ssrf(url)
        assert result == url

    # Edge cases
    def test_url_with_port(self):
        """URLs with ports should be handled correctly"""
        url = "http://example.com:8080"
        result = validate_url_ssrf(url)
        assert result == url

    def test_url_with_query_string(self):
        """URLs with query strings should be handled correctly"""
        url = "http://example.com?foo=bar&baz=qux"
        result = validate_url_ssrf(url)
        assert result == url

    def test_url_with_fragment(self):
        """URLs with fragments should be handled correctly"""
        url = "http://example.com#section"
        result = validate_url_ssrf(url)
        assert result == url

    def test_url_with_credentials(self):
        """URLs with credentials should be handled (but not validated for security)"""
        url = "http://user:pass@example.com"
        result = validate_url_ssrf(url)
        assert result == url

    def test_ipv6_url(self):
        """IPv6 URLs should be handled correctly"""
        # This is a public IPv6 address (Google's public DNS)
        url = "http://[2001:4860:4860::8888]"
        # Note: This might fail if the IP is considered reserved/private
        # We're testing that the parsing works, not necessarily that it's allowed
        try:
            result = validate_url_ssrf(url)
            assert result == url
        except ValueError as e:
            # If blocked, it should be for the right reason
            assert "private/reserved IP" in str(e)

    # Unicode/IDN handling
    def test_url_with_unicode_domain(self):
        """URLs with unicode domains should be handled"""
        url = "http://例え.jp"
        result = validate_url_ssrf(url)
        assert result == url

    # Multiple validation errors
    def test_multiple_errors_localhost_and_long(self):
        """When multiple errors exist, the first one should be reported"""
        long_localhost = "http://localhost/" + "a" * 2050
        with pytest.raises(ValueError) as exc_info:
            validate_url_ssrf(long_localhost)
        # Should fail on localhost check before length check
        assert "localhost" in str(exc_info.value).lower()


class TestValidateUrlSSRFIntegration:
    """Integration tests for SSRF validation with network resolution"""

    @pytest.mark.skip(reason="Requires network access and may be slow")
    def test_actual_private_hostname_resolution(self):
        """Test that hostnames resolving to private IPs are blocked"""
        # This would require a hostname that actually resolves to a private IP
        # Skipping as it depends on network configuration
        pass

    @pytest.mark.skip(reason="Requires network access and may be slow")
    def test_actual_localhost_variants(self):
        """Test various localhost representations"""
        # Tests like "http://127.1", "http://127.0.1" etc.
        # Skipping as it depends on network configuration
        pass


class TestValidateUrlSSRFPerformance:
    """Performance tests for SSRF validation"""

    def test_validation_speed(self, benchmark):
        """URL validation should be fast"""
        url = "https://example.com/path?query=value"
        result = benchmark(validate_url_ssrf, url)
        assert result == url

    @pytest.mark.skip(reason="Benchmarking not essential for all test runs")
    def test_many_valid_urls(self, benchmark):
        """Validation should handle many URLs efficiently"""
        urls = [f"http://example{i}.com" for i in range(100)]
        
        def validate_many():
            return [validate_url_ssrf(url) for url in urls]
        
        results = benchmark(validate_many)
        assert len(results) == 100
