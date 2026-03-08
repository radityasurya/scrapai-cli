"""
Secret redaction utilities for safe logging.

Provides functions to redact sensitive information like passwords from URLs
and connection strings before logging or displaying to users.
"""

import re
from urllib.parse import urlparse, urlunparse


def redact_url_credentials(url: str) -> str:
    """
    Redact password from a URL while preserving the structure.
    
    Args:
        url: URL string that may contain credentials (e.g., postgresql://user:password@host/db)
    
    Returns:
        URL with password redacted (e.g., postgresql://user:***@host/db)
    
    Examples:
        >>> redact_url_credentials("postgresql://user:password@localhost/db")
        "postgresql://user:***@localhost/db"
        >>> redact_url_credentials("sqlite:///scrapai.db")
        "sqlite:///scrapai.db"
    """
    if not url:
        return url
    
    # Parse the URL
    parsed = urlparse(url)
    
    # If there's no password, return as-is
    if not parsed.password:
        return url
    
    # Reconstruct URL with redacted password
    redacted_netloc = f"{parsed.username}:***@{parsed.hostname}"
    if parsed.port:
        redacted_netloc += f":{parsed.port}"
    
    redacted = urlunparse((
        parsed.scheme,
        redacted_netloc,
        parsed.path,
        parsed.params,
        parsed.query,
        parsed.fragment
    ))
    
    return redacted


def redact_connection_string(conn_str: str) -> str:
    """
    Redact password from various connection string formats.
    
    Handles:
    - URLs with credentials (postgresql://user:pass@host/db)
    - Connection strings with password= (password=mypassword;)
    
    Args:
        conn_str: Connection string that may contain sensitive data
    
    Returns:
        Connection string with passwords redacted
    """
    if not conn_str:
        return conn_str
    
    # Try URL format first
    if "://" in conn_str:
        return redact_url_credentials(conn_str)
    
    # Handle key=value format (e.g., "password=mypassword;")
    redacted = re.sub(
        r'(password|passwd|pwd)\s*=\s*[^\s;]+',
        r'\1=***',
        conn_str,
        flags=re.IGNORECASE
    )
    
    return redacted
