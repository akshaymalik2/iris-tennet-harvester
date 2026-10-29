import requests

r = requests.get(
    "https://www.tennet.eu/robots.txt",
    headers={"User-Agent": "IRIS-SIG-27-harvester/0.1 (contact: akshaymalik824@gmail.com)"},
    timeout=20,
)
print("Status:", r.status_code)
print(r.text[:1500])