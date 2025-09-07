"""Database models for Stage 6 Hybrid Chunking."""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all database models."""
    
    pass


class ArticleChunk(Base):
    """Enhanced article chunks table with LLM processing fields."""
    
    __tablename__ = "article_chunks"
    __table_args__ = (
        UniqueConstraint("article_id", "chunk_index", name="uq_article_chunks_id_index"),
        Index("idx_article_chunks_article_id", "article_id"),
        Index("idx_article_chunks_semantic_type", "semantic_type"),
        Index("idx_article_chunks_importance", "importance_score"),
        Index("idx_article_chunks_llm_used", "llm_used"),
        Index("idx_article_chunks_fts", "text_clean", postgresql_using="gin"),
        Index("idx_article_chunks_published_at", "published_at"),
        Index("idx_article_chunks_source_domain", "source_domain"),
        Index("idx_article_chunks_language", "language"),
    )

    # Primary fields
    chunk_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, comment="Unique chunk identifier"
    )
    article_id: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="Parent article identifier"
    )
    chunk_index: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Zero-based index within article"
    )
    
    # Content fields
    text: Mapped[str] = mapped_column(Text, nullable=False, comment="Raw chunk text")
    text_clean: Mapped[str] = mapped_column(
        Text, nullable=False, comment="Cleaned text for FTS"
    )
    word_count_chunk: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Word count in chunk"
    )
    char_count_chunk: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Character count in chunk"
    )
    char_start: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Start position in original text"
    )
    char_end: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="End position in original text"
    )
    
    # Semantic fields
    semantic_type: Mapped[str] = mapped_column(
        String(20), 
        nullable=False, 
        default="body",
        comment="Type: intro/body/list/quote/conclusion/code"
    )
    importance_score: Mapped[Decimal] = mapped_column(
        Numeric(4, 3), 
        nullable=False, 
        default=Decimal("0.500"),
        comment="Importance score 0.000-1.000"
    )
    chunk_strategy: Mapped[str] = mapped_column(
        String(20), 
        nullable=False, 
        default="paragraph",
        comment="Chunking strategy used"
    )
    
    # NEW LLM processing fields
    llm_used: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False,
        comment="Whether LLM was used to refine this chunk"
    )
    llm_action: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True,
        comment="LLM action: keep/merge_prev/merge_next/drop"
    )
    offset_adjust: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0,
        comment="Character offset adjustment from LLM (-120 to +120)"
    )
    llm_confidence: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(3, 2), nullable=True,
        comment="LLM confidence score 0.00-1.00"
    )
    llm_reason: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        comment="LLM reasoning for the action"
    )
    merged_with_prev: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False,
        comment="Whether this chunk was merged with previous"
    )
    merged_reason: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True,
        comment="Reason for merging"
    )
    
    # Processing metadata
    processing_version: Mapped[str] = mapped_column(
        String(10), nullable=False, default="1.0",
        comment="Processing version for migration tracking"
    )
    
    # Denormalized article fields for fast queries
    url: Mapped[str] = mapped_column(
        Text, nullable=False, comment="Article URL"
    )
    title: Mapped[str] = mapped_column(
        Text, nullable=False, comment="Article title"
    )
    title_norm: Mapped[str] = mapped_column(
        Text, nullable=False, comment="Normalized title for search"
    )
    source_domain: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="Source domain"
    )
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        comment="Article publication date (UTC)"
    )
    language: Mapped[str] = mapped_column(
        String(10), nullable=False, comment="Detected language code"
    )
    category: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, comment="Article category"
    )
    tags_norm: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list,
        comment="Normalized tags array"
    )
    authors_norm: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list,
        comment="Normalized authors array"
    )
    quality_score: Mapped[Decimal] = mapped_column(
        Numeric(4, 3), nullable=False, default=Decimal("0.500"),
        comment="Article quality score"
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=func.now(),
        comment="Creation timestamp"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=func.now(),
        onupdate=func.now(), comment="Last update timestamp"
    )


class ChunkingBatch(Base):
    """Tracking table for chunking batches."""
    
    __tablename__ = "chunking_batches"
    __table_args__ = (
        Index("idx_chunking_batches_status", "status"),
        Index("idx_chunking_batches_created_at", "created_at"),
        Index("idx_chunking_batches_worker_id", "worker_id"),
    )

    batch_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, comment="Unique batch identifier"
    )
    worker_id: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="Worker identifier"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="planned",
        comment="Batch status: planned/running/completed/failed"
    )
    
    # Processing counts
    articles_total: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
        comment="Total articles to process"
    )
    articles_processed: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
        comment="Articles successfully processed"
    )
    articles_failed: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
        comment="Articles that failed processing"
    )
    chunks_created: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
        comment="Total chunks created"
    )
    llm_calls_made: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
        comment="Number of LLM API calls made"
    )
    
    # Performance metrics
    processing_time_ms: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True,
        comment="Total processing time in milliseconds"
    )
    llm_cost_estimate_usd: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(8, 4), nullable=True,
        comment="Estimated LLM API cost in USD"
    )
    
    # Configuration snapshot
    config_snapshot: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict,
        comment="Configuration used for this batch"
    )
    
    # Error tracking
    error_message: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="Error message if batch failed"
    )
    error_details: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict,
        comment="Detailed error information"
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=func.now(),
        comment="Batch creation timestamp"
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
        comment="Processing start timestamp"
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
        comment="Processing completion timestamp"
    )
    
    # Correlation tracking
    correlation_id: Mapped[str] = mapped_column(
        UUID, nullable=False, comment="Correlation ID for tracing"
    )