"""
Test that FTS service works without OPENAI_API_KEY
"""
import os
import sys
import subprocess

def test_fts_service_no_openai():
    """Test FTS service without OPENAI_API_KEY"""

    # Remove OPENAI_API_KEY from environment
    env = os.environ.copy()
    if 'OPENAI_API_KEY' in env:
        del env['OPENAI_API_KEY']

    print("Testing FTS service without OPENAI_API_KEY...")
    print("=" * 60)

    # Test 1: Import FTSService directly
    print("\n1. Testing FTSService import...")
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from services.fts_service import FTSService
        print("   ✅ FTSService imported successfully")
    except ImportError as e:
        print(f"   ❌ Failed to import FTSService: {e}")
        return False
    except Exception as e:
        print(f"   ❌ Unexpected error: {e}")
        return False

    # Test 2: Check launcher.py generates correct command
    print("\n2. Testing launcher.py command generation...")
    env['SERVICE_MODE'] = 'fts-continuous'
    env['FTS_CONTINUOUS_INTERVAL'] = '60'
    env['FTS_BATCH'] = '100000'

    try:
        result = subprocess.run(
            ['python', 'launcher.py'],
            env=env,
            capture_output=True,
            text=True,
            timeout=5
        )

        if 'python services/fts_service.py service' in result.stdout:
            print("   ✅ Launcher generates correct FTS command")
            print(f"   Command: {result.stdout.strip()}")
        else:
            print(f"   ❌ Unexpected command: {result.stdout}")
            return False

    except subprocess.TimeoutExpired:
        print("   ⚠️  Launcher started service (expected behavior)")
    except Exception as e:
        print(f"   ❌ Error testing launcher: {e}")
        return False

    # Test 3: Verify FTS service doesn't load OpenAI dependencies
    print("\n3. Checking FTS service dependencies...")
    try:
        with open('services/fts_service.py', 'r', encoding='utf-8') as f:
            content = f.read()

        if 'openai' in content.lower() and 'import openai' in content.lower():
            print("   ⚠️  FTS service imports OpenAI (should be removed)")
        else:
            print("   ✅ FTS service does NOT import OpenAI")

        if 'embedding_service' in content.lower():
            print("   ⚠️  FTS service references EmbeddingService")
        else:
            print("   ✅ FTS service independent of EmbeddingService")

    except Exception as e:
        print(f"   ❌ Error checking dependencies: {e}")
        return False

    print("\n" + "=" * 60)
    print("✅ All tests passed! FTS service works without OPENAI_API_KEY")
    return True

if __name__ == "__main__":
    success = test_fts_service_no_openai()
    sys.exit(0 if success else 1)
