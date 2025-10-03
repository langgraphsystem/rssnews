# Railway Deployment Guide - OpenAI Embedding Migration Service

## 📋 Обзор

Как запустить `openai_embedding_migration_service.py` на Railway как отдельный сервис для непрерывной обработки чанков без эмбеддингов.

---

## 🚀 Два Варианта Запуска на Railway

### ВАРИАНТ 1: Continuous Service (Рекомендуется)

Фоновый сервис, который проверяет новые чанки каждые 60 секунд и обрабатывает их автоматически.

### ВАРИАНТ 2: Scheduled Task (Cron)

Запуск миграции по расписанию (например, каждый час).

---

## 🔧 ВАРИАНТ 1: Continuous Service

### Шаг 1: Создать Procfile

```bash
# В корне проекта создать файл Procfile
echo "embedding-worker: python services/openai_embedding_migration_service.py continuous --interval 60" > Procfile
```

**Или если есть другие процессы:**

```
web: python bot_service/advanced_bot.py
embedding-worker: python services/openai_embedding_migration_service.py continuous --interval 60
```

### Шаг 2: Railway Environment Variables

```bash
railway vars set OPENAI_API_KEY="sk-proj-your-key-here"
railway vars set OPENAI_EMBEDDING_MODEL="text-embedding-3-large"
railway vars set OPENAI_EMBEDDING_SERVICE_ENABLED="true"
railway vars set OPENAI_EMBEDDING_BATCH_SIZE="100"
railway vars set ENABLE_LOCAL_EMBEDDINGS="false"
```

### Шаг 3: Deploy

```bash
railway up
```

Railway автоматически обнаружит Procfile и запустит оба процесса:
- `web` - основной бот
- `embedding-worker` - миграция эмбеддингов

### Шаг 4: Мониторинг

```bash
# Логи embedding worker
railway logs --service embedding-worker

# Или все логи
railway logs
```

**Ожидаемый вывод:**
```
Starting continuous migration service with 60s interval
Found 5611 chunks without embeddings, processing...
Processed 100 chunks
Migration progress: 100/5611 successful (0 errors)
...
```

---

## 🔧 ВАРИАНТ 2: Scheduled Task (Cron)

Если не хотите непрерывный процесс, используйте cron для периодической миграции.

### Шаг 1: Создать скрипт

**Файл:** `scripts/run_embedding_migration.sh`

```bash
#!/bin/bash
cd /app
python services/openai_embedding_migration_service.py migrate --limit 1000
```

Сделать исполняемым:
```bash
chmod +x scripts/run_embedding_migration.sh
```

### Шаг 2: Настроить Railway Cron

В Railway dashboard:

1. Перейти в Settings → Cron Jobs
2. Добавить задачу:
   - **Schedule:** `0 * * * *` (каждый час)
   - **Command:** `./scripts/run_embedding_migration.sh`

### Шаг 3: Environment Variables

```bash
railway vars set OPENAI_API_KEY="sk-proj-your-key-here"
railway vars set OPENAI_EMBEDDING_MODEL="text-embedding-3-large"
railway vars set ENABLE_LOCAL_EMBEDDINGS="false"
```

---

## 📊 Мониторинг и Управление

### Проверить статус

```bash
railway run python check_backlog.py
```

**Вывод:**
```
📊 Embedding Statistics:
   Total chunks: 209,338
   With embeddings: 203,727
   Without embeddings: 5,611
   Completion: 97.3%
```

### Остановить continuous service

```bash
railway ps
# Найти процесс embedding-worker
railway down embedding-worker
```

### Перезапустить

```bash
railway restart embedding-worker
```

### Логи в реальном времени

```bash
railway logs --follow
```

---

## 🛠️ Альтернатива: Один процесс с обеими функциями

Если не хотите два процесса, можно объединить:

**Файл:** `start_all_services.py`

```python
#!/usr/bin/env python
"""Start all services in one process"""

import asyncio
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)

async def run_bot():
    """Run Telegram bot"""
    from bot_service.advanced_bot import main as bot_main
    await bot_main()

async def run_embedding_service():
    """Run embedding migration service"""
    from services.openai_embedding_migration_service import OpenAIEmbeddingMigrationService
    service = OpenAIEmbeddingMigrationService()
    await service.process_continuous(interval_seconds=60)

async def main():
    """Run both services concurrently"""
    await asyncio.gather(
        run_bot(),
        run_embedding_service()
    )

if __name__ == "__main__":
    asyncio.run(main())
```

**Procfile:**
```
web: python start_all_services.py
```

---

## 🔍 Тестирование Локально

Перед деплоем на Railway, протестируйте локально:

### 1. Проверить конфигурацию

```bash
python -c "
from dotenv import load_dotenv
import os
load_dotenv()

print('OPENAI_API_KEY:', 'SET' if os.getenv('OPENAI_API_KEY') else 'NOT SET')
print('OPENAI_EMBEDDING_MODEL:', os.getenv('OPENAI_EMBEDDING_MODEL', 'not set'))
print('ENABLE_LOCAL_EMBEDDINGS:', os.getenv('ENABLE_LOCAL_EMBEDDINGS', 'not set'))
"
```

### 2. Тест API ключа

```bash
python -c "
import asyncio
from dotenv import load_dotenv
load_dotenv()

from openai_embedding_generator import OpenAIEmbeddingGenerator

async def test():
    gen = OpenAIEmbeddingGenerator()
    result = await gen.test_connection()
    print('✅ API key valid' if result else '❌ API key invalid')

asyncio.run(test())
"
```

### 3. Тест миграции (10 чанков)

```bash
python -c "
import asyncio
from dotenv import load_dotenv
load_dotenv()

from services.openai_embedding_migration_service import OpenAIEmbeddingMigrationService

async def test():
    service = OpenAIEmbeddingMigrationService()
    result = await service.migrate_backlog(limit=10)
    print(f'Processed: {result[\"processed\"]}, Successful: {result[\"successful\"]}, Errors: {result[\"errors\"]}')

asyncio.run(test())
"
```

### 4. Тест continuous mode (30 секунд)

```bash
timeout 30 python services/openai_embedding_migration_service.py continuous --interval 10
```

---

## 💰 Стоимость и Производительность

### Текущий backlog: 5,611 чанков

| Параметр | Значение |
|----------|----------|
| **Чанков** | 5,611 |
| **Avg tokens/chunk** | ~500 |
| **Total tokens** | ~2,805,500 |
| **Стоимость** | ~$0.36 |
| **Время (batch=100)** | ~3-5 минут |

### Continuous mode стоимость

| Период | Новых чанков | Стоимость |
|--------|--------------|-----------|
| День | ~50-80 | ~$0.01 |
| Неделя | ~350-560 | ~$0.07 |
| Месяц | ~1500-2000 | ~$0.30 |

### Производительность

**Batch size = 100:**
- Скорость: ~1000 чанков/мин
- Memory: ~100 MB
- CPU: Low (API bound)

---

## ⚠️ Важные Замечания

### 1. API Rate Limits

OpenAI embeddings API имеет лимиты:
- **TPM (tokens per minute):** Depends on your plan
- **RPM (requests per minute):** Depends on your plan

Если превысите, сервис получит `rate_limit_exceeded` и сделает retry.

**Настройка:**
```bash
# Уменьшить batch size если hitting rate limits
railway vars set OPENAI_EMBEDDING_BATCH_SIZE="50"

# Увеличить interval между проверками
# В Procfile: --interval 120 (2 минуты)
```

### 2. Railway Memory

Continuous service использует минимальную память (~100 MB).

**Railway Plan Requirements:**
- **Starter Plan:** ✅ Подходит
- **Developer Plan:** ✅ Подходит
- **Pro Plan:** ✅ Подходит

### 3. Логи

Railway хранит логи ограниченное время. Для долгосрочного мониторинга рассмотрите:
- Logflare integration
- External logging service
- Database logging (добавить в сервис)

### 4. Остановка и Откат

Если нужно остановить миграцию:

```bash
# Остановить процесс
railway down embedding-worker

# Или установить флаг
railway vars set OPENAI_EMBEDDING_SERVICE_ENABLED="false"
railway restart
```

---

## 🔄 Обновление Сервиса

### Обновить код

```bash
git add services/openai_embedding_migration_service.py openai_embedding_generator.py
git commit -m "Update embedding migration service"
git push

# Railway автоматически задеплоит
```

### Обновить конфигурацию

```bash
# Изменить batch size
railway vars set OPENAI_EMBEDDING_BATCH_SIZE="200"

# Изменить interval (требует изменения в Procfile)
railway restart
```

---

## 📝 Checklist для Деплоя

- [ ] ✅ Обновить `OPENAI_API_KEY` в Railway vars
- [ ] ✅ Установить `ENABLE_LOCAL_EMBEDDINGS=false`
- [ ] ✅ Установить `OPENAI_EMBEDDING_MODEL=text-embedding-3-large`
- [ ] ✅ Создать Procfile с `embedding-worker`
- [ ] ✅ Протестировать локально с `--limit 10`
- [ ] ✅ Deploy на Railway
- [ ] ✅ Проверить логи: `railway logs`
- [ ] ✅ Мониторить прогресс через `railway run python check_backlog.py`
- [ ] ✅ После завершения backlog - оставить continuous mode работающим

---

## 🆘 Troubleshooting

### Ошибка: "Incorrect API key"

**Решение:**
```bash
railway vars set OPENAI_API_KEY="sk-proj-new-key"
railway restart
```

### Ошибка: "Rate limit exceeded"

**Решение:**
```bash
# Уменьшить batch size
railway vars set OPENAI_EMBEDDING_BATCH_SIZE="50"

# Увеличить interval в Procfile
embedding-worker: python services/openai_embedding_migration_service.py continuous --interval 120
```

### Процесс крашится

**Проверить:**
```bash
railway logs --tail 100
```

**Частые причины:**
- Неправильный API key
- PG_DSN не установлен
- Нет доступа к БД

### Backlog не уменьшается

**Проверить:**
1. Процесс запущен? `railway ps`
2. Логи без ошибок? `railway logs`
3. API key валидный? Тест локально
4. Worker.py создаёт новые чанки БЕЗ эмбеддингов? Проверить `ENABLE_LOCAL_EMBEDDINGS=false`

---

## 📚 Дополнительные Команды

### Статистика на Railway

```bash
railway run python check_backlog.py
```

### Одноразовая миграция на Railway

```bash
railway run python -c "import asyncio; from dotenv import load_dotenv; load_dotenv(); from services.openai_embedding_migration_service import OpenAIEmbeddingMigrationService; asyncio.run(OpenAIEmbeddingMigrationService().migrate_backlog())"
```

### Проверить переменные окружения

```bash
railway vars
```

### Скейлинг (Pro Plan)

```bash
# Увеличить количество инстансов
railway scale embedding-worker=2
```

---

## ✅ Итоговая Рекомендация

**Для Production:**

1. **Используйте ВАРИАНТ 1 (Continuous Service)**
   - Автоматическая обработка новых чанков
   - Низкая latency (чанки обрабатываются в течение 60 секунд)
   - Простой мониторинг через логи

2. **Настройки:**
   ```bash
   OPENAI_EMBEDDING_BATCH_SIZE=100
   Interval=60 секунд
   ```

3. **Мониторинг:**
   - Проверяйте логи раз в день: `railway logs --tail 50`
   - Раз в неделю: `railway run python check_backlog.py`

4. **После завершения backlog:**
   - Оставьте сервис работающим для обработки новых чанков
   - Стоимость: ~$0.30/месяц

---

**Версия:** 1.0
**Дата:** 2025-10-03
**Автор:** Deployment Team
