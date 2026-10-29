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