import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def main():
    dsn = os.getenv('PG_DSN')
    if not dsn:
        print('PG_DSN not set')
        return 1
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    def run(label, q):
        cur.execute(q)
        print(f"{label}: {cur.fetchone()[0]}")
    run('feeds', 'SELECT count(*) FROM feeds')
    run('raw', 'SELECT count(*) FROM raw')
    run('articles_index', 'SELECT count(*) FROM articles_index')
    run('article_chunks_total', 'SELECT count(*) FROM article_chunks')
    run('article_chunks_7d', "SELECT count(*) FROM article_chunks WHERE published_at >= NOW() - INTERVAL '7 days'")
    run('article_chunks_7d_with_vec', "SELECT count(*) FROM article_chunks WHERE embedding_vector IS NOT NULL AND published_at >= NOW() - INTERVAL '7 days'")
    cur.close(); conn.close()
    return 0

if __name__ == '__main__':
    raise SystemExit(main())

