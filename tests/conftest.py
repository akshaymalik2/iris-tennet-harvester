import os
from dataclasses import replace
from pathlib import Path

import pytest

from harvester.config import Settings

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
REAL_PAGE = ROOT / "data" / "raw" / "listing_page1.html"  # your saved TenneT page (not in Git)


@pytest.fixture
def settings(tmp_path):
    """Settings that write everything into a temporary folder."""
    gazetteer = tmp_path / "gazetteer.csv"
    gazetteer.write_text("source_id,title,lat,lon,source,checked_on\n", encoding="utf-8")
    return replace(Settings(), default_input=FIXTURES / "listing_small.html", raw_dir=tmp_path / "raw",
                   processed_dir=tmp_path / "processed", reports_dir=tmp_path / "reports",
                   gazetteer_file=gazetteer, schema_file=ROOT / "sql" / "schema.sql",
                   backoff_s=0.0, max_retries=2)


@pytest.fixture
def db_settings(settings):
    """Settings for a real PostgreSQL/PostGIS test database. Its iris_staging schema is wiped first."""
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        from harvester.config import load_dotenv
        load_dotenv(ROOT / ".env")
        url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set - database tests skipped")
    import psycopg
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute("DROP SCHEMA IF EXISTS iris_staging CASCADE")
    return replace(settings, database_url=url)


class FakeResponse:
    def __init__(self, status=200, text=""):
        self.status_code = status
        self.text = text


class FakeSession:
    """Pretends to be requests.Session: returns prepared answers per URL and records the calls."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def get(self, url, headers=None, timeout=None):
        self.calls.append(url)
        answer = self.routes.get(url, FakeResponse(404, "not found"))
        if isinstance(answer, list):
            answer = answer.pop(0) if len(answer) > 1 else answer[0]
        if isinstance(answer, Exception):
            raise answer
        return answer
