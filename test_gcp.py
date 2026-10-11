import requests
import json

def test_gcp():
    url = "https://orivanta-87056410261.europe-west1.run.app/api/v1/search/stream"
    payload = {
        "query": "hello",
        "focus_mode": "all",
        "messages": []
    }
    
    print(f"Calling {url}...")
    try:
        response = requests.post(url, json=payload, stream=True, timeout=30)
        print(f"Status Code: {response.status_code}")
        if response.status_code != 200:
            print(f"Error Response: {response.text}")
            return
            
        for line in response.iter_lines():
            if line:
                decoded = line.decode('utf-8')
                print(f"LINE: {decoded}")
                if "done" in decoded.lower():
                    break
    except Exception as e:
        print(f"FAILED: {e}")

if __name__ == "__main__":
    test_gcp()
