"""
Integration tests for Phase 4 end-to-end flow
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch


@pytest.fixture
def mock_bot_context():
    """Create mock bot context"""
    return {
        "chat_id": "123456",
        "user_id": "user_123",
        "personalization": {
            "lang": "en",
            "timezone": "UTC"
        }
    }


@pytest.mark.asyncio
@pytest.mark.integration
class TestPhase4Integration:
    """Integration tests for Phase 4 complete workflow"""

    async def test_dashboard_end_to_end(self, mock_bot_context):
        """Test complete /dashboard command flow"""
        from services.phase4_handlers import get_phase4_handler_service

        service = get_phase4_handler_service()

        with patch.object(service.retrieval_client, 'retrieve', new_callable=AsyncMock) as mock_retrieve:
            mock_retrieve.return_value = [
                {"title": "Test Doc", "article_id": "1", "url": "http://test.com", "score": 0.9}
            ]

            payload = await service.handle_dashboard_command(
                mode="live",
                metrics=["traffic", "ctr"],
                window="24h",
                lang="en",
                correlation_id="test-dashboard"
            )

            assert payload is not None
            assert "text" in payload
            assert "correlation_id" in payload
            assert payload["correlation_id"] == "test-dashboard"

    async def test_reports_end_to_end(self, mock_bot_context):
        """Test complete /reports generate flow"""
        from services.phase4_handlers import get_phase4_handler_service

        service = get_phase4_handler_service()

        with patch.object(service.retrieval_client, 'retrieve', new_callable=AsyncMock) as mock_retrieve:
            mock_retrieve.return_value = [
                {"title": "Article 1", "article_id": "1", "url": "http://test.com/1", "score": 0.9},
                {"title": "Article 2", "article_id": "2", "url": "http://test.com/2", "score": 0.8}
            ]

            payload = await service.handle_reports_command(
                action="generate",
                period="weekly",
                audience="B2B",
                window="1w",
                lang="en",
                correlation_id="test-reports"
            )

            assert payload is not None
            assert "text" in payload
            assert "weekly" in payload["text"].lower() or "report" in payload["text"].lower()

    async def test_optimize_listing_end_to_end(self, mock_bot_context):
        """Test complete /optimize listing flow"""
        from services.phase4_handlers import get_phase4_handler_service

        service = get_phase4_handler_service()

        with patch.object(service.retrieval_client, 'retrieve', new_callable=AsyncMock) as mock_retrieve:
            mock_retrieve.return_value = [
                {"title": "Market Trends", "article_id": "1", "url": "http://test.com", "score": 0.9}
            ]

            payload = await service.handle_optimize_listing_command(
                goal="conversion",
                product="Test Product",
                window="1w",
                lang="en",
                correlation_id="test-optimize"
            )

            assert payload is not None
            assert "text" in payload

    async def test_pricing_advisor_end_to_end(self, mock_bot_context):
        """Test complete /pricing advisor flow"""
        from services.phase4_handlers import get_phase4_handler_service

        service = get_phase4_handler_service()

        with patch.object(service.retrieval_client, 'retrieve', new_callable=AsyncMock) as mock_retrieve:
            mock_retrieve.return_value = [
                {"title": "Pricing Analysis", "article_id": "1", "url": "http://test.com", "score": 0.9}
            ]

            payload = await service.handle_pricing_command(
                product="Pro Plan",
                targets={"roi_min": 3.0, "cac_max": 80.0},
                window="1m",
                lang="en",
                correlation_id="test-pricing"
            )

            assert payload is not None
            assert "text" in payload

    async def test_bot_routing_dashboard(self, mock_bot_context):
        """Test bot correctly routes /dashboard command"""
        from bot_service.advanced_bot import AdvancedRSSBot
        import os

        bot_token = os.getenv('TELEGRAM_BOT_TOKEN', 'test_token')

        with patch('bot_service.advanced_bot.AdvancedRSSBot._send_message', new_callable=AsyncMock) as mock_send:
            with patch('bot_service.advanced_bot.AdvancedRSSBot._send_phase4_response', new_callable=AsyncMock) as mock_phase4_send:
                mock_send.return_value = True
                mock_phase4_send.return_value = True

                bot = AdvancedRSSBot(bot_token)

                result = await bot.handle_dashboard_command(
                    chat_id=mock_bot_context["chat_id"],
                    user_id=mock_bot_context["user_id"],
                    args=["live"]
                )

                # Verify bot called phase4 response handler
                assert mock_phase4_send.called or mock_send.called

    async def test_bot_routing_reports(self, mock_bot_context):
        """Test bot correctly routes /reports command"""
        from bot_service.advanced_bot import AdvancedRSSBot
        import os

        bot_token = os.getenv('TELEGRAM_BOT_TOKEN', 'test_token')

        with patch('bot_service.advanced_bot.AdvancedRSSBot._send_message', new_callable=AsyncMock) as mock_send:
            with patch('bot_service.advanced_bot.AdvancedRSSBot._send_phase4_response', new_callable=AsyncMock) as mock_phase4_send:
                mock_send.return_value = True
                mock_phase4_send.return_value = True

                bot = AdvancedRSSBot(bot_token)

                result = await bot.handle_reports_command(
                    chat_id=mock_bot_context["chat_id"],
                    user_id=mock_bot_context["user_id"],
                    args=["generate", "weekly"]
                )

                assert mock_phase4_send.called or mock_send.called

    async def test_error_handling_chain(self, mock_bot_context):
        """Test error propagates correctly through chain"""
        from services.phase4_handlers import get_phase4_handler_service

        service = get_phase4_handler_service()

        with patch.object(service.retrieval_client, 'retrieve', side_effect=Exception("Test error")):
            payload = await service.handle_dashboard_command(
                mode="live",
                window="24h",
                lang="en",
                correlation_id="test-error"
            )

            assert payload is not None
            assert payload.get("success") is False or "error" in payload["text"].lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "integration"])
