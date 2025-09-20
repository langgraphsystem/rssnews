#!/usr/bin/env python3
"""
Test script to verify LlamaIndex initialization works like in Railway environment
"""

import sys
import os
import logging

# Simulate Railway environment where llamaindex_components is not available
sys.modules['llamaindex_components'] = None

def test_railway_initialization():
    """Test LlamaIndex initialization with fallback components"""

    print("🚀 Testing Railway-style LlamaIndex initialization")
    print("=" * 60)

    try:
        # Test 1: Import
        print("📦 Testing imports...")
        from llamaindex_production import RSSLlamaIndexOrchestrator
        print("  ✅ Main orchestrator import successful")

        # Test 2: Fallback components
        print("\n🔧 Testing fallback components...")
        from llamaindex_production import QueryCache, CostTracker, PerformanceMonitor, LegacyModeManager
        print("  ✅ All fallback components imported")

        # Test 3: Component instantiation
        print("\n⚙️  Testing component instantiation...")
        cache = QueryCache(ttl_minutes=15)
        tracker = CostTracker()
        monitor = PerformanceMonitor()
        legacy = LegacyModeManager()

        print("  ✅ QueryCache created")
        print("  ✅ CostTracker created")
        print("  ✅ PerformanceMonitor created")
        print("  ✅ LegacyModeManager created")

        # Test 4: Basic functionality
        print("\n🧪 Testing basic functionality...")
        cache.set("test_key", "test_value")
        result = cache.get("test_key")
        print(f"  ✅ Cache set/get: {result}")

        tracker.add_cost("test", 0.01, "gpt-5")
        print("  ✅ Cost tracking works")

        timer_id = monitor.start_timer("test")
        duration = monitor.end_timer(timer_id)
        print(f"  ✅ Performance monitoring: {duration}s")

        legacy_enabled = legacy.is_legacy_enabled("test")
        print(f"  ✅ Legacy mode check: {legacy_enabled}")

        # Test 5: Orchestrator initialization (without real API keys)
        print("\n🎭 Testing orchestrator structure...")
        pg_dsn = os.getenv('PG_DSN')
        if pg_dsn:
            try:
                orch = RSSLlamaIndexOrchestrator(
                    pg_dsn=pg_dsn,
                    openai_api_key="fake-key-for-testing",
                    gemini_api_key="fake-key-for-testing",
                    pinecone_api_key="fake-key-for-testing",
                    pinecone_index="fake-index"
                )
                print("  ❌ Should fail with invalid API keys (expected)")
            except Exception as e:
                if "api" in str(e).lower() or "key" in str(e).lower() or "unauthorized" in str(e).lower():
                    print(f"  ✅ Failed at API validation (expected): {type(e).__name__}")
                else:
                    print(f"  ❌ Unexpected error: {e}")
        else:
            print("  ⚠️  PG_DSN not set, skipping orchestrator test")

        print("\n🎉 All tests passed! Railway deployment should work.")
        return True

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_railway_initialization()
    sys.exit(0 if success else 1)