"""
Quick verification script for UCA project implementation.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from uca.db_client import UCADatabaseClient
from uca.core import UCAEngine
from uca.constants import AgentMode

def test_db_connection():
    """Test database connectivity and article retrieval."""
    print("=== Testing Database Connection ===")
    db = UCADatabaseClient()
    
    # Test 1 day
    articles_1d = db.get_recent_articles(days=1, limit=5)
    print(f"✓ Articles from last 1 day: {len(articles_1d)}")
    
    # Test 15 days
    articles_15d = db.get_recent_articles(days=15, limit=5)
    print(f"✓ Articles from last 15 days: {len(articles_15d)}")
    
    # Test 30 days
    articles_30d = db.get_recent_articles(days=30, limit=5)
    print(f"✓ Articles from last 30 days: {len(articles_30d)}")
    
    return articles_1d, articles_15d, articles_30d

def test_uca_engine():
    """Test UCA Engine initialization."""
    print("\n=== Testing UCA Engine ===")
    try:
        engine = UCAEngine(mode=AgentMode.STORE_OWNER)
        print("✓ UCAEngine initialized successfully")
        return True
    except Exception as e:
        print(f"✗ UCAEngine initialization failed: {e}")
        return False

def verify_project_structure():
    """Verify all required files exist."""
    print("\n=== Verifying Project Structure ===")
    required_files = [
        "uca/__init__.py",
        "uca/constants.py",
        "uca/schemas.py",
        "uca/config.py",
        "uca/core.py",
        "uca/db_client.py",
        "uca/llm_client.py",
        "uca/openai_client.py",
        "uca/dashboard.py",
        "uca/modules/trend_analyzer.py",
        "uca/modules/psych_engine.py",
        "uca/modules/product_gen.py",
    ]
    
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    all_exist = True
    
    for file_path in required_files:
        full_path = os.path.join(base_dir, file_path)
        exists = os.path.exists(full_path)
        status = "✓" if exists else "✗"
        print(f"{status} {file_path}")
        if not exists:
            all_exist = False
    
    return all_exist

if __name__ == "__main__":
    print("UCA PROJECT VERIFICATION")
    print("=" * 50)
    
    # 1. Verify structure
    structure_ok = verify_project_structure()
    
    # 2. Test DB
    try:
        articles_1d, articles_15d, articles_30d = test_db_connection()
        db_ok = True
    except Exception as e:
        print(f"\n✗ Database test failed: {e}")
        db_ok = False
    
    # 3. Test Engine
    engine_ok = test_uca_engine()
    
    # Summary
    print("\n" + "=" * 50)
    print("VERIFICATION SUMMARY:")
    print(f"  Project Structure: {'✓ PASS' if structure_ok else '✗ FAIL'}")
    print(f"  Database Client: {'✓ PASS' if db_ok else '✗ FAIL'}")
    print(f"  UCA Engine: {'✓ PASS' if engine_ok else '✗ FAIL'}")
    
    if structure_ok and db_ok and engine_ok:
        print("\n✓✓✓ ALL TESTS PASSED ✓✓✓")
    else:
        print("\n✗ SOME TESTS FAILED")
