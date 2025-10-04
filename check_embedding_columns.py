from dotenv import load_dotenv
load_dotenv()

from pg_client_new import PgClient

db = PgClient()

with db._cursor() as cur:
    cur.execute("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'article_chunks'
        AND column_name LIKE '%embed%'
    """)

    print("Embedding columns in article_chunks:")
    for col_name, data_type in cur.fetchall():
        print(f"  - {col_name}: {data_type}")
