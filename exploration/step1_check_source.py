"""Step 1 (PDF: 'confirm its current format'): what does Python see on the TenneT page?"""
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

URL = "https://www.tennet.eu/de/projekte"
USER_AGENT = "IRIS-SIG-27-harvester/0.1 (contact: akshaymalik824@gmail.com)"
HEADERS = {"User-Agent": USER_AGENT}
RAW_FILE = Path("data/raw/listing_page1.html")


def download_page():
    # Lawful access: read robots.txt with our own, honest User-Agent and follow its rules
    robots_response = requests.get("https://www.tennet.eu/robots.txt", headers=HEADERS, timeout=20)
    if robots_response.status_code != 200:
        print("Could not read robots.txt (status", robots_response.status_code, "). Not downloading.")
        return None
    robots = RobotFileParser()
    robots.parse(robots_response.text.splitlines())
    if not robots.can_fetch(USER_AGENT, URL):
        print("robots.txt does not allow this page. Do not bypass it.")
        return None
    print("robots.txt allows this page.")

    response = requests.get(URL, headers=HEADERS, timeout=20)
    print("HTTP status:", response.status_code)
    if response.status_code != 200:
        print("Download refused. Do not bypass it.")
        return None
    RAW_FILE.parent.mkdir(parents=True, exist_ok=True)
    RAW_FILE.write_text(response.text, encoding="utf-8")  # keep a copy for later steps
    return response.text


# Use a saved copy if one exists, otherwise download once
if RAW_FILE.exists():
    print("Using saved file:", RAW_FILE)
    html = RAW_FILE.read_text(encoding="utf-8")
else:
    html = download_page()
    if html is None:
        raise SystemExit("Stopped. Save the page from Safari instead.")

soup = BeautifulSoup(html, "html.parser")

# Collect every link that points to a project page
project_links = set()
for a in soup.find_all("a", href=True):
    path = urlparse(urljoin(URL, a["href"])).path.rstrip("/")
    if path.startswith("/de/projekte/"):
        project_links.add(path)

sub_pages = [p for p in project_links if p.count("/") > 3]  # e.g. /de/projekte/suedlink/...

print("Page size:", len(html), "characters")
print("Project links found:", len(project_links))
print("  of which sub-pages:", len(sub_pages))
for p in sorted(project_links)[:10]:
    print("   ", p)
print("'Zuletzt aktualisiert' in HTML:", "Zuletzt aktualisiert" in html)
print("'DolWin5' in HTML:", "DolWin5" in html)
print("Pagination-like links:", sorted({a["href"] for a in soup.find_all("a", href=True)
                                        if "page" in a["href"].lower() or "seite" in a["href"].lower()})[:6])