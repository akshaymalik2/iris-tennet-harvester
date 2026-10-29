"""Step 5: load the records into iris_staging.signal_ingest (PostgreSQL 16 / PostGIS 3.4).

Idempotent: each TenneT project can exist only once (UNIQUE source_system + source_record_id).
Running the script again updates changed records and leaves unchanged ones alone.
The database address comes from the DATABASE_URL environment variable - no credentials in code.
"""
import hashlib
import json
import os
import uuid
from collections import Counter
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

IN_FILE = Path("data/processed/signals_geo.json")
SCHEMA_FILE = Path("sql/schema.sql")
SOURCE_SYSTEM = "tennet_de_projekte"

UPSERT_SQL = """
WITH prev AS (
    SELECT content_hash FROM iris_staging.signal_ingest
    WHERE source_system = %(source_system)s AND source_record_id = %(source_record_id)s
)
INSERT INTO iris_staging.signal_ingest AS t (
    source_system, source_record_id, source_url, signal_type, secondary_signal_types, match_reasons,
    title, description, project_status, project_category, project_type, tags, admin_regions,
    published_at, source_updated_at, geom, geo_status, geo_method, geo_note,
    content_hash, first_run_id, last_run_id
) VALUES (
    %(source_system)s, %(source_record_id)s, %(source_url)s, %(signal_type)s, %(secondary)s::text[], %(reasons)s,
    %(title)s, %(description)s, %(status)s, %(category)s, %(project_type)s, %(tags)s::text[], %(regions)s::text[],
    %(published_at)s, %(updated_at)s,
    CASE WHEN %(x)s::float8 IS NULL THEN NULL
         ELSE ST_SetSRID(ST_MakePoint(%(x)s::float8, %(y)s::float8), 25832) END,
    %(geo_status)s, %(geo_method)s, %(geo_note)s,
    %(content_hash)s, %(run_id)s, %(run_id)s
)
ON CONFLICT (source_system, source_record_id) DO UPDATE SET
    source_url = EXCLUDED.source_url, signal_type = EXCLUDED.signal_type,
    secondary_signal_types = EXCLUDED.secondary_signal_types, match_reasons = EXCLUDED.match_reasons,
    title = EXCLUDED.title, description = EXCLUDED.description, project_status = EXCLUDED.project_status,
    project_category = EXCLUDED.project_category, project_type = EXCLUDED.project_type,
    tags = EXCLUDED.tags, admin_regions = EXCLUDED.admin_regions,
    published_at = EXCLUDED.published_at, source_updated_at = EXCLUDED.source_updated_at,
    geom = EXCLUDED.geom, geo_status = EXCLUDED.geo_status, geo_method = EXCLUDED.geo_method,
    geo_note = EXCLUDED.geo_note, content_hash = EXCLUDED.content_hash,
    last_seen_at = now(), last_run_id = EXCLUDED.last_run_id,
    last_changed_at = CASE WHEN t.content_hash <> EXCLUDED.content_hash THEN now() ELSE t.last_changed_at END
RETURNING (SELECT content_hash FROM prev) AS previous_hash
"""


def content_hash(r):
    """Fingerprint of everything we store: same content -> same hash -> 'unchanged'."""
    keys = ["source_url", "signal_type", "secondary_signal_types", "match_reasons", "title", "description",
            "status", "category", "project_type", "tags", "locations", "published_at", "updated_at",
            "geo_status", "x", "y", "geo_method", "geo_note"]
    payload = json.dumps({k: r.get(k) for k in keys}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# Read settings from a local .env file (kept out of Git) if DATABASE_URL is not already set
env_file = Path(".env")
if "DATABASE_URL" not in os.environ and env_file.exists():
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())

database_url = os.environ.get("DATABASE_URL")
if not database_url:
    raise SystemExit("Set DATABASE_URL first (add it to .env or export it)")

records = json.loads(IN_FILE.read_text(encoding="utf-8"))
run_id = uuid.uuid4()
counts = Counter()

with psycopg.connect(database_url, autocommit=True) as conn:
    conn.execute(SCHEMA_FILE.read_text(encoding="utf-8"))            # create PostGIS + tables if missing
    print(conn.execute("SELECT split_part(version(), ' on ', 1), postgis_lib_version()").fetchone())           # create tables if missing
    conn.execute("INSERT INTO iris_staging.ingest_run (run_id) VALUES (%s)", (run_id,))

    for r in records:
        new_hash = content_hash(r)
        params = {
            "source_system": SOURCE_SYSTEM, "source_record_id": r["source_id"], "source_url": r["source_url"],
            "signal_type": r["signal_type"], "secondary": r["secondary_signal_types"],
            "reasons": Jsonb(r["match_reasons"]), "title": r["title"], "description": r["description"],
            "status": r["status"], "category": r["category"], "project_type": r["project_type"],
            "tags": r["tags"], "regions": r["locations"], "published_at": r["published_at"],
            "updated_at": r["updated_at"], "x": r["x"], "y": r["y"], "geo_status": r["geo_status"],
            "geo_method": r["geo_method"], "geo_note": r["geo_note"], "content_hash": new_hash, "run_id": run_id,
        }
        try:
            with conn.transaction():
                previous = conn.execute(UPSERT_SQL, params).fetchone()[0]
        except psycopg.Error as exc:                                   # one bad record must not stop the run
            counts["failed"] += 1
            print("  FAILED", r["source_id"], r["title"], "->", exc)
            continue
        if previous is None:
            counts["inserted"] += 1
        elif previous.strip() == new_hash:
            counts["unchanged"] += 1
        else:
            counts["updated"] += 1

    status = "succeeded" if not counts["failed"] else "partial"
    conn.execute("UPDATE iris_staging.ingest_run SET finished_at = now(), status = %s, counts = %s WHERE run_id = %s",
                 (status, Jsonb(dict(counts)), run_id))
    total = conn.execute("SELECT count(*) FROM iris_staging.signal_ingest").fetchone()[0]

print("Run:", run_id, "| status:", status)
print("Inserted:", counts["inserted"], "| Updated:", counts["updated"],
      "| Unchanged:", counts["unchanged"], "| Failed:", counts["failed"])
print("Rows in iris_staging.signal_ingest:", total)