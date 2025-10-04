#!/usr/bin/env python3
"""Update Railway environment variables via GraphQL API"""
import os
import requests
from dotenv import load_dotenv

load_dotenv()

# Get from environment or set manually
RAILWAY_TOKEN = os.getenv("RAILWAY_TOKEN", "<your-railway-token>")
SERVICE_ID = os.getenv("RAILWAY_SERVICE_ID", "eac4079c-506c-4eab-a6d2-49bd860379de")

headers = {
    "Authorization": f"Bearer {RAILWAY_TOKEN}",
    "Content-Type": "application/json"
}

# Variables to update/add
VARS_TO_UPDATE = {
    "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", "<use key from .env>"),
    "USE_SIMPLE_SEARCH": "true"
}

print("📝 Updating Railway environment variables...")
print()

# First, get project and environment info
get_service_query = """
query {
  service(id: "%s") {
    id
    name
    projectId
  }
}
""" % SERVICE_ID

response = requests.post(
    "https://backboard.railway.app/graphql/v2",
    headers=headers,
    json={"query": get_service_query}
)

print("Service info:", response.json())

# Note: Railway GraphQL API for setting variables requires specific environment and project IDs
# The CLI command is simpler but requires interactive login
print()
print("⚠️  Note: Railway GraphQL API requires project/environment IDs")
print("   Recommended approach: Use Railway CLI")
print()
print("Run these commands manually:")
for key, value in VARS_TO_UPDATE.items():
    if 'KEY' in key or 'SECRET' in key or 'TOKEN' in key:
        masked_value = value[:15] + "..." + value[-10:] if len(value) > 25 else "***"
        print(f'railway variables --set {key}="***masked***"')
    else:
        print(f'railway variables --set {key}="{value}"')
