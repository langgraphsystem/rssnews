"""
Tests for quality routing functionality.
"""

import pytest
from src.chunking.quality_router import QualityRouter, RoutingDecision
from src.chunking.base_chunker import BaseChunker, RawChunk
from tests.conftest import create_test_article_metadata, create_test_chunk


class TestQualityRouter:
    """Test suite for QualityRouter."""
    
    def test_router_initialization(self, test_settings):
        """Test router initializes correctly."""
        router = QualityRouter(test_settings)
        
        assert router.confidence_min == test_settings.chunking.confidence_min
        assert router.settings == test_settings
    
    def test_simple_chunks_skip_llm(self, test_settings):
        """Test simple chunks are marked to skip LLM processing."""
        router = QualityRouter(test_settings)
        
        # Create simple chunks
        chunks = [
            RawChunk(
                index=0,
                text="This is a simple paragraph with normal content.",
                char_start=0,
                char_end=50,
                word_count=9
            ),
            RawChunk(
                index=1, 
                text="Another simple paragraph with straightforward text.",
                char_start=51,
                char_end=102,
                word_count=8
            )
        ]
        
        metadata = create_test_article_metadata()
        decisions = router.route_chunks(chunks, metadata, {})
        
        assert len(decisions) == len(chunks)
        
        for chunk, decision in decisions:
            assert isinstance(decision, RoutingDecision)
            # Simple chunks should not need LLM
            assert decision.needs_llm == False
            assert decision.confidence > 0.5
    
    def test_complex_chunks_trigger_llm(self, test_settings):
        """Test complex chunks trigger LLM processing."""
        router = QualityRouter(test_settings)
        
        # Create complex chunks
        chunks = [
            RawChunk(
                index=0,
                text="""Complex content with lists:
• First bullet point
• Second bullet point
• Third bullet point""",
                char_start=0,
                char_end=100,
                word_count=15
            ),
            RawChunk(
                index=1,
                text="""Code block example:
```python
def example():
    return "hello"
```""",
                char_start=101,
                char_end=180,
                word_count=12
            ),
            RawChunk(
                index=2,
                text="""Table content:
| Column 1 | Column 2 |
|----------|----------|
| Value A  | Value B  |""",
                char_start=181,
                char_end=250,
                word_count=16
            )
        ]
        
        metadata = create_test_article_metadata()
        decisions = router.route_chunks(chunks, metadata, {})
        
        # At least some chunks should trigger LLM
        llm_chunks = [decision for _, decision in decisions if decision.needs_llm]
        assert len(llm_chunks) > 0
        
        # Check reasons are provided
        for chunk, decision in decisions:
            if decision.needs_llm:
                assert len(decision.reasons) > 0
                assert decision.confidence >= 0.0
    
    def test_boundary_issues_detection(self, test_settings):
        """Test detection of chunks with boundary issues."""
        router = QualityRouter(test_settings)
        
        # Create chunks with potential boundary issues
        chunks = [
            RawChunk(
                index=0,
                text="This chunk ends mid-sent",  # Cut off mid-sentence
                char_start=0,
                char_end=25,
                word_count=5
            ),
            RawChunk(
                index=1,
                text="ence and continues here.",  # Continues mid-word
                char_start=25,
                char_end=50,
                word_count=4
            ),
            RawChunk(
                index=2,
                text="A",  # Very short chunk
                char_start=51,
                char_end=52,
                word_count=1
            )
        ]
        
        metadata = create_test_article_metadata()
        decisions = router.route_chunks(chunks, metadata, {})
        
        # Should detect boundary issues
        boundary_issues = []
        for chunk, decision in decisions:
            if any("boundary" in reason.lower() or "incomplete" in reason.lower() 
                   for reason in decision.reasons):
                boundary_issues.append((chunk, decision))
        
        assert len(boundary_issues) > 0
    
    def test_size_based_routing(self, test_settings):
        """Test routing based on chunk size."""
        router = QualityRouter(test_settings)
        
        # Create chunks of different sizes
        chunks = [
            RawChunk(
                index=0,
                text="Short",  # Very short
                char_start=0,
                char_end=5,
                word_count=1
            ),
            RawChunk(
                index=1,
                text=" ".join(["word"] * test_settings.chunking.target_words),  # Target size
                char_start=6,
                char_end=1000,
                word_count=test_settings.chunking.target_words
            ),
            RawChunk(
                index=2,
                text=" ".join(["word"] * (test_settings.chunking.max_words + 10)),  # Oversized
                char_start=1001,
                char_end=5000,
                word_count=test_settings.chunking.max_words + 10
            )
        ]
        
        metadata = create_test_article_metadata()
        decisions = router.route_chunks(chunks, metadata, {})
        
        # Very short and oversized chunks should trigger LLM
        short_chunk_decision = decisions[0][1]
        target_chunk_decision = decisions[1][1]
        oversized_chunk_decision = decisions[2][1]
        
        assert short_chunk_decision.needs_llm  # Too short
        assert not target_chunk_decision.needs_llm  # Just right
        assert oversized_chunk_decision.needs_llm  # Too long
    
    def test_rate_limiting_consideration(self, test_settings):
        """Test rate limiting affects routing decisions."""
        # Reduce rate limits for this test
        test_settings.rate_limit.max_llm_calls_per_batch = 2
        test_settings.rate_limit.max_llm_percentage_per_batch = 0.3
        
        router = QualityRouter(test_settings)
        
        # Create many chunks that would normally trigger LLM
        chunks = []
        for i in range(10):
            chunk = RawChunk(
                index=i,
                text=f"• Bullet point {i}\n• Another bullet\n• Third bullet",  # Complex content
                char_start=i*100,
                char_end=(i+1)*100,
                word_count=10
            )
            chunks.append(chunk)
        
        metadata = create_test_article_metadata()
        batch_context = {'batch_size': len(chunks)}
        
        decisions = router.route_chunks(chunks, metadata, batch_context)
        
        # Should limit number of LLM chunks due to rate limiting
        llm_count = sum(1 for _, decision in decisions if decision.needs_llm)
        
        # Should respect max percentage (30% of 10 = 3 max)
        assert llm_count <= 3
        
        # Should prioritize by confidence/complexity
        llm_decisions = [(chunk, decision) for chunk, decision in decisions 
                        if decision.needs_llm]
        
        for chunk, decision in llm_decisions:
            assert decision.priority > 0.5  # High priority chunks should be selected
    
    def test_content_type_detection(self, test_settings):
        """Test detection of different content types."""
        router = QualityRouter(test_settings)
        
        chunks_by_type = {
            'list': RawChunk(
                index=0,
                text="• Item 1\n• Item 2\n• Item 3",
                char_start=0, char_end=30, word_count=6
            ),
            'code': RawChunk(
                index=1,
                text="```python\ndef func():\n    pass\n```",
                char_start=31, char_end=70, word_count=6
            ),
            'table': RawChunk(
                index=2,
                text="| Header | Value |\n|--------|-------|\n| A | B |",
                char_start=71, char_end=120, word_count=8
            ),
            'quote': RawChunk(
                index=3,
                text='"This is a quoted section that might need special handling."',
                char_start=121, char_end=180, word_count=12
            ),
            'normal': RawChunk(
                index=4,
                text="This is normal paragraph text without special formatting.",
                char_start=181, char_end=240, word_count=10
            )
        }
        
        chunks = list(chunks_by_type.values())
        metadata = create_test_article_metadata()
        decisions = router.route_chunks(chunks, metadata, {})
        
        # Check content type detection
        decision_by_type = {}
        for chunk, decision in decisions:
            if chunk == chunks_by_type['list']:
                decision_by_type['list'] = decision
            elif chunk == chunks_by_type['code']:
                decision_by_type['code'] = decision
            elif chunk == chunks_by_type['table']:
                decision_by_type['table'] = decision
            elif chunk == chunks_by_type['quote']:
                decision_by_type['quote'] = decision
            elif chunk == chunks_by_type['normal']:
                decision_by_type['normal'] = decision
        
        # Structured content should trigger LLM
        assert decision_by_type['list'].needs_llm
        assert decision_by_type['code'].needs_llm
        assert decision_by_type['table'].needs_llm
        
        # Normal content should not trigger LLM
        assert not decision_by_type['normal'].needs_llm
    
    def test_priority_calculation(self, test_settings):
        """Test priority calculation for chunks."""
        router = QualityRouter(test_settings)
        
        chunks = [
            RawChunk(  # High priority - multiple issues
                index=0,
                text="• Incomplete list\n• Second it",  # List + boundary issue
                char_start=0, char_end=30, word_count=5
            ),
            RawChunk(  # Medium priority - single issue
                index=1,
                text="```python\ndef complete_function():\n    return True\n```",
                char_start=31, char_end=80, word_count=8
            ),
            RawChunk(  # Low priority - normal content
                index=2,
                text="This is a normal paragraph with standard content.",
                char_start=81, char_end=130, word_count=10
            )
        ]
        
        metadata = create_test_article_metadata()
        decisions = router.route_chunks(chunks, metadata, {})
        
        priorities = [decision.priority for _, decision in decisions]
        
        # First chunk (multiple issues) should have highest priority
        assert priorities[0] > priorities[1]
        assert priorities[1] > priorities[2]
    
    def test_confidence_thresholding(self, test_settings):
        """Test confidence-based filtering."""
        # Set high confidence threshold
        test_settings.chunking.confidence_min = 0.8
        
        router = QualityRouter(test_settings)
        
        chunks = [
            RawChunk(  # Clear case - should exceed threshold
                index=0,
                text="• Very clear bullet list\n• With proper formatting\n• Multiple items",
                char_start=0, char_end=60, word_count=10
            ),
            RawChunk(  # Borderline case - might not exceed threshold
                index=1,
                text="Some text that could maybe use refinement or maybe not.",
                char_start=61, char_end=115, word_count=11
            )
        ]
        
        metadata = create_test_article_metadata()
        decisions = router.route_chunks(chunks, metadata, {})
        
        # Only high-confidence decisions should trigger LLM
        for chunk, decision in decisions:
            if decision.needs_llm:
                assert decision.confidence >= test_settings.chunking.confidence_min
    
    def test_batch_context_influence(self, test_settings):
        """Test how batch context influences routing."""
        router = QualityRouter(test_settings)
        
        chunks = [
            RawChunk(
                index=0,
                text="• Bullet point item",
                char_start=0, char_end=20, word_count=3
            )
        ]
        
        metadata = create_test_article_metadata()
        
        # Test with high-load batch context
        high_load_context = {
            'batch_size': 100,
            'current_llm_usage': 80,
            'system_load': 'high'
        }
        
        decisions_high_load = router.route_chunks(chunks, metadata, high_load_context)
        
        # Test with normal batch context
        normal_context = {
            'batch_size': 10,
            'current_llm_usage': 5,
            'system_load': 'normal'
        }
        
        decisions_normal = router.route_chunks(chunks, metadata, normal_context)
        
        # High load should be more conservative with LLM usage
        high_load_llm_count = sum(1 for _, d in decisions_high_load if d.needs_llm)
        normal_llm_count = sum(1 for _, d in decisions_normal if d.needs_llm)
        
        assert high_load_llm_count <= normal_llm_count
    
    def test_edge_cases(self, test_settings):
        """Test edge cases and error handling."""
        router = QualityRouter(test_settings)
        
        # Empty chunks list
        decisions = router.route_chunks([], {}, {})
        assert decisions == []
        
        # Chunks with empty text
        empty_chunks = [
            RawChunk(index=0, text="", char_start=0, char_end=0, word_count=0),
            RawChunk(index=1, text="   ", char_start=1, char_end=4, word_count=0)
        ]
        
        metadata = create_test_article_metadata()
        decisions = router.route_chunks(empty_chunks, metadata, {})
        
        # Should handle empty chunks gracefully
        assert len(decisions) == len(empty_chunks)
        
        for chunk, decision in decisions:
            assert isinstance(decision, RoutingDecision)
            # Empty chunks should not trigger LLM
            assert not decision.needs_llm
    
    def test_routing_decision_properties(self, test_settings):
        """Test RoutingDecision object properties."""
        router = QualityRouter(test_settings)
        
        chunks = [
            RawChunk(
                index=0,
                text="• Test bullet point",
                char_start=0, char_end=20, word_count=3
            )
        ]
        
        metadata = create_test_article_metadata()
        decisions = router.route_chunks(chunks, metadata, {})
        
        decision = decisions[0][1]
        
        # Verify decision properties
        assert isinstance(decision.needs_llm, bool)
        assert isinstance(decision.confidence, float)
        assert 0.0 <= decision.confidence <= 1.0
        assert isinstance(decision.priority, float)
        assert 0.0 <= decision.priority <= 1.0
        assert isinstance(decision.reasons, list)
        assert isinstance(decision.estimated_tokens, int)
        assert decision.estimated_tokens >= 0