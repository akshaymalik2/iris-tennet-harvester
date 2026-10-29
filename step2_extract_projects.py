"""Step 2: extract all TenneT projects from the saved listing page.
"""
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

RAW_FILE = Path("data/raw/listing_page1.html")
OUT_FILE = Path("data/processed/projects.json")
BASE_URL = "https://www.tennet.eu"


def ms_to_iso(ms):
    """Convert milliseconds since 1970 (how the site stores dates) to an ISO date string."""
    if not isinstance(ms, (int, float)):
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


# 1. Read the saved page and find the hidden JSON block
html = RAW_FILE.read_text(encoding="utf-8")
script = BeautifulSoup(html, "html.parser").find("script", id="__NEXT_DATA__")
if script is None or not script.string:
    raise SystemExit("No __NEXT_DATA__ block found - the page layout may have changed.")
data = json.loads(script.string)

# 2. Walk down to the list of projects
listing = data["props"]["pageProps"]["programsAndProjects"]
edges = listing.get("edges") or []
if not edges:
    raise SystemExit("The project list is empty.")

# 3. Turn every project into a clean record
records, seen_ids, skipped, duplicates = [], set(), [], 0
for edge in edges:
    node = edge.get("node") or {}
    source_id = node.get("id")
    path = (node.get("path") or "").strip()
    title = (node.get("title") or "").strip()  # some titles have extra spaces

    if not source_id or not path or not title:  # required fields
        skipped.append({"id": source_id, "path": path, "title": title})
        continue
    if source_id in seen_ids:  # same project twice
        duplicates += 1
        continue
    seen_ids.add(source_id)

    records.append({
        "source_id": source_id,
        "source_url": BASE_URL + path,
        "slug": path.rstrip("/").split("/")[-1],
        "title": title,
        "description": (node.get("description") or "").strip() or None,
        "status": node.get("developmentStatus"),          # planning / active / finished / preparation
        "category": node.get("category"),                 # onshore / offshore
        "project_type": (node.get("type") or {}).get("name"),
        "locations": [l["name"] for l in node.get("locations") or [] if l.get("name")],
        "tags": [t["name"] for t in node.get("tags") or [] if t.get("name")],
        "published_at": ms_to_iso(node.get("publishedAt")),
        "updated_at": ms_to_iso(node.get("updatedAt")),   # shown as "Zuletzt aktualisiert"
        "geojson": node.get("geoJson"),
    })

# 4. Save the clean records and print a summary
OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
OUT_FILE.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")

print("Projects in file (total field):", listing.get("total"))
print("Records extracted:", len(records))
print("Skipped (missing id/path/title):", len(skipped))
print("Duplicates removed:", duplicates)
print("With coordinates (geoJson):", sum(1 for r in records if r["geojson"]))
print("Status:", dict(Counter(r["status"] for r in records)))
print("Types:", dict(Counter(r["project_type"] for r in records).most_common(5)))
print("Saved to:", OUT_FILE)
print("\nFirst 3 records:")
for r in records[:3]:
    print(f"  [{r['source_id']}] {r['title']} | {r['status']} | {r['locations']} | published {r['published_at'][:10]}")