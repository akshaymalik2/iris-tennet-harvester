"""Step 3 as functions: keep only projects matching the PDF objective
("substation modernizations, SuedLink progress, and capacity allocations")."""
import re

PRIORITY = ["suedlink_progress", "substation_modernization", "capacity_allocation"]

SUBSTATION_WORDS = re.compile(r"umspannwerk|umspannanlage|konverter|schaltanlage", re.IGNORECASE)
SUBSTATION_TAGS = {"Umspannwerk", "Konverter", "DC-Schaltanlage"}
CAPACITY_WORDS = re.compile(
    r"netzanschlusskapazit|anschlusskapazit|kapazitätsvergabe|kapazitätsreservierung"
    r"|netzanschlusszusage|netzanschlussbegehren|anschlussanfrage",
    re.IGNORECASE,
)
FOREIGN_LOCATIONS = {"Großbritannien", "Niederlande", "Dänemark", "Norwegen"}


def match_signal_types(p):
    """Return {signal_type: [reasons]} for one project."""
    found = {}

    reasons = []
    if "SuedLink" in p["tags"]:
        reasons.append("tag=SuedLink")
    if re.search(r"s(ue|ü)d\s?link", p["title"], re.IGNORECASE):
        reasons.append("title mentions SuedLink")
    if reasons:
        found["suedlink_progress"] = reasons

    # A passing mention in the description is not enough for substations
    reasons = []
    if p["project_type"] == "Umspannwerk":
        reasons.append("type=Umspannwerk")
    if SUBSTATION_WORDS.search(p["title"]):
        reasons.append("title mentions substation/converter")
    for tag in p["tags"]:
        if tag in SUBSTATION_TAGS or tag.startswith("Umspannwerk "):
            reasons.append(f"tag={tag}")
    if reasons:
        found["substation_modernization"] = reasons

    text = p["title"] + " " + (p["description"] or "")
    hits = sorted({m.group(0).lower() for m in CAPACITY_WORDS.finditer(text)})
    if hits:
        found["capacity_allocation"] = [f"text mentions {h}" for h in hits]
    return found


def filter_records(projects):
    """Return (signals, out_of_scope). Every decision carries its reason."""
    signals, out_of_scope = [], []
    for p in projects:
        if p["locations"] and all(loc in FOREIGN_LOCATIONS for loc in p["locations"]):
            out_of_scope.append({"source_id": p["source_id"], "title": p["title"], "reason": "outside Germany"})
            continue
        found = match_signal_types(p)
        if not found:
            out_of_scope.append({"source_id": p["source_id"], "title": p["title"], "reason": "no matching signal type"})
            continue
        ordered = [t for t in PRIORITY if t in found]
        signals.append({**p, "signal_type": ordered[0], "secondary_signal_types": ordered[1:], "match_reasons": found})
    return signals, out_of_scope
