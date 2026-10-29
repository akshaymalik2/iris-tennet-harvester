"""Needs PostgreSQL + PostGIS: set TEST_DATABASE_URL (e.g. in .env). Skipped otherwise."""
from dataclasses import replace

import psycopg
import pytest
from conftest import FIXTURES

from harvester import load
from harvester.pipeline import run


def rows(url, sql):
    with psycopg.connect(url) as conn:
        return conn.execute(sql).fetchall()


def test_rerun_does_not_duplicate(db_settings):
    first = run(db_settings)
    second = run(db_settings)
    assert first["counts"]["inserted"] == 5 and first["counts"]["rows_in_table"] == 5
    assert second["counts"].get("inserted", 0) == 0 and second["counts"]["unchanged"] == 5
    assert second["counts"]["rows_in_table"] == 5


def test_changed_source_record_is_updated_in_place(db_settings):
    run(db_settings)
    report = run(replace(db_settings, default_input=FIXTURES / "listing_small_changed.html"))
    assert report["counts"]["updated"] == 1 and report["counts"]["unchanged"] == 4
    assert report["counts"]["rows_in_table"] == 5


def test_geometry_is_epsg_25832_and_only_for_resolved(db_settings):
    run(db_settings)
    result = rows(db_settings.database_url,
                  "SELECT source_record_id, ST_SRID(geom), geo_status FROM iris_staging.signal_ingest "
                  "WHERE geom IS NOT NULL")
    assert result == [("1001", 25832, "resolved")]


def test_problems_are_stored_in_the_error_table(db_settings):
    report = run(db_settings)
    codes = sorted(r[0] for r in rows(db_settings.database_url,
                   f"SELECT error_code FROM iris_staging.ingest_error WHERE run_id = '{report['run_id']}'"))
    assert codes == ["duplicate_record", "invalid_coordinates", "missing_required_field", "missing_required_field"]


def test_database_rejects_a_point_outside_germany(db_settings):
    run(db_settings)
    bad = {"source_id": "9999", "source_url": "https://www.tennet.eu/x", "signal_type": "substation_modernization",
           "secondary_signal_types": [], "match_reasons": {}, "title": "Bad point", "description": None,
           "status": None, "category": None, "project_type": None, "tags": [], "locations": [],
           "published_at": None, "updated_at": None, "x": 100000.0, "y": 100000.0, "geo_status": "resolved",
           "geo_method": "test", "geo_note": "crafted to bypass Python validation"}
    with load.connect(db_settings.database_url) as conn:
        run_id = rows(db_settings.database_url, "SELECT run_id FROM iris_staging.ingest_run LIMIT 1")[0][0]
        with pytest.raises(psycopg.errors.CheckViolation):
            load.upsert_record(conn, bad, run_id, db_settings.source_system)
