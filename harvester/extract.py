"""Step 2 as a function: read all projects from the listing page's embedded __NEXT_DATA__ JSON."""
import json
from datetime import datetime, timezone

from bs4 import BeautifulSoup


class ExtractError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def ms_to_iso(ms):
    """Convert milliseconds since 1970 (how the site stores dates) to an ISO date string."""
    if not isinstance(ms, (int, float)) or isinstance(ms, bool):
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def parse_listing(html, base_url="https://www.tennet.eu"):
    """Return (records, problems, total). Raises ExtractError if the page cannot be used at all."""
    if not html or not html.strip():
        raise ExtractError("empty_response", "the HTML is empty")
    script = BeautifulSoup(html, "html.parser").find("script", id="__NEXT_DATA__")
    if script is None or not script.string:
        raise ExtractError("missing_next_data", "no __NEXT_DATA__ block found - the page layout may have changed")
    try:
        data = json.loads(script.string)
    except json.JSONDecodeError as exc:
        raise ExtractError("malformed_json", f"__NEXT_DATA__ is not valid JSON: {exc}") from exc
    try:
        listing = data["props"]["pageProps"]["programsAndProjects"]
    except (KeyError, TypeError) as exc:
        raise ExtractError("unexpected_structure", "props > pageProps > programsAndProjects not found") from exc
    edges = listing.get("edges") or []
    if not edges:
        raise ExtractError("empty_listing", "the project list is empty")

    records, problems, seen_ids = [], [], set()
    for edge in edges:
        node = (edge or {}).get("node") or {}
        source_id = node.get("id")
        path = (node.get("path") or "").strip()
        raw_title = node.get("title") or ""
        title = raw_title.strip()  # some titles have extra spaces

        missing = [name for name, value in (("id", source_id), ("path", path), ("title", title)) if not value]
        if missing:
            problems.append({"stage": "extract", "code": "missing_required_field", "source_record_id": source_id,
                             "message": f"skipped: missing {', '.join(missing)}"})
            continue
        if source_id in seen_ids:
            problems.append({"stage": "extract", "code": "duplicate_record", "source_record_id": source_id,
                             "message": "same project id appears twice in the listing; second copy skipped"})
            continue
        seen_ids.add(source_id)

        records.append({
            "source_id": source_id,
            "source_url": base_url + path,
            "slug": path.rstrip("/").split("/")[-1],
            "title": title,
            "description": (node.get("description") or "").strip() or None,
            "status": node.get("developmentStatus"),
            "category": node.get("category"),
            "project_type": (node.get("type") or {}).get("name"),
            "locations": [l["name"] for l in node.get("locations") or [] if l and l.get("name")],
            "tags": [t["name"] for t in node.get("tags") or [] if t and t.get("name")],
            "published_at": ms_to_iso(node.get("publishedAt")),
            "updated_at": ms_to_iso(node.get("updatedAt")),
            "geojson": node.get("geoJson"),
        })
    return records, problems, listing.get("total")
