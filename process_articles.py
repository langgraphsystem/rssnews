"""
Process articles: Chunking and Embedding
Uses LocalLLMChunker for chunking and Ollama for embeddings.
Saves results to SQLite and ChromaDB.
"""
import asyncio
import logging
import json
import os
import sys
import traceback
import httpx
from typing import List, Dict, Any
from datetime import datetime

from local_storage import LocalStorageClient
from local_llm_chunker import LocalLLMChunker
from parser.extract import extract_all
import config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("processing.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class OllamaEmbedder:
    """Generate embeddings using Ollama"""
    
    def __init__(self, base_url: str = None, model: str = None):
        self.base_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.model = model or os.getenv("OLLAMA_EMBEDDING_MODEL", "mxbai-embed-large")
        self.client = httpx.AsyncClient(timeout=60.0)

    async def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Get embeddings for a list of texts"""
        embeddings = []
        for text in texts:
            try:
                response = await self.client.post(
                    f"{self.base_url}/api/embeddings",
                    json={
                        "model": self.model,
                        "prompt": text
                    }
                )
                if response.status_code == 200:
                    data = response.json()
                    embeddings.append(data['embedding'])
                else:
                    logger.error(f"Embedding failed: {response.status_code} - {response.text}")
                    raise Exception(f"Ollama embedding error: {response.text}")
            except Exception as e:
                logger.error(f"Error generating embedding: {e}")
                raise e
        return embeddings

    async def close(self):
        await self.client.aclose()

class ArticleProcessor:
    def __init__(self):
        self.cfg = config.load_config()
        self.storage = LocalStorageClient(
            self.cfg['sqlite_db_path'], 
            self.cfg['chroma_db_path']
        )
        self.chunker = LocalLLMChunker()
        self.embedder = OllamaEmbedder(model=self.cfg.get('ollama_embedding_model'))
        self.http_client = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
        )
        
    async def process_batch(self, batch_size: int = 10):
        """Process a batch of pending articles"""
        articles = self.storage.get_pending_articles(limit=batch_size)
        
        if not articles:
            logger.info("No pending articles found.")
            return 0
            
        logger.info(f"Processing batch of {len(articles)} articles...")
        
        processed_count = 0
        
        for article in articles:
            try:
                await self._process_single_article(article)
                processed_count += 1
            except Exception as e:
                logger.error(f"Failed to process article {article['id']}: {e}")
                self.storage.update_article_status(article['id'], 'error')
                
        return processed_count

    async def _process_single_article(self, article: Dict[str, Any]):
        """Process a single article: Extract -> Chunk -> Embed -> Save"""
        article_id = article['id']
        title = article['title']
        url = article['url']
        
        logger.info(f"Processing article {article_id}: {title[:50]}...")
        
        # 1. Enrich Article (Extract full data)
        # We pass the existing DB article data as a starting point
        enriched_data = await self.enrich_article(article)
        
        # 2. Save Enriched Data (Full text + all metadata)
        self.save_enriched_data(article_id, enriched_data)
        
        # 3. Chunking
        # Use the newly extracted full text
        full_text = enriched_data.full_text
        
        metadata = {
            'title': enriched_data.title,
            'url': enriched_data.url,
            'language': enriched_data.language or 'en',
            'category': enriched_data.section or 'news'
        }
        
        # Use full text or fallback to existing content if extraction failed/was empty
        text_to_chunk = full_text if full_text and len(full_text) > 50 else f"{title}\n{article.get('content', '')}"
        
        chunks = await self.chunker.create_chunks(text_to_chunk, metadata)
        
        if not chunks:
            logger.warning(f"No chunks generated for article {article_id}")
            self.storage.update_article_status(article_id, 'processed_no_chunks')
            return

        # 4. Embeddings
        chunk_texts = [c['text'] for c in chunks]
        embeddings = await self.embedder.get_embeddings(chunk_texts)
        
        # 5. Save Chunks & Vectors
        for chunk in chunks:
            chunk['url'] = url
            chunk['title'] = title
            
        self.storage.save_chunks(article_id, chunks, embeddings)
        
        # 6. Update status
        self.storage.update_article_status(article_id, 'processed')
        logger.info(f"✅ Article {article_id} processed: {len(chunks)} chunks saved.")

    async def enrich_article(self, article: Dict[str, Any]):
        """
        Fetch and extract all available data from the article URL.
        Returns a ParsedArticle object.
        """
        from parser.extract import extract_all, ParsedArticle
        
        url = article['url']
        content = article.get('content', '')
        title = article.get('title', '')
        
        # If content is already long, we might skip re-extraction, 
        # BUT the user requested "extract all data", so we should probably try anyway 
        # to get metadata like images, authors, etc. even if text is present.
        # However, to avoid redundant network calls if we already have good data, 
        # we could check a flag. For now, we'll assume we want to enrich if possible.
        
        logger.info(f"Fetching full data for: {url}")
        try:
            response = await self.http_client.get(url)
            if response.status_code == 200:
                parsed = extract_all(
                    html=response.text,
                    url=url,
                    final_url=str(response.url),
                    rss_data={'title': title, 'summary': content}
                )
                return parsed
            else:
                logger.warning(f"Failed to fetch {url}: {response.status_code}")
                # Return a basic ParsedArticle wrapper around existing data
                return ParsedArticle(
                    url=url,
                    title=title,
                    full_text=content,
                    status='error',
                    error_reason=f"HTTP {response.status_code}"
                )
        except Exception as e:
            logger.error(f"Extraction error for {url}: {e}")
            return ParsedArticle(
                url=url,
                title=title,
                full_text=content,
                status='error',
                error_reason=str(e)
            )

    def save_enriched_data(self, article_id: int, parsed_data):
        """
        Save all extracted data to the database.
        Stores full_text in 'content' and everything else in 'meta'.
        """
        # Convert dataclass to dict
        data_dict = parsed_data.__dict__.copy()
        
        # Separate content and meta
        full_text = data_dict.pop('full_text', '')
        
        # Handle datetime serialization for JSON
        for key, value in data_dict.items():
            if isinstance(value, datetime):
                data_dict[key] = value.isoformat()
        
        # We might want to merge with existing meta instead of overwriting?
        # For now, we overwrite to ensure we have the latest "full" extraction.
        
        self.storage.update_article_content(article_id, full_text, data_dict)
        logger.info(f"💾 Saved enriched data for article {article_id}")
        


    async def close(self):
        await self.embedder.close()
        await self.http_client.aclose()


async def main():
    processor = ArticleProcessor()
    try:
        total_processed = 0
        while True:
            count = await processor.process_batch(batch_size=10)
            if count == 0:
                break
            total_processed += count
            logger.info(f"Total processed so far: {total_processed}")
            
        logger.info("🎉 All pending articles processed!")
    finally:
        await processor.close()

if __name__ == "__main__":
    asyncio.run(main())
