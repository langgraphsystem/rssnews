#!/usr/bin/env python3
"""
Тестирование всех GPT-5 команд с Railway логированием
Симулирует вызовы через Telegram бот без конфликтов
"""

import asyncio
import logging
import os
import sys
from datetime import datetime
from typing import List, Dict, Any

# Setup detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('gpt5_commands_test.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
    logger.info("✅ Environment variables loaded from .env")
except ImportError:
    logger.warning("⚠️ dotenv not available, using system environment only")

class GPT5CommandTester:
    """Тестер для всех GPT-5 команд"""

    def __init__(self):
        self.test_results = {}

    async def mock_get_articles_for_analysis(self, query: str, timeframe: str) -> List[Dict[str, Any]]:
        """Mock функция для получения статей"""
        logger.info(f"🔍 [MOCK] Getting articles for query: {query}, timeframe: {timeframe}")

        # Возвращаем mock данные для тестирования
        return [
            {
                'title': 'AI технологии 2025: новые прорывы в машинном обучении',
                'content': 'Искусственный интеллект продолжает революционизировать индустрию...',
                'source': 'tech.com',
                'published_at': '2025-09-25T10:00:00'
            },
            {
                'title': 'Cryptocurrency market trends показывают рост',
                'content': 'Криптовалютный рынок демонстрирует позитивные тенденции...',
                'source': 'crypto.news',
                'published_at': '2025-09-25T09:30:00'
            },
            {
                'title': 'RSS aggregation системы: будущее контента',
                'content': 'RSS системы становятся все более важными для обработки информации...',
                'source': 'news.tech',
                'published_at': '2025-09-25T08:45:00'
            }
        ]

    def _format_articles_for_gpt(self, articles: List[Dict[str, Any]], include_metadata: bool = False) -> str:
        """Format articles for GPT-5 processing"""
        try:
            formatted = []
            for i, article in enumerate(articles):
                title = article.get('title', 'No title')[:100]
                content = article.get('content', '')[:300]
                source = article.get('source', 'Unknown')
                date = article.get('published_at', 'Unknown date')

                article_text = f"Article {i+1}:\nTitle: {title}\nContent: {content}\n"

                if include_metadata:
                    article_text += f"Source: {source}\nDate: {date}\n"

                article_text += "---\n"
                formatted.append(article_text)

            return '\n'.join(formatted)
        except Exception as e:
            logger.error(f"Error formatting articles for GPT: {e}")
            return "Error formatting articles"

    async def test_analyze_command(self):
        """Test /analyze command"""
        logger.info("=" * 50)
        logger.info("🧠 TESTING /analyze COMMAND")
        logger.info("=" * 50)

        try:
            query = "AI технологии"
            timeframe = "7d"

            logger.info(f"🔍 [RAILWAY] Starting GPT-5 analyze command")
            logger.info(f"🔍 [RAILWAY] Query: {query}")
            logger.info(f"🔍 [RAILWAY] Timeframe: {timeframe}")

            # Get mock articles
            articles = await self.mock_get_articles_for_analysis(query, timeframe)
            logger.info(f"🔍 [RAILWAY] Articles found: {len(articles)}")

            # Prepare analysis prompt
            analysis_prompt = f"""Проанализируй следующие {len(articles)} статей о '{query}':

            ДАННЫЕ:
            {self._format_articles_for_gpt(articles)}

            Предоставь глубокий анализ, включая:
            1. Ключевые тренды и паттерны
            2. Важные инсайты и выводы
            3. Прогнозы и рекомендации
            4. Статистические данные
            5. Сравнительный анализ

            Формат с графиками, таблицами и визуальными элементами с использованием эмодзи."""

            logger.info(f"🔍 [RAILWAY] Analysis prompt length: {len(analysis_prompt)}")

            # Test GPT-5 service
            try:
                logger.info("🔍 [RAILWAY] Creating GPT-5 service for analyze...")
                from gpt5_service_new import create_gpt5_service
                gpt5 = create_gpt5_service("gpt-5-mini")
                logger.info("✅ [RAILWAY] GPT-5 service created for analyze")

                logger.info("🔍 [RAILWAY] Calling send_analysis...")
                analysis = gpt5.send_analysis(analysis_prompt, max_output_tokens=1000)
                logger.info(f"✅ [RAILWAY] GPT-5 analysis response received, length: {len(analysis) if analysis else 0}")

                if analysis:
                    logger.info("✅ /analyze command TEST PASSED")
                    logger.info(f"📄 Analysis preview: {analysis[:200]}...")
                    self.test_results['analyze'] = 'PASSED'
                else:
                    logger.error("❌ /analyze command TEST FAILED - No response")
                    self.test_results['analyze'] = 'FAILED'

            except Exception as gpt5_error:
                logger.error(f"❌ [RAILWAY] GPT-5 analyze error: {str(gpt5_error)}")
                logger.error(f"❌ [RAILWAY] GPT-5 error type: {type(gpt5_error).__name__}")
                import traceback
                logger.error(f"❌ [RAILWAY] GPT-5 traceback:\n{traceback.format_exc()}")
                self.test_results['analyze'] = 'FAILED'

        except Exception as e:
            logger.error(f"❌ Analyze command test failed: {e}")
            self.test_results['analyze'] = 'FAILED'

    async def test_insights_command(self):
        """Test /insights command"""
        logger.info("=" * 50)
        logger.info("💡 TESTING /insights COMMAND")
        logger.info("=" * 50)

        try:
            query = "рынок технологий"

            logger.info(f"🔍 [RAILWAY] Starting GPT-5 insights command")
            logger.info(f"🔍 [RAILWAY] Query: {query}")

            articles = await self.mock_get_articles_for_analysis(query, '7d')
            logger.info(f"🔍 [RAILWAY] Articles found: {len(articles)}")

            insights_prompt = f"""Generate deep business and market insights from these {len(articles)} articles about '{query}':

            ARTICLES:
            {self._format_articles_for_gpt(articles)}

            Provide comprehensive insights covering:
            1. **MARKET INTELLIGENCE**
               - Hidden trends and patterns
               - Competitive landscape shifts
               - Emerging opportunities/threats

            2. **PREDICTIVE ANALYSIS**
               - Short-term forecasts (1-3 months)
               - Long-term implications (6-12 months)
               - Risk factors and catalysts

            3. **STRATEGIC RECOMMENDATIONS**
               - Actionable business insights
               - Investment implications
               - Industry positioning advice

            Format as executive briefing with clear sections."""

            logger.info(f"🔍 [RAILWAY] Insights prompt length: {len(insights_prompt)}")

            try:
                logger.info("🔍 [RAILWAY] Creating GPT-5 service for insights...")
                from gpt5_service_new import create_gpt5_service
                gpt5 = create_gpt5_service("gpt-5")
                logger.info("✅ [RAILWAY] GPT-5 service created for insights")

                logger.info("🔍 [RAILWAY] Calling send_insights for insights...")
                insights = gpt5.send_insights(insights_prompt, max_output_tokens=1200)
                logger.info(f"✅ [RAILWAY] GPT-5 insights response received, length: {len(insights) if insights else 0}")

                if insights:
                    logger.info("✅ /insights command TEST PASSED")
                    logger.info(f"📄 Insights preview: {insights[:200]}...")
                    self.test_results['insights'] = 'PASSED'
                else:
                    logger.error("❌ /insights command TEST FAILED - No response")
                    self.test_results['insights'] = 'FAILED'

            except Exception as gpt5_error:
                logger.error(f"❌ [RAILWAY] GPT-5 insights error: {str(gpt5_error)}")
                logger.error(f"❌ [RAILWAY] GPT-5 error type: {type(gpt5_error).__name__}")
                import traceback
                logger.error(f"❌ [RAILWAY] GPT-5 traceback:\n{traceback.format_exc()}")
                self.test_results['insights'] = 'FAILED'

        except Exception as e:
            logger.error(f"❌ Insights command test failed: {e}")
            self.test_results['insights'] = 'FAILED'

    async def test_sentiment_command(self):
        """Test /sentiment command"""
        logger.info("=" * 50)
        logger.info("😊 TESTING /sentiment COMMAND")
        logger.info("=" * 50)

        try:
            query = "crypto market"
            timeframe = "3d"

            logger.info(f"🔍 [RAILWAY] Starting GPT-5 sentiment command")
            logger.info(f"🔍 [RAILWAY] Query: {query}")

            articles = await self.mock_get_articles_for_analysis(query, timeframe)
            logger.info(f"🔍 [RAILWAY] Articles found: {len(articles)}")

            sentiment_prompt = f"""Perform comprehensive sentiment analysis on {len(articles)} articles about '{query}':

            ARTICLES:
            {self._format_articles_for_gpt(articles)}

            Analyze and provide:
            1. **OVERALL SENTIMENT SCORE** (-100 to +100)
            2. **SENTIMENT DISTRIBUTION**
               - Positive: X% (reasoning)
               - Neutral: X% (reasoning)
               - Negative: X% (reasoning)

            3. **SENTIMENT DRIVERS**
               - Key positive factors
               - Main negative concerns
               - Neutral/mixed signals

            Use emojis and clear formatting."""

            logger.info(f"🔍 [RAILWAY] Sentiment prompt length: {len(sentiment_prompt)}")

            try:
                logger.info("🔍 [RAILWAY] Creating GPT-5 service for sentiment...")
                from gpt5_service_new import create_gpt5_service
                gpt5 = create_gpt5_service("gpt-5-mini")
                logger.info("✅ [RAILWAY] GPT-5 service created for sentiment")

                logger.info("🔍 [RAILWAY] Calling send_sentiment for sentiment...")
                sentiment_analysis = gpt5.send_sentiment(sentiment_prompt, max_output_tokens=1000)
                logger.info(f"✅ [RAILWAY] GPT-5 sentiment response received, length: {len(sentiment_analysis) if sentiment_analysis else 0}")

                if sentiment_analysis:
                    logger.info("✅ /sentiment command TEST PASSED")
                    logger.info(f"📄 Sentiment preview: {sentiment_analysis[:200]}...")
                    self.test_results['sentiment'] = 'PASSED'
                else:
                    logger.error("❌ /sentiment command TEST FAILED - No response")
                    self.test_results['sentiment'] = 'FAILED'

            except Exception as gpt5_error:
                logger.error(f"❌ [RAILWAY] GPT-5 sentiment error: {str(gpt5_error)}")
                logger.error(f"❌ [RAILWAY] GPT-5 error type: {type(gpt5_error).__name__}")
                import traceback
                logger.error(f"❌ [RAILWAY] GPT-5 traceback:\n{traceback.format_exc()}")
                self.test_results['sentiment'] = 'FAILED'

        except Exception as e:
            logger.error(f"❌ Sentiment command test failed: {e}")
            self.test_results['sentiment'] = 'FAILED'

    async def test_summarize_command(self):
        """Test /summarize command"""
        logger.info("=" * 50)
        logger.info("📋 TESTING /summarize COMMAND")
        logger.info("=" * 50)

        try:
            topic = "AI технологии"
            length = "medium"

            logger.info(f"🔍 [RAILWAY] Starting GPT-5 summarize command")
            logger.info(f"🔍 [RAILWAY] Topic: {topic}")
            logger.info(f"🔍 [RAILWAY] Length: {length}")

            articles = await self.mock_get_articles_for_analysis(topic, '7d')
            logger.info(f"🔍 [RAILWAY] Articles found: {len(articles)}")

            summarize_prompt = f"""Create comprehensive summary of {len(articles)} articles about '{topic}' with {length} length:

            ARTICLES:
            {self._format_articles_for_gpt(articles, include_metadata=True)}

            Provide a well-structured summary including:
            1. **EXECUTIVE SUMMARY**
               - Key highlights and main themes
               - Most important developments

            2. **DETAILED CONTENT**
               - Main points from each source
               - Timeline of events
               - Key statistics and data

            3. **CONCLUSIONS**
               - Overall trends identified
               - Future implications

            Format with clear sections and bullet points. Target length: {length}."""

            logger.info(f"🔍 [RAILWAY] Summarize prompt length: {len(summarize_prompt)}")

            try:
                logger.info("🔍 [RAILWAY] Creating GPT-5 service for summarize...")
                from gpt5_service_new import create_gpt5_service
                gpt5 = create_gpt5_service("gpt-5")
                logger.info("✅ [RAILWAY] GPT-5 service created for summarize")

                logger.info("🔍 [RAILWAY] Calling send_chat for summarize...")
                summary = gpt5.send_chat(summarize_prompt, max_output_tokens=1200)
                logger.info(f"✅ [RAILWAY] GPT-5 summarize response received, length: {len(summary) if summary else 0}")

                if summary:
                    logger.info("✅ /summarize command TEST PASSED")
                    logger.info(f"📄 Summary preview: {summary[:200]}...")
                    self.test_results['summarize'] = 'PASSED'
                else:
                    logger.error("❌ /summarize command TEST FAILED - No response")
                    self.test_results['summarize'] = 'FAILED'

            except Exception as gpt5_error:
                logger.error(f"❌ [RAILWAY] GPT-5 summarize error: {str(gpt5_error)}")
                logger.error(f"❌ [RAILWAY] GPT-5 error type: {type(gpt5_error).__name__}")
                import traceback
                logger.error(f"❌ [RAILWAY] GPT-5 traceback:\n{traceback.format_exc()}")
                self.test_results['summarize'] = 'FAILED'

        except Exception as e:
            logger.error(f"❌ Summarize command test failed: {e}")
            self.test_results['summarize'] = 'FAILED'

    async def test_aggregate_command(self):
        """Test /aggregate command"""
        logger.info("=" * 50)
        logger.info("📊 TESTING /aggregate COMMAND")
        logger.info("=" * 50)

        try:
            metric = "источники"
            groupby = "дата"

            logger.info(f"🔍 [RAILWAY] Starting GPT-5 aggregate command")
            logger.info(f"🔍 [RAILWAY] Metric: {metric}")
            logger.info(f"🔍 [RAILWAY] Group by: {groupby}")

            articles = await self.mock_get_articles_for_analysis("технологии", '7d')
            logger.info(f"🔍 [RAILWAY] Articles found: {len(articles)}")

            aggregate_prompt = f"""Perform data aggregation analysis on {len(articles)} articles:

            ARTICLES DATA:
            {self._format_articles_for_gpt(articles, include_metadata=True)}

            AGGREGATION TASK:
            - Metric: {metric}
            - Group by: {groupby}

            Provide comprehensive aggregation including:
            1. **DATA AGGREGATION**
               - Group articles by {groupby}
               - Calculate {metric} statistics
               - Show distribution patterns

            2. **STATISTICAL ANALYSIS**
               - Count by categories
               - Percentage distributions
               - Trends over time

            3. **VISUALIZATION DATA**
               - Top sources/categories
               - Timeline analysis
               - Key metrics summary

            Format with tables, charts (using emojis), and clear data presentation."""

            logger.info(f"🔍 [RAILWAY] Aggregate prompt length: {len(aggregate_prompt)}")

            try:
                logger.info("🔍 [RAILWAY] Creating GPT-5 service for aggregate...")
                from gpt5_service_new import create_gpt5_service
                gpt5 = create_gpt5_service("gpt-5")
                logger.info("✅ [RAILWAY] GPT-5 service created for aggregate")

                logger.info("🔍 [RAILWAY] Calling send_bulk for aggregate...")
                aggregation = gpt5.send_bulk(aggregate_prompt, max_output_tokens=1000)
                logger.info(f"✅ [RAILWAY] GPT-5 aggregate response received, length: {len(aggregation) if aggregation else 0}")

                if aggregation:
                    logger.info("✅ /aggregate command TEST PASSED")
                    logger.info(f"📄 Aggregation preview: {aggregation[:200]}...")
                    self.test_results['aggregate'] = 'PASSED'
                else:
                    logger.error("❌ /aggregate command TEST FAILED - No response")
                    self.test_results['aggregate'] = 'FAILED'

            except Exception as gpt5_error:
                logger.error(f"❌ [RAILWAY] GPT-5 aggregate error: {str(gpt5_error)}")
                logger.error(f"❌ [RAILWAY] GPT-5 error type: {type(gpt5_error).__name__}")
                import traceback
                logger.error(f"❌ [RAILWAY] GPT-5 traceback:\n{traceback.format_exc()}")
                self.test_results['aggregate'] = 'FAILED'

        except Exception as e:
            logger.error(f"❌ Aggregate command test failed: {e}")
            self.test_results['aggregate'] = 'FAILED'

    async def test_filter_command(self):
        """Test /filter command"""
        logger.info("=" * 50)
        logger.info("🔍 TESTING /filter COMMAND")
        logger.info("=" * 50)

        try:
            criteria = "источник"
            value = "tech.com"

            logger.info(f"🔍 [RAILWAY] Starting GPT-5 filter command")
            logger.info(f"🔍 [RAILWAY] Criteria: {criteria}")
            logger.info(f"🔍 [RAILWAY] Value: {value}")

            articles = await self.mock_get_articles_for_analysis("технологии", '7d')
            logger.info(f"🔍 [RAILWAY] Articles found: {len(articles)}")

            filter_prompt = f"""Perform smart filtering on {len(articles)} articles:

            ARTICLES DATA:
            {self._format_articles_for_gpt(articles, include_metadata=True)}

            FILTERING TASK:
            - Filter by: {criteria}
            - Value: {value}

            Apply intelligent filtering and provide:
            1. **FILTERED RESULTS**
               - Articles matching criteria: {criteria} = {value}
               - Count of matching articles
               - Matching score/relevance

            2. **ANALYSIS OF FILTERED DATA**
               - Content quality assessment
               - Key themes in filtered articles
               - Unique insights from this subset

            3. **FILTERING RECOMMENDATIONS**
               - Additional useful filters
               - Related criteria suggestions
               - Data quality observations

            Show both exact matches and intelligent approximations."""

            logger.info(f"🔍 [RAILWAY] Filter prompt length: {len(filter_prompt)}")

            try:
                logger.info("🔍 [RAILWAY] Creating GPT-5 service for filter...")
                from gpt5_service_new import create_gpt5_service
                gpt5 = create_gpt5_service("gpt-5-mini")
                logger.info("✅ [RAILWAY] GPT-5 service created for filter")

                logger.info("🔍 [RAILWAY] Calling send_chat for filter...")
                filtered_results = gpt5.send_chat(filter_prompt, max_output_tokens=1000)
                logger.info(f"✅ [RAILWAY] GPT-5 filter response received, length: {len(filtered_results) if filtered_results else 0}")

                if filtered_results:
                    logger.info("✅ /filter command TEST PASSED")
                    logger.info(f"📄 Filter results preview: {filtered_results[:200]}...")
                    self.test_results['filter'] = 'PASSED'
                else:
                    logger.error("❌ /filter command TEST FAILED - No response")
                    self.test_results['filter'] = 'FAILED'

            except Exception as gpt5_error:
                logger.error(f"❌ [RAILWAY] GPT-5 filter error: {str(gpt5_error)}")
                logger.error(f"❌ [RAILWAY] GPT-5 error type: {type(gpt5_error).__name__}")
                import traceback
                logger.error(f"❌ [RAILWAY] GPT-5 traceback:\n{traceback.format_exc()}")
                self.test_results['filter'] = 'FAILED'

        except Exception as e:
            logger.error(f"❌ Filter command test failed: {e}")
            self.test_results['filter'] = 'FAILED'

    async def test_topics_command(self):
        """Test /topics command"""
        logger.info("=" * 50)
        logger.info("🏷️ TESTING /topics COMMAND")
        logger.info("=" * 50)

        try:
            scope = "технологии"

            logger.info(f"🔍 [RAILWAY] Starting GPT-5 topics command")
            logger.info(f"🔍 [RAILWAY] Scope: {scope}")

            articles = await self.mock_get_articles_for_analysis(scope, '7d')
            logger.info(f"🔍 [RAILWAY] Articles found: {len(articles)}")

            topics_prompt = f"""Perform topic modeling and trend analysis on {len(articles)} articles about '{scope}':

            ARTICLES DATA:
            {self._format_articles_for_gpt(articles, include_metadata=True)}

            TOPIC MODELING TASK:
            Scope: {scope}

            Provide comprehensive topic analysis:
            1. **MAIN TOPICS IDENTIFIED**
               - Top 5-7 topics with descriptions
               - Topic weights/frequency
               - Representative keywords per topic

            2. **TREND ANALYSIS**
               - Emerging topics
               - Declining topics
               - Stable/consistent themes
               - Timeline evolution

            3. **TOPIC RELATIONSHIPS**
               - Topic clustering
               - Cross-topic connections
               - Topic hierarchy/sub-topics

            4. **ACTIONABLE INSIGHTS**
               - Most promising topics to follow
               - Market implications
               - Prediction of future topics

            Use visual formatting with emojis and clear categorization."""

            logger.info(f"🔍 [RAILWAY] Topics prompt length: {len(topics_prompt)}")

            try:
                logger.info("🔍 [RAILWAY] Creating GPT-5 service for topics...")
                from gpt5_service_new import create_gpt5_service
                gpt5 = create_gpt5_service("gpt-5")
                logger.info("✅ [RAILWAY] GPT-5 service created for topics")

                logger.info("🔍 [RAILWAY] Calling send_analysis for topics...")
                topic_analysis = gpt5.send_analysis(topics_prompt, max_output_tokens=1200)
                logger.info(f"✅ [RAILWAY] GPT-5 topics response received, length: {len(topic_analysis) if topic_analysis else 0}")

                if topic_analysis:
                    logger.info("✅ /topics command TEST PASSED")
                    logger.info(f"📄 Topics analysis preview: {topic_analysis[:200]}...")
                    self.test_results['topics'] = 'PASSED'
                else:
                    logger.error("❌ /topics command TEST FAILED - No response")
                    self.test_results['topics'] = 'FAILED'

            except Exception as gpt5_error:
                logger.error(f"❌ [RAILWAY] GPT-5 topics error: {str(gpt5_error)}")
                logger.error(f"❌ [RAILWAY] GPT-5 error type: {type(gpt5_error).__name__}")
                import traceback
                logger.error(f"❌ [RAILWAY] GPT-5 traceback:\n{traceback.format_exc()}")
                self.test_results['topics'] = 'FAILED'

        except Exception as e:
            logger.error(f"❌ Topics command test failed: {e}")
            self.test_results['topics'] = 'FAILED'

    async def run_all_tests(self):
        """Run all GPT-5 command tests"""
        logger.info("🚀 Starting comprehensive GPT-5 commands testing")
        logger.info(f"⏰ Time: {datetime.now()}")
        logger.info(f"🐍 Python: {sys.version}")
        logger.info(f"📍 Working directory: {os.getcwd()}")

        # Check OpenAI API key
        api_key = os.getenv('OPENAI_API_KEY')
        if api_key:
            logger.info(f"🔑 OPENAI_API_KEY found: {api_key[:8]}***{api_key[-4:]}")
        else:
            logger.error("❌ OPENAI_API_KEY not found!")
            return

        # Run individual command tests
        await self.test_analyze_command()
        await self.test_insights_command()
        await self.test_sentiment_command()
        await self.test_summarize_command()
        await self.test_aggregate_command()
        await self.test_filter_command()
        await self.test_topics_command()

        # Summary
        logger.info("=" * 50)
        logger.info("📋 FINAL TEST RESULTS")
        logger.info("=" * 50)

        for command, result in self.test_results.items():
            status_emoji = "✅" if result == 'PASSED' else "❌"
            logger.info(f"{status_emoji} /{command}: {result}")

        passed = sum(1 for r in self.test_results.values() if r == 'PASSED')
        total = len(self.test_results)

        logger.info(f"📊 Overall: {passed}/{total} commands passed")

        if passed == total:
            logger.info("🎉 ALL GPT-5 COMMANDS WORKING CORRECTLY!")
        else:
            logger.error(f"⚠️ {total-passed} commands need attention")

async def main():
    tester = GPT5CommandTester()
    await tester.run_all_tests()

if __name__ == "__main__":
    asyncio.run(main())
