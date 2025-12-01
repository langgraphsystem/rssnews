import sqlite3
import json
import sys
import config

def show_result(article_id):
    cfg = config.load_config()
    db_path = cfg['analysis_db_path']
    
    try:
        conn = sqlite3.connect(db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM analysis_articles WHERE id = ?", (article_id,))
        row = cursor.fetchone()
        
        if not row:
            print(f"❌ Article {article_id} not found in {db_path}")
            return

        print(f"📄 Article ID: {row['id']}")
        print(f"Title: {row['title']}")
        print(f"Status: {row['deep_analysis_status']}")
        print("-" * 50)
        
        result_json = row['deep_analysis_result']
        if result_json:
            try:
                data = json.loads(result_json)
                print(json.dumps(data, indent=2, ensure_ascii=False))
            except json.JSONDecodeError:
                print("❌ Invalid JSON in result column:")
                print(result_json)
        else:
            print("⚠️  No result data found.")
            
        conn.close()

    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python show_analysis_result.py <article_id>")
        # Default to 874 for convenience if no arg provided, as per user context
        print("Showing default example (ID 874)...")
        show_result(874)
    else:
        show_result(int(sys.argv[1]))
