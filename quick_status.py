import sqlite3

conn = sqlite3.connect(r'D:\Articles\SQLite\analysis.db', timeout=30.0)
cursor = conn.cursor()

cursor.execute('SELECT deep_analysis_status, count(*) FROM analysis_articles GROUP BY deep_analysis_status')
print('📊 Status breakdown:')
for row in cursor.fetchall():
    print(f'  {row[0]}: {row[1]}')

conn.close()
