#!/usr/bin/env python3
"""
Pinecone integration for storing and searching 3072-dimensional embeddings.
"""

import os
import asyncio
import logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

import psycopg2
from pinecone import Pinecone
from stage6_hybrid_chunking.src.llm.gemini_client import GeminiClient
from stage6_hybrid_chunking.src.config.settings import Settings

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class ChunkData:
    """Represents a chunk with its metadata."""
    id: str
    article_id: str
    chunk_index: int
    text: str
    url: str
    title: str
    published_at: str
    embedding: Optional[List[float]] = None

class PineconeManager:
    """Manages Pinecone vector database operations."""

    def __init__(self, api_key: str, index_name: str = "rssnews-embeddings"):
        self.pc = Pinecone(api_key=api_key)
        self.index_name = index_name
        self.index = None

    def connect_to_index(self):
        """Connect to existing Pinecone index."""
        try:
            self.index = self.pc.Index(self.index_name)
            stats = self.index.describe_index_stats()
            logger.info(f"Connected to Pinecone index '{self.index_name}'")
            logger.info(f"Index stats: {stats}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to index: {e}")
            return False

    def create_index_if_not_exists(self, dimension: int = 3072):
        """Create Pinecone index if it doesn't exist."""
        try:
            # Check if index exists
            existing_indexes = [idx.name for idx in self.pc.list_indexes()]

            if self.index_name in existing_indexes:
                logger.info(f"Index '{self.index_name}' already exists")
                return self.connect_to_index()

            # Create new index
            logger.info(f"Creating new index '{self.index_name}' with {dimension} dimensions")
            self.pc.create_index(
                name=self.index_name,
                dimension=dimension,
                metric='cosine',
                spec={
                    'serverless': {
                        'cloud': 'aws',
                        'region': 'us-east-1'
                    }
                }
            )

            # Wait for index to be ready
            import time
            time.sleep(10)

            return self.connect_to_index()

        except Exception as e:
            logger.error(f"Failed to create index: {e}")
            return False

    def upsert_vectors(self, vectors: List[Dict]) -> bool:
        """Upload vectors to Pinecone."""
        if not self.index:
            logger.error("Index not connected")
            return False

        try:
            # Batch upsert (max 100 vectors per batch)
            batch_size = 100
            for i in range(0, len(vectors), batch_size):
                batch = vectors[i:i + batch_size]
                self.index.upsert(vectors=batch)
                logger.info(f"Upserted batch {i//batch_size + 1}: {len(batch)} vectors")

            logger.info(f"Successfully upserted {len(vectors)} vectors")
            return True

        except Exception as e:
            logger.error(f"Failed to upsert vectors: {e}")
            return False

    def search_similar(self, query_vector: List[float], top_k: int = 10) -> List[Dict]:
        """Search for similar vectors."""
        if not self.index:
            logger.error("Index not connected")
            return []

        try:
            results = self.index.query(
                vector=query_vector,
                top_k=top_k,
                include_metadata=True
            )

            return [
                {
                    'id': match['id'],
                    'score': match['score'],
                    'metadata': match.get('metadata', {})
                }
                for match in results.get('matches', [])
            ]

        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []

class PineconeEmbeddingMigrator:
    """Migrates embedding data from Railway PostgreSQL to Pinecone."""

    def __init__(self, railway_url: str, gemini_client: GeminiClient, pinecone_manager: PineconeManager):
        self.railway_url = railway_url
        self.gemini_client = gemini_client
        self.pinecone_manager = pinecone_manager

    def fetch_chunks_from_railway(self, limit: Optional[int] = None) -> List[ChunkData]:
        """Fetch chunk data from Railway PostgreSQL."""
        try:
            conn = psycopg2.connect(self.railway_url)
            cursor = conn.cursor()

            query = """
                SELECT
                    CONCAT(article_id, '_', chunk_index) as id,
                    article_id,
                    chunk_index,
                    text,
                    url,
                    title_norm,
                    published_at::text
                FROM article_chunks
                WHERE text IS NOT NULL
                    AND LENGTH(text) > 100
                ORDER BY published_at DESC
            """

            if limit:
                query += f" LIMIT {limit}"

            cursor.execute(query)
            rows = cursor.fetchall()

            chunks = []
            for row in rows:
                chunks.append(ChunkData(
                    id=row[0],
                    article_id=row[1],
                    chunk_index=row[2],
                    text=row[3],
                    url=row[4] or "",
                    title=row[5] or "",
                    published_at=row[6] or ""
                ))

            cursor.close()
            conn.close()

            logger.info(f"Fetched {len(chunks)} chunks from Railway")
            return chunks

        except Exception as e:
            logger.error(f"Failed to fetch chunks: {e}")
            return []

    async def generate_embeddings_for_chunks(self, chunks: List[ChunkData]) -> List[ChunkData]:
        """Generate 3072-dimensional embeddings for chunks."""
        try:
            # Extract texts
            texts = [chunk.text for chunk in chunks]
            logger.info(f"Generating embeddings for {len(texts)} texts...")

            # Generate embeddings (now with 3072 dimensions!)
            embeddings = await self.gemini_client.embed_texts(texts)

            # Attach embeddings to chunks
            for chunk, embedding in zip(chunks, embeddings):
                if embedding:
                    chunk.embedding = embedding
                    logger.debug(f"Generated {len(embedding)}-dim embedding for chunk {chunk.id}")
                else:
                    logger.warning(f"Failed to generate embedding for chunk {chunk.id}")

            success_count = sum(1 for chunk in chunks if chunk.embedding)
            logger.info(f"Successfully generated {success_count}/{len(chunks)} embeddings")

            return chunks

        except Exception as e:
            logger.error(f"Failed to generate embeddings: {e}")
            return chunks

    def prepare_pinecone_vectors(self, chunks: List[ChunkData]) -> List[Dict]:
        """Convert chunks to Pinecone vector format."""
        vectors = []

        for chunk in chunks:
            if not chunk.embedding:
                continue

            vector_data = {
                'id': chunk.id,
                'values': chunk.embedding,
                'metadata': {
                    'article_id': chunk.article_id,
                    'chunk_index': chunk.chunk_index,
                    'text': chunk.text[:1000],  # Truncate for metadata
                    'url': chunk.url,
                    'title': chunk.title,
                    'published_at': chunk.published_at,
                    'dimensions': len(chunk.embedding)
                }
            }
            vectors.append(vector_data)

        logger.info(f"Prepared {len(vectors)} vectors for Pinecone")
        return vectors

    async def run_migration(self, batch_size: int = 500) -> bool:
        """Run the complete migration process."""
        try:
            logger.info("🚀 Starting Pinecone migration...")

            # 1. Setup Pinecone index
            if not self.pinecone_manager.create_index_if_not_exists():
                logger.error("Failed to setup Pinecone index")
                return False

            # 2. Fetch chunks in batches
            total_migrated = 0
            offset = 0

            while True:
                logger.info(f"Processing batch starting at offset {offset}")

                chunks = self.fetch_chunks_from_railway(limit=batch_size)
                if not chunks:
                    break

                # 3. Generate embeddings
                chunks_with_embeddings = await self.generate_embeddings_for_chunks(chunks)

                # 4. Convert to Pinecone format
                vectors = self.prepare_pinecone_vectors(chunks_with_embeddings)

                if not vectors:
                    logger.warning("No valid vectors in this batch, skipping...")
                    offset += batch_size
                    continue

                # 5. Upload to Pinecone
                if self.pinecone_manager.upsert_vectors(vectors):
                    total_migrated += len(vectors)
                    logger.info(f"✅ Migrated {len(vectors)} vectors. Total: {total_migrated}")
                else:
                    logger.error("Failed to upload batch to Pinecone")
                    return False

                # Check if we got fewer than batch_size (end of data)
                if len(chunks) < batch_size:
                    break

                offset += batch_size

            logger.info(f"🎉 Migration completed! Total vectors migrated: {total_migrated}")
            return True

        except Exception as e:
            logger.error(f"Migration failed: {e}")
            return False

async def main():
    """Main function for testing Pinecone integration."""

    # Direct API keys (for testing)
    pinecone_api_key = "pcsk_757TcS_S6kYGDmBVWs3ciuxAmixwRMY6XAb5Dzhaj9D4jizcgzQWBrHJxctHeCKCMP1FiV"
    gemini_api_key = "AIzaSyDRnmJTyoRZlMleRsyERLkIoNi8KNITPq8"
    railway_url = "postgresql://postgres:ug1Hi~XHEMdMh_Lm~4UfUKtAejqLBGdg@crossover.proxy.rlwy.net:12306/railway"

    try:
        # Initialize components
        settings = Settings()
        gemini_client = GeminiClient(settings)
        pinecone_manager = PineconeManager(pinecone_api_key)
        migrator = PineconeEmbeddingMigrator(railway_url, gemini_client, pinecone_manager)

        # Run migration
        success = await migrator.run_migration(batch_size=100)  # Start with smaller batches

        if success:
            print("✅ Migration completed successfully!")

            # Test search
            print("\n🔍 Testing vector search...")
            test_query = "artificial intelligence machine learning"
            test_embeddings = await gemini_client.embed_texts([test_query])

            if test_embeddings[0]:
                results = pinecone_manager.search_similar(test_embeddings[0], top_k=5)
                print(f"Found {len(results)} similar articles:")

                for i, result in enumerate(results, 1):
                    print(f"{i}. Score: {result['score']:.3f}")
                    print(f"   Title: {result['metadata'].get('title', 'N/A')}")
                    print(f"   Text: {result['metadata'].get('text', '')[:100]}...")
                    print()

        await gemini_client.close()

    except Exception as e:
        logger.error(f"Main execution failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())