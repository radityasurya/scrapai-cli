"""
URL validation utilities for SSRF prevention.

Provides reusable SSRF-safe URL validation used across the codebase.
"""

import socket
import ipaddress
from urllib.parse import urlparse


def validate_url_ssrf(url: str) -> str:
    """
    Validate that a URL does not point to localhost, private IPs, or reserved ranges.

    Args:
        url: URL string to validate

    Returns:
        The validated URL string

    Raises:
        ValueError: If URL points to forbidden destinations (localhost, private IPs, etc.)
    """
    if not url or len(url.strip()) == 0:
        raise ValueError("URL cannot be empty")

    # Basic scheme check
    url_lower = url.lower()
    allowed_schemes = {"http", "https"}
    if not any(url_lower.startswith(f"{scheme}://") for scheme in allowed_schemes):
        raise ValueError(
            f"Invalid URL scheme: {url}. Only HTTP and HTTPS are allowed. "
            "This prevents file://, ftp://, and other potentially dangerous schemes."
        )

    # Prevent SSRF to localhost/private IPs
    parsed = urlparse(url)
    hostname = parsed.hostname  # lowercased, brackets stripped

    if hostname:
        # Check string patterns first (catches "localhost" etc.)
        if hostname in ("localhost", "0.0.0.0"):
            raise ValueError(
                f"URL points to localhost: {url}. Blocked to prevent SSRF attacks."
            )

        # Try parsing as IP directly (handles hex, octal, decimal)
        try:
            ip = ipaddress.ip_address(hostname)
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
            ):
                raise ValueError(
                    f"URL points to private/reserved IP: {url}. "
                    "Blocked to prevent SSRF attacks."
                )
        except ValueError as ip_err:
            if "Blocked to prevent SSRF" in str(ip_err):
                raise
            # Not an IP literal — resolve the hostname
            try:
                results = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC)
                for family, _, _, _, sockaddr in results:
                    ip = ipaddress.ip_address(sockaddr[0])
                    if (
                        ip.is_private
                        or ip.is_loopback
                        or ip.is_link_local
                        or ip.is_reserved
                    ):
                        raise ValueError(
                            f"URL hostname '{hostname}' resolves to "
                            f"private IP {ip}: {url}. "
                            "Blocked to prevent SSRF attacks."
                        )
            except socket.gaierror:
                pass  # unresolvable host — let caller handle it

    # Basic length check
    if len(url) > 2048:
        raise ValueError(f"URL too long (max 2048 chars): {url[:50]}...")

    return url
