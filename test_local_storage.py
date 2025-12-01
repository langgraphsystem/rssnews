"""
Test script for local storage implementation
"""
import os
import sys
from local_storage import LocalStorageClient

# Test paths
SQLITE_PATH = r"D:\Articles\SQLite\rag.db"
CHROMA_PATH = r"D:\Articles\chromadb"

def test_basic_operations():
    print("🧪 Testing Local Storage Implementation...")
    print(f"SQLite: {SQLITE_PATH}")
    print(f"ChromaDB: {CHROMA_PATH}")
    print("-" * 60)
    
    try:
        # Initialize client
        print("\n1️⃣ Initializing storage client...")
        client = LocalStorageClient(SQLITE_PATH, CHROMA_PATH)
        print("✅ Storage client initialized successfully")
        
        # Test article insertion
        print("\n2️⃣ Testing article insertion...")
        test_article = {
            'url': 'https://example.com/test-article',
            'title': 'Test Article',
            'full_text': 'This is a test article content for local storage testing.',
        }
        article_id = client.insert_article(test_article)
        print(f"✅ Article inserted with ID: {article_id}")
        
        # Test getting pending articles
        print("\n3️⃣ Testing pending articles retrieval...")
        pending = client.get_pending_articles(limit=5)
        print(f"✅ Found {len(pending)} pending articles")
        if pending:
            print(f"   First article: {pending[0]['title']}")
        
        # Test chunk saving (with mock embeddings)
        print("\n4️⃣ Testing chunk storage...")
        test_chunks = [
            {'text': 'First chunk of the article', 'url': test_article['url'], 'title': test_article['title']},
            {'text': 'Second chunk of the article', 'url': test_article['url'], 'title': test_article['title']},
        ]
        # Mock embeddings (768 dimensions for embeddinggemma)
        mock_embeddings = [[0.1] * 768, [0.2] * 768]
        
        client.save_chunks(article_id, test_chunks, mock_embeddings)
        print(f"✅ Saved {len(test_chunks)} chunks with embeddings")
        
        # Test search
        print("\n5️⃣ Testing vector search...")
        query_embedding = [0.15] * 768  # Mock query
        results = client.search(query_embedding, n_results=2)
        print(f"✅ Search returned {len(results['ids'][0])} results")
        if results['documents'][0]:
            print(f"   Top result: {results['documents'][0][0][:50]}...")
        
        # Update status
        print("\n6️⃣ Testing status update...")
        client.update_article_status(article_id, 'processed')
        print("✅ Article status updated to 'processed'")
        
        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    test_basic_operations()
