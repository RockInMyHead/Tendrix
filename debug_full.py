
import requests
from bs4 import BeautifulSoup

def debug_search():
    url = "https://zakupki.gov.ru/epz/contract/search/results.html"
    params = {
        "searchString": "Перчатки",
        "recordsPerPage": "_1",
        "fz44": "on"
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    resp = requests.get(url, params=params, headers=headers)
    soup = BeautifulSoup(resp.text, "lxml")
    
    items = soup.select("div.search-registry-entry-block")
    if not items:
        items = soup.select("div.registry-entry")
    
    if items:
        print(items[0].prettify())
    else:
        print("No items found")

if __name__ == "__main__":
    debug_search()
