from dataclasses import replace

from conftest import FIXTURES, FakeResponse, FakeSession

from harvester.pipeline import run


def test_dry_run_counts_and_visible_problems(settings):
    report = run(settings, dry_run=True)
    c = report["counts"]
    assert report["status"] == "succeeded"
    assert (c["extracted"], c["in_scope"], c["out_of_scope"]) == (7, 5, 2)
    assert (c["geo_resolved"], c["geo_ambiguous"], c["geo_unresolved"], c["geo_rejected_invalid"]) == (1, 2, 1, 1)
    assert c["missing_published_at"] == 1
    codes = sorted(p["code"] for p in report["problems"])
    assert codes == ["duplicate_record", "invalid_coordinates", "missing_required_field", "missing_required_field"]
    assert all(__import__("os").path.exists(f) for f in report["report_files"])


def test_missing_input_fails_visibly(settings, tmp_path):
    report = run(replace(settings, default_input=tmp_path / "nope.html"), dry_run=True)
    assert report["status"] == "failed" and report["problems"][0]["code"] == "input_missing"


def test_live_run_blocked_by_site_is_not_bypassed(settings):
    session = FakeSession({"https://www.tennet.eu/robots.txt": FakeResponse(200, "User-agent: *\nDisallow: /api/\n"),
                           "https://www.tennet.eu/de/projekte": FakeResponse(403, "Forbidden")})
    report = run(settings, live=True, dry_run=True, session=session, sleep=lambda s: None)
    assert report["status"] == "blocked" and report["problems"][0]["code"] == "access_blocked"
    assert session.calls.count("https://www.tennet.eu/de/projekte") == 1


def test_live_run_success_saves_the_raw_page(settings):
    html = (FIXTURES / "listing_small.html").read_text(encoding="utf-8")
    session = FakeSession({"https://www.tennet.eu/robots.txt": FakeResponse(200, "User-agent: *\nDisallow: /api/\n"),
                           "https://www.tennet.eu/de/projekte": FakeResponse(200, html)})
    report = run(settings, live=True, dry_run=True, session=session, sleep=lambda s: None)
    assert report["status"] == "succeeded" and report["counts"]["in_scope"] == 5
    assert report["saved_raw_file"].endswith(".html")
