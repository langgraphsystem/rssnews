"""Add LLM processing fields to article_chunks

Revision ID: 001
Revises: 
Create Date: 2024-12-30 14:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create chunking_batches table
    op.create_table('chunking_batches',
        sa.Column('batch_id', sa.String(length=64), nullable=False, comment='Unique batch identifier'),
        sa.Column('worker_id', sa.String(length=100), nullable=False, comment='Worker identifier'),
        sa.Column('status', sa.String(length=20), nullable=False, comment='Batch status: planned/running/completed/failed'),
        sa.Column('articles_total', sa.Integer(), nullable=False, comment='Total articles to process'),
        sa.Column('articles_processed', sa.Integer(), nullable=False, comment='Articles successfully processed'),
        sa.Column('articles_failed', sa.Integer(), nullable=False, comment='Articles that failed processing'),
        sa.Column('chunks_created', sa.Integer(), nullable=False, comment='Total chunks created'),
        sa.Column('llm_calls_made', sa.Integer(), nullable=False, comment='Number of LLM API calls made'),
        sa.Column('processing_time_ms', sa.BigInteger(), nullable=True, comment='Total processing time in milliseconds'),
        sa.Column('llm_cost_estimate_usd', sa.Numeric(precision=8, scale=4), nullable=True, comment='Estimated LLM API cost in USD'),
        sa.Column('config_snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=False, comment='Configuration used for this batch'),
        sa.Column('error_message', sa.Text(), nullable=True, comment='Error message if batch failed'),
        sa.Column('error_details', postgresql.JSONB(astext_type=sa.Text()), nullable=False, comment='Detailed error information'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Batch creation timestamp'),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True, comment='Processing start timestamp'),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True, comment='Processing completion timestamp'),
        sa.Column('correlation_id', postgresql.UUID(), nullable=False, comment='Correlation ID for tracing'),
        sa.PrimaryKeyConstraint('batch_id')
    )
    op.create_index('idx_chunking_batches_created_at', 'chunking_batches', ['created_at'], unique=False)
    op.create_index('idx_chunking_batches_status', 'chunking_batches', ['status'], unique=False)
    op.create_index('idx_chunking_batches_worker_id', 'chunking_batches', ['worker_id'], unique=False)

    # Check if article_chunks table exists, if not create it
    # (This assumes the table might exist from the main RSS system)
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    
    if 'article_chunks' not in inspector.get_table_names():
        # Create the complete article_chunks table
        op.create_table('article_chunks',
            sa.Column('chunk_id', sa.String(length=64), nullable=False, comment='Unique chunk identifier'),
            sa.Column('article_id', sa.String(length=64), nullable=False, comment='Parent article identifier'),
            sa.Column('chunk_index', sa.Integer(), nullable=False, comment='Zero-based index within article'),
            sa.Column('text', sa.Text(), nullable=False, comment='Raw chunk text'),
            sa.Column('text_clean', sa.Text(), nullable=False, comment='Cleaned text for FTS'),
            sa.Column('word_count_chunk', sa.Integer(), nullable=False, comment='Word count in chunk'),
            sa.Column('char_count_chunk', sa.Integer(), nullable=False, comment='Character count in chunk'),
            sa.Column('char_start', sa.Integer(), nullable=False, comment='Start position in original text'),
            sa.Column('char_end', sa.Integer(), nullable=False, comment='End position in original text'),
            sa.Column('semantic_type', sa.String(length=20), nullable=False, comment='Type: intro/body/list/quote/conclusion/code'),
            sa.Column('importance_score', sa.Numeric(precision=4, scale=3), nullable=False, comment='Importance score 0.000-1.000'),
            sa.Column('chunk_strategy', sa.String(length=20), nullable=False, comment='Chunking strategy used'),
            sa.Column('llm_used', sa.Boolean(), nullable=False, comment='Whether LLM was used to refine this chunk'),
            sa.Column('llm_action', sa.String(length=20), nullable=True, comment='LLM action: keep/merge_prev/merge_next/drop'),
            sa.Column('offset_adjust', sa.SmallInteger(), nullable=False, comment='Character offset adjustment from LLM (-120 to +120)'),
            sa.Column('llm_confidence', sa.Numeric(precision=3, scale=2), nullable=True, comment='LLM confidence score 0.00-1.00'),
            sa.Column('llm_reason', sa.Text(), nullable=True, comment='LLM reasoning for the action'),
            sa.Column('merged_with_prev', sa.Boolean(), nullable=False, comment='Whether this chunk was merged with previous'),
            sa.Column('merged_reason', sa.String(length=100), nullable=True, comment='Reason for merging'),
            sa.Column('processing_version', sa.String(length=10), nullable=False, comment='Processing version for migration tracking'),
            sa.Column('url', sa.Text(), nullable=False, comment='Article URL'),
            sa.Column('title', sa.Text(), nullable=False, comment='Article title'),
            sa.Column('title_norm', sa.Text(), nullable=False, comment='Normalized title for search'),
            sa.Column('source_domain', sa.String(length=255), nullable=False, comment='Source domain'),
            sa.Column('published_at', sa.DateTime(timezone=True), nullable=False, comment='Article publication date (UTC)'),
            sa.Column('language', sa.String(length=10), nullable=False, comment='Detected language code'),
            sa.Column('category', sa.String(length=50), nullable=True, comment='Article category'),
            sa.Column('tags_norm', postgresql.JSONB(astext_type=sa.Text()), nullable=False, comment='Normalized tags array'),
            sa.Column('authors_norm', postgresql.JSONB(astext_type=sa.Text()), nullable=False, comment='Normalized authors array'),
            sa.Column('quality_score', sa.Numeric(precision=4, scale=3), nullable=False, comment='Article quality score'),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Creation timestamp'),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Last update timestamp'),
            sa.PrimaryKeyConstraint('chunk_id'),
            sa.UniqueConstraint('article_id', 'chunk_index', name='uq_article_chunks_id_index')
        )
    else:
        # Add new LLM fields to existing article_chunks table
        op.add_column('article_chunks', sa.Column('llm_used', sa.Boolean(), nullable=False, server_default=sa.text('false'), comment='Whether LLM was used to refine this chunk'))
        op.add_column('article_chunks', sa.Column('llm_action', sa.String(length=20), nullable=True, comment='LLM action: keep/merge_prev/merge_next/drop'))
        op.add_column('article_chunks', sa.Column('offset_adjust', sa.SmallInteger(), nullable=False, server_default=sa.text('0'), comment='Character offset adjustment from LLM (-120 to +120)'))
        op.add_column('article_chunks', sa.Column('llm_confidence', sa.Numeric(precision=3, scale=2), nullable=True, comment='LLM confidence score 0.00-1.00'))
        op.add_column('article_chunks', sa.Column('llm_reason', sa.Text(), nullable=True, comment='LLM reasoning for the action'))
        op.add_column('article_chunks', sa.Column('merged_with_prev', sa.Boolean(), nullable=False, server_default=sa.text('false'), comment='Whether this chunk was merged with previous'))
        op.add_column('article_chunks', sa.Column('merged_reason', sa.String(length=100), nullable=True, comment='Reason for merging'))

    # Create indexes for article_chunks
    op.create_index('idx_article_chunks_article_id', 'article_chunks', ['article_id'], unique=False)
    op.create_index('idx_article_chunks_fts', 'article_chunks', ['text_clean'], unique=False, postgresql_using='gin')
    op.create_index('idx_article_chunks_importance', 'article_chunks', ['importance_score'], unique=False)
    op.create_index('idx_article_chunks_language', 'article_chunks', ['language'], unique=False)
    op.create_index('idx_article_chunks_llm_used', 'article_chunks', ['llm_used'], unique=False)
    op.create_index('idx_article_chunks_published_at', 'article_chunks', ['published_at'], unique=False)
    op.create_index('idx_article_chunks_semantic_type', 'article_chunks', ['semantic_type'], unique=False)
    op.create_index('idx_article_chunks_source_domain', 'article_chunks', ['source_domain'], unique=False)


def downgrade() -> None:
    # Drop indexes first
    op.drop_index('idx_article_chunks_source_domain', table_name='article_chunks')
    op.drop_index('idx_article_chunks_semantic_type', table_name='article_chunks')
    op.drop_index('idx_article_chunks_published_at', table_name='article_chunks')
    op.drop_index('idx_article_chunks_llm_used', table_name='article_chunks')
    op.drop_index('idx_article_chunks_language', table_name='article_chunks')
    op.drop_index('idx_article_chunks_importance', table_name='article_chunks')
    op.drop_index('idx_article_chunks_fts', table_name='article_chunks')
    op.drop_index('idx_article_chunks_article_id', table_name='article_chunks')
    
    # Remove LLM columns if they were added to existing table
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    columns = [col['name'] for col in inspector.get_columns('article_chunks')]
    
    if 'llm_used' in columns:
        op.drop_column('article_chunks', 'merged_reason')
        op.drop_column('article_chunks', 'merged_with_prev')
        op.drop_column('article_chunks', 'llm_reason')
        op.drop_column('article_chunks', 'llm_confidence')
        op.drop_column('article_chunks', 'offset_adjust')
        op.drop_column('article_chunks', 'llm_action')
        op.drop_column('article_chunks', 'llm_used')
    
    # Drop tables
    op.drop_index('idx_chunking_batches_worker_id', table_name='chunking_batches')
    op.drop_index('idx_chunking_batches_status', table_name='chunking_batches')
    op.drop_index('idx_chunking_batches_created_at', table_name='chunking_batches')
    op.drop_table('chunking_batches')