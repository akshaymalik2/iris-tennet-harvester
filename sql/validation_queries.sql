-- IRIS-SIG-27 validation queries. Checks 1-7 must return ZERO rows.
-- Also run automatically by:  python3 make_samples.py  (results in samples/validation_results.txt)

-- 1. No duplicates (idempotency)
SELECT source_system, source_record_id, count(*) FROM iris_staging.signal_ingest GROUP BY 1, 2 HAVING count(*) > 1;

-- 2. Only the signal types from the objective
SELECT signal_id FROM iris_staging.signal_ingest
WHERE signal_type NOT IN ('substation_modernization', 'suedlink_progress', 'capacity_allocation');

-- 3. Every point is EPSG:25832, valid and inside Germany
SELECT signal_id FROM iris_staging.signal_ingest WHERE geom IS NOT NULL AND (ST_SRID(geom) <> 25832 OR NOT ST_IsValid(geom)
   OR ST_X(geom) NOT BETWEEN 250000 AND 970000 OR ST_Y(geom) NOT BETWEEN 5220000 AND 6230000);

-- 4. A point exists if and only if geo_status = 'resolved'
SELECT signal_id FROM iris_staging.signal_ingest WHERE (geo_status = 'resolved') <> (geom IS NOT NULL);

-- 5. Every record without a point explains why
SELECT signal_id FROM iris_staging.signal_ingest WHERE geo_status <> 'resolved' AND coalesce(geo_note, '') = '';

-- 6. Traceability: source URL, title and a known run on every record
SELECT s.signal_id FROM iris_staging.signal_ingest s
WHERE s.source_url !~ '^https://www\.tennet\.eu/' OR btrim(s.title) = ''
   OR NOT EXISTS (SELECT 1 FROM iris_staging.ingest_run r WHERE r.run_id = s.last_run_id);

-- 7. Missing dates are flagged
SELECT signal_id FROM iris_staging.signal_ingest
WHERE published_at IS NULL AND NOT ('missing_published_at' = ANY (quality_flags));

-- Summaries for review
SELECT signal_type, geo_status, count(*) FROM iris_staging.signal_ingest GROUP BY 1, 2 ORDER BY 1, 2;
SELECT run_id, mode, status, started_at, counts FROM iris_staging.ingest_run ORDER BY started_at DESC LIMIT 5;
SELECT run_id, stage, error_code, source_record_id, message FROM iris_staging.ingest_error ORDER BY occurred_at DESC LIMIT 20;
