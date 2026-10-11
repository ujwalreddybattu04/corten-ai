import requests
import json

def test_stream():
    url = "http://localhost:8000/api/v1/search/stream"
    payload = {
        "query": "What is deep learning?",
        "focus_mode": "all",
        "messages": []
    }
    
    print(f"Calling {url}...")
    try:
        response = requests.post(url, json=payload, stream=True)
        response.raise_for_status()
        
        for line in response.iter_lines():
            if line:
                decoded_line = line.decode('utf-8')
                print(f"RAW: {decoded_line}")
                if decoded_line.startswith("data: "):
                    data_str = decoded_line[6:]
                    if data_str == "[DONE]":
                        print("STREAM DONE")
                        break
                    try:
                        data = json.loads(data_str)
                        if data.get("type") == "sources":
                            print(f"SUCCESS: Received {len(data.get('sources', []))} sources")
                    except:
                        pass
    except Exception as e:
        print(f"FAILED: {e}")

if __name__ == "__main__":
    test_stream()
