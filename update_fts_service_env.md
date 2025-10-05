# Обновление переменных окружения для FTS сервиса

**Service ID:** `ffe65f79-4dc5-4757-b772-5a99c7ea624f`
**Проблема:** Сервис запускает `openai-migration` вместо FTS
**Причина:** Отсутствует переменная `SERVICE_MODE=fts-continuous`

---

## Текущее состояние

### Логи показывают:

```
Starting Container
launcher.py -> executing: python services/openai_embedding_migration_service.py continuous --interval 60 --batch-size 100
```

**Почему:** `launcher.py:27` использует дефолт `openai-migration`:

```python
def build_command() -> str:
    mode = os.getenv("SERVICE_MODE", "openai-migration").strip().lower()
    #                                ^^^^^^^^^^^^^^^^^ DEFAULT
```

---

## Решение: Установить переменные окружения

### Необходимые переменные для FTS сервиса:

```bash
SERVICE_MODE=fts-continuous
FTS_CONTINUOUS_INTERVAL=60
FTS_BATCH=100000
```

### Опциональные переменные (уже должны быть):

```bash
PG_DSN=postgresql://...  # Database connection (обязательно)
```

---

## Как обновить через Railway CLI

### 1. Подключиться к сервису:

```bash
railway link --service ffe65f79-4dc5-4757-b772-5a99c7ea624f
```

### 2. Проверить текущие переменные:

```bash
railway variables
```

### 3. Установить переменные:

```bash
# Установить основную переменную
railway variables --set SERVICE_MODE=fts-continuous

# Установить интервал (опционально, если нужно изменить дефолт)
railway variables --set FTS_CONTINUOUS_INTERVAL=60

# Установить размер batch (опционально)
railway variables --set FTS_BATCH=100000
```

### 4. Перезапустить сервис:

```bash
railway restart
```

### 5. Проверить логи:

```bash
railway logs
```

Должно появиться:

```
Starting Container
launcher.py -> executing: python services/fts_service.py service --interval 60 --batch-size 100000
...
FTS service started with 60s interval
```

---

## Альтернативный способ: Через Railway Dashboard

### 1. Откройте Railway Dashboard
https://railway.app/

### 2. Перейдите в проект → Сервис `ffe65f79-4dc5-4757-b772-5a99c7ea624f`

### 3. Вкладка "Variables"

### 4. Добавьте переменные:

```
SERVICE_MODE = fts-continuous
FTS_CONTINUOUS_INTERVAL = 60
FTS_BATCH = 100000
```

### 5. Railway автоматически перезапустит сервис

---

## Проверка после обновления

### 1. Проверить логи:

```bash
railway logs --service ffe65f79-4dc5-4757-b772-5a99c7ea624f
```

Ожидаемый вывод:

```
Starting Container
launcher.py -> executing: python services/fts_service.py service --interval 60 --batch-size 100000
2025-10-05 XX:XX:XX - pg_client_new - INFO - DB pool initialized
2025-10-05 XX:XX:XX - __main__ - INFO - Starting FTS service with 60s interval
2025-10-05 XX:XX:XX - __main__ - INFO - FTS indexing service started
```

### 2. Проверить переменные:

```bash
railway run printenv | grep SERVICE_MODE
```

Ожидаемый вывод:

```
SERVICE_MODE=fts-continuous
```

### 3. Проверить работу FTS индексации:

```bash
railway run python -c "
from pg_client_new import PgClient
db = PgClient()

with db._cursor() as cur:
    # Check FTS vectors
    cur.execute('''
        SELECT
            COUNT(*) as total,
            COUNT(fts_vector) as with_fts,
            ROUND(100.0 * COUNT(fts_vector) / COUNT(*), 2) as pct
        FROM article_chunks
    ''')
    total, with_fts, pct = cur.fetchone()
    print(f'Total chunks: {total:,}')
    print(f'With FTS: {with_fts:,} ({pct}%)')
"
```

---

## Сравнение режимов

### Текущий режим (openai-migration):

```bash
SERVICE_MODE=openai-migration  # или не установлена (дефолт)
```

**Команда:**
```bash
python services/openai_embedding_migration_service.py continuous --interval 60 --batch-size 100
```

**Что делает:** Генерирует OpenAI embeddings (3072-dim)

---

### Правильный режим (fts-continuous):

```bash
SERVICE_MODE=fts-continuous
```

**Команда:**
```bash
python services/fts_service.py service --interval 60 --batch-size 100000
```

**Что делает:** Создаёт FTS (tsvector) индексы для keyword search

---

## Конфигурация всех режимов launcher.py

Для справки, все поддерживаемые режимы:

```python
# launcher.py поддерживает:
SERVICE_MODE=poll               # RSS polling
SERVICE_MODE=work               # Article processing (one-off)
SERVICE_MODE=work-continuous    # Article processing (continuous)
SERVICE_MODE=embedding          # Embedding generation (one-off)
SERVICE_MODE=chunking           # Chunking (one-off)
SERVICE_MODE=chunk-continuous   # Chunking (continuous)
SERVICE_MODE=fts                # FTS indexing (one-off)
SERVICE_MODE=fts-continuous     # FTS indexing (continuous) ← НУЖЕН ДЛЯ ffe65f79
SERVICE_MODE=openai-migration   # OpenAI embeddings (continuous) [DEFAULT]
SERVICE_MODE=bot                # Telegram bot
```

---

## Важные замечания

### 1. FTS не требует OPENAI_API_KEY

FTS сервис работает только с PostgreSQL:

```bash
# НЕ нужны для FTS:
OPENAI_API_KEY=...  ❌
OPENAI_EMBEDDING_MODEL=...  ❌
```

### 2. Проверка конфликтов

Убедитесь, что другой сервис не использует `fts-continuous`:

```bash
# Проверить все сервисы
railway service list

# Для каждого сервиса проверить SERVICE_MODE
railway link --service <SERVICE_ID>
railway variables | grep SERVICE_MODE
```

### 3. После обновления

Railway автоматически:
- ✅ Перезапустит контейнер
- ✅ Применит новые переменные
- ✅ Запустит правильную команду

**Время перезапуска:** ~30-60 секунд

---

## Мониторинг после запуска

### Проверить FTS индексацию:

```bash
# Смотреть логи в реальном времени
railway logs --follow

# Ожидаемые сообщения:
# - "Starting FTS indexing service"
# - "Updating FTS index for N chunks"
# - "FTS indexing complete: N chunks indexed"
```

### Проверить прогресс индексации:

```bash
railway run python -c "
from pg_client_new import PgClient
import time

db = PgClient()

with db._cursor() as cur:
    cur.execute('SELECT COUNT(*) FROM article_chunks WHERE fts_vector IS NULL')
    pending = cur.fetchone()[0]

    cur.execute('SELECT COUNT(*) FROM article_chunks WHERE fts_vector IS NOT NULL')
    indexed = cur.fetchone()[0]

    total = pending + indexed
    pct = (indexed / total * 100) if total > 0 else 0

    print(f'FTS Progress:')
    print(f'  Indexed: {indexed:,}/{total:,} ({pct:.1f}%)')
    print(f'  Pending: {pending:,}')
"
```

---

## Команда для быстрого обновления

Скопируйте и выполните:

```bash
# 1. Подключиться к FTS сервису
railway link --service ffe65f79-4dc5-4757-b772-5a99c7ea624f

# 2. Установить переменные
railway variables --set SERVICE_MODE=fts-continuous
railway variables --set FTS_CONTINUOUS_INTERVAL=60
railway variables --set FTS_BATCH=100000

# 3. Перезапустить
railway restart

# 4. Проверить логи
railway logs --tail 50
```

---

## Результат после исправления

### До:
```
launcher.py -> executing: python services/openai_embedding_migration_service.py ...
OpenAI embedding generator initialized
No backlog, waiting...
```

### После:
```
launcher.py -> executing: python services/fts_service.py service --interval 60 --batch-size 100000
FTS service started with 60s interval
Updating FTS index for 50,000 chunks
FTS indexing complete: 50,000 chunks indexed
```

---

## Связанные документы

- [launcher.py](launcher.py) - Универсальный лаунчер (строки 73-79 для FTS)
- [services/fts_service.py](services/fts_service.py) - FTS сервис
- [RAILWAY_SERVICES_CONFIG.md](RAILWAY_SERVICES_CONFIG.md) - Конфигурация всех сервисов
- [SERVICE_ffe65f79_FTS_INFO.md](SERVICE_ffe65f79_FTS_INFO.md) - Документация FTS сервиса
- [FTS_OPENAI_KEY_EXPLANATION.md](FTS_OPENAI_KEY_EXPLANATION.md) - Почему FTS не нужен OPENAI_API_KEY

---

**Последнее обновление:** 2025-10-05

**Статус:** ⏳ Ожидает установки переменных окружения в Railway
