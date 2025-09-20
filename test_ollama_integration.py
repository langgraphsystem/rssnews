"""
Test script for Ollama Gemma3 integration via CloudFlare tunnel.
"""

import asyncio
import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_ollama_health():
    """Test Ollama health check."""
    try:
        from stage6_hybrid_chunking.src.llm.ollama_client import OllamaGemma3Client

        async with OllamaGemma3Client(
            base_url="http://localhost:11434",
            model="gemma3:latest"
        ) as client:
            print("🔍 Testing Ollama health check...")
            health = await client.health_check()
            print(f"Health status: {health}")

            if health['status'] == 'healthy':
                print("✅ Ollama server is accessible!")
                print(f"Available models: {health.get('available_models', [])}")
                print(f"Target model available: {health.get('target_model_available', False)}")
                return True
            else:
                print(f"❌ Ollama server not healthy: {health.get('error', 'Unknown error')}")
                return False

    except Exception as e:
        print(f"❌ Failed to connect to Ollama: {e}")
        return False

async def test_ollama_generation():
    """Test Ollama text generation."""
    try:
        from stage6_hybrid_chunking.src.llm.ollama_client import OllamaGemma3Client

        async with OllamaGemma3Client(
            base_url="http://localhost:11434",
            model="gemma3:latest"
        ) as client:
            print("🔍 Testing Ollama text generation...")

            test_prompt = "Analyze this text chunk and suggest an action: 'This is a short test chunk about technology news.'"

            response, metadata = await client._make_request(
                prompt=test_prompt,
                max_tokens=100,
                temperature=0.3
            )

            print(f"✅ Generation successful!")
            print(f"Response: {response[:200]}...")
            print(f"Metadata: {metadata}")
            return True

    except Exception as e:
        print(f"❌ Failed to generate text: {e}")
        return False

async def test_chunk_refinement():
    """Test chunk refinement functionality."""
    try:
        from stage6_hybrid_chunking.src.llm.ollama_client import OllamaGemma3Client

        async with OllamaGemma3Client(
            base_url="http://localhost:11434",
            model="gemma3:latest"
        ) as client:
            print("🔍 Testing chunk refinement...")

            chunk_data = {
                'chunk_index': 0,
                'text': 'This is a test article chunk about technology. It contains important information about AI developments.',
                'char_start': 0,
                'char_end': 100,
                'semantic_type': 'body',
                'word_count': 17
            }

            article_metadata = {
                'title': 'Test Article',
                'source_domain': 'example.com',
                'language': 'en',
                'published_at': '2025-01-20',
                'target_words': 400,
                'max_offset': 120
            }

            action, reason, metadata = await client.refine_chunk_boundaries(
                chunk_data=chunk_data,
                article_metadata=article_metadata
            )

            print(f"✅ Chunk refinement successful!")
            print(f"Action: {action}")
            print(f"Reason: {reason}")
            print(f"Metadata: {metadata}")
            return True

    except Exception as e:
        print(f"❌ Failed chunk refinement: {e}")
        return False

async def main():
    """Run all tests."""
    print("🚀 Testing Ollama Gemma3 integration via CloudFlare tunnel")
    print("=" * 60)

    tests = [
        ("Health Check", test_ollama_health),
        ("Text Generation", test_ollama_generation),
        ("Chunk Refinement", test_chunk_refinement)
    ]

    results = []
    for test_name, test_func in tests:
        print(f"\n📋 Running test: {test_name}")
        print("-" * 40)
        try:
            result = await test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ Test failed with exception: {e}")
            results.append((test_name, False))

    print("\n📊 Test Results:")
    print("=" * 60)
    for test_name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{test_name}: {status}")

    passed = sum(1 for _, success in results if success)
    total = len(results)
    print(f"\nSummary: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All tests passed! Ollama integration is working correctly.")
    else:
        print("⚠️  Some tests failed. Please check the configuration.")

if __name__ == "__main__":
    asyncio.run(main())