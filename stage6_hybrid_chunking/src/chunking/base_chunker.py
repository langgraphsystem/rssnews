"""
Base chunking implementation with deterministic rules.
This module provides paragraph-aware and sliding window chunking strategies.
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger(__name__)


class ChunkingStrategy(Enum):
    """Chunking strategy enumeration."""
    PARAGRAPH = "paragraph"
    SLIDING_WINDOW = "sliding_window"
    HYBRID = "hybrid"


class SemanticType(Enum):
    """Semantic chunk type enumeration."""
    INTRO = "intro"
    BODY = "body" 
    LIST = "list"
    QUOTE = "quote"
    CONCLUSION = "conclusion"
    CODE = "code"


@dataclass
class ChunkBoundary:
    """Represents a chunk boundary with metadata."""
    start_char: int
    end_char: int
    start_word: int
    end_word: int
    confidence: float  # 0.0-1.0, how confident we are this is a good boundary
    boundary_type: str  # paragraph, sentence, word
    

@dataclass
class RawChunk:
    """Raw chunk before LLM processing."""
    index: int
    text: str
    text_clean: str
    word_count: int
    char_count: int
    char_start: int
    char_end: int
    semantic_type: SemanticType
    importance_score: float
    strategy: ChunkingStrategy
    boundaries: List[ChunkBoundary]
    
    # Quality indicators for routing decision
    needs_review: bool = False
    review_reasons: List[str] = None
    
    def __post_init__(self):
        if self.review_reasons is None:
            self.review_reasons = []


class BaseChunker:
    """
    Deterministic base chunker with paragraph-aware and sliding window strategies.
    """
    
    def __init__(self, config: Dict):
        self.target_words = config.get("target_words", 400)
        self.overlap_words = config.get("overlap_words", 80) 
        self.min_words = config.get("min_words", 200)
        self.max_words = config.get("max_words", 600)
        self.min_chars = config.get("min_chars", 800)
        
        # Compiled regex patterns for performance
        self._paragraph_split = re.compile(r'\n\s*\n')
        self._sentence_split = re.compile(r'[.!?]+\s+(?=[A-Z])')
        self._list_markers = re.compile(r'^\s*[-•*]\s+', re.MULTILINE)
        self._numbered_list = re.compile(r'^\s*\d+\.\s+', re.MULTILINE)
        self._code_blocks = re.compile(r'```[\s\S]*?```|`[^`]+`')
        self._quote_blocks = re.compile(r'^>\s+.+$', re.MULTILINE)
        self._heading_markers = re.compile(r'^#{1,6}\s+.+$', re.MULTILINE)
        
        # Boilerplate patterns (common footer/nav content)
        self._boilerplate_patterns = [
            re.compile(r'cookie\s+policy', re.IGNORECASE),
            re.compile(r'privacy\s+policy', re.IGNORECASE), 
            re.compile(r'terms\s+of\s+service', re.IGNORECASE),
            re.compile(r'subscribe\s+to\s+newsletter', re.IGNORECASE),
            re.compile(r'follow\s+us\s+on', re.IGNORECASE),
            re.compile(r'copyright\s+©', re.IGNORECASE),
            re.compile(r'all\s+rights\s+reserved', re.IGNORECASE),
        ]
        
        logger.info("BaseChunker initialized", config=config)
    
    def chunk_text(self, text: str, article_metadata: Dict) -> List[RawChunk]:
        """
        Main chunking entry point. Tries paragraph chunking first, falls back to sliding window.
        
        Args:
            text: Clean article text to chunk
            article_metadata: Article metadata for context
            
        Returns:
            List of raw chunks
        """
        if not text or len(text.strip()) == 0:
            logger.warning("Empty text provided for chunking")
            return []
        
        # Preprocess text
        text_clean = self._preprocess_text(text)
        word_tokens = self._tokenize_words(text_clean)
        
        if len(word_tokens) < self.min_words:
            logger.info("Text too short for chunking", word_count=len(word_tokens))
            return [self._create_single_chunk(text_clean, word_tokens, article_metadata)]
        
        # Try paragraph-based chunking first
        paragraphs = self._split_paragraphs(text_clean)
        
        if len(paragraphs) > 1 and self._is_suitable_for_paragraph_chunking(paragraphs):
            logger.debug("Using paragraph-based chunking", paragraph_count=len(paragraphs))
            chunks = self._chunk_by_paragraphs(text_clean, paragraphs, word_tokens, article_metadata)
        else:
            logger.debug("Using sliding window chunking")
            chunks = self._chunk_by_sliding_window(text_clean, word_tokens, article_metadata)
        
        # Post-process chunks
        chunks = self._post_process_chunks(chunks, article_metadata)
        
        logger.info(
            "Chunking completed", 
            chunk_count=len(chunks),
            strategy=chunks[0].strategy.value if chunks else "none"
        )
        
        return chunks
    
    def _preprocess_text(self, text: str) -> str:
        """Clean and normalize text for chunking."""
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Remove excessive newlines but preserve paragraph breaks
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # Normalize quotes
        text = text.replace('"', '"').replace('"', '"')
        text = text.replace(''', "'").replace(''', "'")
        
        # Fix common issues
        text = re.sub(r'\s+([.!?])', r'\1', text)  # Remove space before punctuation
        text = re.sub(r'([.!?])\s*([A-Z])', r'\1 \2', text)  # Ensure space after sentences
        
        return text.strip()
    
    def _tokenize_words(self, text: str) -> List[str]:
        """Tokenize text into words, preserving boundaries."""
        # Simple word tokenization that preserves contractions
        return re.findall(r"\b\w+(?:'\w+)?\b", text)
    
    def _split_paragraphs(self, text: str) -> List[str]:
        """Split text into paragraphs."""
        paragraphs = self._paragraph_split.split(text)
        return [p.strip() for p in paragraphs if p.strip()]
    
    def _is_suitable_for_paragraph_chunking(self, paragraphs: List[str]) -> bool:
        """Check if text is suitable for paragraph-based chunking."""
        if len(paragraphs) < 2:
            return False
        
        # Check if paragraphs have reasonable size distribution
        word_counts = [len(self._tokenize_words(p)) for p in paragraphs]
        avg_para_words = sum(word_counts) / len(word_counts)
        
        # Avoid paragraph chunking if:
        # 1. Average paragraph is too small (likely poor formatting)
        # 2. Very uneven distribution (one giant paragraph)
        if avg_para_words < 20:
            return False
        
        max_para_words = max(word_counts)
        if max_para_words > avg_para_words * 5:  # One paragraph is 5x larger than average
            return False
        
        return True
    
    def _chunk_by_paragraphs(self, 
                           text: str, 
                           paragraphs: List[str], 
                           word_tokens: List[str], 
                           article_metadata: Dict) -> List[RawChunk]:
        """Chunk text by paragraph boundaries with smart merging."""
        chunks = []
        current_paragraphs = []
        current_word_count = 0
        char_position = 0
        
        for i, paragraph in enumerate(paragraphs):
            para_words = self._tokenize_words(paragraph)
            para_word_count = len(para_words)
            
            # Decide whether to start a new chunk
            would_exceed_target = (current_word_count + para_word_count > self.target_words)
            has_content = len(current_paragraphs) > 0
            
            if would_exceed_target and has_content:
                # Create chunk from accumulated paragraphs
                chunk = self._create_paragraph_chunk(
                    current_paragraphs, len(chunks), char_position, article_metadata
                )
                chunks.append(chunk)
                
                # Start new chunk with overlap if configured
                if self.overlap_words > 0:
                    overlap_paragraphs = self._get_overlap_paragraphs(
                        current_paragraphs, self.overlap_words
                    )
                    current_paragraphs = overlap_paragraphs + [paragraph]
                    current_word_count = sum(len(self._tokenize_words(p)) for p in current_paragraphs)
                else:
                    current_paragraphs = [paragraph]
                    current_word_count = para_word_count
            else:
                # Add paragraph to current chunk
                current_paragraphs.append(paragraph)
                current_word_count += para_word_count
            
            char_position += len(paragraph) + 2  # +2 for paragraph separator
        
        # Handle final chunk
        if current_paragraphs:
            # Only create if meets minimum size or is the only chunk
            if current_word_count >= self.min_words or len(chunks) == 0:
                chunk = self._create_paragraph_chunk(
                    current_paragraphs, len(chunks), char_position, article_metadata
                )
                chunks.append(chunk)
            else:
                # Merge small final chunk with previous
                if chunks:
                    chunks[-1] = self._merge_chunks(chunks[-1], current_paragraphs)
        
        return chunks
    
    def _chunk_by_sliding_window(self, 
                               text: str, 
                               word_tokens: List[str], 
                               article_metadata: Dict) -> List[RawChunk]:
        """Chunk text using sliding window with sentence boundary awareness."""
        chunks = []
        total_words = len(word_tokens)
        
        for i in range(0, total_words, self.target_words - self.overlap_words):
            start_word = i
            end_word = min(i + self.target_words, total_words)
            
            # Skip tiny final chunks
            if end_word - start_word < self.min_words and i > 0:
                break
            
            # Get word slice
            chunk_words = word_tokens[start_word:end_word]
            
            # Convert back to text (approximate reconstruction)
            chunk_text = self._reconstruct_text_from_words(text, chunk_words, start_word, end_word)
            
            # Try to align with sentence boundaries
            if i > 0:  # Not first chunk
                chunk_text = self._align_chunk_start_to_sentence(chunk_text)
            
            if end_word < total_words:  # Not last chunk
                chunk_text = self._align_chunk_end_to_sentence(chunk_text)
            
            # Calculate character positions (approximate)
            char_start = self._estimate_char_position(word_tokens, start_word)
            char_end = char_start + len(chunk_text)
            
            chunk = RawChunk(
                index=len(chunks),
                text=chunk_text,
                text_clean=self._clean_text_for_search(chunk_text),
                word_count=len(chunk_words),
                char_count=len(chunk_text),
                char_start=char_start,
                char_end=char_end,
                semantic_type=self._determine_semantic_type(chunk_text, len(chunks)),
                importance_score=self._calculate_importance_score(
                    chunk_text, len(chunks), article_metadata
                ),
                strategy=ChunkingStrategy.SLIDING_WINDOW,
                boundaries=self._extract_boundaries(chunk_text, char_start)
            )
            
            chunks.append(chunk)
        
        return chunks
    
    def _create_paragraph_chunk(self, 
                              paragraphs: List[str], 
                              index: int, 
                              char_position: int, 
                              article_metadata: Dict) -> RawChunk:
        """Create a chunk from a list of paragraphs."""
        chunk_text = '\n\n'.join(paragraphs)
        word_tokens = self._tokenize_words(chunk_text)
        
        # Calculate character positions more accurately
        char_start = max(0, char_position - len(chunk_text) - 2)
        char_end = char_position
        
        return RawChunk(
            index=index,
            text=chunk_text,
            text_clean=self._clean_text_for_search(chunk_text),
            word_count=len(word_tokens),
            char_count=len(chunk_text),
            char_start=char_start,
            char_end=char_end,
            semantic_type=self._determine_semantic_type(chunk_text, index),
            importance_score=self._calculate_importance_score(chunk_text, index, article_metadata),
            strategy=ChunkingStrategy.PARAGRAPH,
            boundaries=self._extract_boundaries(chunk_text, char_start)
        )
    
    def _create_single_chunk(self, 
                           text: str, 
                           word_tokens: List[str], 
                           article_metadata: Dict) -> RawChunk:
        """Create a single chunk for short articles."""
        return RawChunk(
            index=0,
            text=text,
            text_clean=self._clean_text_for_search(text),
            word_count=len(word_tokens),
            char_count=len(text),
            char_start=0,
            char_end=len(text),
            semantic_type=self._determine_semantic_type(text, 0),
            importance_score=self._calculate_importance_score(text, 0, article_metadata),
            strategy=ChunkingStrategy.PARAGRAPH,
            boundaries=[ChunkBoundary(0, len(text), 0, len(word_tokens), 1.0, "complete")]
        )
    
    def _determine_semantic_type(self, text: str, index: int) -> SemanticType:
        """Determine semantic type of chunk based on content and position."""
        text_lower = text.lower()
        
        # First chunk is likely introduction
        if index == 0:
            return SemanticType.INTRO
        
        # Look for conclusion markers
        conclusion_markers = [
            'conclusion', 'in conclusion', 'to conclude', 'to summarize',
            'in summary', 'finally', 'in closing', 'to sum up'
        ]
        if any(marker in text_lower for marker in conclusion_markers):
            return SemanticType.CONCLUSION
        
        # Look for list patterns
        if self._list_markers.search(text) or self._numbered_list.search(text):
            list_lines = len(self._list_markers.findall(text)) + len(self._numbered_list.findall(text))
            total_lines = len(text.split('\n'))
            if list_lines / max(total_lines, 1) > 0.3:  # >30% of lines are list items
                return SemanticType.LIST
        
        # Look for quote patterns  
        if self._quote_blocks.search(text):
            quote_lines = len(self._quote_blocks.findall(text))
            total_lines = len(text.split('\n'))
            if quote_lines / max(total_lines, 1) > 0.5:  # >50% of lines are quotes
                return SemanticType.QUOTE
        
        # Look for code patterns
        if self._code_blocks.search(text):
            return SemanticType.CODE
        
        # Default to body content
        return SemanticType.BODY
    
    def _calculate_importance_score(self, 
                                  text: str, 
                                  index: int, 
                                  article_metadata: Dict) -> float:
        """Calculate importance score for chunk (0.0-1.0)."""
        score = 0.5  # Base score
        
        # Position-based scoring
        if index == 0:
            score += 0.3  # First chunk is important
        elif index == 1:
            score += 0.1  # Second chunk somewhat important
        
        # Content-based scoring
        semantic_type = self._determine_semantic_type(text, index)
        if semantic_type == SemanticType.INTRO:
            score += 0.2
        elif semantic_type == SemanticType.CONCLUSION:
            score += 0.15
        elif semantic_type == SemanticType.QUOTE:
            score += 0.1
        elif semantic_type == SemanticType.LIST:
            score -= 0.05  # Lists typically less important
        
        # Title keyword overlap
        title = article_metadata.get('title', '').lower()
        if title:
            title_words = set(self._tokenize_words(title))
            text_words = set(self._tokenize_words(text.lower()))
            if title_words and text_words:
                overlap = len(title_words & text_words) / len(title_words)
                score += overlap * 0.2
        
        # Length-based adjustment
        word_count = len(self._tokenize_words(text))
        if word_count < 100:
            score -= 0.1  # Very short chunks less important
        elif word_count > 400:
            score += 0.05  # Longer chunks might be more detailed
        
        # Boilerplate detection penalty
        if self._is_likely_boilerplate(text):
            score -= 0.3
        
        return max(0.0, min(1.0, score))
    
    def _is_likely_boilerplate(self, text: str) -> bool:
        """Check if text is likely boilerplate content."""
        text_lower = text.lower()
        
        # Check against boilerplate patterns
        for pattern in self._boilerplate_patterns:
            if pattern.search(text_lower):
                return True
        
        # Check for repetitive patterns
        words = self._tokenize_words(text_lower)
        if len(words) < 20:  # Short text, check word repetition
            word_freq = {}
            for word in words:
                word_freq[word] = word_freq.get(word, 0) + 1
            
            # If any word appears >30% of the time, likely boilerplate
            max_freq = max(word_freq.values()) if word_freq else 0
            if max_freq / len(words) > 0.3:
                return True
        
        return False
    
    def _clean_text_for_search(self, text: str) -> str:
        """Clean text for search indexing."""
        # Remove excessive whitespace
        clean_text = re.sub(r'\s+', ' ', text)
        
        # Remove special characters that might interfere with FTS
        clean_text = re.sub(r'[^\w\s\-.,!?;:()\[\]{}"\'/]', ' ', clean_text)
        
        return clean_text.strip()
    
    def _extract_boundaries(self, text: str, char_start: int) -> List[ChunkBoundary]:
        """Extract potential boundaries within chunk for later refinement."""
        boundaries = []
        
        # Sentence boundaries
        for match in self._sentence_split.finditer(text):
            boundaries.append(ChunkBoundary(
                start_char=char_start + match.start(),
                end_char=char_start + match.end(),
                start_word=0,  # Would need more complex calculation
                end_word=0,
                confidence=0.8,
                boundary_type="sentence"
            ))
        
        # Paragraph boundaries
        for match in self._paragraph_split.finditer(text):
            boundaries.append(ChunkBoundary(
                start_char=char_start + match.start(),
                end_char=char_start + match.end(),
                start_word=0,
                end_word=0,
                confidence=0.9,
                boundary_type="paragraph"
            ))
        
        return boundaries
    
    def _get_overlap_paragraphs(self, paragraphs: List[str], target_overlap_words: int) -> List[str]:
        """Get paragraphs for overlap between chunks."""
        if not paragraphs or target_overlap_words <= 0:
            return []
        
        # Start from the last paragraph and work backwards
        overlap_paragraphs = []
        word_count = 0
        
        for paragraph in reversed(paragraphs):
            para_words = len(self._tokenize_words(paragraph))
            if word_count + para_words <= target_overlap_words:
                overlap_paragraphs.insert(0, paragraph)  # Maintain order
                word_count += para_words
            else:
                break
        
        return overlap_paragraphs
    
    def _merge_chunks(self, chunk: RawChunk, additional_paragraphs: List[str]) -> RawChunk:
        """Merge additional paragraphs into existing chunk."""
        additional_text = '\n\n'.join(additional_paragraphs)
        merged_text = chunk.text + '\n\n' + additional_text
        merged_words = self._tokenize_words(merged_text)
        
        # Create new chunk with merged content
        return RawChunk(
            index=chunk.index,
            text=merged_text,
            text_clean=self._clean_text_for_search(merged_text),
            word_count=len(merged_words),
            char_count=len(merged_text),
            char_start=chunk.char_start,
            char_end=chunk.char_end + len(additional_text) + 2,
            semantic_type=chunk.semantic_type,
            importance_score=chunk.importance_score,
            strategy=chunk.strategy,
            boundaries=chunk.boundaries
        )
    
    def _reconstruct_text_from_words(self, 
                                   original_text: str, 
                                   words: List[str], 
                                   start_word: int, 
                                   end_word: int) -> str:
        """Reconstruct text from word tokens (approximate)."""
        # This is a simplified reconstruction
        # In a production system, you'd want to preserve exact spacing/punctuation
        return ' '.join(words)
    
    def _align_chunk_start_to_sentence(self, text: str) -> str:
        """Align chunk start to sentence boundary."""
        # Find first sentence boundary
        match = self._sentence_split.search(text)
        if match and match.start() < len(text) // 3:  # Only if within first third
            return text[match.end():].strip()
        return text
    
    def _align_chunk_end_to_sentence(self, text: str) -> str:
        """Align chunk end to sentence boundary."""
        # Find last complete sentence
        matches = list(self._sentence_split.finditer(text))
        if matches:
            last_sentence_end = matches[-1].end()
            if last_sentence_end > len(text) * 2 // 3:  # Only if in last third
                return text[:last_sentence_end].strip()
        return text
    
    def _estimate_char_position(self, word_tokens: List[str], word_index: int) -> int:
        """Estimate character position from word index."""
        # Simple estimation: assume average word length + 1 space
        avg_word_length = 5
        return word_index * (avg_word_length + 1)
    
    def _post_process_chunks(self, chunks: List[RawChunk], article_metadata: Dict) -> List[RawChunk]:
        """Post-process chunks to identify quality issues."""
        for chunk in chunks:
            self._assess_chunk_quality(chunk, article_metadata)
        
        return chunks
    
    def _assess_chunk_quality(self, chunk: RawChunk, article_metadata: Dict) -> None:
        """Assess chunk quality and mark for review if needed."""
        reasons = []
        
        # Size checks
        target_ratio = chunk.word_count / self.target_words
        if target_ratio < 0.5:
            reasons.append("too_short")
        elif target_ratio > 1.5:
            reasons.append("too_long")
        
        # Sentence completeness check (simplified)
        text = chunk.text.strip()
        if text and not re.match(r'^[A-Z]', text):
            reasons.append("incomplete_sentence_start")
        if text and not re.search(r'[.!?]$', text):
            reasons.append("incomplete_sentence_end")
        
        # Boilerplate check
        if self._is_likely_boilerplate(chunk.text):
            reasons.append("boilerplate_detected")
        
        # List/quote boundary check
        if chunk.semantic_type == SemanticType.LIST:
            if not (self._list_markers.search(chunk.text) or self._numbered_list.search(chunk.text)):
                reasons.append("list_boundary_broken")
        
        if chunk.semantic_type == SemanticType.QUOTE:
            if not self._quote_blocks.search(chunk.text):
                reasons.append("quote_boundary_broken")
        
        # Update chunk with review assessment
        chunk.needs_review = len(reasons) > 0
        chunk.review_reasons = reasons