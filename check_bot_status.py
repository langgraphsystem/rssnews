#!/usr/bin/env python3
"""Check Railway bot deployment status via API"""
import os
import requests
from dotenv import load_dotenv

load_dotenv()

RAILWAY_TOKEN = "562cdf71-e227-42de-b275-66208aac85c9"
SERVICE_ID = "eac4079c-506c-4eab-a6d2-49bd860379de"

headers = {
    "Authorization": f"Bearer {RAILWAY_TOKEN}",
    "Content-Type": "application/json"
}

# Get deployment info via GraphQL
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
          url
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

print("📊 Railway Service Status:")
print(response.json())
