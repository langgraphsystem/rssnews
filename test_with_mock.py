#!/usr/bin/env python3
"""
🧪 Testing with Mock GPT-5 Service
Тестирование с заглушкой для демонстрации функциональности
"""

import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('mock_test_results.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# Import mock service
from mock_gpt5_service import MockGPT5Service, create_mock_gpt5_service

class MockDataAnalysisProcessor:
    """Процессор данных с mock GPT-5 сервисом"""

    def __init__(self):
        self.gpt5_service = create_mock_gpt5_service("gpt-5")
        logger.info("✅ Mock data analysis processor initialized")

    def _get_test_articles(self, query: str, limit: int = 3):
        """Получение тестовых статей"""
        return [
            {
                'title': f'Анализ {query}: ключевые тренды 2025',
                'content': f'Исследование {query} показывает значительный рост и развитие новых технологий. Эксперты прогнозируют дальнейшее развитие сферы с увеличением инвестиций на 40%. Основные драйверы роста включают цифровую трансформацию и инновационные решения.',
                'source': 'TechAnalytics',
                'source_domain': 'techanalytics.com',
                'published_at': '2025-09-25T10:00:00',
                'score': 0.95,
                'tags': ['analysis', 'trends', 'technology']
            },
            {
                'title': f'Рыночные перспективы {query}',
                'content': f'Рынок {query} демонстрирует устойчивую тенденцию роста. Инвесторы проявляют активный интерес к данному сегменту, что подтверждается увеличением капитализации на 25%. Ожидается дальнейшее развитие инфраструктуры и экосистемы.',
                'source': 'MarketInsights',
                'source_domain': 'marketinsights.com',
                'published_at': '2025-09-25T09:30:00',
                'score': 0.88,
                'tags': ['market', 'investment', 'growth']
            },
            {
                'title': f'Инновации в области {query}',
                'content': f'Последние инновации в {query} открывают новые возможности для бизнеса и потребителей. Технологические решения становятся более доступными и эффективными. Компании активно внедряют новые подходы для повышения конкурентоспособности.',
                'source': 'InnovationDaily',
                'source_domain': 'innovation.daily',
                'published_at': '2025-09-25T08:45:00',
                'score': 0.91,
                'tags': ['innovation', 'technology', 'business']
            }
        ]

    def _format_articles_for_gpt(self, articles, include_metadata=False):
        """Форматирование статей для GPT"""
        formatted = []
        for i, article in enumerate(articles):
            title = article.get('title', 'No title')[:150]
            content = article.get('content', '')[:400]

            text = f"Статья {i+1}:\nНазвание: {title}\nСодержание: {content}\n"

            if include_metadata:
                source = article.get('source', 'Unknown')
                date = article.get('published_at', 'Unknown')
                score = article.get('score', 0)
                text += f"Источник: {source}\nДата: {date}\nРелевантность: {score:.2f}\n"

            text += "---\n"
            formatted.append(text)

        return '\n'.join(formatted)

    async def test_analyze_command(self, query: str, timeframe: str = "7d"):
        """Тест команды /analyze"""
        logger.info(f"🧠 Testing /analyze: {query}")

        articles = self._get_test_articles(query)
        articles_text = self._format_articles_for_gpt(articles, include_metadata=True)

        prompt = f"""Проанализируй следующие {len(articles)} статей о '{query}':

ДАННЫЕ:
{articles_text}

Предоставь глубокий анализ, включая:
1. Ключевые тренды и паттерны
2. Важные инсайты и выводы
3. Прогнозы и рекомендации
4. Статистические данные
5. Сравнительный анализ

Формат с графиками, таблицами и визуальными элементами с использованием эмодзи."""

        start_time = time.time()
        result = self.gpt5_service.send_analysis(prompt, max_output_tokens=2000)
        processing_time = time.time() - start_time

        return {
            'success': True,
            'result': result,
            'processing_time': processing_time,
            'articles_count': len(articles)
        }

    async def test_summarize_command(self, topic: str, length: str = "medium"):
        """Тест команды /summarize"""
        logger.info(f"📋 Testing /summarize: {topic} ({length})")

        articles = self._get_test_articles(topic)
        articles_text = self._format_articles_for_gpt(articles, include_metadata=True)

        prompt = f"""Создай профессиональную сводку {length} длины по {len(articles)} статьям на тему '{topic}':

ИСХОДНЫЕ ДАННЫЕ:
{articles_text}

ТРЕБОВАНИЯ К СВОДКЕ:
- Размер: {length}
- Структурированный формат
- Выделение ключевых фактов
- Хронологический порядок событий

Используй ясный деловой стиль с маркированными списками."""

        start_time = time.time()
        result = self.gpt5_service.send_chat(prompt, length=length)
        processing_time = time.time() - start_time

        word_count = len(result.split()) if result else 0

        return {
            'success': True,
            'result': result,
            'processing_time': processing_time,
            'word_count': word_count,
            'length': length
        }

    async def test_aggregate_command(self, metric: str, groupby: str, query: str):
        """Тест команды /aggregate"""
        logger.info(f"📊 Testing /aggregate: {metric} by {groupby}")

        articles = self._get_test_articles(query)
        articles_text = self._format_articles_for_gpt(articles, include_metadata=True)

        prompt = f"""Проведи агрегацию и анализ данных по {len(articles)} статьям:

ДАННЫЕ:
{articles_text}

ЗАДАЧА АГРЕГАЦИИ:
- Метрика: {metric}
- Группировка: {groupby}

Представь результаты в структурированном виде с четкими таблицами и графиками."""

        start_time = time.time()
        result = self.gpt5_service.send_bulk(prompt)
        processing_time = time.time() - start_time

        return {
            'success': True,
            'result': result,
            'processing_time': processing_time,
            'metric': metric,
            'groupby': groupby
        }

    async def test_filter_command(self, criteria: str, value: str, query: str):
        """Тест команды /filter"""
        logger.info(f"🔍 Testing /filter: {criteria} = {value}")

        articles = self._get_test_articles(query)
        articles_text = self._format_articles_for_gpt(articles, include_metadata=True)

        prompt = f"""Выполни умную фильтрацию и анализ данных:

ИСХОДНЫЕ ДАННЫЕ ({len(articles)} статей):
{articles_text}

КРИТЕРИИ ФИЛЬТРАЦИИ:
- Параметр: {criteria}
- Значение: {value}

Предоставь детальный анализ с примерами и рекомендациями."""

        start_time = time.time()
        result = self.gpt5_service.send_chat(prompt)
        processing_time = time.time() - start_time

        return {
            'success': True,
            'result': result,
            'processing_time': processing_time,
            'criteria': criteria,
            'value': value
        }

    async def test_insights_command(self, topic: str):
        """Тест команды /insights"""
        logger.info(f"💡 Testing /insights: {topic}")

        articles = self._get_test_articles(topic)
        articles_text = self._format_articles_for_gpt(articles, include_metadata=True)

        prompt = f"""Сгенерируй глубокие бизнес-инсайты на основе {len(articles)} статей по теме '{topic}':

ИСТОЧНИКИ ДАННЫХ:
{articles_text}

Представь как executive briefing с четкими разделами и практическими выводами."""

        start_time = time.time()
        result = self.gpt5_service.send_insights(prompt)
        processing_time = time.time() - start_time

        return {
            'success': True,
            'result': result,
            'processing_time': processing_time,
            'topic': topic
        }

    async def test_sentiment_command(self, query: str):
        """Тест команды /sentiment"""
        logger.info(f"😊 Testing /sentiment: {query}")

        articles = self._get_test_articles(query)
        articles_text = self._format_articles_for_gpt(articles, include_metadata=True)

        prompt = f"""Проведи комплексный анализ тональности {len(articles)} статей по теме '{query}':

ДАННЫЕ ДЛЯ АНАЛИЗА:
{articles_text}

Используй эмодзи и четкое форматирование для наглядности."""

        start_time = time.time()
        result = self.gpt5_service.send_sentiment(prompt)
        processing_time = time.time() - start_time

        return {
            'success': True,
            'result': result,
            'processing_time': processing_time,
            'query': query
        }

    async def test_topics_command(self, scope: str):
        """Тест команды /topics"""
        logger.info(f"🏷️ Testing /topics: {scope}")

        articles = self._get_test_articles(scope)
        articles_text = self._format_articles_for_gpt(articles, include_metadata=True)

        prompt = f"""Проведи моделирование тем и анализ трендов для {len(articles)} статей в области '{scope}':

ДАННЫЕ ДЛЯ АНАЛИЗА:
{articles_text}

Используй визуальное форматирование с эмодзи и четкую категоризацию."""

        start_time = time.time()
        result = self.gpt5_service.send_analysis(prompt)
        processing_time = time.time() - start_time

        return {
            'success': True,
            'result': result,
            'processing_time': processing_time,
            'scope': scope
        }

    async def run_comprehensive_test(self):
        """Запуск комплексного теста всех команд"""
        logger.info("🚀 Starting Comprehensive Mock Testing")
        logger.info("=" * 80)

        results = {}

        # Тест всех команд
        test_cases = [
            ('analyze', self.test_analyze_command, ['технологии', '7d']),
            ('summarize', self.test_summarize_command, ['ИИ разработки', 'medium']),
            ('aggregate', self.test_aggregate_command, ['источники', 'дата', 'рынок']),
            ('filter', self.test_filter_command, ['источник', 'tech', 'новости']),
            ('insights', self.test_insights_command, ['инвестиции']),
            ('sentiment', self.test_sentiment_command, ['криптовалюты']),
            ('topics', self.test_topics_command, ['инновации'])
        ]

        total_start = time.time()

        for command_name, test_func, args in test_cases:
            logger.info(f"\n{'='*20} TESTING /{command_name.upper()} {'='*20}")

            try:
                result = await test_func(*args)

                if result['success']:
                    logger.info(f"✅ /{command_name} - SUCCESS")
                    logger.info(f"   ⏱️ Processing time: {result['processing_time']:.2f}s")

                    # Специфичные метрики для каждой команды
                    if command_name == 'analyze':
                        logger.info(f"   📊 Articles analyzed: {result['articles_count']}")
                    elif command_name == 'summarize':
                        logger.info(f"   📝 Word count: {result['word_count']}")
                        logger.info(f"   📏 Length: {result['length']}")
                    elif command_name == 'aggregate':
                        logger.info(f"   📈 Metric: {result['metric']}")
                        logger.info(f"   🗂️ Group by: {result['groupby']}")
                    elif command_name == 'filter':
                        logger.info(f"   🔍 Criteria: {result['criteria']} = {result['value']}")
                    elif command_name == 'insights':
                        logger.info(f"   💡 Topic: {result['topic']}")
                    elif command_name == 'sentiment':
                        logger.info(f"   😊 Query: {result['query']}")
                    elif command_name == 'topics':
                        logger.info(f"   🏷️ Scope: {result['scope']}")

                    # Показать превью результата
                    preview = result['result'][:200] + "..." if len(result['result']) > 200 else result['result']
                    logger.info(f"   📄 Result preview: {preview}")

                    results[command_name] = {
                        'status': 'SUCCESS',
                        'processing_time': result['processing_time'],
                        'result_length': len(result['result']),
                        'metadata': {k: v for k, v in result.items() if k not in ['result']}
                    }
                else:
                    logger.error(f"❌ /{command_name} - FAILED")
                    results[command_name] = {'status': 'FAILED'}

            except Exception as e:
                logger.error(f"❌ /{command_name} - ERROR: {str(e)}")
                results[command_name] = {'status': 'ERROR', 'error': str(e)}

        total_time = time.time() - total_start

        # Финальный отчет
        self.generate_final_report(results, total_time)

        return results

    def generate_final_report(self, results, total_time):
        """Генерация финального отчета"""
        logger.info("\n" + "=" * 80)
        logger.info("📋 COMPREHENSIVE MOCK TEST REPORT")
        logger.info("=" * 80)

        # Общая статистика
        total_commands = len(results)
        successful = sum(1 for r in results.values() if r.get('status') == 'SUCCESS')
        failed = sum(1 for r in results.values() if r.get('status') == 'FAILED')
        errors = sum(1 for r in results.values() if r.get('status') == 'ERROR')

        logger.info(f"📊 OVERALL STATISTICS:")
        logger.info(f"   ✅ Successful: {successful}/{total_commands} ({successful/total_commands*100:.1f}%)")
        logger.info(f"   ❌ Failed: {failed}/{total_commands} ({failed/total_commands*100:.1f}%)")
        logger.info(f"   🚫 Errors: {errors}/{total_commands} ({errors/total_commands*100:.1f}%)")
        logger.info(f"   ⏱️ Total time: {total_time:.2f}s")

        # Детали по командам
        logger.info(f"\n📋 COMMAND DETAILS:")
        for cmd_name, cmd_result in results.items():
            status_emoji = {
                'SUCCESS': '✅',
                'FAILED': '❌',
                'ERROR': '🚫'
            }.get(cmd_result.get('status'), '❓')

            logger.info(f"   {status_emoji} /{cmd_name}: {cmd_result.get('status')}")

            if cmd_result.get('status') == 'SUCCESS':
                proc_time = cmd_result.get('processing_time', 0)
                result_len = cmd_result.get('result_length', 0)
                logger.info(f"      ⏱️ Time: {proc_time:.2f}s")
                logger.info(f"      📄 Result: {result_len} characters")

        # Анализ производительности
        if successful > 0:
            success_results = [r for r in results.values() if r.get('status') == 'SUCCESS']
            avg_time = sum(r.get('processing_time', 0) for r in success_results) / len(success_results)
            avg_length = sum(r.get('result_length', 0) for r in success_results) / len(success_results)

            logger.info(f"\n📊 PERFORMANCE ANALYSIS:")
            logger.info(f"   ⏱️ Average processing time: {avg_time:.2f}s")
            logger.info(f"   📄 Average result length: {avg_length:.0f} characters")

        # Выводы и рекомендации
        logger.info(f"\n🎯 CONCLUSIONS:")
        if successful == total_commands:
            logger.info("🎉 ALL COMMANDS WORKING PERFECTLY!")
            logger.info("✅ System is ready for production use")
        elif successful >= total_commands * 0.8:
            logger.info(f"✅ MOSTLY SUCCESSFUL ({successful}/{total_commands})")
            logger.info("⚠️ Minor issues need attention")
        else:
            logger.info(f"⚠️ NEEDS IMPROVEMENT ({successful}/{total_commands})")
            logger.info("🔧 System requires debugging")

        # Сохранение отчета
        report_data = {
            'timestamp': datetime.now().isoformat(),
            'total_time': total_time,
            'summary': {
                'total_commands': total_commands,
                'successful': successful,
                'failed': failed,
                'errors': errors,
                'success_rate': successful / total_commands * 100 if total_commands > 0 else 0
            },
            'detailed_results': results
        }

        try:
            with open('mock_test_comprehensive_report.json', 'w', encoding='utf-8') as f:
                json.dump(report_data, f, ensure_ascii=False, indent=2)
            logger.info(f"\n📄 Report saved: mock_test_comprehensive_report.json")
        except Exception as e:
            logger.error(f"❌ Failed to save report: {e}")

        logger.info("=" * 80)


async def test_single_command_mock(command_name: str):
    """Тест одной команды с mock сервисом"""
    processor = MockDataAnalysisProcessor()

    if command_name == 'analyze':
        result = await processor.test_analyze_command('технологические тренды')
    elif command_name == 'summarize':
        result = await processor.test_summarize_command('рынок ИИ', 'medium')
    elif command_name == 'aggregate':
        result = await processor.test_aggregate_command('источники', 'дата', 'новости')
    elif command_name == 'filter':
        result = await processor.test_filter_command('источник', 'tech.com', 'технологии')
    elif command_name == 'insights':
        result = await processor.test_insights_command('инвестиционные тренды')
    elif command_name == 'sentiment':
        result = await processor.test_sentiment_command('криптовалютный рынок')
    elif command_name == 'topics':
        result = await processor.test_topics_command('технологические инновации')
    else:
        logger.error(f"❌ Unknown command: {command_name}")
        return

    logger.info(f"\n🎯 SINGLE COMMAND TEST: /{command_name}")
    logger.info(f"✅ Success: {result.get('success', False)}")
    logger.info(f"⏱️ Time: {result.get('processing_time', 0):.2f}s")
    logger.info(f"📄 Result length: {len(result.get('result', ''))}")
    logger.info(f"📋 Preview: {result.get('result', '')[:300]}...")


async def main():
    """Главная функция"""
    if len(sys.argv) > 1:
        # Тест одной команды
        command = sys.argv[1]
        await test_single_command_mock(command)
    else:
        # Комплексный тест
        processor = MockDataAnalysisProcessor()
        await processor.run_comprehensive_test()


if __name__ == "__main__":
    asyncio.run(main())
