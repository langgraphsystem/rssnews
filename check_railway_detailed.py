#!/usr/bin/env python3
"""Get detailed Railway service information including logs.

Reads credentials from environment variables to avoid hardcoding secrets.

Required env vars:
- RAILWAY_TOKEN
- RAILWAY_SERVICE_ID (defaults to provided ID if missing)
"""
import os
import requests
import json
from datetime import datetime

RAILWAY_TOKEN = os.getenv("RAILWAY_TOKEN")
SERVICE_ID = os.getenv("RAILWAY_SERVICE_ID", "ffe65f79-4dc5-4757-b772-5a99c7ea624f")

if not RAILWAY_TOKEN:
    print("Error: RAILWAY_TOKEN is not set in environment.")
    raise SystemExit(1)

headers = {
    "Authorization": f"Bearer {RAILWAY_TOKEN}",
    "Content-Type": "application/json"
}

print("=" * 80)
print("🔍 Detailed Railway Service Check")
print("=" * 80)
print()

# Get comprehensive service info
query = """
query {
  service(id: "%s") {
    id
    name
    createdAt
    deployments(first: 3) {
      edges {
        node {
          id
          status
          createdAt
          meta
        }
      }
    }
  }
}
""" % SERVICE_ID

print("1️⃣  Fetching service info...")
response = requests.post(
    "https://backboard.railway.app/graphql/v2",
    headers=headers,
    json={"query": query}
)

result = response.json()

if 'errors' in result:
    print(f"❌ GraphQL errors: {result['errors']}")
else:
    service = result['data']['service']
    print(f"✅ Service: {service['name']}")
    print(f"   ID: {service['id']}")
    print(f"   Created: {service['createdAt']}")
    print()

    print("📦 Recent Deployments:")
    for i, edge in enumerate(service['deployments']['edges'], 1):
        deploy = edge['node']
        created = datetime.fromisoformat(deploy['createdAt'].replace('Z', '+00:00'))
        print(f"\n   {i}. Deployment {deploy['id'][:8]}...")
        print(f"      Status: {deploy['status']}")
        print(f"      Created: {created.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        if deploy.get('meta'):
            print(f"      Meta: {deploy['meta']}")

print()
print("2️⃣  Checking current environment variables...")

# Try to get variables (might not work without proper permissions)
vars_query = """
query {
  service(id: "%s") {
    id
    name
  }
}
""" % SERVICE_ID

response = requests.post(
    "https://backboard.railway.app/graphql/v2",
    headers=headers,
    json={"query": vars_query}
)

print("   Note: Variable listing requires additional GraphQL query")
print("   Please check Railway Dashboard → Variables tab")
print()

print("3️⃣  Expected variables (verify in Dashboard):")
print("   ✅ SERVICE_MODE=bot")
print("   ✅ TELEGRAM_BOT_TOKEN=<set>")
print("   ✅ PG_DSN=<set>")
print("   ✅ OPENAI_API_KEY=<set>")
print("   ⭐ USE_SIMPLE_SEARCH=true")
print()

print("=" * 80)
print("💡 Next Steps:")
print("=" * 80)
print()
print("If SERVICE_MODE=bot is set but bot still not working:")
print()
print("1. Check Railway Dashboard → Deployments → Latest → View Logs")
print("   Look for:")
print("   - 'launcher.py -> executing: python start_telegram_bot.py'")
print("   - Any error messages during startup")
print()
print("2. Common issues:")
print("   - Invalid OPENAI_API_KEY → bot crashes on startup")
print("   - Database connection error → check PG_DSN")
print("   - Missing dependencies → check requirements.txt")
print()
print("3. Try manual redeploy:")
print("   - Railway Dashboard → Deployments → Redeploy")
print()
