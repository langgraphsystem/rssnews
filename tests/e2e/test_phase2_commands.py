"""
End-to-end tests for Phase 2 commands
Tests full pipeline with real components (mocked external services)
"""

import pytest
from datetime import datetime, timedelta
from services.orchestrator import (
    execute_predict_trends_command,
    execute_analyze_competitors_command,
    execute_synthesize_command,
)


@pytest.mark.asyncio
class TestPhase2E2E:
    """E2E tests for Phase 2 commands"""

    async def test_predict_trends_e2e(self, monkeypatch):
        """E2E test for /predict trends command"""
        # Mock retrieval to return test docs
        async def mock_retrieval_node(state):
            state["docs"] = [
                {
                    "article_id": f"art-{i}",
                    "title": f"AI Trends Article {i}",
                    "url": f"https://example.com/ai-{i}",
                    "date": (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d"),
                    "content": "AI and machine learning continue to evolve rapidly with new innovations",
                }
                for i in range(15)
            ]
            return state

        monkeypatch.setattr("core.orchestrator.nodes.retrieval_node.retrieval_node", mock_retrieval_node)

        # Execute command through service layer
        payload = await execute_predict_trends_command(
            topic="AI",
            window="1w",
            k_final=5,
            correlation_id="e2e-predict-1"
        )

        # Validate payload structure (Telegram-ready format)
        assert "text" in payload
        assert "buttons" in payload
        assert "parse_mode" in payload
        assert payload["parse_mode"] == "Markdown"

        # Validate context
        assert "context" in payload
        context = payload["context"]
        assert context["command"] == "predict"
        assert context["topic"] == "AI"
        assert context["window"] == "1w"
        assert context["correlation_id"] == "e2e-predict-1"

        # Validate text contains forecast info
        text = payload["text"]
        assert "📈" in text or "📉" in text or "➡️" in text  # Direction emoji

    async def test_analyze_competitors_e2e(self, monkeypatch):
        """E2E test for /analyze competitors command"""
        async def mock_retrieval_node(state):
            state["docs"] = [
                {
                    "article_id": "art-1",
                    "title": "TechCrunch AI Article",
                    "url": "https://techcrunch.com/ai-1",
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "content": "AI machine learning deep learning neural networks",
                },
                {
                    "article_id": "art-2",
                    "title": "Wired AI Article",
                    "url": "https://wired.com/ai-2",
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "content": "AI innovation ML algorithms",
                },
                {
                    "article_id": "art-3",
                    "title": "VentureBeat AI Article",
                    "url": "https://venturebeat.com/ai-3",
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "content": "AI startups machine learning",
                },
                {
                    "article_id": "art-4",
                    "title": "CoinDesk Crypto Article",
                    "url": "https://coindesk.com/crypto-1",
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "content": "blockchain cryptocurrency web3",
                },
            ]
            return state

        monkeypatch.setattr("core.orchestrator.nodes.retrieval_node.retrieval_node", mock_retrieval_node)

        payload = await execute_analyze_competitors_command(
            domains=["techcrunch.com", "wired.com", "venturebeat.com", "coindesk.com"],
            niche=None,
            window="1w",
            k_final=10,
            correlation_id="e2e-competitors-1"
        )

        # Validate payload
        assert "text" in payload
        assert "buttons" in payload
        assert "context" in payload

        context = payload["context"]
        assert context["command"] == "competitors"
        assert "techcrunch.com" in context["domains"]

        # Validate text contains competitor info
        text = payload["text"]
        assert "🏆" in text  # Competitive analysis emoji

    async def test_synthesize_e2e(self, monkeypatch):
        """E2E test for /synthesize command"""
        # Prepare agent outputs from previous commands
        agent_outputs = {
            "topic_modeler": {
                "topics": [
                    {"label": "AI Innovation", "terms": ["AI", "ML", "NLP"], "size": 20, "trend": "rising"},
                    {"label": "Blockchain Tech", "terms": ["blockchain", "crypto"], "size": 10, "trend": "stable"},
                ],
                "emerging": ["LLMs", "AGI", "Quantum AI"],
            },
            "sentiment_emotion": {
                "overall": 0.65,
                "emotions": {"joy": 0.7, "fear": 0.1, "anger": 0.05, "sadness": 0.05, "surprise": 0.1},
                "aspects": [
                    {"name": "innovation", "score": 0.8},
                    {"name": "regulation", "score": -0.3},
                ],
            },
            "keyphrase_mining": {
                "keyphrases": [
                    {"phrase": "AI revolution", "norm": "ai revolution", "score": 0.95, "ngram": 2, "lang": "en"},
                    {"phrase": "machine learning", "norm": "machine learning", "score": 0.9, "ngram": 2, "lang": "en"},
                    {"phrase": "deep learning", "norm": "deep learning", "score": 0.85, "ngram": 2, "lang": "en"},
                ]
            },
            "_docs": [
                {
                    "article_id": "art-1",
                    "title": "AI Innovation Report",
                    "url": "https://example.com/ai-1",
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "content": "AI is transforming industries with unprecedented speed",
                },
                {
                    "article_id": "art-2",
                    "title": "Blockchain Adoption",
                    "url": "https://example.com/crypto-1",
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "content": "Blockchain technology sees steady adoption in enterprise",
                },
            ]
        }

        payload = await execute_synthesize_command(
            agent_outputs=agent_outputs,
            window="24h",
            correlation_id="e2e-synthesize-1"
        )

        # Validate payload
        assert "text" in payload
        assert "buttons" in payload
        assert "context" in payload

        context = payload["context"]
        assert context["command"] == "synthesize"
        assert context["correlation_id"] == "e2e-synthesize-1"

        # Validate text contains synthesis info
        text = payload["text"]
        assert "🔗" in text  # Synthesis emoji

    async def test_predict_error_handling_e2e(self, monkeypatch):
        """E2E test for error handling in /predict trends"""
        # Mock retrieval to return no docs
        async def mock_retrieval_node(state):
            state["docs"] = []
            return state

        monkeypatch.setattr("core.orchestrator.nodes.retrieval_node.retrieval_node", mock_retrieval_node)

        payload = await execute_predict_trends_command(
            topic="NonexistentTopic",
            window="1w",
            k_final=5,
            correlation_id="e2e-predict-error-1"
        )

        # Should return error payload
        assert "text" in payload
        text = payload["text"]
        assert "❌" in text or "Ошибка" in text  # Error indicator

    async def test_competitors_error_handling_e2e(self, monkeypatch):
        """E2E test for error handling in /analyze competitors"""
        async def mock_retrieval_node(state):
            state["docs"] = []
            return state

        monkeypatch.setattr("core.orchestrator.nodes.retrieval_node.retrieval_node", mock_retrieval_node)

        payload = await execute_analyze_competitors_command(
            domains=["nonexistent.com"],
            niche=None,
            window="1w",
            k_final=10,
            correlation_id="e2e-competitors-error-1"
        )

        # Should return error payload
        assert "text" in payload
        text = payload["text"]
        assert "❌" in text or "Ошибка" in text


@pytest.mark.asyncio
class TestPhase2CommandChaining:
    """Test command chaining scenarios"""

    async def test_predict_then_synthesize(self, monkeypatch):
        """Test running /predict then /synthesize on results"""
        # Mock retrieval
        async def mock_retrieval_node(state):
            state["docs"] = [
                {
                    "article_id": f"art-{i}",
                    "title": f"Article {i}",
                    "url": f"https://example.com/{i}",
                    "date": (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d"),
                    "content": "AI trends content",
                }
                for i in range(10)
            ]
            return state

        monkeypatch.setattr("core.orchestrator.nodes.retrieval_node.retrieval_node", mock_retrieval_node)

        # Step 1: Run /predict
        predict_payload = await execute_predict_trends_command(
            topic="AI",
            window="1w",
            k_final=5,
            correlation_id="chain-predict-1"
        )

        assert "context" in predict_payload

        # Step 2: Simulate agent outputs for synthesis
        agent_outputs = {
            "trend_forecaster": {
                "forecast": [
                    {
                        "topic": "AI",
                        "direction": "up",
                        "confidence_interval": (0.6, 0.8),
                        "drivers": [],
                        "horizon": "1w"
                    }
                ]
            },
            "sentiment_emotion": {"overall": 0.5},
            "_docs": [
                {
                    "article_id": "art-1",
                    "title": "Article",
                    "url": "https://example.com/1",
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "content": "Content",
                }
            ]
        }

        # Step 3: Run /synthesize
        synthesize_payload = await execute_synthesize_command(
            agent_outputs=agent_outputs,
            window="24h",
            correlation_id="chain-synthesize-1"
        )

        assert "context" in synthesize_payload
        assert "text" in synthesize_payload
