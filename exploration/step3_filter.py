"""Step 3: keep only the projects that match the PDF objective.

Objective: "Track high-voltage substation modernizations, SuedLink progress,
and capacity allocations."  Each kept record gets a signal_type and the
reasons why it matched, so every decision is traceable.
"""
import json
import re
from collections import Counter
from pathlib import Path

IN_FILE = Path("data/processed/projects.json")
SIGNALS_FILE = Path("data/processed/signals.json")
OUT_OF_SCOPE_FILE = Path("data/processed/out_of_scope.json")

# If a project matches several types, the first one in this list wins
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

    # SuedLink: the site tags SuedLink projects; the title is a backup check
    reasons = []
    if "SuedLink" in p["tags"]:
        reasons.append("tag=SuedLink")
    if re.search(r"s(ue|ü)d\s?link", p["title"], re.IGNORECASE):
        reasons.append("title mentions SuedLink")
    if reasons:
        found["suedlink_progress"] = reasons

    # Substations: project type, title words or tags (a passing mention in the description is not enough)
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

    # Capacity allocation: grid-connection capacity wording (not general "transmission capacity")
    text = p["title"] + " " + (p["description"] or "")
    hits = sorted({m.group(0).lower() for m in CAPACITY_WORDS.finditer(text)})
    if hits:
        found["capacity_allocation"] = [f"text mentions {h}" for h in hits]

    return found


projects = json.loads(IN_FILE.read_text(encoding="utf-8"))
signals, out_of_scope = [], []

for p in projects:
    # Geographic filter: at least one location must be in Germany (incl. North Sea)
    if p["locations"] and all(loc in FOREIGN_LOCATIONS for loc in p["locations"]):
        out_of_scope.append({"source_id": p["source_id"], "title": p["title"], "reason": "outside Germany"})
        continue

    found = match_signal_types(p)
    if not found:
        out_of_scope.append({"source_id": p["source_id"], "title": p["title"], "reason": "no matching signal type"})
        continue

    ordered = [t for t in PRIORITY if t in found]
    signals.append({
        **p,
        "signal_type": ordered[0],
        "secondary_signal_types": ordered[1:],
        "match_reasons": found,
    })

SIGNALS_FILE.write_text(json.dumps(signals, indent=2, ensure_ascii=False), encoding="utf-8")
OUT_OF_SCOPE_FILE.write_text(json.dumps(out_of_scope, indent=2, ensure_ascii=False), encoding="utf-8")

print("Projects checked:", len(projects))
print("In scope (signals):", len(signals))
print("Out of scope:", len(out_of_scope), dict(Counter(o["reason"] for o in out_of_scope)))
print("By signal type:", dict(Counter(s["signal_type"] for s in signals)))
print("With a secondary type:", sum(1 for s in signals if s["secondary_signal_types"]))
print()
for s in signals:
    extra = f"  (+ {', '.join(s['secondary_signal_types'])})" if s["secondary_signal_types"] else ""
    print(f"  {s['signal_type']:<25} {s['title']}{extra}")