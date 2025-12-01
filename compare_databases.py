import sqlite3
import config

cfg = config.load_config()

print("=== Проверка баз данных ===\n")

# Main DB
with sqlite3.connect(cfg['sqlite_db_path'], timeout=30.0) as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT count(*) FROM articles WHERE status = 'processed'")
    main_processed = cursor.fetchone()[0]
    print(f"📊 Main DB (rag.db):")
    print(f"   Processed articles: {main_processed}")

# Analysis DB
with sqlite3.connect(cfg['analysis_db_path'], timeout=30.0) as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT count(*) FROM analysis_articles")
    total = cursor.fetchone()[0]
    cursor.execute("SELECT count(*) FROM analysis_articles WHERE deep_analysis_status = 'pending'")
    pending = cursor.fetchone()[0]
    cursor.execute("SELECT count(*) FROM analysis_articles WHERE deep_analysis_status = 'processed'")
    processed = cursor.fetchone()[0]
    cursor.execute("SELECT count(*) FROM analysis_articles WHERE deep_analysis_status = 'error'")
    errors = cursor.fetchone()[0]
    
    print(f"\n📊 Analysis DB (analysis.db):")
    print(f"   Total: {total}")
    print(f"   Pending: {pending}")
    print(f"   Processed: {processed}")
    print(f"   Errors: {errors}")
    
print(f"\n🔍 Разница: {main_processed - total} статей не скопировано")
