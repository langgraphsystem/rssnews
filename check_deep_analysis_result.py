"""
Check Deep Analysis Result
Fetches and displays the most recent deep analysis result from the database.
"""
import sqlite3
import json
from pprint import pprint

DB_PATH = r"D:\Articles\SQLite\rag.db"

def check_result():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Get the most recently analyzed article
        cursor.execute("""
            SELECT id, title, deep_analysis_result, deep_analysis_at 
            FROM articles 
            WHERE deep_analysis_status = 'processed' 
            ORDER BY deep_analysis_at DESC 
            LIMIT 1
        """)
        
        row = cursor.fetchone()
        
        if row:
            article_id, title, result_json, analyzed_at = row
            print("=" * 80)
            print(f"📄 Article ID: {article_id}")
            print(f"📌 Title: {title}")
            print(f"🕒 Analyzed At: {analyzed_at}")
            print("=" * 80)
            
            if result_json:
                try:
                    result = json.loads(result_json)
                    print("\n📊 Deep Analysis Result (llama3.1:8b):")
                    print("-" * 40)
                    print(json.dumps(result, indent=2, ensure_ascii=False))
                except json.JSONDecodeError:
                    print("❌ Error decoding JSON result")
                    print(result_json)
            else:
                print("⚠️ No result data found")
        else:
            print("❌ No processed articles found with Deep Analysis")
            
        conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    check_result()
