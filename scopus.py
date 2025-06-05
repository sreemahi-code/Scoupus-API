import requests

scopus_id = "7004212771"
url = f"https://api.elsevier.com/content/search/scopus?query=AU-ID({scopus_id})&count=25"
headers = {
    "X-ELS-APIKey": "5a030f90b2416e25e48be43a59a23bba",
    "Accept": "application/json"
}

journal_set = set()
start = 0

while True:
    paged_url = url + f"&start={start}"
    res = requests.get(paged_url, headers=headers)
    data = res.json()
    
    entries = data.get("search-results", {}).get("entry", [])
    if not entries:
        break

    for entry in entries:
        journal = entry.get("prism:publicationName")
        if journal:
            journal_set.add(journal)

    start += 25

print("Unique journals published by author:")
for j in sorted(journal_set):
    print(j)
