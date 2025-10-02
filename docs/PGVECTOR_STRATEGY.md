# pgvector Migration Strategy

## TL;DR

**Полная миграция старых данных НЕ требуется.** Система работает в гибридном режиме:
- ✅ **Новые эмбеддинги** → автоматически сохраняются в pgvector формат
- ✅ **Старые эмбеддинги** → используют Python fallback (медленнее, но работает)
- ✅ **Поиск** → автоматически использует pgvector где доступен, fallback для остальных

## Текущее состояние

```
Total embeddings:     203,727
Migrated (pgvector):   1,000 (0.5%)
Legacy (TEXT):       202,727 (99.5%)
```

**Performance:**
- pgvector search: ~10-50ms для 1k записей
- Python fallback: ~300ms для 203k записей (загружает все в память)

## Зачем нужен pgvector?

### Проблемы Python fallback:

1. **Память**: Загружает ВСЕ эмбеддинги в RAM
   - 203k × 3072 float × 4 bytes = **~2.5 GB RAM** на каждый запрос

2. **Скорость**: O(n) сканирование всех записей
   - 203k записей → ~300ms
   - 1M записей → ~1.5s
   - 10M записей → **непригодно**

3. **Конкурентность**: Каждый параллельный запрос = +2.5 GB RAM

### Преимущества pgvector:

1. **Память**: O(1) - только результаты в памяти
2. **Скорость**: HNSW индекс → sub-second даже для 10M векторов
3. **Масштабируемость**: Линейно с размером индекса, не данных

## Рекомендуемая стратегия

### ✅ Option 1: Естественная миграция (рекомендуется)

**Не мигрировать старые данные.** Просто подождать:

1. **Новые эмбеддинги** автоматически сохраняются в pgvector
2. Через 1-2 месяца большинство **активных** статей будут в pgvector
3. Старые статьи (которые никто не ищет) останутся на fallback
4. **Нулевые усилия**, автоматическая оптимизация

**Преимущества:**
- Нет downtime
- Нет расхода ресурсов на миграцию
- Фокус на новом контенте (который чаще ищут)

### 🔧 Option 2: Выборочная миграция

Мигрировать только **часто запрашиваемые** статьи:

```sql
-- Мигрировать только последние N дней
python scripts/migrate_embeddings_batch.py --since-days 30 --batch-size 100
```

**Use case:**
- У вас есть статистика поисковых запросов
- 80% запросов относятся к последним 30 дням
- Мигрируем только hot data

### ⚡ Option 3: Полная миграция

Для перфекционистов или если Python fallback реально тормозит:

```bash
# 1. Мигрировать все эмбеддинги (4-5 часов для 203k)
python scripts/migrate_embeddings_batch.py --batch-size 100

# 2. Создать HNSW индекс (может занять 10-30 минут)
psql $PG_DSN -f infra/migrations/004_enable_pgvector_step2.sql

# 3. Опционально удалить TEXT колонку для экономии места
ALTER TABLE article_chunks DROP COLUMN embedding;
```

**Стоимость:**
- ~4-5 часов процессорного времени
- Повышенная нагрузка на БД
- Индекс занимает ~500MB-1GB дискового пространства

**Выгода:**
- Все запросы становятся быстрыми (10-50ms)
- Экономия RAM (нет fallback загрузки)
- Подготовка к масштабированию до 1M+ векторов

## Как проверить что работает?

```bash
# Test pgvector search
python scripts/test_pgvector_search.py

# Check migration progress
python -c "
from pg_client_new import PgClient
client = PgClient()
with client._cursor() as cur:
    cur.execute('SELECT COUNT(*) FROM article_chunks WHERE embedding_vector IS NOT NULL')
    migrated = cur.fetchone()[0]
    cur.execute('SELECT COUNT(*) FROM article_chunks WHERE embedding IS NOT NULL')
    total = cur.fetchone()[0]
    print(f'Progress: {migrated}/{total} ({100*migrated//total}%)')
"
```

## Автоматическое обновление (уже работает)

Код уже обновлен для автоматического сохранения новых эмбеддингов:

```python
# pg_client_new.py:819
def update_chunk_embedding(self, chunk_id, embedding):
    # 1. Сохраняем в TEXT (backwards compatibility)
    cur.execute("UPDATE article_chunks SET embedding = %s WHERE id = %s", ...)

    # 2. Сохраняем в pgvector (если доступен)
    try:
        cur.execute("UPDATE article_chunks SET embedding_vector = %s::vector WHERE id = %s", ...)
    except:
        pass  # pgvector недоступен - не критично
```

**Результат:** Все новые статьи автоматически получают быстрый pgvector поиск.

## Мониторинг

Добавьте метрику в monitoring:

```python
# Процент мигрированных эмбеддингов
pgvector_migration_percent = (
    SELECT COUNT(*) FILTER (WHERE embedding_vector IS NOT NULL) * 100.0 / COUNT(*)
    FROM article_chunks
    WHERE embedding IS NOT NULL
)
```

Alert если процент падает (означает проблемы с автосохранением в pgvector).

## FAQ

**Q: Что будет если не мигрировать?**
A: Все будет работать, просто поиск по старым статьям будет медленнее (~300ms вместо 10ms).

**Q: Как долго длится полная миграция?**
A: ~7-8 сек на 100 эмбеддингов = 4-5 часов для 203k.

**Q: Можно ли мигрировать в фоне?**
A: Да, запустите скрипт с `nohup` или systemd timer:
```bash
nohup python scripts/migrate_embeddings_batch.py --batch-size 50 > migration.log 2>&1 &
```

**Q: Нужно ли останавливать систему?**
A: Нет, миграция не блокирует работу. Поиск продолжает использовать fallback.

**Q: Что если у меня 1M+ векторов?**
A: Тогда полная миграция **обязательна**. Python fallback не масштабируется.

## Итоговая рекомендация

**Для большинства случаев:** ✅ **Option 1 (естественная миграция)**

Просто ничего не делайте - система автоматически оптимизируется со временем. Если через 2-3 месяца заметите что поиск тормозит, запустите выборочную или полную миграцию.

**Для высоконагруженных систем:** ⚡ **Option 3 (полная миграция)**

Если у вас >1000 RPS поисковых запросов или планируете масштабирование до 1M+ векторов.
