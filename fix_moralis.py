import os
import requests
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("MORALIS_API_KEY")
headers = {"X-API-Key": API_KEY, "Content-Type": "application/json"}

# Get all streams
resp = requests.get("https://api.moralis-streams.com/streams/evm?limit=100", headers=headers)
if resp.status_code != 200:
    print(f"Error fetching streams: {resp.text}")
    exit(1)

streams = resp.json().get("result", [])
print(f"Found {len(streams)} streams.")

for s in streams:
    status = s.get("status")
    print(f"Stream {s['id']} ({s.get('tag')}): {status}")
    if status == "error":
        print(f"Reactivating {s['id']}...")
        r = requests.post(f"https://api.moralis-streams.com/streams/evm/{s['id']}/status", headers=headers, json={"status": "active"})
        if r.status_code == 200:
            print("Successfully reactivated!")
        else:
            print(f"Failed: {r.text}")
