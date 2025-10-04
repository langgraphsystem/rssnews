#!/usr/bin/env python3
"""
Set SERVICE_MODE=bot on Railway via GraphQL API
This will make the bot start correctly
"""
import requests
import json

RAILWAY_TOKEN = "562cdf71-e227-42de-b275-66208aac85c9"
SERVICE_ID = "eac4079c-506c-4eab-a6d2-49bd860379de"

headers = {
    "Authorization": f"Bearer {RAILWAY_TOKEN}",
    "Content-Type": "application/json"
}

print("🔧 Setting SERVICE_MODE=bot on Railway")
print("=" * 80)
print()

# First, get service info to find environment ID
get_service_query = """
query {
  service(id: "%s") {
    id
    name
    project {
      id
      name
      environments {
        edges {
          node {
            id
            name
          }
        }
      }
    }
  }
}
""" % SERVICE_ID

print("1️⃣  Getting service and environment info...")
response = requests.post(
    "https://backboard.railway.app/graphql/v2",
    headers=headers,
    json={"query": get_service_query}
)

result = response.json()

if 'errors' in result:
    print(f"❌ GraphQL errors: {result['errors']}")
    print()
    print("💡 Alternative: Use Railway Dashboard or CLI")
    print("   Dashboard: https://railway.app/")
    print("   CLI: railway variables --set SERVICE_MODE=bot")
    exit(1)

if 'data' not in result or not result['data']['service']:
    print(f"❌ Failed to get service info: {result}")
    exit(1)

service = result['data']['service']
project = service['project']

print(f"✅ Service: {service['name']}")
print(f"✅ Project: {project['name']}")
print()

# Get first (production) environment
environments = project['environments']['edges']
if not environments:
    print("❌ No environments found")
    exit(1)

env = environments[0]['node']
env_id = env['id']
env_name = env['name']

print(f"📦 Environment: {env_name} ({env_id})")
print()

# Now try to set the variable
# Note: Railway's variable mutation requires specific format
set_var_mutation = """
mutation VariableUpsert($input: VariableUpsertInput!) {
  variableUpsert(input: $input)
}
"""

variable_input = {
    "environmentId": env_id,
    "serviceId": SERVICE_ID,
    "name": "SERVICE_MODE",
    "value": "bot"
}

print("2️⃣  Setting SERVICE_MODE=bot...")
print(f"   Environment: {env_id}")
print(f"   Service: {SERVICE_ID}")
print()

response = requests.post(
    "https://backboard.railway.app/graphql/v2",
    headers=headers,
    json={
        "query": set_var_mutation,
        "variables": {"input": variable_input}
    }
)

result = response.json()

if 'errors' in result:
    print(f"❌ Failed to set variable:")
    print(json.dumps(result['errors'], indent=2))
    print()
    print("💡 This might be due to API permissions.")
    print("   Please use Railway Dashboard or CLI instead:")
    print()
    print("   Dashboard:")
    print("   1. Go to https://railway.app/")
    print("   2. Navigate to your service")
    print("   3. Variables tab")
    print("   4. Add: SERVICE_MODE=bot")
    print()
    print("   CLI:")
    print("   $ railway variables --set SERVICE_MODE=bot")
else:
    print("✅ SERVICE_MODE=bot has been set!")
    print()
    print("3️⃣  Next steps:")
    print("   - Service will redeploy automatically")
    print("   - Wait ~30 seconds for deployment")
    print("   - Test bot: send /start to @rssnewsusabot")
    print()
    print("📝 Verify with:")
    print("   $ railway logs -s eac4079c-506c-4eab-a6d2-49bd860379de")
    print()
    print("   Look for:")
    print("   launcher.py -> executing: python start_telegram_bot.py")

print()
print("=" * 80)
