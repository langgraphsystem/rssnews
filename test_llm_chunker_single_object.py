"""
Test LLM chunker's ability to parse single chunk objects
"""
import sys
import asyncio
from local_llm_chunker import LocalLLMChunker

def test_single_chunk_parsing():
    """Test parsing of single chunk object format"""

    chunker = LocalLLMChunker()

    # Test case 1: Single chunk object (the problematic format from logs)
    response1 = '''{
        "text": "FICO to include buy now, pay later data in new credit score models | Fox Business",
        "topic": "Article Title",
        "type": "intro"
    }'''

    original_text = "FICO to include buy now, pay later data in new credit score models | Fox Business"

    print("Test 1: Single chunk object format")
    print("=" * 60)
    try:
        chunks = chunker._parse_chunks_response(response1, original_text)
        print(f"✅ Parsed successfully: {len(chunks)} chunk(s)")
        if chunks:
            print(f"   Text: {chunks[0]['text'][:80]}...")
            print(f"   Topic: {chunks[0].get('llm_topic', 'N/A')}")
            print(f"   Type: {chunks[0].get('semantic_type', 'N/A')}")
    except Exception as e:
        print(f"❌ Failed: {e}")
        return False

    # Test case 2: Array format (should still work)
    response2 = '''[
        {
            "text": "First chunk text here",
            "topic": "Introduction",
            "type": "intro"
        },
        {
            "text": "Second chunk text here",
            "topic": "Main Content",
            "type": "body"
        }
    ]'''

    original_text2 = "First chunk text here Second chunk text here"

    print("\nTest 2: Array format (existing behavior)")
    print("=" * 60)
    try:
        chunks = chunker._parse_chunks_response(response2, original_text2)
        print(f"✅ Parsed successfully: {len(chunks)} chunk(s)")
        for i, chunk in enumerate(chunks):
            print(f"   Chunk {i+1}: {chunk['text'][:50]}...")
    except Exception as e:
        print(f"❌ Failed: {e}")
        return False

    # Test case 3: Object with chunks key (should still work)
    response3 = '''{
        "chunks": [
            {
                "text": "Chunk one",
                "topic": "Topic 1",
                "type": "intro"
            },
            {
                "text": "Chunk two",
                "topic": "Topic 2",
                "type": "body"
            }
        ]
    }'''

    original_text3 = "Chunk one Chunk two"

    print("\nTest 3: Object with chunks key (existing behavior)")
    print("=" * 60)
    try:
        chunks = chunker._parse_chunks_response(response3, original_text3)
        print(f"✅ Parsed successfully: {len(chunks)} chunk(s)")
        for i, chunk in enumerate(chunks):
            print(f"   Chunk {i+1}: {chunk['text'][:50]}...")
    except Exception as e:
        print(f"❌ Failed: {e}")
        return False

    # Test case 4: Short text (from logs)
    response4 = '''{
        "text": "Scientists link gene to emergence of spoken language | Fox News",
        "topic": "News Headline",
        "type": "intro"
    }'''

    original_text4 = "Scientists link gene to emergence of spoken language | Fox News"

    print("\nTest 4: Short headline (real example from logs)")
    print("=" * 60)
    try:
        chunks = chunker._parse_chunks_response(response4, original_text4)
        print(f"✅ Parsed successfully: {len(chunks)} chunk(s)")
        if chunks:
            print(f"   Text: {chunks[0]['text']}")
            print(f"   Topic: {chunks[0].get('llm_topic', 'N/A')}")
            print(f"   Type: {chunks[0].get('semantic_type', 'N/A')}")
    except Exception as e:
        print(f"❌ Failed: {e}")
        return False

    print("\n" + "=" * 60)
    print("✅ All tests passed!")
    print("=" * 60)
    return True

if __name__ == "__main__":
    success = test_single_chunk_parsing()
    sys.exit(0 if success else 1)
