import psycopg2
import os

passwords = ['postgres', 'password', '12345', 'admin', 'root', '']
user = 'postgres'
dbname = 'rssnews'
host = 'localhost'
port = '5432'

for pwd in passwords:
    try:
        dsn = f"postgresql://{user}:{pwd}@{host}:{port}/{dbname}"
        print(f"Trying {dsn}...")
        conn = psycopg2.connect(dsn)
        print(f"SUCCESS: {dsn}")
        conn.close()
        break
    except Exception as e:
        print(f"Failed with {pwd}: {e}")
