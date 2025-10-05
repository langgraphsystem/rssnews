#!/usr/bin/env python3
"""Check Railway environment variables via API.

Reads credentials from environment variables to avoid hardcoding secrets.

Required env vars:
- RAILWAY_TOKEN
- RAILWAY_SERVICE_ID (defaults to provided ID if missing)
"""
import os
import sys
import requests

RAILWAY_TOKEN = os.getenv("RAILWAY_TOKEN")
SERVICE_ID = os.getenv("RAILWAY_SERVICE_ID", "ffe65f79-4dc5-4757-b772-5a99c7ea624f")

if not RAILWAY_TOKEN:
    print("Error: RAILWAY_TOKEN is not set in environment.")
    sys.exit(1)

headers = {
    "Authorization": f"Bearer {RAILWAY_TOKEN}",
    "Content-Type": "application/json"
}

# Get service variables
query = """
query($serviceId: String!) {
  variables(serviceId: $serviceId) {
    edges {
      node {
        name
        value
      }
    }
  }
}
"""

response = requests.post(
    "https://backboard.railway.app/graphql/v2",
    headers=headers,
    json={
        "query": query,
        "variables": {"serviceId": SERVICE_ID}
    }
)

print("📋 Railway Environment Variables:")
result = response.json()

if 'data' in result and 'variables' in result['data']:
    vars_list = result['data']['variables']['edges']

    # Filter sensitive keys
    for var in vars_list:
        name = var['node']['name']
        value = var['node']['value']

        if name in ['OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'GEMINI_API_KEY']:
            # Show only first/last 10 chars
            if value and len(value) > 20:
                masked = value[:10] + "..." + value[-10:]
            else:
                masked = "***"
            print(f"  {name}: {masked}")
        elif 'TOKEN' in name or 'KEY' in name or 'SECRET' in name or 'PASSWORD' in name:
            print(f"  {name}: ***")
        else:
            print(f"  {name}: {value}")
else:
    print("Error:", result)
