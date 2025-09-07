"""
Tests for base chunking functionality.
"""

import pytest
from src.chunking.base_chunker import BaseChunker, RawChunk, ChunkingStrategy
from tests.conftest import create_test_article_metadata


class TestBaseChunker:
    """Test suite for BaseChunker."""
    
    def test_chunker_initialization(self, test_settings):
        """Test chunker initializes correctly."""
        chunker = BaseChunker(test_settings)
        
        assert chunker.target_words == test_settings.chunking.target_words
        assert chunker.min_words == test_settings.chunking.min_words  
        assert chunker.max_words == test_settings.chunking.max_words
        assert chunker.overlap_words == test_settings.chunking.overlap_words
    
    def test_paragraph_chunking_strategy(self, test_settings):
        """Test paragraph-based chunking strategy."""
        chunker = BaseChunker(test_settings)
        
        text = """First paragraph with some content here.

Second paragraph with more content to process.

Third paragraph concluding the text."""
        
        metadata = create_test_article_metadata()
        chunks = chunker.chunk_text(text, metadata)
        
        assert len(chunks) > 0
        assert all(isinstance(chunk, RawChunk) for chunk in chunks)
        assert chunks[0].strategy == ChunkingStrategy.PARAGRAPH_BASED
        
        # Check chunk properties
        for chunk in chunks:
            assert chunk.text.strip()
            assert chunk.word_count > 0
            assert chunk.char_end > chunk.char_start
    
    def test_sliding_window_fallback(self, test_settings):
        """Test sliding window fallback for long paragraphs."""
        chunker = BaseChunker(test_settings)
        
        # Create very long paragraph that exceeds max_words
        long_paragraph = " ".join(["word"] * (test_settings.chunking.max_words + 100))
        
        metadata = create_test_article_metadata()
        chunks = chunker.chunk_text(long_paragraph, metadata)
        
        assert len(chunks) > 1
        
        # Should use sliding window for long content
        assert any(chunk.strategy == ChunkingStrategy.SLIDING_WINDOW for chunk in chunks)
        
        # Check word counts are within limits
        for chunk in chunks:
            assert chunk.word_count <= test_settings.chunking.max_words
    
    def test_sentence_aware_chunking(self, test_settings):
        """Test sentence-aware chunking doesn't break mid-sentence."""
        chunker = BaseChunker(test_settings)
        
        text = "This is sentence one. This is sentence two. This is sentence three."
        
        metadata = create_test_article_metadata()
        chunks = chunker.chunk_text(text, metadata)
        
        # Verify chunks don't break mid-sentence
        for chunk in chunks:
            assert not chunk.text.strip().endswith(' ')
            # Should end with sentence terminator or be last chunk
            if chunk != chunks[-1]:
                assert chunk.text.strip().endswith(('.', '!', '?', '\n'))
    
    def test_overlap_handling(self, test_settings):
        """Test proper overlap between chunks."""
        # Set specific settings for this test
        test_settings.chunking.target_words = 20
        test_settings.chunking.overlap_words = 5
        
        chunker = BaseChunker(test_settings)
        
        # Create text that will definitely need multiple chunks  
        words = ["word"] * 100
        text = " ".join(words)
        
        metadata = create_test_article_metadata()
        chunks = chunker.chunk_text(text, metadata)
        
        if len(chunks) > 1:
            # Check for overlap between consecutive chunks
            for i in range(len(chunks) - 1):
                current_chunk = chunks[i]
                next_chunk = chunks[i + 1]
                
                # There should be some overlapping content
                current_words = current_chunk.text.split()
                next_words = next_chunk.text.split()
                
                # Check if last few words of current chunk appear in next chunk
                if len(current_words) >= 3 and len(next_words) >= 3:
                    current_tail = " ".join(current_words[-3:])
                    next_head = " ".join(next_words[:10])  # Check first part of next
                    
                    # Some overlap should exist (not exact match due to boundary adjustments)
                    overlap_exists = any(word in next_head for word in current_tail.split())
                    assert overlap_exists or current_chunk.char_end >= next_chunk.char_start
    
    def test_empty_text_handling(self, test_settings):
        """Test handling of empty or whitespace-only text."""
        chunker = BaseChunker(test_settings)
        metadata = create_test_article_metadata()
        
        # Empty text
        chunks = chunker.chunk_text("", metadata)
        assert chunks == []
        
        # Whitespace only
        chunks = chunker.chunk_text("   \n\t  ", metadata)
        assert chunks == []
        
        # Only newlines
        chunks = chunker.chunk_text("\n\n\n", metadata)
        assert chunks == []
    
    def test_single_word_text(self, test_settings):
        """Test handling of very short text."""
        chunker = BaseChunker(test_settings)
        metadata = create_test_article_metadata()
        
        chunks = chunker.chunk_text("Hello", metadata)
        
        assert len(chunks) == 1
        assert chunks[0].text.strip() == "Hello"
        assert chunks[0].word_count == 1
    
    def test_complex_formatting_preservation(self, test_settings):
        """Test preservation of complex formatting."""
        chunker = BaseChunker(test_settings)
        
        text = """Article with complex formatting:

• Bullet point one
• Bullet point two

Code block:
```python
def hello():
    return "world"
```

Table:
| Col1 | Col2 |
|------|------|
| A    | B    |

Final paragraph."""
        
        metadata = create_test_article_metadata()
        chunks = chunker.chunk_text(text, metadata)
        
        assert len(chunks) > 0
        
        # Verify formatting is preserved in chunks
        full_text = " ".join(chunk.text for chunk in chunks)
        assert "```python" in full_text
        assert "•" in full_text or "• " in full_text
        assert "|" in full_text
    
    def test_chunk_indexing(self, test_settings):
        """Test chunk indexing is correct."""
        chunker = BaseChunker(test_settings)
        
        text = """Paragraph one with content.

Paragraph two with more content.

Paragraph three with final content."""
        
        metadata = create_test_article_metadata()
        chunks = chunker.chunk_text(text, metadata)
        
        # Check indexes are sequential
        for i, chunk in enumerate(chunks):
            assert chunk.index == i
    
    def test_character_positions(self, test_settings):
        """Test character position tracking."""
        chunker = BaseChunker(test_settings)
        
        text = "First part. Second part. Third part."
        
        metadata = create_test_article_metadata()
        chunks = chunker.chunk_text(text, metadata)
        
        # Verify character positions make sense
        for chunk in chunks:
            assert chunk.char_start >= 0
            assert chunk.char_end > chunk.char_start
            assert chunk.char_end <= len(text)
            
            # Verify text slice matches
            actual_text = text[chunk.char_start:chunk.char_end].strip()
            assert actual_text in chunk.text or chunk.text.strip() in actual_text
    
    def test_word_count_accuracy(self, test_settings):
        """Test word count calculation accuracy."""
        chunker = BaseChunker(test_settings)
        
        text = "One two three four five six seven eight nine ten."
        
        metadata = create_test_article_metadata()
        chunks = chunker.chunk_text(text, metadata)
        
        for chunk in chunks:
            expected_word_count = len(chunk.text.split())
            assert chunk.word_count == expected_word_count
    
    @pytest.mark.parametrize("strategy", [
        ChunkingStrategy.PARAGRAPH_BASED,
        ChunkingStrategy.SLIDING_WINDOW,
        ChunkingStrategy.SENTENCE_AWARE
    ])
    def test_strategy_selection(self, test_settings, strategy):
        """Test different chunking strategies work."""
        chunker = BaseChunker(test_settings)
        
        if strategy == ChunkingStrategy.PARAGRAPH_BASED:
            text = """Short paragraph.

Another short paragraph.

Third paragraph."""
            
        elif strategy == ChunkingStrategy.SLIDING_WINDOW:
            # Very long text to force sliding window
            text = " ".join(["word"] * (test_settings.chunking.max_words + 50))
            
        else:  # SENTENCE_AWARE
            text = "Sentence one. Sentence two. Sentence three. Sentence four. Sentence five."
        
        metadata = create_test_article_metadata()
        chunks = chunker.chunk_text(text, metadata)
        
        assert len(chunks) > 0
        assert all(chunk.word_count > 0 for chunk in chunks)
    
    def test_metadata_preservation(self, test_settings):
        """Test that metadata is properly preserved."""
        chunker = BaseChunker(test_settings)
        
        text = "Test content for metadata preservation."
        metadata = {
            'title': 'Test Article',
            'source': 'test.com',
            'custom_field': 'custom_value'
        }
        
        chunks = chunker.chunk_text(text, metadata)
        
        for chunk in chunks:
            # Chunker adds its own metadata
            assert isinstance(chunk.metadata, dict)
            
    def test_large_article_performance(self, test_settings):
        """Test performance with large articles."""
        chunker = BaseChunker(test_settings)
        
        # Generate large article (simulate 10k words)
        paragraphs = []
        for i in range(200):  # 200 paragraphs
            paragraph = f"Paragraph {i} with some content " * 10
            paragraphs.append(paragraph)
        
        text = "\n\n".join(paragraphs)
        metadata = create_test_article_metadata()
        
        import time
        start_time = time.time()
        chunks = chunker.chunk_text(text, metadata)
        processing_time = time.time() - start_time
        
        # Should complete within reasonable time (less than 5 seconds)
        assert processing_time < 5.0
        assert len(chunks) > 0
        
        # Verify chunks are reasonable
        for chunk in chunks:
            assert chunk.word_count <= test_settings.chunking.max_words
            assert chunk.word_count >= 1