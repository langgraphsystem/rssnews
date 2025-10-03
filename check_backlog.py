#!/usr/bin/env python
"""Quick script to check embedding backlog"""

from dotenv import load_dotenv
load_dotenv()

from services.openai_embedding_migration_service import OpenAIEmbeddingMigrationService

service = OpenAIEmbeddingMigrationService()
stats = service.get_statistics()

print('\n📊 Embedding Statistics:\n')
print(f'   Total chunks: {stats.get("total_chunks", 0):,}')
print(f'   With TEXT embeddings: {stats.get("with_text_embeddings", 0):,}')
print(f'   With pgvector embeddings: {stats.get("with_pgvector_embeddings", 0):,}')
print(f'   Without embeddings: {stats.get("without_embeddings", 0):,}')
print(f'   Completion: {stats.get("percentage_complete", 0):.1f}%')
print()

if stats.get('without_embeddings', 0) > 0:
    backlog = stats['without_embeddings']
    cost = backlog * 500 * 0.00013 / 1000  # avg 500 tokens per chunk

    print(f'⚠️  Found {backlog:,} chunks without embeddings')
    print(f'   Estimated cost: ~${cost:.2f}')
    print()
    print('🚀 To migrate:')
    print('   python -c "import asyncio; from dotenv import load_dotenv; load_dotenv(); from services.openai_embedding_migration_service import OpenAIEmbeddingMigrationService; asyncio.run(OpenAIEmbeddingMigrationService().migrate_backlog())"')
else:
    print('✅ Все чанки имеют эмбеддинги!')
