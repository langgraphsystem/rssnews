"""
Unit tests for CompetitorNews agent (Phase 2)
Tests domain extraction, Jaccard similarity, stance classification
"""

import pytest
from core.agents.competitor_news import (
    extract_domain,
    compute_jaccard_similarity,
    classify_stance,
    run_competitor_news,
)


class TestDomainExtraction:
    """Test domain extraction from URLs"""

    def test_extract_domain_https(self):
        """Test domain extraction from HTTPS URL"""
        assert extract_domain("https://techcrunch.com/article/123") == "techcrunch.com"

    def test_extract_domain_http(self):
        """Test domain extraction from HTTP URL"""
        assert extract_domain("http://example.com/path") == "example.com"

    def test_extract_domain_subdomain(self):
        """Test domain extraction with subdomain"""
        domain = extract_domain("https://blog.example.com/article")
        assert "example.com" in domain

    def test_extract_domain_invalid_url(self):
        """Test domain extraction with invalid URL"""
        assert extract_domain("not-a-url") is None

    def test_extract_domain_none(self):
        """Test domain extraction with None"""
        assert extract_domain(None) is None


class TestJaccardSimilarity:
    """Test Jaccard similarity computation"""

    def test_jaccard_identical_sets(self):
        """Test Jaccard for identical sets"""
        set1 = {"AI", "ML", "NLP"}
        set2 = {"AI", "ML", "NLP"}
        assert compute_jaccard_similarity(set1, set2) == 1.0

    def test_jaccard_disjoint_sets(self):
        """Test Jaccard for disjoint sets"""
        set1 = {"AI", "ML"}
        set2 = {"blockchain", "crypto"}
        assert compute_jaccard_similarity(set1, set2) == 0.0

    def test_jaccard_partial_overlap(self):
        """Test Jaccard for partial overlap"""
        set1 = {"AI", "ML", "NLP"}
        set2 = {"AI", "blockchain"}
        similarity = compute_jaccard_similarity(set1, set2)
        assert 0.0 < similarity < 1.0
        assert similarity == 1 / 4  # 1 common / 4 total

    def test_jaccard_empty_sets(self):
        """Test Jaccard for empty sets"""
        assert compute_jaccard_similarity(set(), set()) == 0.0


class TestStanceClassification:
    """Test competitive stance classification"""

    def test_classify_stance_leader(self):
        """Test stance classification for leader"""
        stance = classify_stance("techcrunch.com", domain_article_count=15, total_articles=50, topic_diversity=8)
        assert stance == "leader"

    def test_classify_stance_fast_follower(self):
        """Test stance classification for fast follower"""
        stance = classify_stance("example.com", domain_article_count=8, total_articles=50, topic_diversity=4)
        assert stance == "fast_follower"

    def test_classify_stance_niche(self):
        """Test stance classification for niche player"""
        stance = classify_stance("small.com", domain_article_count=2, total_articles=50, topic_diversity=1)
        assert stance == "niche"


@pytest.mark.asyncio
class TestRunCompetitorNews:
    """Integration tests for run_competitor_news"""

    async def test_competitors_with_domains(self):
        """Test competitor analysis with specified domains"""
        docs = [
            {
                "article_id": "art-1",
                "title": "AI Article 1",
                "url": "https://techcrunch.com/ai-1",
                "date": "2025-01-01",
                "content": "AI ML NLP",
            },
            {
                "article_id": "art-2",
                "title": "AI Article 2",
                "url": "https://techcrunch.com/ai-2",
                "date": "2025-01-02",
                "content": "AI deep learning",
            },
            {
                "article_id": "art-3",
                "title": "Blockchain Article",
                "url": "https://coindesk.com/crypto-1",
                "date": "2025-01-01",
                "content": "blockchain crypto",
            },
        ]
        result = await run_competitor_news(
            docs, domains=["techcrunch.com", "coindesk.com"], niche=None, correlation_id="test-comp-1"
        )

        assert result["success"] is True
        assert "overlap_matrix" in result
        assert "positioning" in result
        assert "top_domains" in result
        assert len(result["positioning"]) >= 1

    async def test_competitors_with_niche(self):
        """Test competitor analysis with niche filter"""
        docs = [
            {
                "article_id": f"art-{i}",
                "title": f"AI Article {i}",
                "url": f"https://example{i}.com/ai",
                "date": "2025-01-01",
                "content": "AI machine learning",
            }
            for i in range(10)
        ]
        result = await run_competitor_news(docs, domains=None, niche="AI", correlation_id="test-comp-2")

        assert result["success"] is True
        assert len(result["top_domains"]) >= 1

    async def test_competitors_gaps_detection(self):
        """Test gap detection in competitor analysis"""
        docs = [
            {
                "article_id": "art-1",
                "title": "AI Article",
                "url": "https://techcrunch.com/ai",
                "date": "2025-01-01",
                "content": "AI ML",
            },
            {
                "article_id": "art-2",
                "title": "Blockchain Article",
                "url": "https://coindesk.com/crypto",
                "date": "2025-01-01",
                "content": "blockchain crypto",
            },
        ]
        result = await run_competitor_news(docs, domains=None, niche=None, correlation_id="test-comp-3")

        assert result["success"] is True
        # Gaps should be detected for uncovered topics
        assert "gaps" in result

    async def test_competitors_overlap_matrix(self):
        """Test overlap matrix construction"""
        docs = [
            {
                "article_id": "art-1",
                "title": "AI Article",
                "url": "https://techcrunch.com/ai",
                "date": "2025-01-01",
                "content": "AI ML NLP",
            },
            {
                "article_id": "art-2",
                "title": "AI Article 2",
                "url": "https://wired.com/ai",
                "date": "2025-01-01",
                "content": "AI deep learning",
            },
        ]
        result = await run_competitor_news(docs, domains=None, niche=None, correlation_id="test-comp-4")

        assert result["success"] is True
        assert len(result["overlap_matrix"]) >= 1
        for overlap in result["overlap_matrix"]:
            assert 0.0 <= overlap["overlap_score"] <= 1.0
            assert len(overlap["domain"]) > 0
            assert len(overlap["topic"]) > 0
