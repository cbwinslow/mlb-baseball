
"""
================================================================================
HTTP Utilities
Date: 2026-05-09

Shared HTTP client and retry logic for all sources.
================================================================================
"""

from typing import Any, Dict, Optional

import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
)


def create_http_client(timeout: int = 30) -> httpx.Client:
    """Create HTTP client with sensible defaults.

    Args:
        timeout: Request timeout in seconds

    Returns:
        Configured httpx.Client
    """
    return httpx.Client(
        timeout=timeout,
        limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
    )


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
)
def http_get(
    url: str,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    client: Optional[httpx.Client] = None,
) -> httpx.Response:
    """Make HTTP GET request with retries.

    Args:
        url: URL to request
        params: Query parameters
        headers: Request headers
        client: httpx.Client instance

    Returns:
        HTTP response

    Raises:
        httpx.HTTPError: On HTTP errors
    """
    if client is None:
        client = create_http_client()

    response = client.get(url, params=params, headers=headers)
    response.raise_for_status()
    return response