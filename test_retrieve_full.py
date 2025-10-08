#!/usr/bin/env python3
"""Full validation test for /retrieve API endpoint"""

import requests
import json
from datetime import datetime

# API endpoint
url = "https://rssnews-production-eaa2.up.railway.app/retrieve"

def test_basic_search():
    """Test 1: Basic search"""
    print("=" * 80)
    print("TEST 1: Basic search")
    print("=" * 80)

    payload = {
        "query": "artificial intelligence",
        "hours": 24,
        "k": 5
    }

    print(f"Request: {json.dumps(payload, indent=2)}")

    try:
        response = requests.post(url, json=payload, timeout=30)
        print(f"\nStatus Code: {response.status_code}")

        if response.status_code == 200:
            data = response.json()

            # Validate response structure
            print("\n✅ Response structure validation:")

            required_keys = ['items', 'next_cursor', 'total_available', 'coverage', 'freshness_stats', 'diagnostics']
            for key in required_keys:
                if key in data:
                    print(f"  ✅ '{key}' present")
                else:
                    print(f"  ❌ '{key}' MISSING")

            # Validate items structure
            if data.get('items'):
                print(f"\n✅ Items found: {len(data['items'])}")
                print("\n  First item structure:")
                first_item = data['items'][0]
                item_keys = ['title', 'url', 'source_domain', 'published_at', 'snippet', 'relevance_score']
                for key in item_keys:
                    value = first_item.get(key)
                    if key in first_item:
                        print(f"    ✅ {key}: {str(value)[:60]}...")
                    else:
                        print(f"    ❌ {key}: MISSING")
            else:
                print("\n⚠️  No items returned")

            # Validate metrics
            print("\n✅ Metrics:")
            print(f"  - Total available: {data.get('total_available')}")
            print(f"  - Coverage: {data.get('coverage')}")
            print(f"  - Freshness median: {data.get('freshness_stats', {}).get('median_age_seconds')}s")
            print(f"  - Next cursor: {data.get('next_cursor')}")

            # Validate diagnostics
            diag = data.get('diagnostics', {})
            print("\n✅ Diagnostics:")
            print(f"  - Total results: {diag.get('total_results')}")
            print(f"  - Offset: {diag.get('offset')}")
            print(f"  - Returned: {diag.get('returned')}")
            print(f"  - Has more: {diag.get('has_more')}")
            print(f"  - Window: {diag.get('window')}")

            return data
        else:
            print(f"\n❌ Error response:")
            print(json.dumps(response.json(), indent=2))
            return None

    except Exception as e:
        print(f"\n❌ Exception: {e}")
        return None


def test_with_filters():
    """Test 2: Search with filters"""
    print("\n" + "=" * 80)
    print("TEST 2: Search with filters (sources)")
    print("=" * 80)

    payload = {
        "query": "technology",
        "hours": 48,
        "k": 10,
        "filters": {
            "sources": ["theguardian.com", "reuters.com"],
            "lang": "en"
        },
        "correlation_id": "test-filters-001"
    }

    print(f"Request: {json.dumps(payload, indent=2)}")

    try:
        response = requests.post(url, json=payload, timeout=30)
        print(f"\nStatus Code: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print(f"\n✅ Results: {len(data.get('items', []))} items")
            print(f"✅ Coverage: {data.get('coverage')}")
            print(f"✅ Window: {data.get('diagnostics', {}).get('window')}")

            # Check if sources are filtered
            if data.get('items'):
                sources = set(item['source_domain'] for item in data['items'])
                print(f"\n✅ Unique sources in results: {sources}")

            return data
        else:
            print(f"\n❌ Error: {response.json()}")
            return None

    except Exception as e:
        print(f"\n❌ Exception: {e}")
        return None


def test_pagination():
    """Test 3: Pagination with cursor"""
    print("\n" + "=" * 80)
    print("TEST 3: Pagination test")
    print("=" * 80)

    # First request
    payload1 = {
        "query": "news",
        "hours": 24,
        "k": 3
    }

    print(f"Request 1 (initial): {json.dumps(payload1, indent=2)}")

    try:
        response1 = requests.post(url, json=payload1, timeout=30)
        if response1.status_code == 200:
            data1 = response1.json()
            print(f"\n✅ Page 1: {len(data1.get('items', []))} items")
            print(f"✅ Total available: {data1.get('total_available')}")

            cursor = data1.get('next_cursor')
            if cursor:
                print(f"✅ Next cursor: {cursor[:30]}...")

                # Second request with cursor
                payload2 = {
                    "query": "news",
                    "hours": 24,
                    "k": 3,
                    "cursor": cursor
                }

                print(f"\nRequest 2 (with cursor):")
                response2 = requests.post(url, json=payload2, timeout=30)

                if response2.status_code == 200:
                    data2 = response2.json()
                    print(f"✅ Page 2: {len(data2.get('items', []))} items")
                    print(f"✅ Offset in diagnostics: {data2.get('diagnostics', {}).get('offset')}")

                    # Verify different articles
                    if data1.get('items') and data2.get('items'):
                        urls1 = {item['url'] for item in data1['items']}
                        urls2 = {item['url'] for item in data2['items']}
                        overlap = urls1 & urls2

                        if not overlap:
                            print("✅ Pagination works: No duplicate articles between pages")
                        else:
                            print(f"⚠️  Found {len(overlap)} duplicate articles")

                    return data2
            else:
                print("⚠️  No next cursor (fewer results than requested)")
                return None
        else:
            print(f"❌ Error: {response1.json()}")
            return None

    except Exception as e:
        print(f"❌ Exception: {e}")
        return None


def test_edge_cases():
    """Test 4: Edge cases"""
    print("\n" + "=" * 80)
    print("TEST 4: Edge cases")
    print("=" * 80)

    # Test 4.1: Large k
    print("\n4.1: Large k value (k=50)")
    payload = {"query": "news", "hours": 72, "k": 50}
    response = requests.post(url, json=payload, timeout=30)
    if response.status_code == 200:
        data = response.json()
        print(f"  ✅ Returned: {len(data.get('items', []))} items")
        print(f"  ✅ Coverage: {data.get('coverage')}")
    else:
        print(f"  ❌ Failed: {response.status_code}")

    # Test 4.2: Empty query (should still work)
    print("\n4.2: Empty query")
    payload = {"query": "", "hours": 24, "k": 5}
    response = requests.post(url, json=payload, timeout=30)
    print(f"  Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"  ✅ Returned: {len(data.get('items', []))} items")
    else:
        print(f"  ⚠️  Error (expected): {response.json().get('error', {}).get('error_code')}")

    # Test 4.3: Very specific query (likely no results)
    print("\n4.3: Very specific query (likely no results)")
    payload = {"query": "xyzabc123nonexistent", "hours": 24, "k": 5}
    response = requests.post(url, json=payload, timeout=30)
    if response.status_code == 200:
        data = response.json()
        print(f"  ✅ Returned: {len(data.get('items', []))} items")
        if len(data.get('items', [])) == 0:
            print("  ✅ Correctly returned empty results (not error)")
    else:
        print(f"  ❌ Unexpected error: {response.status_code}")


def test_health_endpoint():
    """Test 5: Health endpoint"""
    print("\n" + "=" * 80)
    print("TEST 5: Health endpoint")
    print("=" * 80)

    health_url = "https://rssnews-production-eaa2.up.railway.app/health"

    try:
        response = requests.get(health_url, timeout=10)
        print(f"Status Code: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print(f"\n✅ Health check response:")
            print(json.dumps(data, indent=2))
        else:
            print(f"❌ Unhealthy: {response.json()}")

    except Exception as e:
        print(f"❌ Exception: {e}")


def main():
    print("\n" + "=" * 80)
    print("FULL VALIDATION TEST FOR /retrieve API")
    print("=" * 80)
    print(f"Timestamp: {datetime.utcnow().isoformat()}")
    print(f"Target URL: {url}")
    print()

    # Run all tests
    test_health_endpoint()
    test_basic_search()
    test_with_filters()
    test_pagination()
    test_edge_cases()

    print("\n" + "=" * 80)
    print("TESTS COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
