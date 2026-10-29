"""All steps in one run: get page -> extract -> filter -> locations -> load -> report.

Every problem is collected in one list and ends up in three places: the console,
the iris_staging.ingest_error table and the run report in reports/.
"""
import json
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from . import load
from .classify import filter_records
from .extract import ExtractError, parse_listing
from .fetch import AccessBlocked, FetchError, RobotsDisallowed, fetch_listing
from .geo import load_gazetteer, resolve


def quality_flags(record):
    """Missing optional fields stay visible on every record."""
    flags = [f"missing_{field}" for field, value in (
        ("description", record["description"]), ("published_at", record["published_at"]),
        ("updated_at", record["updated_at"]), ("locations", record["locations"])) if not value]
    if record["geo_status"] != "resolved":
        flags.append(f"geo_{record['geo_status']}")
    return flags


def _write_report(report, settings):
    settings.reports_dir.mkdir(parents=True, exist_ok=True)
    base = settings.reports_dir / f"run_{report['started_at'][:19].replace(':', '')}_{report['run_id'][:8]}"
    Path(f"{base}.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = [f"# Run report {report['run_id']}", "",
             f"- Mode: {report['mode']} | Input: {report['input']} | Dry run: {report['dry_run']}",
             f"- Status: **{report['status']}**", "", "## Counts", ""]
    lines += [f"- {k}: {v}" for k, v in report["counts"].items()]
    lines += ["", "## Problems", ""]
    lines += [f"- [{p['stage']}] {p['code']} {p.get('source_record_id') or ''}: {p.get('message')}"
              for p in report["problems"]] or ["- none"]
    Path(f"{base}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    report["report_files"] = [f"{base}.json", f"{base}.md"]


def run(settings, live=False, input_path=None, dry_run=False, session=None, sleep=time.sleep):
    run_id = uuid.uuid4()
    mode = "live" if live else "saved_page"
    source = settings.listing_url if live else str(input_path or settings.default_input)
    report = {"run_id": str(run_id), "mode": mode, "input": source, "dry_run": dry_run,
              "started_at": datetime.now(timezone.utc).isoformat(), "status": "running",
              "counts": {}, "problems": [], "out_of_scope": []}
    counts = Counter()
    problems = report["problems"]
    conn = None

    def finish(status):
        report["status"] = status
        report["counts"] = dict(counts)
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        if conn is not None:
            for p in problems:
                load.log_problem(conn, run_id, p)
            load.finish_run(conn, run_id, status, dict(counts))
            conn.close()
        _write_report(report, settings)
        return report

    # 0. Database first, so that even a failed run is recorded
    if not dry_run:
        try:
            conn = load.connect(settings.database_url)
            load.apply_schema(conn, settings.schema_file)
            load.start_run(conn, run_id, mode, source)
        except Exception as exc:  # database unreachable, wrong URL ...
            conn = None
            problems.append({"stage": "load", "code": "database_unavailable", "message": f"{type(exc).__name__}: {exc}"})
            return finish("failed")

    # 1. Get the page (live download or a saved copy)
    try:
        if live:
            html = fetch_listing(settings, session=session, sleep=sleep)
            settings.raw_dir.mkdir(parents=True, exist_ok=True)
            saved = settings.raw_dir / f"listing_live_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.html"
            saved.write_text(html, encoding="utf-8")
            report["saved_raw_file"] = str(saved)
        else:
            path = Path(source)
            if not path.exists():
                problems.append({"stage": "fetch", "code": "input_missing", "message": f"{path} not found"})
                return finish("failed")
            html = path.read_text(encoding="utf-8")
    except (AccessBlocked, RobotsDisallowed) as exc:
        problems.append({"stage": "fetch", "code": exc.code,
                         "message": f"{exc} - not bypassed; run with a saved page instead (see README)"})
        return finish("blocked")
    except FetchError as exc:
        problems.append({"stage": "fetch", "code": exc.code, "message": str(exc)})
        return finish("failed")

    # 2. Extract
    try:
        records, extract_problems, total = parse_listing(html, settings.base_url)
    except ExtractError as exc:
        problems.append({"stage": "extract", "code": exc.code, "message": str(exc)})
        return finish("failed")
    problems.extend(extract_problems)
    counts["listing_total"] = total
    counts["extracted"] = len(records)

    # 3. Filter
    signals, out_of_scope = filter_records(records)
    report["out_of_scope"] = out_of_scope
    counts["in_scope"] = len(signals)
    counts["out_of_scope"] = len(out_of_scope)
    for s in signals:
        counts[f"type_{s['signal_type']}"] += 1

    # 4. Locations
    gazetteer, gazetteer_problems = load_gazetteer(settings.gazetteer_file)
    problems.extend(gazetteer_problems)
    for record in signals:
        record.update(resolve(record, gazetteer))
        record["srid"] = 25832
        record["quality_flags"] = quality_flags(record)
        counts[f"geo_{record['geo_status']}"] += 1
        if record["geo_status"] == "rejected_invalid":
            problems.append({"stage": "geo", "code": "invalid_coordinates",
                             "source_record_id": record["source_id"], "message": record["geo_note"]})
    for flag in ("missing_description", "missing_published_at", "missing_updated_at", "missing_locations"):
        counts[flag] = sum(1 for r in signals if flag in r["quality_flags"])

    settings.processed_dir.mkdir(parents=True, exist_ok=True)
    (settings.processed_dir / "signals_geo.json").write_text(
        json.dumps(signals, indent=2, ensure_ascii=False), encoding="utf-8")

    # 5. Load
    if dry_run:
        return finish("succeeded")
    for record in signals:
        try:
            counts[load.upsert_record(conn, record, run_id, settings.source_system)] += 1
        except Exception as exc:  # one bad record must not stop the run
            counts["failed"] += 1
            problems.append({"stage": "load", "code": "db_error", "source_record_id": record["source_id"],
                             "message": f"{type(exc).__name__}: {exc}"})
    counts["rows_in_table"] = conn.execute("SELECT count(*) FROM iris_staging.signal_ingest").fetchone()[0]
    return finish("partial" if counts["failed"] else "succeeded")
