"""IRIS-SIG-27 harvester - one command for the whole pipeline.

  python3 run_pipeline.py                      use the saved page data/raw/listing_page1.html
  python3 run_pipeline.py --input FILE.html    use another saved page
  python3 run_pipeline.py --live               try a polite live download first (TenneT currently answers 403)
  python3 run_pipeline.py --dry-run            everything except writing to the database

Exit codes: 0 succeeded, 1 partial, 2 failed, 3 blocked by the source.
"""
import argparse
import sys

from harvester.config import get_settings
from harvester.pipeline import run

EXIT_CODES = {"succeeded": 0, "partial": 1, "failed": 2, "blocked": 3}


def main():
    parser = argparse.ArgumentParser(description="IRIS-SIG-27 TenneT project harvester")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--input", help="saved listing page (default: data/raw/listing_page1.html)")
    source.add_argument("--live", action="store_true", help="download the listing page politely first")
    parser.add_argument("--dry-run", action="store_true", help="do not write to the database")
    args = parser.parse_args()

    report = run(get_settings(), live=args.live, input_path=args.input, dry_run=args.dry_run)

    print(f"Run {report['run_id']} | mode: {report['mode']} | status: {report['status']}")
    for key, value in report["counts"].items():
        print(f"  {key}: {value}")
    print(f"Problems: {len(report['problems'])}")
    for p in report["problems"]:
        print(f"  [{p['stage']}] {p['code']} {p.get('source_record_id') or ''}: {p.get('message')}")
    print("Report:", report["report_files"][1])
    sys.exit(EXIT_CODES[report["status"]])


if __name__ == "__main__":
    main()
