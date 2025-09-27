#!/usr/bin/env python3
"""
🧪 Individual Command Testing Suite
Тестирование каждой команды по отдельности с детальным анализом результатов
"""

import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import Dict, Any, List

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('individual_commands_test.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# Load environment
try:
    from dotenv import load_dotenv
    load_dotenv()
    logger.info("✅ Environment loaded")
except ImportError:
    logger.warning("⚠️ dotenv not available")

class IndividualCommandTester:
    """Тестирование команд по отдельности"""

    def __init__(self):
        self.results = {}
        self.test_data = self._get_test_data()

    def _get_test_data(self) -> List[Dict[str, Any]]:
        """Подготовка тестовых данных"""
        return [
            {
                'title': 'Искусственный интеллект: прорыв в технологиях 2025',
                'content': 'Новейшие разработки в области ИИ демонстрируют значительный прогресс. GPT-5 и аналогичные модели показывают улучшение на 40% в точности анализа данных. Эксперты прогнозируют революционные изменения в автоматизации бизнес-процессов и принятии решений.',
                'source': 'TechNews',
                'source_domain': 'technews.com',
                'published_at': '2025-09-25T10:00:00',
                'score': 0.95,
                'tags': ['AI', 'technology', 'automation']
            },
            {
                'title': 'Рынок криптовалют: анализ трендов и перспектив',
                'content': 'Криптовалютный рынок демонстрирует стабилизацию после волатильного периода. Bitcoin торгуется в диапазоне $45,000-$50,000, показывая признаки консолидации. Институциональные инвесторы проявляют возрастающий интерес к цифровым активам.',
                'source': 'CryptoDaily',
                'source_domain': 'crypto.daily',
                'published_at': '2025-09-25T09:30:00',
                'score': 0.88,
                'tags': ['crypto', 'market', 'investment']
            },
            {
                'title': 'Зеленые технологии привлекают рекордные инвестиции',
                'content': 'Сектор экологически чистых технологий получил $127 млрд инвестиций в 2025 году. Солнечная энергетика и ветроэнергетика показывают рекордную эффективность. Правительства активно поддерживают переход к устойчивой энергетике.',
                'source': 'GreenTech',
                'source_domain': 'greentech.org',
                'published_at': '2025-09-25T08:45:00',
                'score': 0.91,
                'tags': ['green', 'energy', 'investment']
            }
        ]

    async def test_analyze_command(self):
        """Тест команды /analyze"""
        logger.info("🧠 TESTING /analyze COMMAND")
        logger.info("=" * 50)

        try:
            from data_analysis_processor import analyze_data

            # Тест с разными параметрами
            test_cases = [
                {
                    'name': 'Basic Analysis',
                    'query': 'технологии',
                    'timeframe': '7d'
                },
                {
                    'name': 'Market Analysis',
                    'query': 'рынок криптовалют',
                    'timeframe': '14d'
                },
                {
                    'name': 'Long-term Analysis',
                    'query': 'инвестиции',
                    'timeframe': '30d'
                }
            ]

            results = []
            for case in test_cases:
                logger.info(f"\n🔬 Testing: {case['name']}")

                start_time = time.time()
                result = await analyze_data(
                    query=case['query'],
                    timeframe=case['timeframe']
                )
                processing_time = time.time() - start_time

                # Анализ результата
                analysis_result = self._analyze_result(result, case, processing_time)
                results.append(analysis_result)

                # Логирование результатов
                self._log_result(case['name'], result, analysis_result)

            self.results['analyze'] = {
                'overall_success': all(r['success'] for r in results),
                'test_cases': results,
                'recommendations': self._generate_analyze_recommendations(results)
            }

        except Exception as e:
            logger.error(f"❌ /analyze test failed: {e}")
            self.results['analyze'] = {'error': str(e), 'success': False}

    async def test_summarize_command(self):
        """Тест команды /summarize"""
        logger.info("📋 TESTING /summarize COMMAND")
        logger.info("=" * 50)

        try:
            from data_analysis_processor import summarize_data

            test_cases = [
                {
                    'name': 'Short Summary',
                    'topic': 'технологические новости',
                    'length': 'short',
                    'timeframe': '7d'
                },
                {
                    'name': 'Medium Summary',
                    'topic': 'рыночная аналитика',
                    'length': 'medium',
                    'timeframe': '7d'
                },
                {
                    'name': 'Long Summary',
                    'topic': 'инвестиционные тренды',
                    'length': 'long',
                    'timeframe': '7d'
                }
            ]

            results = []
            for case in test_cases:
                logger.info(f"\n📝 Testing: {case['name']}")

                start_time = time.time()
                result = await summarize_data(
                    topic=case['topic'],
                    length=case['length'],
                    timeframe=case['timeframe']
                )
                processing_time = time.time() - start_time

                analysis_result = self._analyze_summarize_result(result, case, processing_time)
                results.append(analysis_result)
                self._log_result(case['name'], result, analysis_result)

            self.results['summarize'] = {
                'overall_success': all(r['success'] for r in results),
                'test_cases': results,
                'recommendations': self._generate_summarize_recommendations(results)
            }

        except Exception as e:
            logger.error(f"❌ /summarize test failed: {e}")
            self.results['summarize'] = {'error': str(e), 'success': False}

    async def test_aggregate_command(self):
        """Тест команды /aggregate"""
        logger.info("📊 TESTING /aggregate COMMAND")
        logger.info("=" * 50)

        try:
            from data_analysis_processor import aggregate_data

            test_cases = [
                {
                    'name': 'Source Aggregation',
                    'metric': 'источники',
                    'groupby': 'дата',
                    'query': 'новости технологий'
                },
                {
                    'name': 'Content Aggregation',
                    'metric': 'контент',
                    'groupby': 'источник',
                    'query': 'рыночные данные'
                },
                {
                    'name': 'Time Aggregation',
                    'metric': 'темы',
                    'groupby': 'время',
                    'query': 'инвестиции'
                }
            ]

            results = []
            for case in test_cases:
                logger.info(f"\n📈 Testing: {case['name']}")

                start_time = time.time()
                result = await aggregate_data(
                    metric=case['metric'],
                    groupby=case['groupby'],
                    query=case['query'],
                    timeframe='7d'
                )
                processing_time = time.time() - start_time

                analysis_result = self._analyze_aggregate_result(result, case, processing_time)
                results.append(analysis_result)
                self._log_result(case['name'], result, analysis_result)

            self.results['aggregate'] = {
                'overall_success': all(r['success'] for r in results),
                'test_cases': results,
                'recommendations': self._generate_aggregate_recommendations(results)
            }

        except Exception as e:
            logger.error(f"❌ /aggregate test failed: {e}")
            self.results['aggregate'] = {'error': str(e), 'success': False}

    async def test_filter_command(self):
        """Тест команды /filter"""
        logger.info("🔍 TESTING /filter COMMAND")
        logger.info("=" * 50)

        try:
            from data_analysis_processor import filter_data

            test_cases = [
                {
                    'name': 'Source Filter',
                    'criteria': 'источник',
                    'value': 'technews.com',
                    'query': 'технологии'
                },
                {
                    'name': 'Content Filter',
                    'criteria': 'содержание',
                    'value': 'ИИ',
                    'query': 'искусственный интеллект'
                },
                {
                    'name': 'Title Filter',
                    'criteria': 'название',
                    'value': 'рынок',
                    'query': 'рыночный анализ'
                }
            ]

            results = []
            for case in test_cases:
                logger.info(f"\n🔎 Testing: {case['name']}")

                start_time = time.time()
                result = await filter_data(
                    criteria=case['criteria'],
                    value=case['value'],
                    query=case['query'],
                    timeframe='7d'
                )
                processing_time = time.time() - start_time

                analysis_result = self._analyze_filter_result(result, case, processing_time)
                results.append(analysis_result)
                self._log_result(case['name'], result, analysis_result)

            self.results['filter'] = {
                'overall_success': all(r['success'] for r in results),
                'test_cases': results,
                'recommendations': self._generate_filter_recommendations(results)
            }

        except Exception as e:
            logger.error(f"❌ /filter test failed: {e}")
            self.results['filter'] = {'error': str(e), 'success': False}

    async def test_insights_command(self):
        """Тест команды /insights"""
        logger.info("💡 TESTING /insights COMMAND")
        logger.info("=" * 50)

        try:
            from data_analysis_processor import generate_insights

            test_cases = [
                {
                    'name': 'Tech Insights',
                    'topic': 'технологический рынок',
                    'timeframe': '7d'
                },
                {
                    'name': 'Investment Insights',
                    'topic': 'инвестиционные возможности',
                    'timeframe': '14d'
                },
                {
                    'name': 'Market Insights',
                    'topic': 'рыночные тенденции',
                    'timeframe': '30d'
                }
            ]

            results = []
            for case in test_cases:
                logger.info(f"\n💼 Testing: {case['name']}")

                start_time = time.time()
                result = await generate_insights(
                    topic=case['topic'],
                    timeframe=case['timeframe']
                )
                processing_time = time.time() - start_time

                analysis_result = self._analyze_insights_result(result, case, processing_time)
                results.append(analysis_result)
                self._log_result(case['name'], result, analysis_result)

            self.results['insights'] = {
                'overall_success': all(r['success'] for r in results),
                'test_cases': results,
                'recommendations': self._generate_insights_recommendations(results)
            }

        except Exception as e:
            logger.error(f"❌ /insights test failed: {e}")
            self.results['insights'] = {'error': str(e), 'success': False}

    async def test_sentiment_command(self):
        """Тест команды /sentiment"""
        logger.info("😊 TESTING /sentiment COMMAND")
        logger.info("=" * 50)

        try:
            from data_analysis_processor import analyze_sentiment

            test_cases = [
                {
                    'name': 'Tech Sentiment',
                    'query': 'технологические новости',
                    'timeframe': '7d'
                },
                {
                    'name': 'Market Sentiment',
                    'query': 'рыночные настроения',
                    'timeframe': '14d'
                },
                {
                    'name': 'Crypto Sentiment',
                    'query': 'криптовалютный рынок',
                    'timeframe': '30d'
                }
            ]

            results = []
            for case in test_cases:
                logger.info(f"\n😊 Testing: {case['name']}")

                start_time = time.time()
                result = await analyze_sentiment(
                    query=case['query'],
                    timeframe=case['timeframe']
                )
                processing_time = time.time() - start_time

                analysis_result = self._analyze_sentiment_result(result, case, processing_time)
                results.append(analysis_result)
                self._log_result(case['name'], result, analysis_result)

            self.results['sentiment'] = {
                'overall_success': all(r['success'] for r in results),
                'test_cases': results,
                'recommendations': self._generate_sentiment_recommendations(results)
            }

        except Exception as e:
            logger.error(f"❌ /sentiment test failed: {e}")
            self.results['sentiment'] = {'error': str(e), 'success': False}

    async def test_topics_command(self):
        """Тест команды /topics"""
        logger.info("🏷️ TESTING /topics COMMAND")
        logger.info("=" * 50)

        try:
            from data_analysis_processor import analyze_topics

            test_cases = [
                {
                    'name': 'Tech Topics',
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

            results = []
            for case in test_cases:
                logger.info(f"\n🏷️ Testing: {case['name']}")

                start_time = time.time()
                result = await analyze_topics(
                    scope=case['scope'],
                    timeframe=case['timeframe']
                )
                processing_time = time.time() - start_time

                analysis_result = self._analyze_topics_result(result, case, processing_time)
                results.append(analysis_result)
                self._log_result(case['name'], result, analysis_result)

            self.results['topics'] = {
                'overall_success': all(r['success'] for r in results),
                'test_cases': results,
                'recommendations': self._generate_topics_recommendations(results)
            }

        except Exception as e:
            logger.error(f"❌ /topics test failed: {e}")
            self.results['topics'] = {'error': str(e), 'success': False}

    def _analyze_result(self, result, case, processing_time):
        """Базовый анализ результата"""
        analysis = {
            'success': result.success,
            'processing_time': processing_time,
            'case_name': case['name'],
            'metadata': result.metadata if result.success else None,
            'issues': [],
            'strengths': []
        }

        if result.success:
            # Проверка качества результата
            if 'analysis' in result.data:
                content = result.data['analysis']
                if len(content) < 50:
                    analysis['issues'].append('Анализ слишком короткий')
                elif len(content) > 100:
                    analysis['strengths'].append('Детальный анализ')

            if processing_time < 1.0:
                analysis['strengths'].append('Быстрая обработка')
            elif processing_time > 5.0:
                analysis['issues'].append('Медленная обработка')

        else:
            analysis['issues'].append(f'Ошибка: {result.error}')

        return analysis

    def _analyze_summarize_result(self, result, case, processing_time):
        """Анализ результата суммаризации"""
        analysis = self._analyze_result(result, case, processing_time)

        if result.success and 'summary' in result.data:
            word_count = result.data.get('word_count', 0)
            expected_ranges = {
                'short': (20, 100),
                'medium': (50, 200),
                'long': (100, 400)
            }

            expected_range = expected_ranges.get(case['length'], (50, 200))
            if expected_range[0] <= word_count <= expected_range[1]:
                analysis['strengths'].append(f'Корректная длина: {word_count} слов')
            else:
                analysis['issues'].append(f'Некорректная длина: {word_count} (ожидалось {expected_range})')

        return analysis

    def _analyze_aggregate_result(self, result, case, processing_time):
        """Анализ результата агрегации"""
        analysis = self._analyze_result(result, case, processing_time)

        if result.success:
            if 'raw_aggregation' in result.data:
                analysis['strengths'].append('Есть сырые данные агрегации')

            if 'aggregation_analysis' in result.data:
                analysis['strengths'].append('Есть анализ агрегации')

        return analysis

    def _analyze_filter_result(self, result, case, processing_time):
        """Анализ результата фильтрации"""
        analysis = self._analyze_result(result, case, processing_time)

        if result.success and 'filter_stats' in result.data:
            stats = result.data['filter_stats']
            filter_ratio = stats.get('filter_ratio', 0)

            if 0 < filter_ratio < 1:
                analysis['strengths'].append(f'Эффективная фильтрация: {filter_ratio:.1%}')
            elif filter_ratio == 0:
                analysis['issues'].append('Фильтр ничего не нашел')
            elif filter_ratio == 1:
                analysis['issues'].append('Фильтр не отфильтровал ничего')

        return analysis

    def _analyze_insights_result(self, result, case, processing_time):
        """Анализ результата инсайтов"""
        analysis = self._analyze_result(result, case, processing_time)

        if result.success:
            confidence = result.data.get('confidence_score', 0)
            if confidence > 0.7:
                analysis['strengths'].append(f'Высокая уверенность: {confidence:.2f}')
            elif confidence < 0.3:
                analysis['issues'].append(f'Низкая уверенность: {confidence:.2f}')

        return analysis

    def _analyze_sentiment_result(self, result, case, processing_time):
        """Анализ результата анализа тональности"""
        analysis = self._analyze_result(result, case, processing_time)

        if result.success and 'sentiment_metrics' in result.data:
            metrics = result.data['sentiment_metrics']
            avg_sentiment = metrics.get('average_sentiment', 0)

            if -1 <= avg_sentiment <= 1:
                analysis['strengths'].append(f'Корректная тональность: {avg_sentiment:.2f}')
            else:
                analysis['issues'].append(f'Некорректная тональность: {avg_sentiment}')

        return analysis

    def _analyze_topics_result(self, result, case, processing_time):
        """Анализ результата моделирования тем"""
        analysis = self._analyze_result(result, case, processing_time)

        if result.success and 'topic_metrics' in result.data:
            metrics = result.data['topic_metrics']
            diversity = metrics.get('topic_diversity', 0)

            if diversity > 0.1:
                analysis['strengths'].append(f'Хорошее разнообразие тем: {diversity:.2f}')
            else:
                analysis['issues'].append(f'Низкое разнообразие тем: {diversity:.2f}')

        return analysis

    def _log_result(self, test_name, result, analysis):
        """Логирование результата теста"""
        status = "✅ SUCCESS" if analysis['success'] else "❌ FAILED"
        logger.info(f"   {status} - {test_name}")
        logger.info(f"     ⏱️ Time: {analysis['processing_time']:.2f}s")

        if analysis['strengths']:
            logger.info(f"     💪 Strengths: {', '.join(analysis['strengths'])}")

        if analysis['issues']:
            logger.info(f"     ⚠️ Issues: {', '.join(analysis['issues'])}")

        if result.success and result.data:
            for key, value in result.data.items():
                if isinstance(value, str) and len(value) > 100:
                    logger.info(f"     📄 {key}: {value[:100]}...")
                elif not isinstance(value, dict):
                    logger.info(f"     📊 {key}: {value}")

    def _generate_analyze_recommendations(self, results):
        """Рекомендации для команды analyze"""
        recommendations = []

        # Анализ времени обработки
        avg_time = sum(r['processing_time'] for r in results) / len(results)
        if avg_time > 3.0:
            recommendations.append("Оптимизировать время обработки анализа")

        # Анализ качества контента
        short_analyses = sum(1 for r in results if 'Анализ слишком короткий' in r.get('issues', []))
        if short_analyses > 0:
            recommendations.append("Увеличить детальность анализа")

        return recommendations

    def _generate_summarize_recommendations(self, results):
        """Рекомендации для команды summarize"""
        recommendations = []

        length_issues = sum(1 for r in results if any('длина' in issue for issue in r.get('issues', [])))
        if length_issues > 0:
            recommendations.append("Настроить алгоритм определения длины суммаризации")

        return recommendations

    def _generate_aggregate_recommendations(self, results):
        """Рекомендации для команды aggregate"""
        recommendations = []

        missing_data = sum(1 for r in results if not r.get('success'))
        if missing_data > 0:
            recommendations.append("Улучшить обработку данных агрегации")

        return recommendations

    def _generate_filter_recommendations(self, results):
        """Рекомендации для команды filter"""
        recommendations = []

        ineffective_filters = sum(1 for r in results if 'ничего не нашел' in str(r.get('issues', [])))
        if ineffective_filters > 0:
            recommendations.append("Улучшить алгоритмы фильтрации")

        return recommendations

    def _generate_insights_recommendations(self, results):
        """Рекомендации для команды insights"""
        recommendations = []

        low_confidence = sum(1 for r in results if 'Низкая уверенность' in str(r.get('issues', [])))
        if low_confidence > 0:
            recommendations.append("Повысить точность генерации инсайтов")

        return recommendations

    def _generate_sentiment_recommendations(self, results):
        """Рекомендации для команды sentiment"""
        recommendations = []

        incorrect_sentiment = sum(1 for r in results if 'Некорректная тональность' in str(r.get('issues', [])))
        if incorrect_sentiment > 0:
            recommendations.append("Исправить алгоритм анализа тональности")

        return recommendations

    def _generate_topics_recommendations(self, results):
        """Рекомендации для команды topics"""
        recommendations = []

        low_diversity = sum(1 for r in results if 'Низкое разнообразие' in str(r.get('issues', [])))
        if low_diversity > 0:
            recommendations.append("Улучшить алгоритм выявления тем")

        return recommendations

    async def run_all_individual_tests(self):
        """Запуск всех индивидуальных тестов"""
        logger.info("🚀 Starting Individual Command Testing")
        logger.info(f"⏰ Start time: {datetime.now()}")

        # Проверка API ключа
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            logger.error("❌ OPENAI_API_KEY not found!")
            return

        # Запуск тестов по очереди
        await self.test_analyze_command()
        await self.test_summarize_command()
        await self.test_aggregate_command()
        await self.test_filter_command()
        await self.test_insights_command()
        await self.test_sentiment_command()
        await self.test_topics_command()

        # Финальный отчет
        self.generate_final_report()

    def generate_final_report(self):
        """Генерация финального отчета"""
        logger.info("\n" + "=" * 80)
        logger.info("📋 FINAL INDIVIDUAL TESTING REPORT")
        logger.info("=" * 80)

        # Общая статистика
        total_commands = len(self.results)
        successful_commands = sum(1 for r in self.results.values() if r.get('overall_success', False))

        logger.info(f"📊 OVERALL STATISTICS:")
        logger.info(f"   ✅ Successful commands: {successful_commands}/{total_commands}")
        logger.info(f"   ❌ Failed commands: {total_commands - successful_commands}/{total_commands}")

        # Детали по каждой команде
        logger.info(f"\n📋 COMMAND DETAILS:")
        for cmd_name, cmd_results in self.results.items():
            if 'error' in cmd_results:
                logger.info(f"   ❌ /{cmd_name}: ERROR - {cmd_results['error']}")
            else:
                success_rate = cmd_results.get('overall_success', False)
                status = "✅" if success_rate else "⚠️"

                test_cases = cmd_results.get('test_cases', [])
                passed_cases = sum(1 for tc in test_cases if tc['success'])
                total_cases = len(test_cases)

                logger.info(f"   {status} /{cmd_name}: {passed_cases}/{total_cases} test cases passed")

                # Рекомендации
                recommendations = cmd_results.get('recommendations', [])
                if recommendations:
                    logger.info(f"      💡 Recommendations:")
                    for rec in recommendations:
                        logger.info(f"         - {rec}")

        # Сохранение детального отчета
        report_data = {
            'timestamp': datetime.now().isoformat(),
            'summary': {
                'total_commands': total_commands,
                'successful_commands': successful_commands,
                'success_rate': successful_commands / total_commands * 100 if total_commands > 0 else 0
            },
            'detailed_results': self.results
        }

        try:
            with open('individual_commands_report.json', 'w', encoding='utf-8') as f:
                json.dump(report_data, f, ensure_ascii=False, indent=2)
            logger.info(f"\n📄 Detailed report saved to: individual_commands_report.json")
        except Exception as e:
            logger.error(f"❌ Failed to save report: {e}")

        logger.info("=" * 80)


async def test_single_command(command_name: str):
    """Тестирование одной конкретной команды"""
    tester = IndividualCommandTester()

    if command_name == 'analyze':
        await tester.test_analyze_command()
    elif command_name == 'summarize':
        await tester.test_summarize_command()
    elif command_name == 'aggregate':
        await tester.test_aggregate_command()
    elif command_name == 'filter':
        await tester.test_filter_command()
    elif command_name == 'insights':
        await tester.test_insights_command()
    elif command_name == 'sentiment':
        await tester.test_sentiment_command()
    elif command_name == 'topics':
        await tester.test_topics_command()
    else:
        logger.error(f"❌ Unknown command: {command_name}")
        return

    # Показать результаты для одной команды
    if command_name in tester.results:
        result = tester.results[command_name]
        logger.info(f"\n🎯 RESULTS FOR /{command_name}:")
        logger.info(f"   Success: {result.get('overall_success', False)}")

        if 'recommendations' in result:
            logger.info(f"   Recommendations: {result['recommendations']}")


async def main():
    """Главная функция"""
    if len(sys.argv) > 1:
        # Тестирование одной команды
        command = sys.argv[1]
        await test_single_command(command)
    else:
        # Тестирование всех команд
        tester = IndividualCommandTester()
        await tester.run_all_individual_tests()


if __name__ == "__main__":
    asyncio.run(main())