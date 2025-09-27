#!/usr/bin/env python3
"""
🤖 GPT-5 Data Analysis Processor
Расширенная система обработки информации по командам GPT-5

Команды:
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
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

# Import project modules
try:
    from gpt5_service_new import create_gpt5_service, GPT5Service
    from pg_client_new import PgClient
    from ranking_api import RankingAPI
    from caching_service import CachingService
    from clustering_service import ClusteringService
except ImportError as e:
    logging.error(f"Import error: {e}")
    sys.exit(1)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('data_analysis.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

class AnalysisType(Enum):
    """Типы анализа данных"""
    DEEP_ANALYSIS = "analyze"
    SUMMARY = "summarize"
    AGGREGATION = "aggregate"
    FILTERING = "filter"
    INSIGHTS = "insights"
    SENTIMENT = "sentiment"
    TOPICS = "topics"

@dataclass
class AnalysisRequest:
    """Запрос на анализ данных"""
    command: AnalysisType
    query: str = ""
    timeframe: str = "7d"
    parameters: Dict[str, Any] = None
    limit: int = 100

    def __post_init__(self):
        if self.parameters is None:
            self.parameters = {}

@dataclass
class AnalysisResult:
    """Результат анализа данных"""
    success: bool
    data: Dict[str, Any]
    metadata: Dict[str, Any]
    processing_time: float
    error: Optional[str] = None

class DataAnalysisProcessor:
    """Главный процессор для анализа данных GPT-5"""

    def __init__(self):
        """Инициализация процессора"""
        self.gpt5_service: Optional[GPT5Service] = None
        self.pg_client: Optional[PgClient] = None
        self.ranking_api: Optional[RankingAPI] = None
        self.caching_service: Optional[CachingService] = None
        self.clustering_service: Optional[ClusteringService] = None
        self._initialize_services()

    def _initialize_services(self):
        """Инициализация всех сервисов"""
        try:
            # GPT-5 Service
            self.gpt5_service = create_gpt5_service("gpt-5")
            logger.info("✅ GPT-5 service initialized")

            # Database connection
            dsn = os.getenv("PG_DSN")
            if dsn:
                self.pg_client = PgClient(dsn)
                logger.info("✅ PostgreSQL client initialized")

            # Ranking API
            if self.pg_client:
                self.ranking_api = RankingAPI(self.pg_client)
                logger.info("✅ Ranking API initialized")

            # Caching service
            self.caching_service = CachingService()
            logger.info("✅ Caching service initialized")

            # Clustering service
            if self.pg_client:
                self.clustering_service = ClusteringService(self.pg_client)
                logger.info("✅ Clustering service initialized")

        except Exception as e:
            logger.error(f"❌ Service initialization error: {e}")

    async def process_analysis_request(self, request: AnalysisRequest) -> AnalysisResult:
        """Основной метод обработки запроса на анализ"""
        start_time = datetime.now()

        try:
            logger.info(f"🔍 Processing {request.command.value} request: {request.query}")

            # Получение данных
            articles = await self._get_articles_for_analysis(
                request.query,
                request.timeframe,
                request.limit
            )

            # Выбор метода анализа
            result_data = await self._route_analysis(request, articles)

            processing_time = (datetime.now() - start_time).total_seconds()

            return AnalysisResult(
                success=True,
                data=result_data,
                metadata={
                    'articles_count': len(articles),
                    'request_type': request.command.value,
                    'query': request.query,
                    'timeframe': request.timeframe,
                    'timestamp': datetime.now().isoformat()
                },
                processing_time=processing_time
            )

        except Exception as e:
            processing_time = (datetime.now() - start_time).total_seconds()
            logger.error(f"❌ Analysis processing error: {e}")

            return AnalysisResult(
                success=False,
                data={},
                metadata={
                    'request_type': request.command.value,
                    'query': request.query,
                    'timestamp': datetime.now().isoformat()
                },
                processing_time=processing_time,
                error=str(e)
            )

    async def _get_articles_for_analysis(self, query: str, timeframe: str, limit: int) -> List[Dict[str, Any]]:
        """Получение статей для анализа"""
        try:
            if not self.ranking_api:
                # Fallback mock data for testing
                return self._get_mock_articles(query, limit)

            # Преобразование timeframe в дни
            days = self._parse_timeframe(timeframe)

            # Поиск через Ranking API
            from ranking_api import SearchRequest
            search_request = SearchRequest(
                query=query,
                method="hybrid",
                limit=limit,
                filters={'time_range': f'{days}d'}
            )

            response = await self.ranking_api.search(search_request)

            if response.success and response.results:
                return response.results
            else:
                logger.warning(f"No results from ranking API, using mock data")
                return self._get_mock_articles(query, limit)

        except Exception as e:
            logger.error(f"Error getting articles: {e}")
            return self._get_mock_articles(query, limit)

    def _get_mock_articles(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """Mock данные для тестирования"""
        mock_articles = [
            {
                'title': f'AI технологии 2025: новые прорывы в {query}',
                'content': f'Исследование показывает значительный прогресс в области {query}. Новые технологии демонстрируют улучшение производительности на 40% по сравнению с предыдущими решениями...',
                'source': 'tech.com',
                'source_domain': 'tech.com',
                'published_at': '2025-09-25T10:00:00',
                'score': 0.95,
                'tags': ['AI', 'technology', 'innovation']
            },
            {
                'title': f'Рыночные тенденции {query}: анализ экспертов',
                'content': f'Аналитики прогнозируют рост рынка {query} на 25% в следующем году. Основными драйверами роста являются инновации и увеличение спроса...',
                'source': 'market.news',
                'source_domain': 'market.news',
                'published_at': '2025-09-25T09:30:00',
                'score': 0.88,
                'tags': ['market', 'trends', 'growth']
            },
            {
                'title': f'Будущее {query}: прогнозы и реальность',
                'content': f'Экспертное мнение о развитии {query} включает анализ текущих трендов и будущих возможностей. Ключевые факторы влияния...',
                'source': 'future.tech',
                'source_domain': 'future.tech',
                'published_at': '2025-09-25T08:45:00',
                'score': 0.82,
                'tags': ['future', 'predictions', 'analysis']
            }
        ]

        return mock_articles[:min(limit, len(mock_articles))]

    def _parse_timeframe(self, timeframe: str) -> int:
        """Парсинг временного диапазона в дни"""
        timeframe = timeframe.lower().strip()

        if timeframe.endswith('d'):
            return int(timeframe[:-1])
        elif timeframe.endswith('w'):
            return int(timeframe[:-1]) * 7
        elif timeframe.endswith('m'):
            return int(timeframe[:-1]) * 30
        else:
            try:
                return int(timeframe)
            except ValueError:
                return 7  # default 1 week

    async def _route_analysis(self, request: AnalysisRequest, articles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Маршрутизация к соответствующему методу анализа"""

        if request.command == AnalysisType.DEEP_ANALYSIS:
            return await self._process_deep_analysis(request, articles)
        elif request.command == AnalysisType.SUMMARY:
            return await self._process_summary(request, articles)
        elif request.command == AnalysisType.AGGREGATION:
            return await self._process_aggregation(request, articles)
        elif request.command == AnalysisType.FILTERING:
            return await self._process_filtering(request, articles)
        elif request.command == AnalysisType.INSIGHTS:
            return await self._process_insights(request, articles)
        elif request.command == AnalysisType.SENTIMENT:
            return await self._process_sentiment(request, articles)
        elif request.command == AnalysisType.TOPICS:
            return await self._process_topics(request, articles)
        else:
            raise ValueError(f"Unknown analysis type: {request.command}")

    async def _process_deep_analysis(self, request: AnalysisRequest, articles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Глубокий анализ данных"""
        logger.info(f"🧠 Processing deep analysis for: {request.query}")

        # Подготовка данных для GPT-5
        articles_text = self._format_articles_for_gpt(articles, include_metadata=True)

        prompt = f"""Проведи глубокий комплексный анализ {len(articles)} статей по теме '{request.query}':

ДАННЫЕ ДЛЯ АНАЛИЗА:
{articles_text}

ТРЕБУЕМЫЙ АНАЛИЗ:
1. **КЛЮЧЕВЫЕ ТРЕНДЫ И ПАТТЕРНЫ**
   - Выявление основных тенденций
   - Анализ закономерностей в данных
   - Временная динамика изменений

2. **СТАТИСТИЧЕСКИЕ ИНСАЙТЫ**
   - Количественные метрики
   - Распределение по источникам
   - Частота упоминаний ключевых терминов

3. **КАЧЕСТВЕННЫЙ АНАЛИЗ**
   - Глубина освещения темы
   - Экспертные мнения и прогнозы
   - Противоречия и спорные моменты

4. **ПРОГНОСТИЧЕСКАЯ АНАЛИТИКА**
   - Краткосрочные прогнозы (1-3 месяца)
   - Долгосрочные тренды (6-12 месяцев)
   - Факторы риска и возможности

5. **РЕКОМЕНДАЦИИ**
   - Стратегические выводы
   - Практические рекомендации
   - Области для дальнейшего изучения

Используй структурированный формат с таблицами, графиками (через эмодзи) и визуальными элементами."""

        try:
            analysis_result = self.gpt5_service.send_analysis(
                prompt,
                max_output_tokens=2000,
                verbosity="high",
                reasoning_effort="high"
            )

            # Дополнительные метрики
            metrics = self._calculate_analysis_metrics(articles)

            return {
                'analysis': analysis_result,
                'metrics': metrics,
                'summary_stats': {
                    'total_articles': len(articles),
                    'date_range': self._get_date_range(articles),
                    'top_sources': self._get_top_sources(articles),
                    'avg_score': self._get_average_score(articles)
                }
            }

        except Exception as e:
            logger.error(f"❌ Deep analysis error: {e}")
            return {'error': str(e), 'analysis': 'Анализ недоступен'}

    async def _process_summary(self, request: AnalysisRequest, articles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """AI-powered суммаризация"""
        logger.info(f"📋 Processing summary for: {request.query}")

        length = request.parameters.get('length', 'medium')
        articles_text = self._format_articles_for_gpt(articles, include_metadata=True)

        # Определение размера summary по параметру length
        token_limits = {
            'short': 500,
            'medium': 1000,
            'long': 1500,
            'detailed': 2000
        }
        max_tokens = token_limits.get(length, 1000)

        prompt = f"""Создай профессиональную сводку {length} длины по {len(articles)} статьям на тему '{request.query}':

ИСХОДНЫЕ ДАННЫЕ:
{articles_text}

ТРЕБОВАНИЯ К СВОДКЕ:
- Размер: {length}
- Структурированный формат
- Выделение ключевых фактов
- Хронологический порядок событий
- Важные цифры и статистика

СТРУКТУРА СВОДКИ:
1. **EXECUTIVE SUMMARY**
   - Основные выводы (2-3 пункта)
   - Ключевые цифры

2. **ОСНОВНЫЕ СОБЫТИЯ**
   - Важнейшие новости
   - Временная последовательность

3. **АНАЛИТИКА**
   - Тренды и закономерности
   - Мнения экспертов

4. **ЗАКЛЮЧЕНИЕ**
   - Общие выводы
   - Значимость для отрасли

Используй ясный деловой стиль с маркированными списками."""

        try:
            summary_result = self.gpt5_service.send_chat(
                prompt,
                max_output_tokens=max_tokens,
                verbosity="medium"
            )

            return {
                'summary': summary_result,
                'length': length,
                'word_count': len(summary_result.split()) if summary_result else 0,
                'articles_processed': len(articles),
                'coverage_stats': self._calculate_coverage_stats(articles)
            }

        except Exception as e:
            logger.error(f"❌ Summary error: {e}")
            return {'error': str(e), 'summary': 'Сводка недоступна'}

    async def _process_aggregation(self, request: AnalysisRequest, articles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Агрегация данных"""
        logger.info(f"📊 Processing aggregation for: {request.query}")

        metric = request.parameters.get('metric', 'источники')
        groupby = request.parameters.get('groupby', 'дата')

        # Базовая агрегация данных
        aggregated_data = self._perform_data_aggregation(articles, metric, groupby)

        # GPT-5 анализ агрегированных данных
        articles_text = self._format_articles_for_gpt(articles, include_metadata=True)

        prompt = f"""Проведи агрегацию и анализ данных по {len(articles)} статьям:

ДАННЫЕ:
{articles_text}

ЗАДАЧА АГРЕГАЦИИ:
- Метрика: {metric}
- Группировка: {groupby}

ТРЕБУЕМЫЙ АНАЛИЗ:
1. **КОЛИЧЕСТВЕННАЯ АГРЕГАЦИЯ**
   - Подсчет по категориям
   - Процентное распределение
   - Статистические показатели

2. **ВРЕМЕННОЙ АНАЛИЗ**
   - Динамика по времени
   - Пиковые периоды
   - Тренды роста/спада

3. **СРАВНИТЕЛЬНЫЙ АНАЛИЗ**
   - Топ источников/категорий
   - Сравнение показателей
   - Выявление аномалий

4. **ВИЗУАЛИЗАЦИЯ ДАННЫХ**
   - Таблицы с результатами
   - Графики (текстовые)
   - Диаграммы распределения

Представь результаты в структурированном виде с четкими таблицами и графиками."""

        try:
            analysis_result = self.gpt5_service.send_bulk(
                prompt,
                max_output_tokens=1200,
                verbosity="high"
            )

            return {
                'aggregation_analysis': analysis_result,
                'raw_aggregation': aggregated_data,
                'metric': metric,
                'groupby': groupby,
                'total_items': len(articles)
            }

        except Exception as e:
            logger.error(f"❌ Aggregation error: {e}")
            return {'error': str(e), 'aggregation': 'Агрегация недоступна'}

    async def _process_filtering(self, request: AnalysisRequest, articles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Умная фильтрация данных"""
        logger.info(f"🔍 Processing filtering for: {request.query}")

        criteria = request.parameters.get('criteria', 'источник')
        value = request.parameters.get('value', 'tech.com')

        # Применение фильтров
        filtered_articles = self._apply_smart_filters(articles, criteria, value)

        articles_text = self._format_articles_for_gpt(articles, include_metadata=True)
        filtered_text = self._format_articles_for_gpt(filtered_articles, include_metadata=True)

        prompt = f"""Выполни умную фильтрацию и анализ данных:

ИСХОДНЫЕ ДАННЫЕ ({len(articles)} статей):
{articles_text}

ОТФИЛЬТРОВАННЫЕ ДАННЫЕ ({len(filtered_articles)} статей):
{filtered_text}

КРИТЕРИИ ФИЛЬТРАЦИИ:
- Параметр: {criteria}
- Значение: {value}

АНАЛИЗ ФИЛЬТРАЦИИ:
1. **РЕЗУЛЬТАТЫ ФИЛЬТРАЦИИ**
   - Количество найденных статей
   - Процент от общего объема
   - Релевантность результатов

2. **КАЧЕСТВЕННЫЙ АНАЛИЗ**
   - Соответствие критериям
   - Точность фильтрации
   - Пропущенные релевантные материалы

3. **СОДЕРЖАТЕЛЬНЫЙ АНАЛИЗ**
   - Основные темы в отфильтрованных данных
   - Уникальные инсайты
   - Ключевые выводы

4. **РЕКОМЕНДАЦИИ ПО ФИЛЬТРАЦИИ**
   - Дополнительные полезные фильтры
   - Улучшения критериев поиска
   - Альтернативные подходы

Предоставь детальный анализ с примерами и рекомендациями."""

        try:
            analysis_result = self.gpt5_service.send_chat(
                prompt,
                max_output_tokens=1200,
                verbosity="medium"
            )

            return {
                'filtering_analysis': analysis_result,
                'filtered_articles': filtered_articles,
                'filter_stats': {
                    'criteria': criteria,
                    'value': value,
                    'original_count': len(articles),
                    'filtered_count': len(filtered_articles),
                    'filter_ratio': len(filtered_articles) / len(articles) if articles else 0
                }
            }

        except Exception as e:
            logger.error(f"❌ Filtering error: {e}")
            return {'error': str(e), 'filtering': 'Фильтрация недоступна'}

    async def _process_insights(self, request: AnalysisRequest, articles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Генерация бизнес-инсайтов"""
        logger.info(f"💡 Processing insights for: {request.query}")

        articles_text = self._format_articles_for_gpt(articles, include_metadata=True)

        prompt = f"""Сгенерируй глубокие бизнес-инсайты на основе {len(articles)} статей по теме '{request.query}':

ИСТОЧНИКИ ДАННЫХ:
{articles_text}

ТРЕБУЕМЫЕ ИНСАЙТЫ:
1. **РЫНОЧНАЯ АНАЛИТИКА**
   - Скрытые тренды и паттерны
   - Изменения в конкурентной среде
   - Новые возможности и угрозы
   - Движущие силы рынка

2. **ПРОГНОСТИЧЕСКАЯ АНАЛИТИКА**
   - Краткосрочные прогнозы (1-3 месяца)
   - Долгосрочные перспективы (6-12 месяцев)
   - Факторы риска и катализаторы
   - Сценарии развития событий

3. **СТРАТЕГИЧЕСКИЕ РЕКОМЕНДАЦИИ**
   - Практические бизнес-инсайты
   - Инвестиционные возможности
   - Рекомендации по позиционированию
   - Операционные выводы

4. **ИНДИКАТОРЫ ЭФФЕКТИВНОСТИ**
   - Ключевые метрики для отслеживания
   - Benchmarks и сравнения
   - Сигналы раннего предупреждения

Представь как executive briefing с четкими разделами и практическими выводами."""

        try:
            insights_result = self.gpt5_service.send_insights(
                prompt,
                max_output_tokens=1500,
                verbosity="high",
                reasoning_effort="high"
            )

            # Дополнительные метрики для инсайтов
            business_metrics = self._calculate_business_metrics(articles)

            return {
                'insights': insights_result,
                'business_metrics': business_metrics,
                'confidence_score': self._calculate_confidence_score(articles),
                'market_indicators': self._extract_market_indicators(articles)
            }

        except Exception as e:
            logger.error(f"❌ Insights error: {e}")
            return {'error': str(e), 'insights': 'Инсайты недоступны'}

    async def _process_sentiment(self, request: AnalysisRequest, articles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Анализ тональности"""
        logger.info(f"😊 Processing sentiment for: {request.query}")

        articles_text = self._format_articles_for_gpt(articles, include_metadata=True)

        prompt = f"""Проведи комплексный анализ тональности {len(articles)} статей по теме '{request.query}':

ДАННЫЕ ДЛЯ АНАЛИЗА:
{articles_text}

ТРЕБУЕМЫЙ АНАЛИЗ ТОНАЛЬНОСТИ:
1. **ОБЩАЯ ОЦЕНКА ТОНАЛЬНОСТИ**
   - Итоговый sentiment score (-100 до +100)
   - Доверительный интервал оценки
   - Степень уверенности в анализе

2. **РАСПРЕДЕЛЕНИЕ ТОНАЛЬНОСТИ**
   - Позитивные: X% (с обоснованием)
   - Нейтральные: X% (с обоснованием)
   - Негативные: X% (с обоснованием)
   - Смешанные: X% (с обоснованием)

3. **ФАКТОРЫ ТОНАЛЬНОСТИ**
   - Ключевые позитивные факторы
   - Основные негативные аспекты
   - Нейтральные/смешанные сигналы
   - Эмоциональные индикаторы

4. **ДИНАМИКА НАСТРОЕНИЙ**
   - Изменения во времени
   - Триггеры изменений
   - Тренды развития настроений

5. **ВЛИЯНИЕ НА РЫНОК**
   - Воздействие на восприятие
   - Влияние на решения инвесторов
   - Прогноз изменений тональности

Используй эмодзи и четкое форматирование для наглядности."""

        try:
            sentiment_result = self.gpt5_service.send_sentiment(
                prompt,
                max_output_tokens=1200,
                verbosity="high"
            )

            # Базовый анализ тональности
            sentiment_metrics = self._calculate_sentiment_metrics(articles)

            return {
                'sentiment_analysis': sentiment_result,
                'sentiment_metrics': sentiment_metrics,
                'emotional_indicators': self._extract_emotional_indicators(articles),
                'confidence_level': self._calculate_sentiment_confidence(articles)
            }

        except Exception as e:
            logger.error(f"❌ Sentiment error: {e}")
            return {'error': str(e), 'sentiment': 'Анализ тональности недоступен'}

    async def _process_topics(self, request: AnalysisRequest, articles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Моделирование тем и анализ трендов"""
        logger.info(f"🏷️ Processing topics for: {request.query}")

        scope = request.parameters.get('scope', request.query)
        articles_text = self._format_articles_for_gpt(articles, include_metadata=True)

        prompt = f"""Проведи моделирование тем и анализ трендов для {len(articles)} статей в области '{scope}':

ДАННЫЕ ДЛЯ АНАЛИЗА:
{articles_text}

ЗАДАЧИ АНАЛИЗА:
1. **ВЫЯВЛЕНИЕ ОСНОВНЫХ ТЕМ**
   - Топ-7 ключевых тем с описаниями
   - Весовые коэффициенты тем (частота/важность)
   - Репрезентативные ключевые слова для каждой темы
   - Примеры статей для каждой темы

2. **АНАЛИЗ ТРЕНДОВ**
   - Растущие темы (emerging topics)
   - Угасающие темы (declining topics)
   - Стабильные/устойчивые темы
   - Временная эволюция тематик

3. **ВЗАИМОСВЯЗИ ТЕМ**
   - Кластеризация похожих тем
   - Связи между различными темами
   - Иерархия тем и подтем
   - Корреляции и зависимости

4. **ПРОГНОЗНАЯ АНАЛИТИКА**
   - Наиболее перспективные темы для отслеживания
   - Влияние на рынок и индустрию
   - Прогноз появления новых тем
   - Рекомендации по фокусировке внимания

Используй визуальное форматирование с эмодзи и четкую категоризацию."""

        try:
            topics_result = self.gpt5_service.send_analysis(
                prompt,
                max_output_tokens=1500,
                verbosity="high",
                reasoning_effort="medium"
            )

            # Дополнительный анализ тем
            topic_metrics = self._calculate_topic_metrics(articles)

            return {
                'topics_analysis': topics_result,
                'topic_metrics': topic_metrics,
                'trend_indicators': self._calculate_trend_indicators(articles),
                'topic_evolution': self._analyze_topic_evolution(articles)
            }

        except Exception as e:
            logger.error(f"❌ Topics error: {e}")
            return {'error': str(e), 'topics': 'Анализ тем недоступен'}

    # Вспомогательные методы

    def _format_articles_for_gpt(self, articles: List[Dict[str, Any]], include_metadata: bool = False) -> str:
        """Форматирование статей для GPT-5"""
        if not articles:
            return "Нет данных для анализа"

        formatted = []
        for i, article in enumerate(articles):
            title = article.get('title', 'Без названия')[:150]
            content = article.get('content', '')[:400]

            text = f"Статья {i+1}:\nНазвание: {title}\nСодержание: {content}\n"

            if include_metadata:
                source = article.get('source', 'Неизвестно')
                date = article.get('published_at', 'Неизвестно')
                score = article.get('score', 0)
                text += f"Источник: {source}\nДата: {date}\nРелевантность: {score:.2f}\n"

            text += "---\n"
            formatted.append(text)

        return '\n'.join(formatted)

    def _calculate_analysis_metrics(self, articles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Расчет метрик для анализа"""
        if not articles:
            return {}

        return {
            'avg_relevance': sum(a.get('score', 0) for a in articles) / len(articles),
            'source_diversity': len(set(a.get('source_domain', '') for a in articles)),
            'time_span_days': self._calculate_time_span(articles),
            'content_density': sum(len(a.get('content', '')) for a in articles) / len(articles)
        }

    def _get_date_range(self, articles: List[Dict[str, Any]]) -> Dict[str, str]:
        """Получение временного диапазона статей"""
        if not articles:
            return {}

        dates = [a.get('published_at', '') for a in articles if a.get('published_at')]
        if not dates:
            return {}

        return {
            'earliest': min(dates),
            'latest': max(dates)
        }

    def _get_top_sources(self, articles: List[Dict[str, Any]], limit: int = 5) -> List[Dict[str, Any]]:
        """Получение топ источников"""
        source_counts = {}
        for article in articles:
            source = article.get('source_domain', 'Unknown')
            source_counts[source] = source_counts.get(source, 0) + 1

        return [
            {'source': source, 'count': count}
            for source, count in sorted(source_counts.items(), key=lambda x: x[1], reverse=True)[:limit]
        ]

    def _get_average_score(self, articles: List[Dict[str, Any]]) -> float:
        """Получение средней оценки релевантности"""
        if not articles:
            return 0.0

        scores = [a.get('score', 0) for a in articles]
        return sum(scores) / len(scores) if scores else 0.0

    def _calculate_coverage_stats(self, articles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Расчет статистики покрытия"""
        return {
            'sources_count': len(set(a.get('source_domain', '') for a in articles)),
            'avg_content_length': sum(len(a.get('content', '')) for a in articles) / len(articles) if articles else 0,
            'date_coverage': self._get_date_range(articles)
        }

    def _perform_data_aggregation(self, articles: List[Dict[str, Any]], metric: str, groupby: str) -> Dict[str, Any]:
        """Выполнение агрегации данных"""
        if not articles:
            return {}

        aggregation = {}

        if groupby == 'источник':
            for article in articles:
                source = article.get('source_domain', 'Unknown')
                if source not in aggregation:
                    aggregation[source] = {'count': 0, 'scores': []}
                aggregation[source]['count'] += 1
                aggregation[source]['scores'].append(article.get('score', 0))

        elif groupby == 'дата':
            for article in articles:
                date = article.get('published_at', '')[:10]  # YYYY-MM-DD
                if date not in aggregation:
                    aggregation[date] = {'count': 0, 'scores': []}
                aggregation[date]['count'] += 1
                aggregation[date]['scores'].append(article.get('score', 0))

        return aggregation

    def _apply_smart_filters(self, articles: List[Dict[str, Any]], criteria: str, value: str) -> List[Dict[str, Any]]:
        """Применение умных фильтров"""
        filtered = []

        for article in articles:
            match = False

            if criteria == 'источник':
                if value.lower() in article.get('source_domain', '').lower():
                    match = True
            elif criteria == 'дата':
                if value in article.get('published_at', ''):
                    match = True
            elif criteria == 'содержание':
                if value.lower() in article.get('content', '').lower():
                    match = True
            elif criteria == 'название':
                if value.lower() in article.get('title', '').lower():
                    match = True

            if match:
                filtered.append(article)

        return filtered

    def _calculate_business_metrics(self, articles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Расчет бизнес-метрик"""
        return {
            'market_coverage': len(set(a.get('source_domain', '') for a in articles)),
            'information_velocity': len(articles) / max(1, self._calculate_time_span(articles)),
            'content_quality_score': self._get_average_score(articles),
            'trend_strength': self._calculate_trend_strength(articles)
        }

    def _calculate_confidence_score(self, articles: List[Dict[str, Any]]) -> float:
        """Расчет уровня уверенности в анализе"""
        if not articles:
            return 0.0

        # Факторы уверенности: количество статей, разнообразие источников, качество контента
        article_factor = min(1.0, len(articles) / 20)  # до 20 статей = максимум
        source_factor = min(1.0, len(set(a.get('source_domain', '') for a in articles)) / 5)  # до 5 источников
        quality_factor = self._get_average_score(articles)

        return (article_factor + source_factor + quality_factor) / 3

    def _extract_market_indicators(self, articles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Извлечение рыночных индикаторов"""
        return {
            'publication_frequency': len(articles),
            'source_diversity': len(set(a.get('source_domain', '') for a in articles)),
            'average_relevance': self._get_average_score(articles),
            'time_distribution': self._analyze_time_distribution(articles)
        }

    def _calculate_sentiment_metrics(self, articles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Базовый расчет метрик тональности"""
        # Примерный анализ на основе ключевых слов
        positive_words = ['рост', 'успех', 'прогресс', 'развитие', 'улучшение', 'инновации']
        negative_words = ['спад', 'проблема', 'кризис', 'снижение', 'риск', 'угроза']

        sentiment_scores = []
        for article in articles:
            content = (article.get('title', '') + ' ' + article.get('content', '')).lower()
            positive_count = sum(1 for word in positive_words if word in content)
            negative_count = sum(1 for word in negative_words if word in content)

            if positive_count + negative_count > 0:
                score = (positive_count - negative_count) / (positive_count + negative_count)
            else:
                score = 0
            sentiment_scores.append(score)

        avg_sentiment = sum(sentiment_scores) / len(sentiment_scores) if sentiment_scores else 0

        return {
            'average_sentiment': avg_sentiment,
            'positive_ratio': sum(1 for s in sentiment_scores if s > 0.1) / len(sentiment_scores) if sentiment_scores else 0,
            'negative_ratio': sum(1 for s in sentiment_scores if s < -0.1) / len(sentiment_scores) if sentiment_scores else 0,
            'neutral_ratio': sum(1 for s in sentiment_scores if -0.1 <= s <= 0.1) / len(sentiment_scores) if sentiment_scores else 0
        }

    def _extract_emotional_indicators(self, articles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Извлечение эмоциональных индикаторов"""
        return {
            'urgency_level': self._calculate_urgency_level(articles),
            'optimism_score': self._calculate_optimism_score(articles),
            'concern_level': self._calculate_concern_level(articles)
        }

    def _calculate_sentiment_confidence(self, articles: List[Dict[str, Any]]) -> float:
        """Расчет уверенности в анализе тональности"""
        return min(1.0, len(articles) / 10)  # Уверенность растет с количеством статей

    def _calculate_topic_metrics(self, articles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Расчет метрик по темам"""
        return {
            'topic_diversity': self._calculate_topic_diversity(articles),
            'keyword_density': self._calculate_keyword_density(articles),
            'thematic_coherence': self._calculate_thematic_coherence(articles)
        }

    def _calculate_trend_indicators(self, articles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Расчет индикаторов трендов"""
        return {
            'publication_trend': self._analyze_publication_trend(articles),
            'interest_momentum': self._calculate_interest_momentum(articles),
            'topic_evolution_rate': self._calculate_topic_evolution_rate(articles)
        }

    def _analyze_topic_evolution(self, articles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Анализ эволюции тем"""
        return {
            'emerging_themes': self._identify_emerging_themes(articles),
            'declining_themes': self._identify_declining_themes(articles),
            'stable_themes': self._identify_stable_themes(articles)
        }

    # Дополнительные вспомогательные методы для расчетов

    def _calculate_time_span(self, articles: List[Dict[str, Any]]) -> int:
        """Расчет временного промежутка в днях"""
        dates = [a.get('published_at', '') for a in articles if a.get('published_at')]
        if not dates:
            return 1

        try:
            date_objects = [datetime.fromisoformat(d.replace('Z', '+00:00')) for d in dates]
            span = (max(date_objects) - min(date_objects)).days
            return max(1, span)
        except:
            return 1

    def _calculate_trend_strength(self, articles: List[Dict[str, Any]]) -> float:
        """Расчет силы тренда"""
        return min(1.0, len(articles) / 50)  # Условная формула

    def _analyze_time_distribution(self, articles: List[Dict[str, Any]]) -> Dict[str, int]:
        """Анализ распределения по времени"""
        distribution = {}
        for article in articles:
            date = article.get('published_at', '')[:10]
            distribution[date] = distribution.get(date, 0) + 1
        return distribution

    def _calculate_urgency_level(self, articles: List[Dict[str, Any]]) -> float:
        """Расчет уровня срочности"""
        urgent_words = ['срочно', 'немедленно', 'критично', 'экстренно']
        total_urgency = 0
        for article in articles:
            content = (article.get('title', '') + ' ' + article.get('content', '')).lower()
            total_urgency += sum(1 for word in urgent_words if word in content)
        return total_urgency / len(articles) if articles else 0

    def _calculate_optimism_score(self, articles: List[Dict[str, Any]]) -> float:
        """Расчет уровня оптимизма"""
        optimistic_words = ['надежда', 'перспектива', 'возможность', 'потенциал']
        total_optimism = 0
        for article in articles:
            content = (article.get('title', '') + ' ' + article.get('content', '')).lower()
            total_optimism += sum(1 for word in optimistic_words if word in content)
        return total_optimism / len(articles) if articles else 0

    def _calculate_concern_level(self, articles: List[Dict[str, Any]]) -> float:
        """Расчет уровня обеспокоенности"""
        concern_words = ['беспокойство', 'тревога', 'озабоченность', 'опасение']
        total_concern = 0
        for article in articles:
            content = (article.get('title', '') + ' ' + article.get('content', '')).lower()
            total_concern += sum(1 for word in concern_words if word in content)
        return total_concern / len(articles) if articles else 0

    def _calculate_topic_diversity(self, articles: List[Dict[str, Any]]) -> float:
        """Расчет разнообразия тем"""
        all_words = []
        for article in articles:
            content = (article.get('title', '') + ' ' + article.get('content', '')).lower()
            words = content.split()
            all_words.extend(words)

        unique_words = len(set(all_words))
        total_words = len(all_words)
        return unique_words / total_words if total_words > 0 else 0

    def _calculate_keyword_density(self, articles: List[Dict[str, Any]]) -> float:
        """Расчет плотности ключевых слов"""
        # Упрощенный расчет
        return len(articles) * 0.1  # Условная формула

    def _calculate_thematic_coherence(self, articles: List[Dict[str, Any]]) -> float:
        """Расчет тематической согласованности"""
        return min(1.0, len(articles) / 30)  # Условная формула

    def _analyze_publication_trend(self, articles: List[Dict[str, Any]]) -> str:
        """Анализ тренда публикаций"""
        if len(articles) > 10:
            return "растущий"
        elif len(articles) > 5:
            return "стабильный"
        else:
            return "снижающийся"

    def _calculate_interest_momentum(self, articles: List[Dict[str, Any]]) -> float:
        """Расчет моментума интереса"""
        return len(articles) / 10  # Условная формула

    def _calculate_topic_evolution_rate(self, articles: List[Dict[str, Any]]) -> float:
        """Расчет скорости эволюции тем"""
        return len(set(a.get('source_domain', '') for a in articles)) / 5  # Условная формула

    def _identify_emerging_themes(self, articles: List[Dict[str, Any]]) -> List[str]:
        """Выявление развивающихся тем"""
        return ["новые технологии", "цифровая трансформация"]  # Заглушка

    def _identify_declining_themes(self, articles: List[Dict[str, Any]]) -> List[str]:
        """Выявление угасающих тем"""
        return ["устаревшие подходы"]  # Заглушка

    def _identify_stable_themes(self, articles: List[Dict[str, Any]]) -> List[str]:
        """Выявление стабильных тем"""
        return ["основные тренды", "рыночные изменения"]  # Заглушка


# Главные функции для использования

async def analyze_data(query: str, timeframe: str = "7d", **kwargs) -> AnalysisResult:
    """Глубокий анализ данных"""
    processor = DataAnalysisProcessor()
    request = AnalysisRequest(
        command=AnalysisType.DEEP_ANALYSIS,
        query=query,
        timeframe=timeframe,
        parameters=kwargs
    )
    return await processor.process_analysis_request(request)

async def summarize_data(topic: str, length: str = "medium", timeframe: str = "7d") -> AnalysisResult:
    """AI-powered суммаризация"""
    processor = DataAnalysisProcessor()
    request = AnalysisRequest(
        command=AnalysisType.SUMMARY,
        query=topic,
        timeframe=timeframe,
        parameters={'length': length}
    )
    return await processor.process_analysis_request(request)

async def aggregate_data(metric: str, groupby: str, query: str = "", timeframe: str = "7d") -> AnalysisResult:
    """Агрегация данных"""
    processor = DataAnalysisProcessor()
    request = AnalysisRequest(
        command=AnalysisType.AGGREGATION,
        query=query or "общий анализ",
        timeframe=timeframe,
        parameters={'metric': metric, 'groupby': groupby}
    )
    return await processor.process_analysis_request(request)

async def filter_data(criteria: str, value: str, query: str = "", timeframe: str = "7d") -> AnalysisResult:
    """Умная фильтрация"""
    processor = DataAnalysisProcessor()
    request = AnalysisRequest(
        command=AnalysisType.FILTERING,
        query=query or "фильтрация данных",
        timeframe=timeframe,
        parameters={'criteria': criteria, 'value': value}
    )
    return await processor.process_analysis_request(request)

async def generate_insights(topic: str, timeframe: str = "7d") -> AnalysisResult:
    """Генерация бизнес-инсайтов"""
    processor = DataAnalysisProcessor()
    request = AnalysisRequest(
        command=AnalysisType.INSIGHTS,
        query=topic,
        timeframe=timeframe
    )
    return await processor.process_analysis_request(request)

async def analyze_sentiment(query: str, timeframe: str = "7d") -> AnalysisResult:
    """Анализ тональности"""
    processor = DataAnalysisProcessor()
    request = AnalysisRequest(
        command=AnalysisType.SENTIMENT,
        query=query,
        timeframe=timeframe
    )
    return await processor.process_analysis_request(request)

async def analyze_topics(scope: str, timeframe: str = "7d") -> AnalysisResult:
    """Моделирование тем и анализ трендов"""
    processor = DataAnalysisProcessor()
    request = AnalysisRequest(
        command=AnalysisType.TOPICS,
        query=scope,
        timeframe=timeframe,
        parameters={'scope': scope}
    )
    return await processor.process_analysis_request(request)


# CLI интерфейс для тестирования
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="GPT-5 Data Analysis Processor")
    parser.add_argument("command", choices=["analyze", "summarize", "aggregate", "filter", "insights", "sentiment", "topics"])
    parser.add_argument("query", help="Search query or topic")
    parser.add_argument("--timeframe", default="7d", help="Time frame (e.g., 7d, 2w, 1m)")
    parser.add_argument("--param1", help="First parameter (e.g., length for summarize, metric for aggregate)")
    parser.add_argument("--param2", help="Second parameter (e.g., groupby for aggregate)")

    args = parser.parse_args()

    async def main():
        try:
            if args.command == "analyze":
                result = await analyze_data(args.query, args.timeframe)
            elif args.command == "summarize":
                result = await summarize_data(args.query, args.param1 or "medium", args.timeframe)
            elif args.command == "aggregate":
                result = await aggregate_data(args.param1 or "источники", args.param2 or "дата", args.query, args.timeframe)
            elif args.command == "filter":
                result = await filter_data(args.param1 or "источник", args.param2 or "tech.com", args.query, args.timeframe)
            elif args.command == "insights":
                result = await generate_insights(args.query, args.timeframe)
            elif args.command == "sentiment":
                result = await analyze_sentiment(args.query, args.timeframe)
            elif args.command == "topics":
                result = await analyze_topics(args.query, args.timeframe)

            print(f"\n🤖 Результат анализа '{args.command}':")
            print(f"⏱️ Время обработки: {result.processing_time:.2f}с")
            print(f"✅ Успешно: {result.success}")

            if result.success:
                print(f"📊 Метаданные: {json.dumps(result.metadata, ensure_ascii=False, indent=2)}")
                print(f"📄 Основные данные:")
                for key, value in result.data.items():
                    if isinstance(value, str) and len(value) > 200:
                        print(f"  {key}: {value[:200]}...")
                    else:
                        print(f"  {key}: {value}")
            else:
                print(f"❌ Ошибка: {result.error}")

        except Exception as e:
            print(f"❌ Критическая ошибка: {e}")
            import traceback
            print(traceback.format_exc())

    asyncio.run(main())
