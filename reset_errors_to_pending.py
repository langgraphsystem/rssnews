import sqlite3
import config

cfg = config.load_config()

print("🔄 Сброс ошибочных статей в pending...\n")

with sqlite3.connect(cfg['analysis_db_path'], timeout=30.0) as conn:
    cursor = conn.cursor()
    
    # Показать ошибки
    cursor.execute("SELECT count(*) FROM analysis_articles WHERE deep_analysis_status = 'error'")
    error_count = cursor.fetchone()[0]
    print(f"Найдено ошибок: {error_count}")
    
    if error_count > 0:
        # Сбросить все ошибки в pending
        cursor.execute("""
            UPDATE analysis_articles 
            SET deep_analysis_status = 'pending',
                deep_analysis_result = NULL,
                deep_analysis_at = NULL
            WHERE deep_analysis_status = 'error'
        """)
        conn.commit()
        print(f"✅ {error_count} статей сброшено в pending")
    else:
        print("Нет ошибочных статей")

print("\nМожно запускать: python process_deep_analysis.py")
