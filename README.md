# TenneT Projects Harvester (IRIS-SIG-27)

This project reads the TenneT project list (https://www.tennet.eu/de/projekte), keeps the projects about
substations, SuedLink and capacity allocation, and saves them in the PostgreSQL table
`iris_staging.signal_ingest`.

## Results (29 Oct 2026)

- 112 projects found, 26 kept (15 substation, 11 SuedLink)
- Second run: 0 new rows, 26 unchanged, so no duplicates
- 38 tests pass, 7 validation checks pass
- Tested with Python 3.12, PostgreSQL 16.15 and PostGIS 3.4.6

## Data source

- robots.txt allows `/de/projekte` (for normal bots only `/api/` is blocked).
- The website answers HTTP 403 when a script downloads the page. I did not try to get around this.
- Instead, I saved the page from the browser (Safari: File > Save As > Page Source) as
  `data/raw/listing_page1.html`. The script reads this file.
- `--live` mode tries a normal download first and stops if the site answers 403.
- All projects are inside the page as JSON (`<script id="__NEXT_DATA__">`). The 6 pages in the browser are
  made by JavaScript, so no extra downloads are needed.
- The browser shows 109 projects, the JSON contains 112. I keep all 112.
- I compared 10 "Zuletzt aktualisiert" dates in the browser with `updatedAt` in the JSON. All 10 match.
- TenneT publishes no coordinates (`geoJson` is empty for every project).

## Which projects are kept

| signal_type | Rule | Count |
|---|---|---|
| suedlink_progress | tag "SuedLink" or "SuedLink" in the title | 11 |
| substation_modernization | type "Umspannwerk", or Umspannwerk / Konverter / Schaltanlage in the title or tags | 15 |
| capacity_allocation | words like "Anschlusskapazität" or "Netzanschlusszusage" | 0 (1 project as second type) |

- A word only in the description is not enough. Power lines often mention the substations at their ends.
- "Übertragungskapazität" (how much a line can carry) is not counted as capacity allocation.
- Projects located only outside Germany are removed.
- The reason for each decision is saved in `match_reasons`.

## Mapping assumptions

The PDF gives the table name but not the columns, so I chose them (`sql/schema.sql`).

| Column | Source |
|---|---|
| source_record_id | `id` (TenneT project id) |
| source_url | `https://www.tennet.eu` + `path` |
| title | `title` (extra spaces removed) |
| published_at | `publishedAt` |
| source_updated_at | `updatedAt` ("Zuletzt aktualisiert") |
| admin_regions | `locations` (federal states) |
| project_status, project_type, tags | `developmentStatus`, `type`, `tags` |
| signal_type | my filter rules (above) |
| geom, geo_status, geo_note | see Locations |

## Locations (EPSG:25832)

| geo_status | Meaning | Count |
|---|---|---|
| resolved | valid point, converted to EPSG:25832 | 0 |
| ambiguous | one point would be wrong (SuedLink is a long power line) | 11 |
| unresolved | no coordinates from TenneT, only the federal state | 15 |
| rejected_invalid | coordinates exist but are wrong | 0 |

- Wrong coordinates (0/0, swapped lat/lon, outside Germany) are rejected and logged, never accepted.
- The database also blocks points outside Germany.
- `config/gazetteer.csv` can hold coordinates checked by hand. It is empty.

## No duplicates

- Each TenneT project id can exist only once (unique key + `INSERT ... ON CONFLICT DO UPDATE`).
- A hash of each record shows if it is new, changed or unchanged.
- Each run is saved in `iris_staging.ingest_run`, so every row can be traced to its run.

## Errors and missing fields

- Errors are printed, saved in `iris_staging.ingest_error`, and written to a report in `reports/`.
- Examples: missing id or title, duplicate id, wrong coordinates, HTTP 403, network errors
  (retried 3 times), empty page, broken JSON.
- Missing fields are listed per record in the `quality_flags` column.

## Setup

Needs Python 3.11+ and PostgreSQL 16 with PostGIS 3.4.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

createdb iris        # main database
createdb iris_test   # test database (the tests clear it)
cp .env.example .env # then set DATABASE_URL and TEST_DATABASE_URL
```

Save https://www.tennet.eu/de/projekte from the browser as `data/raw/listing_page1.html`.
This folder is not in Git because it contains TenneT's page.

## How to run

```bash
python3 run_pipeline.py              # read the saved page and load the database
python3 run_pipeline.py --dry-run    # same, without the database
python3 run_pipeline.py --live       # try to download the page first
python3 make_samples.py              # write the sample CSV and validation results
```

## Tests

```bash
python3 -m pytest -v
```

38 tests. They use two small fake pages with broken data on purpose (missing id, duplicate, empty title,
swapped coordinates, missing date) and fake HTTP answers (403, server errors, timeouts, empty page).
The database tests check that a second run creates no duplicates and that a changed project is updated.
They need `TEST_DATABASE_URL` and are skipped without it.

## Sample output

- `samples/signal_ingest_sample.csv`: the 26 saved records (without long descriptions)
- `samples/validation_results.txt`: results of the 7 checks
- `samples/last_run_report.md`: report of the last run
- `sql/validation_queries.sql`: the same checks in SQL (queries 1 to 7 must return 0 rows)

## Known limitations

- The page has to be saved by hand because the site answers 403 to scripts.
- TenneT publishes no coordinates, so no record has a point yet.
- This page has no projects that are mainly about capacity allocation.
- The browser shows 109 projects, the JSON has 112.
- The filter uses tags, types and titles, so it can miss a project that is only described in the text.

## Folders

```
run_pipeline.py   runs everything
make_samples.py   writes the sample output
harvester/        the code (download, extract, filter, locations, database)
sql/              table definitions and validation queries
tests/            tests and fake test pages
samples/          sample output
exploration/      my first step-by-step scripts and notes
config/           optional hand-checked coordinates
```
