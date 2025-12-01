import chromadb
import sqlite3
import logging
import config

logging.basicConfig(level=logging.INFO, format='%(message)s')

def check_embeddings():
    cfg = config.load_config()
    
    print(f"📂 Checking ChromaDB at: {cfg['chroma_db_path']}")
    
    try:
        client = chromadb.PersistentClient(path=cfg['chroma_db_path'])
        collection = client.get_collection("rss_chunks")
        
        count = collection.count()
        print(f"📊 Total embeddings (chunks) in ChromaDB: {count}")
        
        if count > 0:
            # Get the last 5 items
            results = collection.peek(limit=5)
            print("\n🔍 Recent Embeddings Sample:")
            for i in range(len(results['ids'])):
                print(f"  - ID: {results['ids'][i]}")
                print(f"    Metadata: {results['metadatas'][i]}")
                # Check if embedding vector exists and has non-zero length
                emb_len = len(results['embeddings'][i]) if results['embeddings'] is not None else 0
                print(f"    Vector Length: {emb_len} (Should be 1024 for mxbai-embed-large)")
                print("-" * 40)
        else:
            print("⚠️  Collection is empty!")

        # Check SQLite for comparison
        print("\n📂 Checking SQLite 'chunks' table...")
        conn = sqlite3.connect(cfg['sqlite_db_path'])
        cursor = conn.cursor()
        cursor.execute("SELECT count(*) FROM chunks")
        sqlite_count = cursor.fetchone()[0]
        print(f"📊 Total chunks in SQLite: {sqlite_count}")
        conn.close()
        
        if count != sqlite_count:
            print(f"\n⚠️  Mismatch! SQLite has {sqlite_count} chunks, ChromaDB has {count}.")
        else:
            print(f"\n✅ Counts match between SQLite and ChromaDB.")

    except Exception as e:
        print(f"❌ Error checking embeddings: {e}")

if __name__ == "__main__":
    check_embeddings()
