import pytest
from conftest import FIXTURES, REAL_PAGE

from harvester.extract import ExtractError, ms_to_iso, parse_listing


def test_extracts_valid_records_and_reports_bad_ones():
    records, problems, total = parse_listing((FIXTURES / "listing_small.html").read_text(encoding="utf-8"))
    assert total == 10
    assert [r["source_id"] for r in records] == ["1001", "1002", "1003", "1004", "1005", "1006", "1008"]
    codes = sorted(p["code"] for p in problems)
    assert codes == ["duplicate_record", "missing_required_field", "missing_required_field"]


def test_cleans_and_maps_fields():
    records, _, _ = parse_listing((FIXTURES / "listing_small.html").read_text(encoding="utf-8"))
    by_id = {r["source_id"]: r for r in records}
    assert by_id["1006"]["title"] == "Umspannwerk Leerzeichen"            # extra spaces removed
    assert by_id["1001"]["source_url"] == "https://www.tennet.eu/de/projekte/test-1001"
    assert by_id["1002"]["tags"] == ["SuedLink"]
    assert by_id["1003"]["published_at"] is None                          # missing date stays missing
    assert by_id["1001"]["published_at"].startswith("2026-07-01")


def test_date_conversion():
    assert ms_to_iso(1790319427000).startswith("2026-09-25")
    assert ms_to_iso(None) is None and ms_to_iso("x") is None


@pytest.mark.parametrize("html, code", [
    ("", "empty_response"),
    ("<html><body>no data here</body></html>", "missing_next_data"),
    ('<script id="__NEXT_DATA__">{broken json</script>', "malformed_json"),
    ('<script id="__NEXT_DATA__">{"props": {}}</script>', "unexpected_structure"),
    ('<script id="__NEXT_DATA__">{"props": {"pageProps": {"programsAndProjects": {"edges": []}}}}</script>', "empty_listing"),
])
def test_unusable_pages_raise_clear_errors(html, code):
    with pytest.raises(ExtractError) as exc:
        parse_listing(html)
    assert exc.value.code == code


@pytest.mark.skipif(not REAL_PAGE.exists(), reason="saved TenneT page not present")
def test_real_saved_page():
    records, problems, total = parse_listing(REAL_PAGE.read_text(encoding="utf-8"))
    assert total == 112 and len(records) == 112 and problems == []
