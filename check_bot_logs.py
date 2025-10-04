#!/usr/bin/env python3
"""Check Railway bot logs via API"""
import requests
import json

RAILWAY_TOKEN = "562cdf71-e227-42de-b275-66208aac85c9"
SERVICE_ID = "eac4079c-506c-4eab-a6d2-49bd860379de"

headers = {
    "Authorization": f"Bearer {RAILWAY_TOKEN}",
    "Content-Type": "application/json"
}

# Get recent deployment logs
query = """
query {
  service(id: "%s") {
    id
    name
    deployments(first: 1) {
      edges {
        node {
          id
          status
          createdAt
          staticUrl
        }
      }
    }
  }
}
""" % SERVICE_ID

response = requests.post(
    "https://backboard.railway.app/graphql/v2",
    headers=headers,
    json={"query": query}
)

result = response.json()
print("📊 Railway Deployment Status:")
print(json.dumps(result, indent=2))

if 'data' in result and result['data']['service']:
    service = result['data']['service']
    print(f"\n🤖 Service: {service['name']}")

    if service['deployments']['edges']:
        deployment = service['deployments']['edges'][0]['node']
        print(f"📦 Latest deployment:")
        print(f"  ID: {deployment['id']}")
        print(f"  Status: {deployment['status']}")
        print(f"  Created: {deployment['createdAt']}")
        print(f"  URL: {deployment.get('staticUrl', 'N/A')}")
