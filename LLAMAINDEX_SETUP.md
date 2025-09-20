# 🚀 LlamaIndex RSS Integration Setup Guide

Полное руководство по установке и настройке LlamaIndex интеграции для RSS News System.

## 📋 Что реализовано

### ✅ Архитектура (согласно вашим требованиям):

1. **🔄 Интеграционная матрица**:
   - **Postgres (Railway)**: сырьё/мета/чанки + FTS по ключевым словам
   - **Pinecone**: вектора (эмбеддинги Gemini), hot/archive namespace
   - **Gemini Embeddings**: создание векторов (индексация и запросы)
   - **OpenAI (GPT-5)** и/или **Gemini LLM**: синтез ответов поверх фактов
   - **LlamaIndex**: управление всей цепочкой

2. **⚡ Жёсткие правила маршрутизации**:
   - Эмбеддинги: всегда **Gemini** (консистентность Pinecone)
   - Ретривер: **Hybrid (FTS Postgres + Vector Pinecone)**
   - LLM: **OpenAI (GPT-5)** по умолчанию, автопереключение на **Gemini**
   - Индексы: `hot` (7–30 дней) → `archive` (старше)
   - Язык: en/ru раздельные маршруты

3. **🗃️ Единый идентификатор**: `{article_id}#{chunk_index}`

4. **📊 Пресеты вывода**:
   - **digest**: списки с ссылками и датами
   - **qa**: краткие ответы + источники
   - **shorts**: сценарии видео
   - **ideas**: широкое исследование

5. **💰 Производительность и контроль затрат**:
   - Top-K умеренный (24 → 8-12 финал)
   - Кэш результатов (15 минут)
   - Cost-guard с лимитами

6. **🛡️ Фолбэки и Legacy Mode**:
   - Кнопка "Legacy Mode" для отката
   - Плавная миграция по компонентам

## 🛠️ Установка

### 1. Установка зависимостей

```bash
# Установить LlamaIndex и компоненты
pip install -r requirements_llamaindex.txt

# Или по отдельности:
pip install llama-index>=0.13.0
pip install llama-index-vector-stores-postgres llama-index-vector-stores-pinecone
pip install llama-index-llms-openai llama-index-llms-gemini
pip install llama-index-embeddings-gemini
pip install pgvector pinecone-client sentence-transformers
```

### 2. Настройка переменных окружения

Добавьте в `.env` файл:

```env
# Существующие переменные (уже должны быть)
PG_DSN=postgresql://postgres:password@host:port/database
OPENAI_API_KEY=sk-...

# Новые переменные для LlamaIndex
GEMINI_API_KEY=your-gemini-api-key
PINECONE_API_KEY=your-pinecone-api-key
PINECONE_INDEX=rssnews-embeddings
PINECONE_REGION=us-east-1-aws

# Опциональные настройки
LLAMAINDEX_CACHE_TTL=15  # минут
LLAMAINDEX_DAILY_BUDGET=100.00  # USD
```

### 3. Настройка базы данных

```bash
# Применить схему LlamaIndex
psql $PG_DSN -f llamaindex_schema.sql

# Или через CLI
python main.py ensure  # Проверит и создаст таблицы
```

### 4. Настройка Pinecone

```bash
# Создать индекс в Pinecone (если еще нет)
# Dimension: 768 (Gemini embeddings)
# Metric: cosine
# Namespaces: en_hot, en_archive, ru_hot, ru_archive
```

## 🚦 Первый запуск

### 1. Проверка установки

```bash
# Проверить доступность LlamaIndex команд
python main.py --help | grep llamaindex

# Проверить конфигурацию
python main.py llamaindex-monitor
```

### 2. Тестовая миграция

```bash
# Обработать 10 новых статей для тестирования
python main.py llamaindex-ingest --limit 10

# Проверить результат
python main.py llamaindex-monitor
```

### 3. Тестовый запрос

```bash
# Простой Q&A запрос
python main.py llamaindex-query "What are the latest tech news?" --preset qa

# Дайджест за неделю
python main.py llamaindex-query "Tech news this week" --preset digest --max-sources 12
```

## 📚 Использование

### Основные команды

```bash
# 1. Обработка статей (замена Stage 6-7)
python main.py llamaindex-ingest --limit 100

# 2. Умные запросы с разными пресетами
python main.py llamaindex-query "AI developments 2025" --preset qa
python main.py llamaindex-query "Weekly tech digest" --preset digest
python main.py llamaindex-query "Video idea about crypto" --preset shorts
python main.py llamaindex-query "Future of robotics" --preset ideas

# 3. Миграция существующих данных
python main.py llamaindex-migrate fresh --limit 1000      # Новые статьи
python main.py llamaindex-migrate backfill --limit 5000   # Последние 30 дней
python main.py llamaindex-migrate archive --limit 10000   # Старые статьи

# 4. Мониторинг и аналитика
python main.py llamaindex-monitor

# 5. Управление Legacy режимом
python main.py llamaindex-legacy status
python main.py llamaindex-legacy enable --components chunking
python main.py llamaindex-legacy disable
```

### Пресеты запросов

#### **digest** - Новостные дайджесты
```bash
python main.py llamaindex-query "AI news this week" --preset digest --max-sources 12
```
**Формат**: Список с 1-2 предложениями + ссылка + дата, ≥3 домена

#### **qa** - Вопросы и ответы
```bash
python main.py llamaindex-query "What improvements does GPT-5 introduce?" --preset qa
```
**Формат**: Краткий ответ + источники, self-check при <3 источников

#### **shorts** - Сценарии видео
```bash
python main.py llamaindex-query "Bitcoin price analysis" --preset shorts
```
**Формат**: Хук + ключевые моменты (30-60 сек) + заключение + ссылки

#### **ideas** - Широкое исследование
```bash
python main.py llamaindex-query "Future of renewable energy" --preset ideas
```
**Формат**: Тренды, связи между источниками, прогнозы, разные перспективы

## 📊 Мониторинг и аналитика

### Performance Dashboard

```bash
# Общая статистика
python main.py llamaindex-monitor

# Детальная аналитика (SQL)
psql $PG_DSN -c "SELECT * FROM llamaindex_daily_costs ORDER BY date DESC LIMIT 7;"
psql $PG_DSN -c "SELECT * FROM llamaindex_query_stats WHERE date >= CURRENT_DATE - 7;"
```

### Ключевые метрики

- **Время отклика**: среднее, P95 по операциям
- **Качество поиска**: релевантность, диверсификация доменов
- **Затраты**: OpenAI vs Gemini, эмбеддинги, лимиты
- **Кэш**: hit rate, размер, TTL
- **Ошибки**: rate, типы, компоненты

## 🔄 Стратегия поэтапного внедрения

### Phase 1: Параллельное тестирование (1-2 недели)
```bash
# Обработка в параллель с существующей системой
python main.py llamaindex-ingest --limit 100  # Новые статьи
python main.py chunk --limit 100               # Старая система

# Сравнение качества результатов
python main.py llamaindex-query "test query" --preset qa
python main.py rag "test query"
```

### Phase 2: Селективная замена (2-4 недели)
```bash
# Включить LlamaIndex для новых статей
python main.py llamaindex-legacy enable --components chunking

# Бэкфилл горячих данных
python main.py llamaindex-migrate backfill --limit 5000
```

### Phase 3: Полная интеграция (4-8 недель)
```bash
# Отключить Legacy режим
python main.py llamaindex-legacy disable

# Мигрировать все данные
python main.py llamaindex-migrate archive --limit 50000
```

## ⚠️ Troubleshooting

### Проблема: "LlamaIndex CLI not available"
```bash
pip install -r requirements_llamaindex.txt
# Проверить импорты
python -c "import llama_index; print('OK')"
```

### Проблема: "Pinecone connection failed"
```bash
# Проверить переменные
echo $PINECONE_API_KEY
echo $PINECONE_INDEX

# Тест подключения
python -c "
import pinecone
pinecone.init(api_key='$PINECONE_API_KEY', environment='$PINECONE_REGION')
print(pinecone.list_indexes())
"
```

### Проблема: "No embeddings generated"
```bash
# Проверить Gemini API
python -c "
from llama_index.embeddings.gemini import GeminiEmbedding
embed = GeminiEmbedding(api_key='$GEMINI_API_KEY')
result = embed.get_text_embedding('test')
print(f'Embedding length: {len(result)}')
"
```

### Проблема: "Budget exceeded"
```bash
# Проверить расходы
python main.py llamaindex-monitor

# Увеличить лимиты (SQL)
psql $PG_DSN -c "
UPDATE llamaindex_costs
SET daily_limit = 200.00
WHERE date = CURRENT_DATE;
"
```

## 🔧 Advanced Configuration

### Тонкая настройка маршрутизации

```sql
-- Изменить параметры через конфигурацию
UPDATE llamaindex_config
SET value = '0.7'
WHERE key = 'routing.alpha_default';

-- Включить/отключить компоненты
UPDATE llamaindex_config
SET value = 'false'
WHERE key = 'features.domain_diversification';
```

### Кастомные промпты

Отредактируйте шаблоны в `llamaindex_production.py`:
- `DIGEST_TEMPLATE`
- `QA_TEMPLATE`
- `SHORTS_TEMPLATE`
- `IDEAS_TEMPLATE`

### Производительность

```bash
# Настройка batch размеров
export LLAMAINDEX_BATCH_SIZE=20

# Кэш настройки
export LLAMAINDEX_CACHE_TTL=30  # минут

# Параллелизм
export LLAMAINDEX_MAX_WORKERS=5
```

## 📈 Ожидаемые улучшения

### Качество обработки
- **+30-50%** качество чанкинга (границы по предложениям)
- **+20-40%** точность поиска (hybrid из коробки)
- **Автоматическое извлечение** ключевых слов, вопросов, заголовков

### Производительность
- **-60%** кода для поддержки (готовые компоненты)
- **Кэширование** популярных запросов
- **Умная маршрутизация** по языкам и временным окнам

### Новые возможности
- **4 пресета** вывода для разных сценариев
- **Диверсификация доменов** в результатах
- **Boost свежести** для недавних новостей
- **Семантический rerank** результатов
- **Мониторинг затрат** в реальном времени

## 🚨 Важные ограничения

1. **Gemini API лимиты**: следите за квотами эмбеддингов
2. **Pinecone costs**: векторное хранилище платное
3. **Memory usage**: LlamaIndex может быть ресурсоемким
4. **Migration time**: полная миграция займет время

## 📞 Поддержка

При проблемах:
1. Проверьте `python main.py llamaindex-monitor`
2. Просмотрите логи в `logs/rssnews.log`
3. Включите Legacy режим при критических ошибках
4. Изучите performance таблицы в БД

---

**🎯 Результат**: Продвинутая RSS система с умным поиском, автоматической аналитикой и готовыми пресетами для разных сценариев использования!
