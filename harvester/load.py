"""Step 5 as functions: idempotent load into iris_staging.signal_ingest + run and error logging."""
import hashlib
import json

import psycopg
from psycopg.types.json import Jsonb

UPSERT_SQL = """
WITH prev AS (
    SELECT content_hash FROM iris_staging.signal_ingest
    WHERE source_system = %(source_system)s AND source_record_id = %(source_record_id)s
)
INSERT INTO iris_staging.signal_ingest AS t (
    source_system, source_record_id, source_url, signal_type, secondary_signal_types, match_reasons,
    title, description, project_status, project_category, project_type, tags, admin_regions,
    published_at, source_updated_at, geom, geo_status, geo_method, geo_note, quality_flags,
    content_hash, first_run_id, last_run_id
) VALUES (
    %(source_system)s, %(source_record_id)s, %(source_url)s, %(signal_type)s, %(secondary)s::text[], %(reasons)s,
    %(title)s, %(description)s, %(status)s, %(category)s, %(project_type)s, %(tags)s::text[], %(regions)s::text[],
    %(published_at)s, %(updated_at)s,
    CASE WHEN %(x)s::float8 IS NULL THEN NULL
         ELSE ST_SetSRID(ST_MakePoint(%(x)s::float8, %(y)s::float8), 25832) END,
    %(geo_status)s, %(geo_method)s, %(geo_note)s, %(quality_flags)s::text[],
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
    geo_note = EXCLUDED.geo_note, quality_flags = EXCLUDED.quality_flags, content_hash = EXCLUDED.content_hash,
    last_seen_at = now(), last_run_id = EXCLUDED.last_run_id,
    last_changed_at = CASE WHEN t.content_hash <> EXCLUDED.content_hash THEN now() ELSE t.last_changed_at END
RETURNING (SELECT content_hash FROM prev) AS previous_hash
"""

HASH_KEYS = ["source_url", "signal_type", "secondary_signal_types", "match_reasons", "title", "description",
             "status", "category", "project_type", "tags", "locations", "published_at", "updated_at",
             "geo_status", "x", "y", "geo_method", "geo_note"]


def content_hash(record):
    """Fingerprint of the stored content: same content -> same hash -> 'unchanged'."""
    payload = json.dumps({k: record.get(k) for k in HASH_KEYS}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def apply_schema(conn, schema_file):
    conn.execute(schema_file.read_text(encoding="utf-8"))


def start_run(conn, run_id, mode, input_desc):
    conn.execute("INSERT INTO iris_staging.ingest_run (run_id, mode, input) VALUES (%s, %s, %s)",
                 (run_id, mode, input_desc))


def finish_run(conn, run_id, status, counts):
    conn.execute("UPDATE iris_staging.ingest_run SET finished_at = now(), status = %s, counts = %s WHERE run_id = %s",
                 (status, Jsonb(counts), run_id))


def log_problem(conn, run_id, problem):
    conn.execute(
        "INSERT INTO iris_staging.ingest_error (run_id, stage, error_code, source_record_id, message) "
        "VALUES (%s, %s, %s, %s, %s)",
        (run_id, problem["stage"], problem["code"], problem.get("source_record_id"), problem.get("message")),
    )


def upsert_record(conn, record, run_id, source_system):
    """Insert or update one record. Returns 'inserted', 'updated' or 'unchanged'."""
    new_hash = content_hash(record)
    params = {
        "source_system": source_system, "source_record_id": record["source_id"], "source_url": record["source_url"],
        "signal_type": record["signal_type"], "secondary": record["secondary_signal_types"],
        "reasons": Jsonb(record["match_reasons"]), "title": record["title"], "description": record["description"],
        "status": record["status"], "category": record["category"], "project_type": record["project_type"],
        "tags": record["tags"], "regions": record["locations"], "published_at": record["published_at"],
        "updated_at": record["updated_at"], "x": record["x"], "y": record["y"], "geo_status": record["geo_status"],
        "geo_method": record["geo_method"], "geo_note": record["geo_note"],
        "quality_flags": record.get("quality_flags", []), "content_hash": new_hash, "run_id": run_id,
    }
    with conn.transaction():
        previous = conn.execute(UPSERT_SQL, params).fetchone()[0]
    if previous is None:
        return "inserted"
    return "unchanged" if previous.strip() == new_hash else "updated"


def connect(database_url):
    if not database_url:
        raise SystemExit("DATABASE_URL is not set (add it to .env or use --dry-run)")
    return psycopg.connect(database_url, autocommit=True)
