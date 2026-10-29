"""Polite, lawful download (PDF: "use only lawful, authorized access", "handle network failures").

- reads robots.txt with our own honest User-Agent and obeys it
- retries timeouts, connection errors, HTTP 429 and 5xx with growing pauses
- stops on 401/403/451 (access refused) and never tries to get around it
"""
import time
from urllib.robotparser import RobotFileParser

import requests


class FetchError(Exception):
    code = "fetch_error"


class AccessBlocked(FetchError):
    code = "access_blocked"


class RobotsDisallowed(FetchError):
    code = "robots_disallowed"


class EmptyResponse(FetchError):
    code = "empty_response"


class NetworkError(FetchError):
    code = "network_failure"


def _get_with_retries(session, url, settings, sleep):
    headers = {"User-Agent": settings.full_user_agent}
    problem = "unknown"
    for attempt in range(settings.max_retries + 1):
        try:
            response = session.get(url, headers=headers, timeout=settings.timeout_s)
        except (requests.ConnectionError, requests.Timeout) as exc:
            problem = type(exc).__name__
        else:
            if response.status_code == 429 or response.status_code >= 500:
                problem = f"HTTP {response.status_code}"
            else:
                return response
        if attempt < settings.max_retries:
            sleep(settings.backoff_s * 2 ** attempt)  # 2 s, 4 s, 8 s ...
    raise NetworkError(f"{url}: gave up after {settings.max_retries + 1} attempts ({problem})")


def fetch_listing(settings, session=None, sleep=time.sleep):
    """Download the listing page once and return its HTML, or raise a FetchError."""
    session = session or requests.Session()

    robots_url = settings.base_url + "/robots.txt"
    robots_response = _get_with_retries(session, robots_url, settings, sleep)
    if robots_response.status_code != 200:
        raise RobotsDisallowed(f"robots.txt not readable (HTTP {robots_response.status_code}); not downloading")
    robots = RobotFileParser()
    robots.parse(robots_response.text.splitlines())
    if not robots.can_fetch(settings.full_user_agent, settings.listing_url):
        raise RobotsDisallowed(f"robots.txt does not allow {settings.listing_url}")

    response = _get_with_retries(session, settings.listing_url, settings, sleep)
    if response.status_code in (401, 403, 451):
        raise AccessBlocked(f"HTTP {response.status_code}: the site refused access; not bypassing")
    if response.status_code >= 400:
        raise FetchError(f"HTTP {response.status_code} for {settings.listing_url}")
    if not (response.text or "").strip():
        raise EmptyResponse(f"empty response from {settings.listing_url}")
    return response.text
