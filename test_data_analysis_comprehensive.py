#!/usr/bin/env python3
"""
🤖 Comprehensive Testing Suite for GPT-5 Data Analysis Commands
Полное тестирование всех команд обработки данных

Команды для тестирования:
• /analyze [query] [timeframe] - Deep data analysis
• /summarize [topic] [length] - AI-powered summaries
• /aggregate [metric] [groupby] - Data aggregation
• /filter [criteria] [value] - Smart filtering
• /insights [topic] - Business insights generation
• /sentiment [query] - Sentiment analysis
• /topics [scope] - Topic modeling & trends
"""

import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import Dict, Any, List

# Setup comprehensive logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('data_analysis_comprehensive_test.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# Load environment
try:
    from dotenv import load_dotenv
    load_dotenv()
    logger.info("✅ Environment variables loaded")
except ImportError:
    logger.warning("⚠️ dotenv not available")

class DataAnalysisTestSuite:
    """Comprehensive test suite for all data analysis commands"""

    def __init__(self):
        self.test_results = {}
        self.total_start_time = None
        self.test_data = {
            'tech_articles': self._get_tech_test_data(),
            'market_articles': self._get_market_test_data(),
            'general_articles': self._get_general_test_data()
        }

    def _get_tech_test_data(self) -> List[Dict[str, Any]]:
        """Tech-focused test data"""
        return [
            {
                'title': 'Революция в ИИ: GPT-5 меняет индустрию технологий',
                'content': 'Новая модель GPT-5 демонстрирует беспрецедентные возможности в области анализа данных и автоматизации бизнес-процессов. Эксперты отмечают 40% улучшение точности по сравнению с предыдущими версиями...',
                'source': 'TechNews',
                'source_domain': 'technews.com',
                'published_at': '2025-09-25T10:00:00',
                'score': 0.95,
                'tags': ['AI', 'GPT-5', 'technology', 'automation']
            },
            {
                'title': 'Квантовые вычисления: прорыв в обработке данных',
                'content': 'Исследователи достигли нового рекорда в квантовых вычислениях, что открывает новые возможности для анализа больших данных. Потенциал для ускорения машинного обучения в тысячи раз...',
                'source': 'QuantumTech',
                'source_domain': 'quantumtech.com',
                'published_at': '2025-09-25T09:30:00',
                'score': 0.92,
                'tags': ['quantum', 'computing', 'data', 'ML']
            },
            {
                'title': 'Блокчейн технологии в 2025: новые применения',
                'content': 'Blockchain продолжает эволюционировать, находя применение в системах аналитики и обработки данных. Децентрализованные решения становятся более эффективными и доступными...',
                'source': 'BlockchainDaily',
                'source_domain': 'blockchain.daily',
                'published_at': '2025-09-25T08:45:00',
                'score': 0.88,
                'tags': ['blockchain', 'decentralization', 'analytics']
            }
        ]

    def _get_market_test_data(self) -> List[Dict[str, Any]]:
        """Market-focused test data"""
        return [
            {
                'title': 'Рынок ИИ достигнет $500 млрд к 2026 году',
                'content': 'Аналитики прогнозируют взрывной рост рынка искусственного интеллекта. Основными драйверами станут корпоративные внедрения и развитие автономных систем. Инвестиции увеличились на 65% за год...',
                'source': 'MarketWatch',
                'source_domain': 'marketwatch.com',
                'published_at': '2025-09-25T11:00:00',
                'score': 0.94,
                'tags': ['market', 'AI', 'investment', 'growth']
            },
            {
                'title': 'Криптовалютный рынок: анализ трендов Q3 2025',
                'content': 'Третий квартал 2025 года показал стабилизацию криптовалютного рынка. Bitcoin и Ethereum демонстрируют устойчивый рост, в то время как альткоины переживают период консолидации...',
                'source': 'CryptoInsider',
                'source_domain': 'cryptoinsider.com',
                'published_at': '2025-09-25T10:30:00',
                'score': 0.89,
                'tags': ['crypto', 'market', 'trends', 'bitcoin']
            },
            {
                'title': 'Технологические акции: перспективы роста',
                'content': 'Акции технологических компаний продолжают привлекать инвесторов. Особенно выделяются компании, работающие с ИИ и квантовыми технологиями. Аналитики рекомендуют диверсификацию портфеля...',
                'source': 'InvestorDaily',
                'source_domain': 'investor.daily',
                'published_at': '2025-09-25T09:15:00',
                'score': 0.91,
                'tags': ['stocks', 'tech', 'investment', 'growth']
            }
        ]

    def _get_general_test_data(self) -> List[Dict[str, Any]]:
        """General news test data"""
        return [
            {
                'title': 'Цифровая трансформация меняет бизнес-процессы',
                'content': 'Компании всех отраслей активно внедряют цифровые решения для оптимизации процессов. Автоматизация и аналитика данных становятся ключевыми факторами конкурентоспособности...',
                'source': 'BusinessNews',
                'source_domain': 'business.news',
                'published_at': '2025-09-25T12:00:00',
                'score': 0.87,
                'tags': ['digital', 'transformation', 'business', 'automation']
            },
            {
                'title': 'Экологические технологии набирают обороты',
                'content': 'Green Tech сектор привлекает рекордные инвестиции. Новые решения в области возобновляемой энергетики и устойчивого развития показывают впечатляющие результаты...',
                'source': 'EcoTech',
                'source_domain': 'ecotech.org',
                'published_at': '2025-09-25T11:30:00',
                'score': 0.85,
                'tags': ['green', 'ecology', 'sustainability', 'energy']
            }
        ]

    async def run_comprehensive_tests(self):
        """Run all comprehensive tests"""
        self.total_start_time = time.time()

        logger.info("🚀 Starting Comprehensive Data Analysis Testing Suite")
        logger.info(f"⏰ Start time: {datetime.now()}")
        logger.info(f"🐍 Python version: {sys.version}")
        logger.info(f"📁 Working directory: {os.getcwd()}")

        # Check API key
        api_key = os.getenv('OPENAI_API_KEY')
        if api_key:
            logger.info(f"🔑 OpenAI API Key: {api_key[:8]}***{api_key[-4:]}")
        else:
            logger.error("❌ OPENAI_API_KEY not found!")
            return

        # Run all test scenarios
        await self.test_deep_analysis_scenarios()
        await self.test_summarization_scenarios()
        await self.test_aggregation_scenarios()
        await self.test_filtering_scenarios()
        await self.test_insights_scenarios()
        await self.test_sentiment_scenarios()
        await self.test_topics_scenarios()

        # Generate comprehensive report
        self.generate_comprehensive_report()

    async def test_deep_analysis_scenarios(self):
        """Test deep analysis with different scenarios"""
        logger.info("=" * 60)
        logger.info("🧠 TESTING DEEP ANALYSIS SCENARIOS")
        logger.info("=" * 60)

        scenarios = [
            {
                'name': 'Tech Innovation Analysis',
                'query': 'технологические инновации',
                'timeframe': '7d',
                'data': self.test_data['tech_articles']
            },
            {
                'name': 'Market Trends Analysis',
                'query': 'рыночные тренды',
                'timeframe': '14d',
                'data': self.test_data['market_articles']
            },
            {
                'name': 'Cross-Industry Analysis',
                'query': 'цифровая трансформация',
                'timeframe': '30d',
                'data': self.test_data['tech_articles'] + self.test_data['general_articles']
            }
        ]

        for scenario in scenarios:
            await self.test_analysis_scenario(scenario)

    async def test_analysis_scenario(self, scenario: Dict[str, Any]):
        """Test a specific analysis scenario"""
        logger.info(f"🔬 Testing scenario: {scenario['name']}")

        try:
            # Import and test
            from data_analysis_processor import analyze_data

            start_time = time.time()
            result = await analyze_data(
                query=scenario['query'],
                timeframe=scenario['timeframe']
            )
            processing_time = time.time() - start_time

            if result.success:
                logger.info(f"✅ {scenario['name']} - SUCCESS")
                logger.info(f"⏱️ Processing time: {processing_time:.2f}s")
                logger.info(f"📊 Articles analyzed: {result.metadata.get('articles_count', 0)}")

                # Validate result structure
                if 'analysis' in result.data:
                    analysis_length = len(result.data['analysis']) if result.data['analysis'] else 0
                    logger.info(f"📄 Analysis length: {analysis_length} characters")

                    if analysis_length > 100:
                        logger.info(f"📋 Analysis preview: {result.data['analysis'][:200]}...")
                    else:
                        logger.warning("⚠️ Analysis seems too short")

                self.test_results[f"analyze_{scenario['name']}"] = {
                    'status': 'PASSED',
                    'processing_time': processing_time,
                    'details': result.metadata
                }
            else:
                logger.error(f"❌ {scenario['name']} - FAILED: {result.error}")
                self.test_results[f"analyze_{scenario['name']}"] = {
                    'status': 'FAILED',
                    'error': result.error
                }

        except Exception as e:
            logger.error(f"❌ {scenario['name']} - EXCEPTION: {str(e)}")
            self.test_results[f"analyze_{scenario['name']}"] = {
                'status': 'ERROR',
                'error': str(e)
            }

    async def test_summarization_scenarios(self):
        """Test summarization with different lengths and topics"""
        logger.info("=" * 60)
        logger.info("📋 TESTING SUMMARIZATION SCENARIOS")
        logger.info("=" * 60)

        scenarios = [
            {
                'name': 'Short Tech Summary',
                'topic': 'ИИ технологии',
                'length': 'short',
                'timeframe': '7d'
            },
            {
                'name': 'Medium Market Summary',
                'topic': 'рыночная аналитика',
                'length': 'medium',
                'timeframe': '14d'
            },
            {
                'name': 'Long Detailed Summary',
                'topic': 'технологические тренды',
                'length': 'long',
                'timeframe': '30d'
            },
            {
                'name': 'Ultra Detailed Summary',
                'topic': 'цифровая экономика',
                'length': 'detailed',
                'timeframe': '7d'
            }
        ]

        for scenario in scenarios:
            await self.test_summarization_scenario(scenario)

    async def test_summarization_scenario(self, scenario: Dict[str, Any]):
        """Test a specific summarization scenario"""
        logger.info(f"📝 Testing summarization: {scenario['name']}")

        try:
            from data_analysis_processor import summarize_data

            start_time = time.time()
            result = await summarize_data(
                topic=scenario['topic'],
                length=scenario['length'],
                timeframe=scenario['timeframe']
            )
            processing_time = time.time() - start_time

            if result.success:
                logger.info(f"✅ {scenario['name']} - SUCCESS")
                logger.info(f"⏱️ Processing time: {processing_time:.2f}s")

                summary = result.data.get('summary', '')
                word_count = result.data.get('word_count', 0)

                logger.info(f"📊 Word count: {word_count}")
                logger.info(f"📏 Length setting: {scenario['length']}")

                if summary:
                    logger.info(f"📋 Summary preview: {summary[:150]}...")

                # Validate length appropriateness
                expected_ranges = {
                    'short': (50, 300),
                    'medium': (200, 600),
                    'long': (400, 1000),
                    'detailed': (600, 1500)
                }

                expected_range = expected_ranges.get(scenario['length'], (100, 500))
                if expected_range[0] <= word_count <= expected_range[1]:
                    logger.info(f"✅ Word count within expected range: {expected_range}")
                else:
                    logger.warning(f"⚠️ Word count outside expected range: {expected_range}")

                self.test_results[f"summarize_{scenario['name']}"] = {
                    'status': 'PASSED',
                    'processing_time': processing_time,
                    'word_count': word_count,
                    'details': result.metadata
                }
            else:
                logger.error(f"❌ {scenario['name']} - FAILED: {result.error}")
                self.test_results[f"summarize_{scenario['name']}"] = {
                    'status': 'FAILED',
                    'error': result.error
                }

        except Exception as e:
            logger.error(f"❌ {scenario['name']} - EXCEPTION: {str(e)}")
            self.test_results[f"summarize_{scenario['name']}"] = {
                'status': 'ERROR',
                'error': str(e)
            }

    async def test_aggregation_scenarios(self):
        """Test data aggregation scenarios"""
        logger.info("=" * 60)
        logger.info("📊 TESTING AGGREGATION SCENARIOS")
        logger.info("=" * 60)

        scenarios = [
            {
                'name': 'Source Aggregation by Date',
                'metric': 'источники',
                'groupby': 'дата',
                'query': 'технологии',
                'timeframe': '7d'
            },
            {
                'name': 'Content Aggregation by Source',
                'metric': 'контент',
                'groupby': 'источник',
                'query': 'рынок',
                'timeframe': '14d'
            },
            {
                'name': 'Topic Aggregation by Time',
                'metric': 'темы',
                'groupby': 'время',
                'query': 'инновации',
                'timeframe': '30d'
            }
        ]

        for scenario in scenarios:
            await self.test_aggregation_scenario(scenario)

    async def test_aggregation_scenario(self, scenario: Dict[str, Any]):
        """Test a specific aggregation scenario"""
        logger.info(f"📈 Testing aggregation: {scenario['name']}")

        try:
            from data_analysis_processor import aggregate_data

            start_time = time.time()
            result = await aggregate_data(
                metric=scenario['metric'],
                groupby=scenario['groupby'],
                query=scenario['query'],
                timeframe=scenario['timeframe']
            )
            processing_time = time.time() - start_time

            if result.success:
                logger.info(f"✅ {scenario['name']} - SUCCESS")
                logger.info(f"⏱️ Processing time: {processing_time:.2f}s")

                if 'aggregation_analysis' in result.data:
                    analysis = result.data['aggregation_analysis']
                    logger.info(f"📊 Aggregation analysis length: {len(analysis) if analysis else 0}")
                    if analysis:
                        logger.info(f"📋 Analysis preview: {analysis[:150]}...")

                self.test_results[f"aggregate_{scenario['name']}"] = {
                    'status': 'PASSED',
                    'processing_time': processing_time,
                    'details': result.metadata
                }
            else:
                logger.error(f"❌ {scenario['name']} - FAILED: {result.error}")
                self.test_results[f"aggregate_{scenario['name']}"] = {
                    'status': 'FAILED',
                    'error': result.error
                }

        except Exception as e:
            logger.error(f"❌ {scenario['name']} - EXCEPTION: {str(e)}")
            self.test_results[f"aggregate_{scenario['name']}"] = {
                'status': 'ERROR',
                'error': str(e)
            }

    async def test_filtering_scenarios(self):
        """Test smart filtering scenarios"""
        logger.info("=" * 60)
        logger.info("🔍 TESTING FILTERING SCENARIOS")
        logger.info("=" * 60)

        scenarios = [
            {
                'name': 'Filter by Source Domain',
                'criteria': 'источник',
                'value': 'technews.com',
                'query': 'технологии',
                'timeframe': '7d'
            },
            {
                'name': 'Filter by Content Keywords',
                'criteria': 'содержание',
                'value': 'ИИ',
                'query': 'искусственный интеллект',
                'timeframe': '14d'
            },
            {
                'name': 'Filter by Title Keywords',
                'criteria': 'название',
                'value': 'рынок',
                'query': 'рыночная аналитика',
                'timeframe': '30d'
            }
        ]

        for scenario in scenarios:
            await self.test_filtering_scenario(scenario)

    async def test_filtering_scenario(self, scenario: Dict[str, Any]):
        """Test a specific filtering scenario"""
        logger.info(f"🔎 Testing filtering: {scenario['name']}")

        try:
            from data_analysis_processor import filter_data

            start_time = time.time()
            result = await filter_data(
                criteria=scenario['criteria'],
                value=scenario['value'],
                query=scenario['query'],
                timeframe=scenario['timeframe']
            )
            processing_time = time.time() - start_time

            if result.success:
                logger.info(f"✅ {scenario['name']} - SUCCESS")
                logger.info(f"⏱️ Processing time: {processing_time:.2f}s")

                filter_stats = result.data.get('filter_stats', {})
                logger.info(f"📊 Original count: {filter_stats.get('original_count', 0)}")
                logger.info(f"📊 Filtered count: {filter_stats.get('filtered_count', 0)}")
                logger.info(f"📊 Filter ratio: {filter_stats.get('filter_ratio', 0):.2%}")

                if 'filtering_analysis' in result.data:
                    analysis = result.data['filtering_analysis']
                    if analysis:
                        logger.info(f"📋 Analysis preview: {analysis[:150]}...")

                self.test_results[f"filter_{scenario['name']}"] = {
                    'status': 'PASSED',
                    'processing_time': processing_time,
                    'filter_stats': filter_stats
                }
            else:
                logger.error(f"❌ {scenario['name']} - FAILED: {result.error}")
                self.test_results[f"filter_{scenario['name']}"] = {
                    'status': 'FAILED',
                    'error': result.error
                }

        except Exception as e:
            logger.error(f"❌ {scenario['name']} - EXCEPTION: {str(e)}")
            self.test_results[f"filter_{scenario['name']}"] = {
                'status': 'ERROR',
                'error': str(e)
            }

    async def test_insights_scenarios(self):
        """Test business insights generation scenarios"""
        logger.info("=" * 60)
        logger.info("💡 TESTING INSIGHTS SCENARIOS")
        logger.info("=" * 60)

        scenarios = [
            {
                'name': 'Tech Market Insights',
                'topic': 'рынок технологий',
                'timeframe': '7d'
            },
            {
                'name': 'AI Industry Insights',
                'topic': 'индустрия ИИ',
                'timeframe': '14d'
            },
            {
                'name': 'Investment Opportunities',
                'topic': 'инвестиционные возможности',
                'timeframe': '30d'
            }
        ]

        for scenario in scenarios:
            await self.test_insights_scenario(scenario)

    async def test_insights_scenario(self, scenario: Dict[str, Any]):
        """Test a specific insights scenario"""
        logger.info(f"💼 Testing insights: {scenario['name']}")

        try:
            from data_analysis_processor import generate_insights

            start_time = time.time()
            result = await generate_insights(
                topic=scenario['topic'],
                timeframe=scenario['timeframe']
            )
            processing_time = time.time() - start_time

            if result.success:
                logger.info(f"✅ {scenario['name']} - SUCCESS")
                logger.info(f"⏱️ Processing time: {processing_time:.2f}s")

                insights = result.data.get('insights', '')
                confidence = result.data.get('confidence_score', 0)

                logger.info(f"📊 Confidence score: {confidence:.2f}")

                if insights:
                    logger.info(f"📋 Insights preview: {insights[:150]}...")

                self.test_results[f"insights_{scenario['name']}"] = {
                    'status': 'PASSED',
                    'processing_time': processing_time,
                    'confidence_score': confidence
                }
            else:
                logger.error(f"❌ {scenario['name']} - FAILED: {result.error}")
                self.test_results[f"insights_{scenario['name']}"] = {
                    'status': 'FAILED',
                    'error': result.error
                }

        except Exception as e:
            logger.error(f"❌ {scenario['name']} - EXCEPTION: {str(e)}")
            self.test_results[f"insights_{scenario['name']}"] = {
                'status': 'ERROR',
                'error': str(e)
            }

    async def test_sentiment_scenarios(self):
        """Test sentiment analysis scenarios"""
        logger.info("=" * 60)
        logger.info("😊 TESTING SENTIMENT SCENARIOS")
        logger.info("=" * 60)

        scenarios = [
            {
                'name': 'Tech News Sentiment',
                'query': 'технологические новости',
                'timeframe': '7d'
            },
            {
                'name': 'Market Sentiment',
                'query': 'рыночные настроения',
                'timeframe': '14d'
            },
            {
                'name': 'Investment Sentiment',
                'query': 'инвестиционный климат',
                'timeframe': '30d'
            }
        ]

        for scenario in scenarios:
            await self.test_sentiment_scenario(scenario)

    async def test_sentiment_scenario(self, scenario: Dict[str, Any]):
        """Test a specific sentiment scenario"""
        logger.info(f"😊 Testing sentiment: {scenario['name']}")

        try:
            from data_analysis_processor import analyze_sentiment

            start_time = time.time()
            result = await analyze_sentiment(
                query=scenario['query'],
                timeframe=scenario['timeframe']
            )
            processing_time = time.time() - start_time

            if result.success:
                logger.info(f"✅ {scenario['name']} - SUCCESS")
                logger.info(f"⏱️ Processing time: {processing_time:.2f}s")

                sentiment_metrics = result.data.get('sentiment_metrics', {})
                confidence = result.data.get('confidence_level', 0)

                logger.info(f"📊 Average sentiment: {sentiment_metrics.get('average_sentiment', 0):.2f}")
                logger.info(f"📊 Positive ratio: {sentiment_metrics.get('positive_ratio', 0):.2%}")
                logger.info(f"📊 Confidence level: {confidence:.2f}")

                if 'sentiment_analysis' in result.data:
                    analysis = result.data['sentiment_analysis']
                    if analysis:
                        logger.info(f"📋 Analysis preview: {analysis[:150]}...")

                self.test_results[f"sentiment_{scenario['name']}"] = {
                    'status': 'PASSED',
                    'processing_time': processing_time,
                    'sentiment_metrics': sentiment_metrics
                }
            else:
                logger.error(f"❌ {scenario['name']} - FAILED: {result.error}")
                self.test_results[f"sentiment_{scenario['name']}"] = {
                    'status': 'FAILED',
                    'error': result.error
                }

        except Exception as e:
            logger.error(f"❌ {scenario['name']} - EXCEPTION: {str(e)}")
            self.test_results[f"sentiment_{scenario['name']}"] = {
                'status': 'ERROR',
                'error': str(e)
            }

    async def test_topics_scenarios(self):
        """Test topic modeling scenarios"""
        logger.info("=" * 60)
        logger.info("🏷️ TESTING TOPICS SCENARIOS")
        logger.info("=" * 60)

        scenarios = [
            {
                'name': 'Technology Topics',
                'scope': 'технологические тренды',
                'timeframe': '7d'
            },
            {
                'name': 'Market Topics',
                'scope': 'рыночная динамика',
                'timeframe': '14d'
            },
            {
                'name': 'Innovation Topics',
                'scope': 'инновационные решения',
                'timeframe': '30d'
            }
        ]

        for scenario in scenarios:
            await self.test_topics_scenario(scenario)

    async def test_topics_scenario(self, scenario: Dict[str, Any]):
        """Test a specific topics scenario"""
        logger.info(f"🏷️ Testing topics: {scenario['name']}")

        try:
            from data_analysis_processor import analyze_topics

            start_time = time.time()
            result = await analyze_topics(
                scope=scenario['scope'],
                timeframe=scenario['timeframe']
            )
            processing_time = time.time() - start_time

            if result.success:
                logger.info(f"✅ {scenario['name']} - SUCCESS")
                logger.info(f"⏱️ Processing time: {processing_time:.2f}s")

                topic_metrics = result.data.get('topic_metrics', {})
                trend_indicators = result.data.get('trend_indicators', {})

                logger.info(f"📊 Topic diversity: {topic_metrics.get('topic_diversity', 0):.2f}")
                logger.info(f"📊 Keyword density: {topic_metrics.get('keyword_density', 0):.2f}")

                if 'topics_analysis' in result.data:
                    analysis = result.data['topics_analysis']
                    if analysis:
                        logger.info(f"📋 Analysis preview: {analysis[:150]}...")

                self.test_results[f"topics_{scenario['name']}"] = {
                    'status': 'PASSED',
                    'processing_time': processing_time,
                    'topic_metrics': topic_metrics
                }
            else:
                logger.error(f"❌ {scenario['name']} - FAILED: {result.error}")
                self.test_results[f"topics_{scenario['name']}"] = {
                    'status': 'FAILED',
                    'error': result.error
                }

        except Exception as e:
            logger.error(f"❌ {scenario['name']} - EXCEPTION: {str(e)}")
            self.test_results[f"topics_{scenario['name']}"] = {
                'status': 'ERROR',
                'error': str(e)
            }

    def generate_comprehensive_report(self):
        """Generate comprehensive test report"""
        total_time = time.time() - self.total_start_time if self.total_start_time else 0

        logger.info("=" * 80)
        logger.info("📋 COMPREHENSIVE TEST RESULTS REPORT")
        logger.info("=" * 80)

        # Count results by status
        passed = sum(1 for result in self.test_results.values() if result['status'] == 'PASSED')
        failed = sum(1 for result in self.test_results.values() if result['status'] == 'FAILED')
        errors = sum(1 for result in self.test_results.values() if result['status'] == 'ERROR')
        total = len(self.test_results)

        logger.info(f"📊 OVERALL STATISTICS:")
        logger.info(f"   ✅ Passed: {passed}/{total} ({passed/total*100:.1f}%)")
        logger.info(f"   ❌ Failed: {failed}/{total} ({failed/total*100:.1f}%)")
        logger.info(f"   🚫 Errors: {errors}/{total} ({errors/total*100:.1f}%)")
        logger.info(f"   ⏱️ Total time: {total_time:.2f}s")

        # Detailed results by command type
        command_types = ['analyze', 'summarize', 'aggregate', 'filter', 'insights', 'sentiment', 'topics']

        logger.info(f"\n📋 RESULTS BY COMMAND TYPE:")
        for cmd_type in command_types:
            cmd_results = {k: v for k, v in self.test_results.items() if k.startswith(cmd_type)}
            if cmd_results:
                cmd_passed = sum(1 for r in cmd_results.values() if r['status'] == 'PASSED')
                cmd_total = len(cmd_results)
                success_rate = cmd_passed / cmd_total * 100 if cmd_total > 0 else 0

                status_emoji = "✅" if success_rate == 100 else "⚠️" if success_rate >= 50 else "❌"
                logger.info(f"   {status_emoji} /{cmd_type}: {cmd_passed}/{cmd_total} ({success_rate:.1f}%)")

        # Individual test results
        logger.info(f"\n📋 INDIVIDUAL TEST RESULTS:")
        for test_name, result in self.test_results.items():
            status_emoji = {"PASSED": "✅", "FAILED": "❌", "ERROR": "🚫"}[result['status']]

            time_info = f" ({result.get('processing_time', 0):.2f}s)" if 'processing_time' in result else ""
            error_info = f" - {result['error']}" if result['status'] != 'PASSED' and 'error' in result else ""

            logger.info(f"   {status_emoji} {test_name}{time_info}{error_info}")

        # Performance analysis
        if passed > 0:
            processing_times = [r.get('processing_time', 0) for r in self.test_results.values() if r['status'] == 'PASSED']
            if processing_times:
                avg_time = sum(processing_times) / len(processing_times)
                max_time = max(processing_times)
                min_time = min(processing_times)

                logger.info(f"\n📊 PERFORMANCE ANALYSIS:")
                logger.info(f"   ⏱️ Average processing time: {avg_time:.2f}s")
                logger.info(f"   ⏱️ Max processing time: {max_time:.2f}s")
                logger.info(f"   ⏱️ Min processing time: {min_time:.2f}s")

        # Final status
        logger.info(f"\n🎯 FINAL STATUS:")
        if passed == total:
            logger.info("🎉 ALL TESTS PASSED! Data analysis system is fully operational.")
        elif passed >= total * 0.8:
            logger.info(f"✅ MOSTLY SUCCESSFUL! {passed}/{total} tests passed. Minor issues detected.")
        elif passed >= total * 0.5:
            logger.info(f"⚠️ PARTIALLY SUCCESSFUL! {passed}/{total} tests passed. Significant issues need attention.")
        else:
            logger.info(f"❌ MAJOR ISSUES DETECTED! Only {passed}/{total} tests passed. System needs repair.")

        # Save results to file
        report_data = {
            'timestamp': datetime.now().isoformat(),
            'total_time': total_time,
            'summary': {
                'total_tests': total,
                'passed': passed,
                'failed': failed,
                'errors': errors,
                'success_rate': passed / total * 100 if total > 0 else 0
            },
            'detailed_results': self.test_results
        }

        try:
            with open('data_analysis_test_report.json', 'w', encoding='utf-8') as f:
                json.dump(report_data, f, ensure_ascii=False, indent=2)
            logger.info(f"📄 Detailed report saved to: data_analysis_test_report.json")
        except Exception as e:
            logger.error(f"❌ Failed to save report: {e}")

        logger.info("=" * 80)


async def main():
    """Main test execution"""
    test_suite = DataAnalysisTestSuite()
    await test_suite.run_comprehensive_tests()


if __name__ == "__main__":
    asyncio.run(main())