# Railway Service: c015bdb5-710d-46b8-ad86-c566b99e7560

## 📋 Основная информация

**Название:** OpenAIEmbending Service (Continuous)

**Service ID:** `c015bdb5-710d-46b8-ad86-c566b99e7560`

**Режим работы:** Continuous (непрерывный)

---

## 🎯 Назначение

Сервис отвечает за **генерацию OpenAI embeddings** для чанков статей.

### Что он делает:

1. **Мониторит таблицу** `article_chunks` на наличие записей без embeddings
2. **Генерирует embeddings** используя OpenAI API
3. **Сохраняет векторы** в поле `embedding_vector` (размерность 3072)
4. **Работает непрерывно** с интервалом проверки 60 секунд

---

## ⚙️ Конфигурация

### Environment Variables:

```bash
SERVICE_MODE=openai-migration
MIGRATION_INTERVAL=60                           # Проверка каждые 60 секунд
OPENAI_API_KEY=sk-proj-...                      # API ключ OpenAI
OPENAI_EMBEDDING_MODEL=text-embedding-3-large   # Модель embeddings (3072 dim)
OPENAI_EMBEDDING_BATCH_SIZE=100                 # Размер батча
OPENAI_EMBEDDING_MAX_RETRIES=3                  # Количество повторов при ошибке
```

### Команда запуска:

```bash
python launcher.py
# или напрямую
python services/openai_embedding_migration_service.py continuous --interval 60 --batch-size 100
```

---

## 🔄 Процесс работы

### Цикл обработки:

```
1. Проверка БД каждые 60 секунд
   ↓
2. Поиск чанков без embeddings:
   SELECT * FROM article_chunks
   WHERE embedding_vector IS NULL
   ORDER BY published_at DESC
   LIMIT 100
   ↓
3. Генерация embeddings через OpenAI API:
   POST https://api.openai.com/v1/embeddings
   {
     "model": "text-embedding-3-large",
     "input": [chunk_text_1, chunk_text_2, ...]
   }
   ↓
4. Сохранение в БД:
   UPDATE article_chunks
   SET embedding_vector = %s::vector
   WHERE id = %s
   ↓
5. Повтор цикла
```

---

## 📊 Используемые данные

### Таблица: `article_chunks`

**Читаемые поля:**
- `id` - идентификатор чанка
- `text` - текст для генерации embedding
- `published_at` - дата для сортировки
- `embedding_vector` - проверка наличия (IS NULL)

**Записываемые поля:**
- `embedding_vector` - 3072-мерный вектор (vector type)

### Модель: text-embedding-3-large

**Характеристики:**
- Размерность: **3072**
- Провайдер: OpenAI
- Стоимость: ~$0.13 за 1M токенов
- Качество: Высокое (лучше чем ada-002)

---

## 🔍 Мониторинг

### Проверка backlog:

```bash
# Подключиться к сервису
railway link --service c015bdb5-710d-46b8-ad86-c566b99e7560

# Проверить статус
railway run python check_backlog.py

# Или через прямой запрос
railway run python -c "
from database.production_db_client import ProductionDBClient
db = ProductionDBClient()
with db._cursor() as cur:
    cur.execute('SELECT COUNT(*) FROM article_chunks WHERE embedding_vector IS NULL')
    pending = cur.fetchone()[0]
    cur.execute('SELECT COUNT(*) FROM article_chunks')
    total = cur.fetchone()[0]
    print(f'Pending: {pending:,} | Total: {total:,} | Done: {((total-pending)/total*100):.1f}%')
"
```

### Проверка логов:

```bash
railway logs --service c015bdb5-710d-46b8-ad86-c566b99e7560 --limit 50
```

### Метрики:

```bash
# Статус обработки
railway run python -c "
from services.openai_embedding_migration_service import OpenAIEmbeddingMigrationService
service = OpenAIEmbeddingMigrationService()
stats = service.get_stats()
print(f'Processed: {stats.get(\"processed\", 0):,}')
print(f'Failed: {stats.get(\"failed\", 0):,}')
print(f'Rate: {stats.get(\"rate\", 0):.1f} chunks/min')
"
```

---

## 🚨 Возможные проблемы

### 1. OpenAI API Rate Limit
**Симптомы:** Ошибки 429 в логах
**Решение:** Уменьшить `OPENAI_EMBEDDING_BATCH_SIZE` или увеличить `MIGRATION_INTERVAL`

### 2. Timeout при больших батчах
**Симптомы:** Connection timeout
**Решение:** Уменьшить batch size до 50

### 3. Дубликаты embeddings
**Симптомы:** Один чанк обрабатывается несколько раз
**Решение:** Проверить логику SELECT (должен быть WHERE embedding_vector IS NULL)

### 4. Нет API ключа
**Симптомы:** Authentication failed
**Решение:** Проверить `OPENAI_API_KEY` в Railway переменных

---

## 📈 Производительность

### Текущие показатели (по данным проверки):

- **Всего чанков:** 3,772 (за 24ч)
- **С embeddings:** 3,772 (100%)
- **Скорость:** ~100 чанков/мин (при batch_size=100)
- **Стоимость:** ~$0.001 за 1000 чанков

### Оптимизация:

**Для быстрой обработки:**
```bash
OPENAI_EMBEDDING_BATCH_SIZE=200
MIGRATION_INTERVAL=30
```

**Для экономии:**
```bash
OPENAI_EMBEDDING_BATCH_SIZE=50
MIGRATION_INTERVAL=120
```

---

## 🔗 Связанные сервисы

### Зависит от:
1. **PostgreSQL** - база данных с article_chunks
2. **CHUNK Service** - создает чанки для обработки

### Используется в:
1. **Bot Service** - команды /search, /analyze, /trends
2. **Ranking API** - semantic search через pgvector

---

## 📝 Код сервиса

**Основной файл:** `services/openai_embedding_migration_service.py`

**Ключевые методы:**
- `run_continuous()` - основной цикл
- `process_batch()` - обработка батча чанков
- `generate_embeddings()` - вызов OpenAI API
- `save_embeddings()` - сохранение в БД

---

## ✅ Текущий статус

**По данным последней проверки:**
- ✅ Сервис работает
- ✅ 100% чанков имеют embeddings
- ✅ Размерность 3072 (text-embedding-3-large)
- ✅ Индексы созданы (HNSW)

**Рекомендации:**
- Продолжать мониторинг backlog
- Следить за rate limits OpenAI
- Проверять стоимость в OpenAI dashboard

---

## 🔧 Управление сервисом

### Запуск:
```bash
railway up --service c015bdb5-710d-46b8-ad86-c566b99e7560
```

### Остановка:
```bash
railway down --service c015bdb5-710d-46b8-ad86-c566b99e7560
```

### Перезапуск:
```bash
railway restart --service c015bdb5-710d-46b8-ad86-c566b99e7560
```

### Изменение переменных:
```bash
railway vars set OPENAI_EMBEDDING_BATCH_SIZE=200 --service c015bdb5-710d-46b8-ad86-c566b99e7560
```

---

## 📌 Итоговое заключение

**Сервис c015bdb5-710d-46b8-ad86-c566b99e7560** - это **OpenAI Embedding Generation Service**

**Критическая важность:** ⭐⭐⭐⭐⭐ (5/5)

Без этого сервиса не работают:
- ❌ Semantic search
- ❌ /analyze команда
- ❌ /trends команда
- ❌ Hybrid search

**Статус:** ✅ Активен и работает корректно
