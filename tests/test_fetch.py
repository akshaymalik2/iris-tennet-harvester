import pytest
import requests
from conftest import FakeResponse, FakeSession

from harvester.fetch import AccessBlocked, EmptyResponse, NetworkError, RobotsDisallowed, fetch_listing

ROBOTS = "https://www.tennet.eu/robots.txt"
PAGE = "https://www.tennet.eu/de/projekte"
ROBOTS_OK = FakeResponse(200, "User-agent: GPTBot\nDisallow: /\n\nUser-agent: *\nDisallow: /api/\n")


def test_robots_disallow_stops_before_the_page_is_requested(settings):
    session = FakeSession({ROBOTS: FakeResponse(200, "User-agent: *\nDisallow: /de/\n")})
    with pytest.raises(RobotsDisallowed):
        fetch_listing(settings, session=session, sleep=lambda s: None)
    assert session.calls == [ROBOTS]


def test_403_is_access_blocked_and_not_retried(settings):
    session = FakeSession({ROBOTS: ROBOTS_OK, PAGE: FakeResponse(403, "Forbidden")})
    with pytest.raises(AccessBlocked):
        fetch_listing(settings, session=session, sleep=lambda s: None)
    assert session.calls.count(PAGE) == 1


def test_server_error_is_retried_then_succeeds(settings):
    session = FakeSession({ROBOTS: ROBOTS_OK, PAGE: [FakeResponse(503), FakeResponse(200, "<html>ok</html>")]})
    assert fetch_listing(settings, session=session, sleep=lambda s: None) == "<html>ok</html>"
    assert session.calls.count(PAGE) == 2


def test_network_failure_gives_up_after_retries(settings):
    session = FakeSession({ROBOTS: ROBOTS_OK, PAGE: [requests.ConnectionError("down")]})
    pauses = []
    with pytest.raises(NetworkError):
        fetch_listing(settings, session=session, sleep=pauses.append)
    assert session.calls.count(PAGE) == settings.max_retries + 1 and len(pauses) == settings.max_retries


def test_empty_response(settings):
    session = FakeSession({ROBOTS: ROBOTS_OK, PAGE: FakeResponse(200, "   ")})
    with pytest.raises(EmptyResponse):
        fetch_listing(settings, session=session, sleep=lambda s: None)
