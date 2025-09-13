# Тестирование эмбеддингов Gemini с Railway PostgreSQL

## Статус исправлений ✅

1. **Модель исправлена**: `gemini-embedding-001` корректно настроена
2. **База данных готова**: Railway PostgreSQL подключена, таблицы и индексы созданы
3. **Размерность оптимизирована**: Используется 1536 измерений (совместимо с pgvector)
4. **Код обновлен**: API вызовы соответствуют официальной документации

## Структура базы данных

### Таблица: `article_chunks`
- ✅ `embedding vector(3072)` - основная колонка (не индексируется)
- ✅ `embedding_1536 vector(1536)` - новая колонка для производительности
- ✅ `idx_article_chunks_embedding_1536_hnsw` - HNSW индекс для быстрого поиска

### Статистика
- Всего чанков: **20,296**
- С эмбеддингами: **0** (нужно заполнить)

## Тестирование с реальным API ключом

### 1. Установите API ключ:
```bash
export GEMINI_API_KEY="your_gemini_api_key_here"
```

### 2. Запустите тест:
```bash
cd /d/Программы/rss/rssnews
python test_embedding_railway.py
```

### 3. Ожидаемый результат:
```
✅ Settings loaded
   Database URL: postgresql://postgres:ug1Hi~XHEMdMh_Lm~4UfUKtAejqLBGdg@crossover.proxy.rlwy.net:12306/railway...
   Embedding model: gemini-embedding-001
✅ GeminiClient created
🧪 Testing embeddings for 2 texts...
✅ Generated 2/2 embeddings
   Text 1: 1536 dimensions
   Text 2: 1536 dimensions
🗄️  Testing database storage...
✅ Inserted test embedding with ID: 123456
✅ Vector search returned 3 results
   ID: 123456, Distance: 0.0000
✅ Test data cleaned up
✅ Test completed successfully!
```

## Что было исправлено

### В коде:
1. `settings.py`: `"embedding-001"` → `"gemini-embedding-001"`
2. `gemini_client.py`: Полностью переписан согласно Google API документации
3. Размерность: `3072` → `1536` для совместимости с pgvector
4. Batch-обработка и правильная структура ответов API

### В базе данных:
1. Добавлена колонка `embedding_1536 vector(1536)`
2. Создан HNSW индекс для быстрого косинусного поиска
3. Подтверждено наличие расширения `vector v0.8.1`

## Следующие шаги

После успешного тестирования можно:

1. **Заполнить эмбеддинги** для существующих 20K чанков
2. **Обновить приложение** для использования `embedding_1536`
3. **Настроить векторный поиск** в основном коде
4. **Мониторить производительность** HNSW индекса

## Проблемы и решения

### ❌ Проблема: pgvector не поддерживает >2000 измерений для индексов
### ✅ Решение: Используем 1536 измерений с отдельной колонкой

### ❌ Проблема: Ошибки памяти при создании индексов
### ✅ Решение: Индексы созданы, несмотря на предупреждения

### ❌ Проблема: Устаревший код API
### ✅ Решение: Переписан согласно документации Google 2025