#!/usr/bin/env python3
"""Test /retrieve API endpoint"""

import requests
import json

# API endpoint
url = "https://rssnews-production-eaa2.up.railway.app/retrieve"

# Test request
payload = {
    "query": "artificial intelligence",
    "hours": 24,
    "k": 3
}

print(f"Testing {url}")
print(f"Payload: {json.dumps(payload, indent=2)}")
print()

try:
    response = requests.post(url, json=payload, timeout=30)
    print(f"Status Code: {response.status_code}")
    print(f"Response:")
    print(json.dumps(response.json(), indent=2))
except Exception as e:
    print(f"Error: {e}")
    print(f"Response text: {response.text if 'response' in locals() else 'N/A'}")
