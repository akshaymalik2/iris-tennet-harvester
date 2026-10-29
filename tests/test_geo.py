import math

import pytest

from harvester.geo import check_coordinates, load_gazetteer, resolve, to_point


@pytest.mark.parametrize("lat, lon, reason", [
    (0, 0, "0/0 placeholder"),
    (95.0, 9.0, "out of range"),
    (9.1, 52.5, "latitude and longitude look swapped"),
    (48.85, 2.35, "outside Germany"),                 # Paris
    (float("nan"), 9.0, "missing or not a number"),
    (None, 9.0, "missing or not a number"),
])
def test_invalid_coordinates_are_rejected(lat, lon, reason):
    assert check_coordinates(lat, lon) == reason
    result = to_point(lat, lon, "test", "note")
    assert result["geo_status"] == "rejected_invalid" and result["x"] is None


def test_valid_point_is_converted_to_epsg_25832():
    result = to_point(51.0, 10.0, "test", "note")
    assert result["geo_status"] == "resolved"
    assert math.isclose(result["x"], 570168.86, abs_tol=0.5) and math.isclose(result["y"], 5650300.79, abs_tol=0.5)


def record(**kw):
    base = {"source_id": "1", "signal_type": "substation_modernization", "locations": ["Hessen"], "geojson": None}
    return {**base, **kw}


def test_resolution_order():
    assert resolve(record(geojson={"type": "Point", "coordinates": [9.5, 51.0]}), {})["geo_status"] == "resolved"
    assert resolve(record(geojson={"type": "LineString", "coordinates": []}), {})["geo_status"] == "ambiguous"
    assert resolve(record(signal_type="suedlink_progress"), {})["geo_status"] == "ambiguous"
    assert resolve(record(), {"1": (51.0, 10.0, "OSM")})["geo_method"] == "gazetteer"
    unresolved = resolve(record(), {})
    assert unresolved["geo_status"] == "unresolved" and "Hessen" in unresolved["geo_note"]


def test_gazetteer_bad_row_is_reported(tmp_path):
    f = tmp_path / "g.csv"
    f.write_text("source_id,title,lat,lon,source,checked_on\n1,A,51.0,10.0,OSM,2026-10-29\n2,B,abc,10.0,OSM,2026-10-29\n")
    entries, problems = load_gazetteer(f)
    assert list(entries) == ["1"] and problems[0]["code"] == "bad_gazetteer_row"
