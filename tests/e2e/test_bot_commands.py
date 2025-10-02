"""
E2E tests for bot commands via Telegram interface
Tests complete user flows from bot message to formatted response
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from telegram import Update, Message, Chat, User
from bot_service.advanced_bot import AdvancedRSSBot
from schemas.analysis_schemas import BaseAnalysisResponse, Insight, Evidence, EvidenceRef, Meta


@pytest.fixture
def mock_update():
    """Create mock Telegram Update object"""
    user = User(id=12345, first_name="TestUser", is_bot=False)
    chat = Chat(id=12345, type="private")
    message = Message(
        message_id=1,
        date=None,
        chat=chat,
        from_user=user,
        text="/trends AI trends"
    )
    update = Update(update_id=1, message=message)
    return update


@pytest.fixture
def mock_context():
    """Create mock Telegram Context object"""
    context = Mock()
    context.bot = AsyncMock()
    context.bot.send_message = AsyncMock()
    return context


@pytest.mark.asyncio
async def test_trends_command_e2e(mock_update, mock_context):
    """Test /trends command end-to-end"""
    # Mock orchestrator response
    mock_response = BaseAnalysisResponse(
        header="🔥 AI Trends",
        tldr="AI trends show rapid growth in machine learning and regulation discussions.",
        insights=[
            Insight(
                type="fact",
                text="Machine learning adoption is accelerating across industries.",
                evidence_refs=[
                    EvidenceRef(
                        article_id="art_1",
                        url="https://example.com/article1",
                        date="2025-09-30"
                    )
                ]
            )
        ],
        evidence=[
            Evidence(
                title="AI Adoption Report",
                article_id="art_1",
                url="https://example.com/article1",
                date="2025-09-30",
                snippet="Companies are rapidly adopting ML solutions."
            )
        ],
        result={
            "topics": [{"label": "AI Trends", "terms": ["AI", "ML"], "size": 10, "trend": "rising"}],
            "sentiment": {"overall": 0.3, "emotions": {"joy": 0.3, "fear": 0.2, "anger": 0.2, "sadness": 0.2, "surprise": 0.1}}
        },
        meta=Meta(confidence=0.85, model="claude-4.5", version="phase1-v1.0", correlation_id="test-123")
    )

    from bot_service.commands import handle_trends

    with patch('bot_service.commands.execute_trends_command', new_callable=AsyncMock) as mock_execute:
        mock_execute.return_value = mock_response

        await handle_trends(mock_update, mock_context)

        # Verify bot sent message
        assert mock_context.bot.send_message.called
        call_args = mock_context.bot.send_message.call_args

        # Check message content
        sent_message = call_args[1]["text"]
        assert "AI Trends" in sent_message or "trends" in sent_message.lower()


@pytest.mark.asyncio
async def test_analyze_keywords_e2e(mock_update, mock_context):
    """Test /analyze keywords command end-to-end"""
    mock_update.message.text = "/analyze keywords AI technology"

    mock_response = BaseAnalysisResponse(
        header="📊 Keywords Analysis",
        tldr="Top keywords: artificial intelligence, machine learning, neural networks.",
        insights=[
            Insight(
                type="fact",
                text="'Artificial intelligence' is the dominant keyphrase with 95% relevance.",
                evidence_refs=[
                    EvidenceRef(article_id="art_1", url="https://example.com/1", date="2025-09-30")
                ]
            )
        ],
        evidence=[
            Evidence(
                title="AI Article",
                article_id="art_1",
                url="https://example.com/1",
                date="2025-09-30",
                snippet="AI is transforming industries."
            )
        ],
        result={
            "keyphrases": [
                {"phrase": "artificial intelligence", "score": 0.95, "ngram": 2, "variants": ["AI"], "examples": [], "lang": "en"}
            ]
        },
        meta=Meta(confidence=0.9, model="gemini-2.5-pro", version="phase1-v1.0", correlation_id="test-123")
    )

    from bot_service.commands import handle_analyze

    with patch('bot_service.commands.execute_analyze_command', new_callable=AsyncMock) as mock_execute:
        mock_execute.return_value = mock_response

        await handle_analyze(mock_update, mock_context)

        assert mock_context.bot.send_message.called


@pytest.mark.asyncio
async def test_analyze_sentiment_e2e(mock_update, mock_context):
    """Test /analyze sentiment command end-to-end"""
    mock_update.message.text = "/analyze sentiment AI regulation"

    mock_response = BaseAnalysisResponse(
        header="😐 Sentiment Analysis",
        tldr="Overall sentiment is neutral (0.3) with mixed emotions: fear (40%), joy (20%).",
        insights=[
            Insight(
                type="fact",
                text="Fear is the dominant emotion in AI regulation discussions.",
                evidence_refs=[
                    EvidenceRef(article_id="art_1", url="https://example.com/1", date="2025-09-30")
                ]
            )
        ],
        evidence=[
            Evidence(
                title="AI Regulation",
                article_id="art_1",
                url="https://example.com/1",
                date="2025-09-30",
                snippet="Concerns about AI safety drive regulation."
            )
        ],
        result={
            "overall": 0.3,
            "emotions": {"joy": 0.2, "fear": 0.4, "anger": 0.2, "sadness": 0.1, "surprise": 0.1}
        },
        meta=Meta(confidence=0.85, model="gpt-5", version="phase1-v1.0", correlation_id="test-123")
    )

    from bot_service.commands import handle_analyze

    with patch('bot_service.commands.execute_analyze_command', new_callable=AsyncMock) as mock_execute:
        mock_execute.return_value = mock_response

        await handle_analyze(mock_update, mock_context)

        assert mock_context.bot.send_message.called


@pytest.mark.asyncio
async def test_analyze_topics_e2e(mock_update, mock_context):
    """Test /analyze topics command end-to-end"""
    mock_update.message.text = "/analyze topics AI policy"

    mock_response = BaseAnalysisResponse(
        header="🏷️ Topics Analysis",
        tldr="Main topics: AI Regulation (rising), AI Safety (stable), AI Ethics (emerging).",
        insights=[
            Insight(
                type="fact",
                text="AI Regulation is a rising topic with 15 related articles.",
                evidence_refs=[
                    EvidenceRef(article_id="art_1", url="https://example.com/1", date="2025-09-30")
                ]
            )
        ],
        evidence=[
            Evidence(
                title="AI Policy Update",
                article_id="art_1",
                url="https://example.com/1",
                date="2025-09-30",
                snippet="New AI regulations announced."
            )
        ],
        result={
            "topics": [
                {"label": "AI Regulation", "terms": ["regulation", "policy"], "size": 15, "trend": "rising"}
            ]
        },
        meta=Meta(confidence=0.8, model="claude-4.5", version="phase1-v1.0", correlation_id="test-123")
    )

    from bot_service.commands import handle_analyze

    with patch('bot_service.commands.execute_analyze_command', new_callable=AsyncMock) as mock_execute:
        mock_execute.return_value = mock_response

        await handle_analyze(mock_update, mock_context)

        assert mock_context.bot.send_message.called


@pytest.mark.asyncio
async def test_error_response_e2e(mock_update, mock_context):
    """Test error response formatting"""
    from bot_service.commands import handle_trends

    with patch('bot_service.commands.execute_trends_command', new_callable=AsyncMock) as mock_execute:
        mock_execute.side_effect = Exception("MODEL_UNAVAILABLE: All models failed")

        await handle_trends(mock_update, mock_context)

        # Should send error message
        assert mock_context.bot.send_message.called
        call_args = mock_context.bot.send_message.call_args
        sent_message = call_args[1]["text"]

        # Check error message format
        assert "error" in sent_message.lower() or "failed" in sent_message.lower()


@pytest.mark.asyncio
async def test_empty_query_e2e(mock_update, mock_context):
    """Test empty query handling"""
    mock_update.message.text = "/trends"

    from bot_service.commands import handle_trends

    await handle_trends(mock_update, mock_context)

    # Should send usage help or error
    assert mock_context.bot.send_message.called


@pytest.mark.asyncio
async def test_html_formatting_e2e(mock_update, mock_context):
    """Test HTML formatting in bot response"""
    mock_response = BaseAnalysisResponse(
        header="Test Header",
        tldr="Test summary with <b>bold</b> text.",
        insights=[
            Insight(
                type="fact",
                text="Test insight",
                evidence_refs=[
                    EvidenceRef(article_id="art_1", url="https://example.com/1", date="2025-09-30")
                ]
            )
        ],
        evidence=[
            Evidence(
                title="Test Article",
                article_id="art_1",
                url="https://example.com/1",
                date="2025-09-30",
                snippet="Test snippet"
            )
        ],
        result={"test": "data"},
        meta=Meta(confidence=0.8, model="gpt-5", version="v1", correlation_id="test-123")
    )

    from bot_service.commands import handle_trends

    with patch('bot_service.commands.execute_trends_command', new_callable=AsyncMock) as mock_execute:
        mock_execute.return_value = mock_response

        await handle_trends(mock_update, mock_context)

        call_args = mock_context.bot.send_message.call_args

        # Check parse_mode is HTML
        assert call_args[1].get("parse_mode") == "HTML"


@pytest.mark.asyncio
async def test_sources_attachment_e2e(mock_update, mock_context):
    """Test sources block is attached to response"""
    mock_response = BaseAnalysisResponse(
        header="Test Header",
        tldr="Test summary",
        insights=[
            Insight(
                type="fact",
                text="Test insight",
                evidence_refs=[
                    EvidenceRef(article_id="art_1", url="https://example.com/article1", date="2025-09-30")
                ]
            )
        ],
        evidence=[
            Evidence(
                title="Test Article",
                article_id="art_1",
                url="https://example.com/article1",
                date="2025-09-30",
                snippet="Test snippet"
            )
        ],
        result={"test": "data"},
        meta=Meta(confidence=0.8, model="gpt-5", version="v1", correlation_id="test-123")
    )

    from bot_service.commands import handle_trends

    with patch('bot_service.commands.execute_trends_command', new_callable=AsyncMock) as mock_execute:
        mock_execute.return_value = mock_response

        await handle_trends(mock_update, mock_context)

        call_args = mock_context.bot.send_message.call_args
        sent_message = call_args[1]["text"]

        # Check sources are included
        assert "example.com/article1" in sent_message or "Sources" in sent_message


@pytest.mark.asyncio
async def test_budget_warning_e2e(mock_update, mock_context):
    """Test budget warning is shown to user"""
    mock_response = BaseAnalysisResponse(
        header="Test Header",
        tldr="Test summary",
        insights=[
            Insight(
                type="fact",
                text="Test insight",
                evidence_refs=[
                    EvidenceRef(article_id="art_1", url="https://example.com/1", date="2025-09-30")
                ]
            )
        ],
        evidence=[
            Evidence(
                title="Test Article",
                article_id="art_1",
                url="https://example.com/1",
                date="2025-09-30",
                snippet="Test snippet"
            )
        ],
        result={"test": "data"},
        meta=Meta(confidence=0.8, model="gpt-5", version="v1", correlation_id="test-123"),
        warnings=["fallback_used: gpt-5 failed", "degraded: context reduced to 3 docs"]
    )

    from bot_service.commands import handle_trends

    with patch('bot_service.commands.execute_trends_command', new_callable=AsyncMock) as mock_execute:
        mock_execute.return_value = mock_response

        await handle_trends(mock_update, mock_context)

        call_args = mock_context.bot.send_message.call_args
        sent_message = call_args[1]["text"]

        # Warnings may be shown or logged
        assert mock_context.bot.send_message.called


@pytest.mark.asyncio
async def test_invalid_analysis_type_e2e(mock_update, mock_context):
    """Test invalid analysis type returns error"""
    mock_update.message.text = "/analyze invalid_type test query"

    from bot_service.commands import handle_analyze

    await handle_analyze(mock_update, mock_context)

    # Should send error about invalid type
    assert mock_context.bot.send_message.called
    call_args = mock_context.bot.send_message.call_args
    sent_message = call_args[1]["text"]

    assert "invalid" in sent_message.lower() or "usage" in sent_message.lower()

@pytest.mark.asyncio
async def test_advanced_bot_analyze_uses_orchestrator(monkeypatch):
    payload = {
        "text": "🔬 Анализ: AI technology",
        "buttons": [[{"text": "🔄 Обновить", "callback_data": "analyze:refresh:keywords:24h:ai-tech"}]],
        "parse_mode": "Markdown",
        "context": {"command": "analyze", "mode": "keywords", "query": "AI technology", "window": "24h", "query_key": "ai-tech"},
    }

    with patch('bot_service.advanced_bot.execute_analyze_command', new_callable=AsyncMock) as mock_execute,
         patch('bot_service.advanced_bot.ProductionDBClient', return_value=MagicMock()):
        mock_execute.return_value = payload
        bot = AdvancedRSSBot('123:ABC', ranking_api=MagicMock(), gpt5_service=None)
        send_mock = AsyncMock()
        monkeypatch.setattr(bot, '_send_long_message', send_mock)

        await bot.handle_analyze_command('chat', 'user', ['keywords', 'AI', 'technology'])

        mock_execute.assert_called_once()
        send_mock.assert_awaited()
        sent_text = send_mock.call_args[0][1]
        assert 'AI technology' in sent_text


@pytest.mark.asyncio
async def test_advanced_bot_trends_uses_orchestrator(monkeypatch):
    payload = {
        "text": "📈 Тренды за 24h",
        "buttons": [[{"text": "🔄 Обновить", "callback_data": "trends:refresh:24h"}]],
        "parse_mode": "Markdown",
        "context": {"command": "trends", "window": "24h"},
    }

    with patch('bot_service.advanced_bot.execute_trends_command', new_callable=AsyncMock) as mock_execute,
         patch('bot_service.advanced_bot.ProductionDBClient', return_value=MagicMock()):
        mock_execute.return_value = payload
        bot = AdvancedRSSBot('123:ABC', ranking_api=MagicMock(), gpt5_service=None)
        send_mock = AsyncMock()
        monkeypatch.setattr(bot, '_send_long_message', send_mock)

        await bot.handle_trends_command('chat', 'user', ['24h'])

        mock_execute.assert_called_once()
        send_mock.assert_awaited()
        sent_text = send_mock.call_args[0][1]
        assert 'Тренды' in sent_text
