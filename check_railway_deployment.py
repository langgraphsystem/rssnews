#!/usr/bin/env python3
"""Check Railway deployment status and recent logs"""

import os
import requests
import json
from datetime import datetime

RAILWAY_TOKEN = os.getenv('RAILWAY_TOKEN', '562cdf71-e227-42de-b275-66208aac85c9')
SERVICE_ID = 'eac4079c-506c-4eab-a6d2-49bd860379de'

headers = {
    'Authorization': f'Bearer {RAILWAY_TOKEN}',
    'Content-Type': 'application/json'
}

# GraphQL query to get deployment info
query = """
query getDeployments($serviceId: String!) {
  deployments(input: {serviceId: $serviceId}, first: 3) {
    edges {
      node {
        id
        status
        createdAt
        meta
        staticUrl
      }
    }
  }
}
"""

variables = {
    'serviceId': SERVICE_ID
}

print("🚂 Checking Railway deployment status...")
print(f"Service ID: {SERVICE_ID}")
print("-" * 80)

response = requests.post(
    'https://backboard.railway.app/graphql/v2',
    headers=headers,
    json={'query': query, 'variables': variables}
)

if response.status_code != 200:
    print(f"❌ API error: {response.status_code}")
    print(response.text)
    exit(1)

data = response.json()

if 'errors' in data:
    print("❌ GraphQL errors:")
    print(json.dumps(data['errors'], indent=2))
    exit(1)

deployments = data.get('data', {}).get('deployments', {}).get('edges', [])

print(f"\n📦 Last 3 deployments:\n")

for i, edge in enumerate(deployments, 1):
    node = edge['node']
    status = node['status']
    created = node['createdAt']
    meta = node.get('meta', {})

    # Parse timestamp
    dt = datetime.fromisoformat(created.replace('Z', '+00:00'))

    # Get commit info
    commit_sha = meta.get('commitSha', 'N/A')[:7]
    commit_msg = meta.get('commitMessage', 'N/A')[:60]

    status_emoji = {
        'SUCCESS': '✅',
        'FAILED': '❌',
        'BUILDING': '🔨',
        'DEPLOYING': '🚀',
        'CRASHED': '💥'
    }.get(status, '❓')

    print(f"{i}. {status_emoji} {status}")
    print(f"   Time: {dt.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"   Commit: {commit_sha} - {commit_msg}")
    print()

# Check if latest deployment is our fix
latest = deployments[0]['node'] if deployments else None
if latest:
    meta = latest.get('meta', {})
    commit_sha = meta.get('commitSha', '')
    commit_msg = meta.get('commitMessage', '')

    print("-" * 80)
    print("\n🔍 Latest deployment analysis:")

    if '1521e7a' in commit_sha:
        print("✅ Latest deployment includes LSH fix (1521e7a)")
    elif '354fdef' in commit_sha:
        print("⚠️ Latest deployment is 354fdef (before LSH fix)")
        print("   Missing: 1521e7a (LSH duplicate key fix)")
    elif '2176333' in commit_sha:
        print("⚠️ Latest deployment is 2176333 (before time filter fix)")
        print("   Missing: 354fdef (time filter) and 1521e7a (LSH fix)")
    else:
        print(f"📍 Latest commit: {commit_sha[:7]}")
        print(f"   Message: {commit_msg}")

    if latest['status'] == 'SUCCESS':
        print("\n✅ Deployment successful")
    elif latest['status'] == 'FAILED':
        print("\n❌ Deployment failed - check build logs")
    elif latest['status'] in ['BUILDING', 'DEPLOYING']:
        print("\n⏳ Deployment in progress...")
    elif latest['status'] == 'CRASHED':
        print("\n💥 Service crashed after deployment")

print("\n" + "=" * 80)
