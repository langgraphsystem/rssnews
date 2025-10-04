#!/usr/bin/env python3
"""Test OpenAI API key validity"""
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# Test keys from .env
# Add your OpenAI API keys here for testing
KEYS_TO_TEST = [
    ("Key from .env", os.getenv("OPENAI_API_KEY", "")),
    # Add more keys to test if needed
]

print("🔑 Testing OpenAI API Keys")
print("=" * 80)
print()

for name, api_key in KEYS_TO_TEST:
    print(f"Testing: {name}")
    print(f"  Key: {api_key[:20]}...{api_key[-10:]}")

    try:
        client = OpenAI(api_key=api_key)

        # Try to create an embedding
        response = client.embeddings.create(
            model="text-embedding-3-large",
            input="Test query"
        )

        if response.data and len(response.data) > 0:
            embedding_dim = len(response.data[0].embedding)
            print(f"  ✅ VALID - Generated {embedding_dim}-dim embedding")
            print(f"  💡 Use this key!")
            print()
            print(f"Update .env with:")
            print(f"OPENAI_API_KEY={api_key}")
            break
        else:
            print(f"  ❌ Invalid response")

    except Exception as e:
        error_msg = str(e)
        if "401" in error_msg or "Incorrect API key" in error_msg:
            print(f"  ❌ INVALID - Authentication failed")
        elif "429" in error_msg:
            print(f"  ⚠️  Rate limited (key might be valid)")
        else:
            print(f"  ❌ Error: {error_msg[:100]}")

    print()
