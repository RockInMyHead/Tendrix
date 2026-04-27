
import requests
from bs4 import BeautifulSoup

def debug_search():
    url = "https://zakupki.gov.ru/epz/contract/search/results.html"
    params = {
        "searchString": "Перчатки смотровые/процедурные нитриловые",
        "morphology": "on",
        "fz44": "on",
        "fz223": "on",
        "recordsPerPage": "_10"
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    print(f"Fetching {url}...")
    resp = requests.get(url, params=params, headers=headers)
    resp.raise_for_status()
    
    soup = BeautifulSoup(resp.text, "lxml")
    
    items = soup.select("div.search-registry-entry-block")
    if not items:
        items = soup.select("div.registry-entry")
        
    print(f"Found {len(items)} items.")
    
    for i, item in enumerate(items[:2]):
        print(f"\n--- Item {i+1} ---")
        
        # Header Top
        header_top = item.select_one("div.registry-entry__header-top")
        if header_top:
            print(f"Header Top HTML: {header_top.prettify()[:500]}...")
            print(f"Header Top Text: {header_top.get_text(strip=True)}")
            
        # Try to find region specific classes
        titles = item.select("div.registry-entry__header-top__title")
        for t in titles:
             print(f"Top Title found: '{t.get_text(strip=True)}'")

        icons = item.select("div.registry-entry__header-top__icon")
        for ic in icons:
             print(f"Top Icon found: '{ic.get_text(strip=True)}'")
             
        # Customer Block
        customer_block = None
        for block in item.select("div.registry-entry__body-block"):
            title = block.select_one("div.registry-entry__body-title")
            if title and "Заказчик" in title.get_text():
                 print(f"Customer Block: {block.get_text(strip=True)[:200]}")

if __name__ == "__main__":
    debug_search()
