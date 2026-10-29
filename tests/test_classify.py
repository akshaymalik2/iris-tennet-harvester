from conftest import FIXTURES, REAL_PAGE
import pytest

from harvester.classify import filter_records, match_signal_types
from harvester.extract import parse_listing


def project(**kw):
    base = {"source_id": "1", "title": "Projekt", "description": "", "project_type": "Neubau",
            "tags": [], "locations": ["Bayern"]}
    return {**base, **kw}


def test_rules():
    assert "suedlink_progress" in match_signal_types(project(tags=["SuedLink"]))
    assert "substation_modernization" in match_signal_types(project(project_type="Umspannwerk"))
    assert "substation_modernization" in match_signal_types(project(title="Konverter-Bereich X"))
    assert "capacity_allocation" in match_signal_types(project(description="Netzanschlusszusage erteilt"))


def test_passing_mention_in_description_is_not_enough():
    assert match_signal_types(project(description="Die Leitung endet am Umspannwerk A.")) == {}


def test_line_capacity_is_not_an_allocation():
    assert match_signal_types(project(description="Die Übertragungskapazität steigt.")) == {}


def test_priority_and_secondary_type():
    signals, _ = filter_records([project(tags=["SuedLink"], title="Konverter SuedLink")])
    assert signals[0]["signal_type"] == "suedlink_progress"
    assert signals[0]["secondary_signal_types"] == ["substation_modernization"]


def test_fixture_filtering_with_reasons():
    records, _, _ = parse_listing((FIXTURES / "listing_small.html").read_text(encoding="utf-8"))
    signals, out = filter_records(records)
    assert sorted(s["source_id"] for s in signals) == ["1001", "1002", "1003", "1006", "1008"]
    assert {o["source_id"]: o["reason"] for o in out} == {"1004": "no matching signal type", "1005": "outside Germany"}


@pytest.mark.skipif(not REAL_PAGE.exists(), reason="saved TenneT page not present")
def test_real_saved_page_counts():
    records, _, _ = parse_listing(REAL_PAGE.read_text(encoding="utf-8"))
    signals, _ = filter_records(records)
    types = [s["signal_type"] for s in signals]
    assert len(signals) == 26 and types.count("substation_modernization") == 15 and types.count("suedlink_progress") == 11
