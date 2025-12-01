import sqlite3
import requests
import sys

print("--- DIAGNOSTICS START ---")

# 1. Check DB
try:
    conn = sqlite3.connect('D:/Articles/SQLite/rag.db')
    cursor = conn.cursor()
    cursor.execute("SELECT status, COUNT(*) FROM articles GROUP BY status")
    rows = cursor.fetchall()
    print("\n📊 Database Status:")
    if not rows:
        print("   No articles found in DB!")
    for status, count in rows:
        print(f"   - {status}: {count}")
    conn.close()
except Exception as e:
    print(f"\n❌ Database Error: {e}")

# 2. Check Ollama
print("\n🤖 Checking Ollama...")
try:
    resp = requests.get('http://localhost:11434/api/tags', timeout=2)
    if resp.status_code == 200:
        models = [m['name'] for m in resp.json().get('models', [])]
        print(f"   ✅ Ollama is UP. Models: {', '.join(models)}")
    else:
        print(f"   ⚠️ Ollama returned status {resp.status_code}")
except Exception as e:
    print(f"   ❌ Ollama Connection Failed: {e}")
    print("   Make sure Ollama is running!")

print("\n--- DIAGNOSTICS END ---")
