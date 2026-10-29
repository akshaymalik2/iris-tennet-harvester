"""Step 4: resolve locations to EPSG:25832 points (PDF: "where the source provides
sufficient information; document ambiguous or unresolved locations").

Finding: TenneT publishes no coordinates (geoJson is null on the listing and on the
project pages, and the map is switched off). So each record gets a geo_status:
  resolved          - a valid point exists (from geoJson, or from config/gazetteer.csv)
  ambiguous         - a single point would be misleading (SuedLink is a ~700 km line)
  unresolved        - no coordinates available; only the region is known
  rejected_invalid  - coordinates exist but fail validation (never silently accepted)
"""
import csv
import json
import math
from collections import Counter
from pathlib import Path

from pyproj import Transformer

IN_FILE = Path("data/processed/signals.json")
OUT_FILE = Path("data/processed/signals_geo.json")
GAZETTEER_FILE = Path("config/gazetteer.csv")

# Germany incl. its North Sea / Baltic Sea zone, in WGS84 (lon_min, lat_min, lon_max, lat_max)
GERMANY_BBOX = (5.8, 47.2, 15.1, 56.0)
TO_25832 = Transformer.from_crs("EPSG:4326", "EPSG:25832", always_xy=True)


def check_coordinates(lat, lon):
    """Return None if the WGS84 point is valid, otherwise the reason it is invalid."""
    if lat is None or lon is None or not (math.isfinite(lat) and math.isfinite(lon)):
        return "missing or not a number"
    if lat == 0 and lon == 0:
        return "0/0 placeholder"
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return "out of range"
    lon_min, lat_min, lon_max, lat_max = GERMANY_BBOX
    if not (lon_min <= lon <= lon_max and lat_min <= lat <= lat_max):
        if lon_min <= lat <= lon_max and lat_min <= lon <= lat_max:
            return "latitude and longitude look swapped"
        return "outside Germany"
    return None


def to_point(lat, lon, method, note):
    """Validate a WGS84 point and convert it to EPSG:25832."""
    problem = check_coordinates(lat, lon)
    if problem:
        return {"geo_status": "rejected_invalid", "x": None, "y": None, "geo_method": method,
                "geo_note": f"Coordinates ({lat}, {lon}) rejected: {problem}"}
    x, y = TO_25832.transform(lon, lat)  # always_xy=True -> (lon, lat) in, (x, y) out
    return {"geo_status": "resolved", "x": round(x, 2), "y": round(y, 2), "geo_method": method, "geo_note": note}


def load_gazetteer():
    """Optional hand-checked coordinates, keyed by TenneT's project ID."""
    if not GAZETTEER_FILE.exists():
        return {}
    entries = {}
    with GAZETTEER_FILE.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            try:
                entries[row["source_id"]] = (float(row["lat"]), float(row["lon"]), row.get("source") or "")
            except (TypeError, ValueError):
                print("Gazetteer row ignored (lat/lon not numeric):", row)
    return entries


def resolve(record, gazetteer):
    regions = ", ".join(record["locations"]) or "none"
    geo = record.get("geojson")

    # 1. Coordinates published by TenneT (none today, but handled if they appear)
    if isinstance(geo, dict) and geo.get("type") == "Point" and len(geo.get("coordinates") or []) >= 2:
        lon, lat = geo["coordinates"][:2]  # GeoJSON order is [lon, lat]
        return to_point(lat, lon, "source_geojson", "Point published by TenneT")
    if geo:
        return {"geo_status": "ambiguous", "x": None, "y": None, "geo_method": "source_geojson",
                "geo_note": f"Source geometry is {geo.get('type') if isinstance(geo, dict) else 'not a Point'}; no single point chosen"}

    # 2. SuedLink is a corridor, not a place
    if record["signal_type"] == "suedlink_progress":
        return {"geo_status": "ambiguous", "x": None, "y": None, "geo_method": None,
                "geo_note": f"Linear HVDC corridor; a single point would be misleading. Regions: {regions}"}

    # 3. Hand-checked coordinates from config/gazetteer.csv
    if record["source_id"] in gazetteer:
        lat, lon, source = gazetteer[record["source_id"]]
        return to_point(lat, lon, "gazetteer", f"Hand-checked coordinates ({source})")

    # 4. Nothing available
    return {"geo_status": "unresolved", "x": None, "y": None, "geo_method": None,
            "geo_note": f"TenneT publishes no coordinates for this project; region only: {regions}"}


signals = json.loads(IN_FILE.read_text(encoding="utf-8"))
gazetteer = load_gazetteer()
for record in signals:
    record.update(resolve(record, gazetteer))
    record["srid"] = 25832

OUT_FILE.write_text(json.dumps(signals, indent=2, ensure_ascii=False), encoding="utf-8")
print("Records:", len(signals), "| gazetteer entries:", len(gazetteer))
print("geo_status:", dict(Counter(r["geo_status"] for r in signals)))
print("Saved to:", OUT_FILE)
print()
for r in signals:
    point = f"({r['x']}, {r['y']})" if r["x"] is not None else ""
    print(f"  {r['geo_status']:<17} {r['title'][:45]:<45} {point}")