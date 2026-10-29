-- IRIS-SIG-27 staging schema (PostgreSQL 16 / PostGIS 3.4). Safe to run many times.
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE SCHEMA IF NOT EXISTS iris_staging;

-- One row per harvester run: makes every record traceable to the run that loaded it
CREATE TABLE IF NOT EXISTS iris_staging.ingest_run (
    run_id      uuid PRIMARY KEY,
    started_at  timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    status      text NOT NULL DEFAULT 'running',
    counts      jsonb
);
ALTER TABLE iris_staging.ingest_run ADD COLUMN IF NOT EXISTS mode text;
ALTER TABLE iris_staging.ingest_run ADD COLUMN IF NOT EXISTS input text;

CREATE TABLE IF NOT EXISTS iris_staging.signal_ingest (
    signal_id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_system          text NOT NULL,                 -- 'tennet_de_projekte'
    source_record_id       text NOT NULL,                 -- TenneT project id, e.g. '494'
    source_url             text NOT NULL CHECK (source_url ~ '^https?://'),
    signal_type            text NOT NULL CHECK (signal_type IN
                               ('substation_modernization', 'suedlink_progress', 'capacity_allocation')),
    secondary_signal_types text[] NOT NULL DEFAULT '{}',
    match_reasons          jsonb NOT NULL DEFAULT '{}',
    title                  text NOT NULL CHECK (btrim(title) <> ''),
    description            text,
    project_status         text,                          -- planning / active / finished / preparation
    project_category       text,                          -- onshore / offshore
    project_type           text,
    tags                   text[] NOT NULL DEFAULT '{}',
    admin_regions          text[] NOT NULL DEFAULT '{}',  -- geographic context from the source
    published_at           timestamptz,                   -- publishedAt from the source
    source_updated_at      timestamptz,                   -- updatedAt ("Zuletzt aktualisiert")
    geom                   geometry(Point, 25832),
    geo_status             text NOT NULL CHECK (geo_status IN ('resolved', 'ambiguous', 'unresolved', 'rejected_invalid')),
    geo_method             text,
    geo_note               text,
    content_hash           char(64) NOT NULL,
    first_seen_at          timestamptz NOT NULL DEFAULT now(),
    last_seen_at           timestamptz NOT NULL DEFAULT now(),
    last_changed_at        timestamptz NOT NULL DEFAULT now(),
    first_run_id           uuid REFERENCES iris_staging.ingest_run (run_id),
    last_run_id            uuid REFERENCES iris_staging.ingest_run (run_id),
    -- Idempotency: the same source record can only exist once
    CONSTRAINT signal_ingest_source_uk UNIQUE (source_system, source_record_id),
    -- A point exists only when the location is resolved
    CONSTRAINT signal_ingest_geom_status_ck CHECK ((geo_status = 'resolved') = (geom IS NOT NULL)),
    -- Second safety net: points must lie in Germany (EPSG:25832 range)
    CONSTRAINT signal_ingest_geom_germany_ck CHECK (geom IS NULL OR (
        ST_X(geom) BETWEEN 250000 AND 970000 AND ST_Y(geom) BETWEEN 5220000 AND 6230000))
);
-- Missing optional fields are listed per record (e.g. missing_published_at, geo_unresolved)
ALTER TABLE iris_staging.signal_ingest ADD COLUMN IF NOT EXISTS quality_flags text[] NOT NULL DEFAULT '{}';

-- Every problem found during a run (skipped records, rejected coordinates, load failures ...)
CREATE TABLE IF NOT EXISTS iris_staging.ingest_error (
    error_id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id           uuid NOT NULL REFERENCES iris_staging.ingest_run (run_id),
    occurred_at      timestamptz NOT NULL DEFAULT now(),
    stage            text NOT NULL,            -- fetch / extract / geo / load
    error_code       text NOT NULL,
    source_record_id text,
    message          text
);
