# IRIS-SIG-27 – TenneT TSO Grid Expansion & Substation Projects Harvester

Python harvester (integration pattern B, HTML) for TenneT Germany's project catalogue
(https://www.tennet.eu/de/projekte). It extracts all projects, keeps those matching the objective
(high-voltage substation modernisation, SuedLink progress, capacity allocation), resolves locations to
EPSG:25832 where the source allows it, and loads the records idempotently into
`iris_staging.signal_ingest` on PostgreSQL 16 / PostGIS 3.4.

## Results at a glance (last run, 29 Oct 2026)

| Item | Result |
|---|---|
| Projects in the source listing | 112 |
| In scope | 26 (15 substation_modernization, 11 suedlink_progress) |
| Out of scope (with reason) | 86 |
| First load / re-run | 26 inserted / 0 inserted, 26 unchanged (no duplicates) |
| Automated tests | 38 passed |
| Validation checks | 7 of 7 pass |
| Tested on | Python 3.12.7, PostgreSQL 16.15 + PostGIS 3.4.6 (Postgres.app, macOS) |

## Data source and access (verified 29 Oct 2026)

- robots.txt (https://www.tennet.eu/robots.txt) is readable. It blocks a list of named AI crawlers; for all
  other user agents only `/api/` is disallowed, so `/de/projekte` is allowed. It also lists a sitemap.
- An automated request to `/de/projekte` with an honest User-Agent (`IRIS-SIG-27-harvester/0.1 (contact: …)`)
  returned HTTP 403 (site protection). As required by the brief, this was not bypassed: no browser
  impersonation, no proxies, no headless browser.
- Justified alternative: the listing page was saved manually from a normal browser session
  (Safari: File > Save As > Format "Page Source") to `data/raw/listing_page1.html`, and the harvester processes
  that file. The `--live` mode implements the polite download (robots.txt, retries, stop on 403) and works
  unchanged if access is granted. Further alternatives, not implemented: asking TenneT for a feed, or
  official registers such as netzausbau.de.
- Current format: the page is built with Next.js. All projects are embedded as JSON in
  `<script id="__NEXT_DATA__">` at `props > pageProps > programsAndProjects` (`total` and `edges[].node`).
  The 6 pages in the browser are client-side only, so one response contains every project and no further
  page requests are needed (this answers the pagination requirement).
- Open question: the browser shows "109 of 109 projects", the embedded data contains 112. All 112 are processed.
- Dates verified, not assumed: the "Zuletzt aktualisiert" date of 10 projects in the browser was compared
  with `updatedAt` in the data; all 10 match. `publishedAt` is a separate, real publication date.
  Project detail pages contain no dates.
- Coordinates: `geoJson` is null for all 112 projects in the listing and on two sampled detail pages
  (umspannwerk-borken, suedlink), where the map is also switched off (`displayMap: false`).
- Detail pages declare a canonical link `/de/projects/<slug>` while the real path is `/de/projekte/<slug>`;
  the harvester uses the `path` field.

## What is collected (signal type and geographic filter)

| signal_type | Rule | Records |
|---|---|---|
| suedlink_progress | tag "SuedLink", or "SuedLink" in the title | 11 |
| substation_modernization | project type "Umspannwerk", or Umspannwerk / Umspannanlage / Konverter / Schaltanlage in the title, or tag "Umspannwerk", "Konverter", "DC-Schaltanlage", "Umspannwerk <name>" | 15 |
| capacity_allocation | grid-connection capacity wording (Netzanschlusskapazität, Anschlusskapazität, Kapazitätsvergabe, Netzanschlusszusage, …) | 0 primary, 1 secondary |

- If several types match, the order above decides the primary type; the others are kept in
  `secondary_signal_types`. The reasons for every decision are stored in `match_reasons`.
- A word that appears only in the description does not count for substations: power-line projects
  often mention the substations at their ends.
- General "Übertragungskapazität" (how much a line can carry) is not treated as a capacity allocation.
  The project catalogue currently publishes no capacity-allocation announcements; only
  "Umspannwerk Markt Bibart Ost" mentions grid-connection capacity (secondary type).
- Geographic filter: projects located only outside Germany are excluded (no current in-scope project is
  affected). Every excluded project is listed with its reason in the run report.

## Field mapping (source to `iris_staging.signal_ingest`)

| Column | Source (`__NEXT_DATA__` node) | Notes |
|---|---|---|
| source_system | constant `tennet_de_projekte` | |
| source_record_id | `id` | stable TenneT id, e.g. SuedLink = 494 |
| source_url | `https://www.tennet.eu` + `path` | |
| title | `title` | leading/trailing spaces removed (3 titles affected) |
| description | `description` | |
| signal_type, secondary_signal_types, match_reasons | derived | filter rules above |
| project_status | `developmentStatus` | planning / active / finished / preparation |
| project_category | `category` | onshore / offshore |
| project_type | `type.name` | e.g. Umspannwerk, Neubau |
| tags | `tags[].name` | |
| admin_regions | `locations[].name` | federal states, Nordsee, occasionally a municipality |
| published_at | `publishedAt` | milliseconds since 1970, stored as UTC |
| source_updated_at | `updatedAt` | shown on the site as "Zuletzt aktualisiert" |
| geom, geo_status, geo_method, geo_note | `geoJson` (null) or `config/gazetteer.csv` | see Locations |
| quality_flags | derived | e.g. missing_published_at, geo_unresolved |
| content_hash, first/last_seen_at, last_changed_at, first/last_run_id | pipeline | idempotency and lineage |

The target table name comes from the brief. The column layout is an assumption (the brief does not define
it); it is in `sql/schema.sql`. The database name is configurable through `DATABASE_URL`.

## Locations (EPSG:25832)

Order of evidence, giving one `geo_status` per record:

1. A Point in the source `geoJson`: validated and converted from EPSG:4326 to EPSG:25832 (pyproj).
   Other geometry types become `ambiguous`.
2. SuedLink records become `ambiguous`: a corridor of about 700 km cannot be represented by one point.
3. Hand-checked coordinates in `config/gazetteer.csv` (optional, keyed by TenneT id, with source and date).
4. Otherwise `unresolved`, with the known region in `geo_note`.

Validation rejects missing or non-numeric values, 0/0 placeholders, out-of-range values, likely
latitude/longitude swaps, and points outside Germany including its North Sea / Baltic Sea zone. Rejected
coordinates get `geo_status = rejected_invalid`, are logged as an error, and are never silently corrected or
replaced. The database enforces the same rules as a second safety net (CHECK constraints: a point exists
only when resolved and must lie inside Germany's EPSG:25832 range).

Current result: 15 unresolved (TenneT publishes no coordinates), 11 ambiguous (SuedLink), 0 resolved.
The gazetteer is empty; coordinates should only be added after manual verification (e.g. OpenStreetMap,
which requires the credit "© OpenStreetMap contributors").

## Idempotency and traceability

- `UNIQUE (source_system, source_record_id)` plus `INSERT … ON CONFLICT DO UPDATE`: a project can only
  exist once.
- `content_hash` (SHA-256 of the stored content) classifies each record as inserted, updated or unchanged;
  `last_changed_at` moves only when the content changes.
- Every run is recorded in `iris_staging.ingest_run` (mode, input, status, counts), and every record
  points to its first and last run.

## Errors and missing fields

All problems are shown on the console, stored in `iris_staging.ingest_error`, and written to a run report
(`reports/run_<time>_<id>.md` and `.json`). Missing optional fields are listed per record in `quality_flags`
and counted in the run report.

| Situation | Code | Behaviour |
|---|---|---|
| Site refuses access (401/403/451) | access_blocked | run stops, status `blocked`, no bypass |
| robots.txt disallows or is unreadable | robots_disallowed | run stops, status `blocked` |
| Timeout, connection error, HTTP 429/5xx | network_failure | retried with growing pauses, then reported |
| Empty response / missing input file | empty_response / input_missing | run fails with a clear message |
| No `__NEXT_DATA__`, broken JSON, changed structure | missing_next_data / malformed_json / unexpected_structure | run fails with a clear message |
| Empty project list | empty_listing | run fails with a clear message |
| Project without id, path or title | missing_required_field | record skipped and logged |
| Same project twice in the listing | duplicate_record | second copy skipped and logged |
| Invalid coordinates | invalid_coordinates | record kept as rejected_invalid, logged |
| Unusable gazetteer row | bad_gazetteer_row | row ignored and logged |
| Database unreachable / record rejected by the database | database_unavailable / db_error | run fails / that record fails, the rest continue |

Exit codes: 0 succeeded, 1 partial, 2 failed, 3 blocked by the source.

## Setup

Requirements: Python 3.11+, PostgreSQL 16 with PostGIS 3.4 (tested with Postgres.app 16.15 / PostGIS 3.4.6;
the Docker image `postgis/postgis:16-3.4` can be used instead).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

createdb iris          # main database
createdb iris_test     # separate database for the automated tests
cp .env.example .env   # then edit DATABASE_URL and TEST_DATABASE_URL
```

Input: open https://www.tennet.eu/de/projekte in a browser and save it as page source to
`data/raw/listing_page1.html` (this folder is not in Git because it holds TenneT's content).

## How to run

```bash
python3 run_pipeline.py                  # process data/raw/listing_page1.html and load the database
python3 run_pipeline.py --input FILE     # another saved page
python3 run_pipeline.py --dry-run        # everything except writing to the database
python3 run_pipeline.py --live           # polite live download first (currently answered with HTTP 403)
python3 make_samples.py                  # samples/signal_ingest_sample.csv + samples/validation_results.txt
```

The schema is created automatically and safely on every run (`sql/schema.sql`).

## Tests

```bash
python3 -m pytest -v
```

38 tests using two synthetic fixtures (`tests/fixtures/`) with the real page structure and deliberate errors
(missing id, duplicate id, blank title, extra spaces, missing date, swapped coordinates, a LineString, a
foreign location), plus mocked HTTP answers. Covered: extraction and error codes, filter rules, coordinate
validation and EPSG:25832 conversion, robots.txt / 403 / retries / empty responses, the full pipeline incl. a
blocked live run, and against a real PostGIS database: re-run without duplicates, update of a changed record,
SRID 25832, error table, and the database rejecting a point outside Germany.

- Database tests need `TEST_DATABASE_URL`; they are skipped otherwise. The `iris_staging` schema in that
  database is deleted and recreated, so never point it at your main database.
- Two tests use the saved real page in `data/raw/` and are skipped when it is not present.

## Sample output and validation

- `samples/signal_ingest_sample.csv`: the 26 loaded records (public-source data; long descriptions left out)
- `samples/validation_results.txt`: the 7 validation checks (all PASS) and summaries
- `samples/last_run_report.md`: the run report of the last pipeline run
- `sql/validation_queries.sql`: the same checks for psql; queries 1–7 must return zero rows

## Error and quality report (last run)

| Item | Result |
|---|---|
| Records extracted / skipped / duplicates | 112 / 0 / 0 |
| Missing description, publishedAt, updatedAt, locations (in-scope records) | 0, 0, 0, 0 |
| Titles cleaned (extra spaces) | 3 |
| geo_status | 15 unresolved, 11 ambiguous, 0 resolved, 0 rejected_invalid |
| Load | 0 inserted, 0 updated, 26 unchanged, 0 failed |
| Errors logged | 0 |
| Validation checks | 7 PASS |

## Known limitations

- Automated access is currently refused (HTTP 403), so the input page must be saved manually; a scheduled
  refresh needs TenneT's permission or a feed.
- The embedded data contains 112 projects while the browser shows 109; the difference is not explained by
  the source.
- TenneT publishes no coordinates, so no record has a point yet; the code resolves points as soon as
  `geoJson` or verified gazetteer entries exist.
- The project catalogue publishes no capacity-allocation announcements; these are likely published elsewhere.
- Classification uses tags, types and titles; projects described only in their text may be missed.
- Detail pages (e.g. SuedLink section progress) are not harvested; this would be a natural extension.
- If TenneT changes the page technology, extraction stops with a clear error code instead of loading wrong data.
- Dates are stored in UTC; use `AT TIME ZONE 'Europe/Berlin'` to show them as on the website.

## Project structure

```
run_pipeline.py            one command for the whole pipeline
make_samples.py            sample CSV and validation results
harvester/                 pipeline code: config, fetch, extract, classify, geo, load, pipeline
sql/schema.sql             tables (safe to run repeatedly)
sql/validation_queries.sql validation checks for psql
config/gazetteer.csv       optional hand-checked coordinates (empty)
tests/                     38 automated tests and synthetic fixtures
samples/                   sample output, validation results, last run report
exploration/               step-by-step scripts used to investigate the source, and notes
requirements.txt, .env.example, .gitignore, pytest.ini
data/raw/                  saved TenneT page (not in Git)
```
