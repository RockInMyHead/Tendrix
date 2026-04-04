
import requests

def debug_api():
    base_url = "http://localhost:8080"
    
    # 1. Register
    reg_data = {"username": "debug_user_99", "password": "password123"}
    try:
        requests.post(f"{base_url}/register", json=reg_data)
    except:
        pass # maybe already exists

    # 2. Login
    login_data = {"username": "debug_user_99", "password": "password123"}
    resp = requests.post(f"{base_url}/token", data=login_data)
    if resp.status_code != 200:
        print(f"Login failed: {resp.text}")
        return
    
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # 3. Search
    params = {
        "law_44": "true",
        "law_223": "false",
        "page": "1",
        "records_per_page": "50"
    }
    
    print("\n--- Testing Search ---")
    resp = requests.get(f"{base_url}/api/search", headers=headers, params=params)
    print(f"Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print(f"Count: {data.get('count')}")
        print(f"Total: {data.get('total')}")
        if data.get('data'):
            print(f"First item: {data['data'][0]['number']}")
    else:
        print(resp.text)

if __name__ == "__main__":
    debug_api()
