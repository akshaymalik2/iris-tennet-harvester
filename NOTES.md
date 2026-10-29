# Notes - IRIS-SIG-27

## 29 Oct 2026 - Source access check
- robots.txt (https://www.tennet.eu/robots.txt): readable (HTTP 200).
  Blocks named AI crawlers; for all other agents only /api/ is disallowed.
  /de/projekte is allowed. Sitemap: https://www.tennet.eu/sitemap.xml
- GET https://www.tennet.eu/de/projekte with honest User-Agent
  "IRIS-SIG-27-harvester/0.1 (contact: ...)": HTTP 403 (site protection).
- Not bypassed (no fake browser identity, no proxies, no headless browser),
  as required by the brief.
- Alternative: pages saved manually from Safari, processed from local files.
- Browser view: 109 projects, shown on 6 pages; each row shows
  "Zuletzt aktualisiert" date, title, status, type, onshore/offshore.


  - Listing page embeds ALL projects as JSON in <script id="__NEXT_DATA__">
  (props > pageProps > programsAndProjects). total = 112; browser shows 109 (open question).
  Browser pagination (6 pages) is client-side only -> one file contains everything.
- "Zuletzt aktualisiert" = updatedAt: verified for 10 projects against the browser.
  publishedAt is a separate, real publication date.
- geoJson is null for all 112 projects -> no coordinates in the listing.
- 3 titles had leading/trailing spaces -> stripped.

- Step 3 filter: 26 of 112 in scope (15 substation_modernization, 11 suedlink_progress).
  Rules use project type, title and tags; description-only mentions are not enough.
- capacity_allocation: 0 primary records on /de/projekte (only 1 secondary:
  Umspannwerk Markt Bibart Ost). "Übertragungskapazität" (line capacity) deliberately
  not counted as allocation. Capacity allocation news is likely published elsewhere.

  - Project pages (umspannwerk-borken, suedlink): geoJson null, displayMap false
  -> TenneT publishes no coordinates. Project pages have no dates (dates come from listing).
- Canonical link uses /de/projects/<slug>, real path is /de/projekte/<slug> -> use path field.
- Step 4 result: 11 ambiguous (SuedLink corridor), 15 unresolved (no coordinates published).
  Code validates and converts coordinates if they appear (geoJson or config/gazetteer.csv).

  - Step 5: database = PostgreSQL 16.15 (Postgres.app) with PostGIS 3.4.6.
  Run 1: 26 inserted. Run 2: 0 inserted, 26 unchanged
  Run 2:  status: succeeded
         Inserted: 0 | Updated: 0 | Unchanged: 26 | Failed: 0
         Rows in iris_staging.signal_ingest: 26.
  DATABASE_URL is read from .env (git-ignored); no credentials in code.