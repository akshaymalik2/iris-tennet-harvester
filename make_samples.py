"""Creates the sample output the PDF asks for, from the data in your database:
  samples/signal_ingest_sample.csv   the loaded records (public-source data; long descriptions left out)
  samples/validation_results.txt     the validation checks (all must be 0) and summaries
"""
import csv
from pathlib import Path

from harvester import load
from harvester.config import get_settings

CHECKS = [
    ("no duplicate source records", """SELECT source_system, source_record_id FROM iris_staging.signal_ingest
        GROUP BY 1, 2 HAVING count(*) > 1"""),
    ("only objective signal types", """SELECT signal_id FROM iris_staging.signal_ingest WHERE signal_type NOT IN
        ('substation_modernization', 'suedlink_progress', 'capacity_allocation')"""),
    ("points are valid EPSG:25832 inside Germany", """SELECT signal_id FROM iris_staging.signal_ingest
        WHERE geom IS NOT NULL AND (ST_SRID(geom) <> 25832 OR NOT ST_IsValid(geom)
        OR ST_X(geom) NOT BETWEEN 250000 AND 970000 OR ST_Y(geom) NOT BETWEEN 5220000 AND 6230000)"""),
    ("point exists only when resolved", """SELECT signal_id FROM iris_staging.signal_ingest
        WHERE (geo_status = 'resolved') <> (geom IS NOT NULL)"""),
    ("records without a point explain why", """SELECT signal_id FROM iris_staging.signal_ingest
        WHERE geo_status <> 'resolved' AND coalesce(geo_note, '') = ''"""),
    ("traceable: URL, title, run", """SELECT s.signal_id FROM iris_staging.signal_ingest s
        WHERE s.source_url !~ '^https://www\\.tennet\\.eu/' OR btrim(s.title) = ''
        OR NOT EXISTS (SELECT 1 FROM iris_staging.ingest_run r WHERE r.run_id = s.last_run_id)"""),
    ("missing dates are flagged", """SELECT signal_id FROM iris_staging.signal_ingest
        WHERE published_at IS NULL AND NOT ('missing_published_at' = ANY (quality_flags))"""),
]

EXPORT_SQL = """
SELECT source_record_id, source_url, signal_type, array_to_string(secondary_signal_types, ';') AS secondary_types,
       title, project_status, project_type, project_category, array_to_string(admin_regions, ';') AS regions,
       to_char(published_at, 'YYYY-MM-DD') AS published, to_char(source_updated_at, 'YYYY-MM-DD') AS updated,
       geo_status, ST_AsText(geom) AS geom_epsg25832, geo_note, array_to_string(quality_flags, ';') AS quality_flags,
       first_seen_at, last_seen_at
FROM iris_staging.signal_ingest ORDER BY signal_type, title
"""

settings = get_settings()
Path("samples").mkdir(exist_ok=True)
with load.connect(settings.database_url) as conn:
    cursor = conn.execute(EXPORT_SQL)
    columns = [c.name for c in cursor.description]
    data = cursor.fetchall()
    with open("samples/signal_ingest_sample.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        writer.writerows(data)

    lines, failed = [], 0
    for name, sql in CHECKS:
        bad = len(conn.execute(sql).fetchall())
        failed += bad > 0
        lines.append(f"[{'PASS' if bad == 0 else f'FAIL ({bad} rows)'}] {name}")
    lines.append("\nRecords by signal type and geo status:")
    for row in conn.execute("SELECT signal_type, geo_status, count(*) FROM iris_staging.signal_ingest GROUP BY 1, 2 ORDER BY 1, 2"):
        lines.append("  " + " | ".join(map(str, row)))
    lines.append("\nLast runs:")
    for row in conn.execute("SELECT left(run_id::text, 8), mode, status, counts FROM iris_staging.ingest_run "
                            "ORDER BY started_at DESC LIMIT 5"):
        lines.append("  " + " | ".join(map(str, row)))
    version = conn.execute("SELECT split_part(version(), ' on ', 1), postgis_lib_version()").fetchone()
    lines.append(f"\nDatabase: {version[0]} / PostGIS {version[1]}")

Path("samples/validation_results.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
print("\n".join(lines))
print(f"\nWrote samples/signal_ingest_sample.csv ({len(data)} records) and samples/validation_results.txt")
