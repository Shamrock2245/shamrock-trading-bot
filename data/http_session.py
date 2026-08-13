"""
data/http_session.py — Shared requests.Session with connection pooling.

Every provider module should use `get_session()` instead of raw `requests.get/post`.
Benefits:
  - HTTP keep-alive reuses TCP+SSL connections (saves ~100ms per call)
  - Connection pool limits prevent socket exhaustion
  - Retry policy with exponential backoff built-in
  - Thread-safe by default (requests.Session uses urllib3 thread-safe pools)

Usage:
    from data.http_session import get_session
    resp = get_session().get(url, timeout=15)
"""

import os
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

_session: requests.Session | None = None

_MORALIS_HOST_MARKERS = (
    "moralis.io",
    "moralis-streams.com",
    "moralis-nodes.com",
)


def _moralis_url_blocked(url: object) -> bool:
    """Refuse Moralis hosts unless MORALIS_ENABLED=true. Fail closed."""
    if os.getenv("MORALIS_ENABLED", "false").lower() == "true":
        return False
    url_l = str(url or "").lower()
    return any(marker in url_l for marker in _MORALIS_HOST_MARKERS)


class TimeoutSession(requests.Session):
    def request(self, method, url, *args, **kwargs):
        if _moralis_url_blocked(url):
            raise requests.exceptions.RequestException(
                "Moralis disabled (MORALIS_ENABLED=false) — blocked request to "
                f"{url}"
            )
        if 'timeout' not in kwargs:
            kwargs['timeout'] = 15.0  # Global default timeout to prevent hangs
        try:
            return super().request(method, url, *args, **kwargs)
        except requests.exceptions.RequestException as e:
            # Catch timeouts and other request exceptions and raise them clearly, 
            # or we could return a dummy response. But since callers expect a response, 
            # we should let them handle the RequestException, or we can log it.
            # We must ensure that the caller handles it.
            raise

def get_session() -> requests.Session:
    """Return a shared requests.Session with connection pooling and retry policy."""
    global _session
    if _session is None:
        _session = TimeoutSession()
        retries = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            raise_on_status=False,  # Let callers handle status codes
        )
        adapter = HTTPAdapter(
            pool_connections=20,   # Number of distinct hosts to pool
            pool_maxsize=20,       # Max connections per host
            max_retries=retries,
        )
        _session.mount("https://", adapter)
        _session.mount("http://", adapter)
    return _session
