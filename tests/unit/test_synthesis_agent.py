"""
Unit tests for SynthesisAgent (Phase 2)
Tests conflict detection, action generation, meta-analysis
"""

import pytest
from core.agents.synthesis_agent import (
    detect_conflicts,
    generate_actions,
    run_synthesis_agent,
)


class TestConflictDetection:
    """Test conflict detection logic"""

    def test_detect_sentiment_trend_conflict(self):
        """Test detection of sentiment-trend conflict"""
        agent_outputs = {
            "sentiment_emotion": {
                "overall": -0.6,  # Negative sentiment
                "emotions": {"joy": 0.1, "fear": 0.5, "anger": 0.3, "sadness": 0.1, "surprise": 0.0},
            },
            "topic_modeler": {
                "topics": [
                    {"label": "AI Innovation", "terms": ["AI", "ML"], "size": 10, "trend": "rising"}
                ]
            },
        }
        docs = [
            {
                "article_id": "art-1",
                "title": "AI Article",
                "url": "https://example.com/ai",
                "date": "2025-01-01",
                "content": "AI is concerning",
            }
        ]

        conflicts = detect_conflicts(agent_outputs, docs)
        assert len(conflicts) >= 1
        assert any("negative" in c["description"].lower() for c in conflicts)

    def test_detect_no_conflicts(self):
        """Test no conflicts with aligned signals"""
        agent_outputs = {
            "sentiment_emotion": {
                "overall": 0.7,  # Positive sentiment
                "emotions": {"joy": 0.8, "fear": 0.1, "anger": 0.05, "sadness": 0.05, "surprise": 0.0},
            },
            "topic_modeler": {
                "topics": [
                    {"label": "AI Innovation", "terms": ["AI", "ML"], "size": 10, "trend": "rising"}
                ]
            },
        }
        docs = [
            {
                "article_id": "art-1",
                "title": "AI Article",
                "url": "https://example.com/ai",
                "date": "2025-01-01",
                "content": "AI is exciting",
            }
        ]

        conflicts = detect_conflicts(agent_outputs, docs)
        # Should have no conflicts when sentiment and trend align
        assert len(conflicts) == 0 or "aligned" in conflicts[0]["description"].lower()

    def test_detect_conflicts_missing_data(self):
        """Test conflict detection with missing agent data"""
        agent_outputs = {}
        docs = []

        conflicts = detect_conflicts(agent_outputs, docs)
        assert isinstance(conflicts, list)  # Should return empty list, not crash


class TestActionGeneration:
    """Test action generation logic"""

    def test_generate_actions_rising_trend(self):
        """Test action generation for rising trend"""
        agent_outputs = {
            "topic_modeler": {
                "topics": [
                    {"label": "AI Innovation", "terms": ["AI", "ML"], "size": 10, "trend": "rising"}
                ],
                "emerging": ["LLMs", "AGI"],
            },
            "sentiment_emotion": {
                "overall": 0.6,
            },
        }
        docs = [
            {
                "article_id": "art-1",
                "title": "AI Article",
                "url": "https://example.com/ai",
                "date": "2025-01-01",
                "content": "AI trends",
            }
        ]
        conflicts = []

        actions = generate_actions(agent_outputs, docs, conflicts)
        assert len(actions) >= 1
        assert any(action["impact"] in ["low", "medium", "high"] for action in actions)
        assert all(len(action["evidence_refs"]) >= 1 for action in actions)

    def test_generate_actions_negative_sentiment(self):
        """Test action generation for negative sentiment"""
        agent_outputs = {
            "sentiment_emotion": {
                "overall": -0.5,
            },
            "topic_modeler": {
                "topics": [{"label": "Risks", "terms": ["risk", "concern"], "size": 5, "trend": "stable"}]
            },
        }
        docs = [
            {
                "article_id": "art-1",
                "title": "Risk Article",
                "url": "https://example.com/risk",
                "date": "2025-01-01",
                "content": "Concerns rising",
            }
        ]
        conflicts = []

        actions = generate_actions(agent_outputs, docs, conflicts)
        assert len(actions) >= 1
        # Negative sentiment should trigger risk management actions
        assert any("risk" in action["recommendation"].lower() for action in actions)

    def test_generate_actions_with_conflicts(self):
        """Test action generation with detected conflicts"""
        agent_outputs = {
            "sentiment_emotion": {"overall": -0.3},
            "topic_modeler": {"topics": []},
        }
        docs = [
            {
                "article_id": "art-1",
                "title": "Article",
                "url": "https://example.com/1",
                "date": "2025-01-01",
                "content": "Content",
            }
        ]
        conflicts = [
            {
                "description": "Negative sentiment but rising trend",
                "evidence_refs": [{"article_id": "art-1", "url": "https://example.com/1", "date": "2025-01-01"}],
            }
        ]

        actions = generate_actions(agent_outputs, docs, conflicts)
        assert len(actions) >= 1
        # Should generate actions addressing the conflict
        assert any(action["impact"] == "high" for action in actions)


@pytest.mark.asyncio
class TestRunSynthesisAgent:
    """Integration tests for run_synthesis_agent"""

    async def test_synthesis_full_flow(self):
        """Test full synthesis flow with multiple agents"""
        agent_outputs = {
            "topic_modeler": {
                "topics": [
                    {"label": "AI", "terms": ["AI", "ML"], "size": 10, "trend": "rising"},
                    {"label": "Blockchain", "terms": ["crypto", "web3"], "size": 5, "trend": "stable"},
                ],
                "emerging": ["LLMs"],
            },
            "sentiment_emotion": {
                "overall": 0.4,
                "emotions": {"joy": 0.5, "fear": 0.2, "anger": 0.1, "sadness": 0.1, "surprise": 0.1},
            },
            "keyphrase_mining": {
                "keyphrases": [
                    {"phrase": "AI revolution", "norm": "ai revolution", "score": 0.9, "ngram": 2, "lang": "en"}
                ]
            },
        }
        docs = [
            {
                "article_id": "art-1",
                "title": "AI Innovation",
                "url": "https://example.com/ai",
                "date": "2025-01-01",
                "content": "AI is transforming industries",
            },
            {
                "article_id": "art-2",
                "title": "Crypto News",
                "url": "https://example.com/crypto",
                "date": "2025-01-01",
                "content": "Blockchain adoption growing",
            },
        ]

        result = await run_synthesis_agent(agent_outputs, docs, correlation_id="test-synth-1")

        assert result["success"] is True
        assert "summary" in result
        assert len(result["summary"]) <= 400
        assert "conflicts" in result
        assert "actions" in result
        assert 1 <= len(result["actions"]) <= 5
        assert all(action["impact"] in ["low", "medium", "high"] for action in result["actions"])

    async def test_synthesis_minimal_agents(self):
        """Test synthesis with minimal agent outputs"""
        agent_outputs = {
            "sentiment_emotion": {"overall": 0.5}
        }
        docs = [
            {
                "article_id": "art-1",
                "title": "Article",
                "url": "https://example.com/1",
                "date": "2025-01-01",
                "content": "Content",
            }
        ]

        result = await run_synthesis_agent(agent_outputs, docs, correlation_id="test-synth-2")

        assert result["success"] is True
        assert len(result["actions"]) >= 1  # Should always generate at least 1 action

    async def test_synthesis_no_docs(self):
        """Test synthesis with no documents"""
        agent_outputs = {
            "topic_modeler": {"topics": [{"label": "Test", "terms": ["test"], "size": 1, "trend": "stable"}]}
        }
        docs = []

        result = await run_synthesis_agent(agent_outputs, docs, correlation_id="test-synth-3")

        # Should handle gracefully, possibly with fallback actions
        assert result["success"] is True
        assert "summary" in result
