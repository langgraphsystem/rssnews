# 🚀 Quick Start: Railway Deployment

## Запуск OpenAI Embedding Service на Railway (5 минут)

---

## 📋 Предварительные Требования

1. ✅ Railway account: https://railway.app
2. ✅ Railway CLI: `npm install -g @railway/cli`
3. ✅ OpenAI API key: https://platform.openai.com/account/api-keys
4. ✅ Git repository подключен к Railway

---

## ⚡ Быстрый Старт (Автоматически)

### Вариант 1: Через скрипт

```bash
chmod +x scripts/railway_setup.sh
./scripts/railway_setup.sh
```

Скрипт запросит API key и автоматически настроит всё.

---

## 🛠️ Быстрый Старт (Вручную)

### Шаг 1: Установить переменные окружения

```bash
railway vars set OPENAI_API_KEY="sk-proj-your-actual-key-here"
railway vars set OPENAI_EMBEDDING_MODEL="text-embedding-3-large"
railway vars set ENABLE_LOCAL_EMBEDDINGS="false"
railway vars set OPENAI_EMBEDDING_SERVICE_ENABLED="true"
railway vars set OPENAI_EMBEDDING_BATCH_SIZE="100"
```

### Шаг 2: Deploy

```bash
railway up
```

Railway автоматически обнаружит `Procfile` и запустит два процесса:
- `web` - Telegram бот
- `embedding-worker` - Миграция эмбеддингов

### Шаг 3: Проверить

```bash
# Статус
railway status

# Логи
railway logs --service embedding-worker

# Backlog
railway run python check_backlog.py
```

---

## 📊 Что Произойдёт После Deploy

### Continuous Service запустится и:

1. **Каждые 60 секунд:**
   - Проверяет новые чанки БЕЗ эмбеддингов
   - Обрабатывает до 100 чанков за раз
   - Генерирует эмбеддинги через OpenAI
   - Сохраняет в БД (TEXT + pgvector)

2. **Логи будут показывать:**
   ```
   Starting continuous migration service with 60s interval
   Found 5611 chunks without embeddings, processing...
   Processing batch 1/57 (100 chunks)...
   Migration progress: 100/5611 successful (0 errors)
   Processing batch 2/57 (100 chunks)...
   ...
   ```

3. **После завершения backlog:**
   ```
   No backlog, waiting...
   ```

---

## 💰 Стоимость

### Текущий backlog (5,611 чанков):
- **Одноразово:** ~$0.36

### Новые чанки (continuous):
- **В месяц:** ~$0.30
- **В день:** ~$0.01

**ИТОГО: ~$0.66 первый месяц, потом ~$0.30/месяц**

---

## 🔍 Мониторинг

### Проверить прогресс

```bash
railway run python check_backlog.py
```

**Вывод:**
```
📊 Embedding Statistics:
   Total chunks: 209,338
   Without embeddings: 5,611 → 4,500 → 3,000 → ...
   Completion: 97.3% → 98.0% → 98.5% → ...
```

### Логи в реальном времени

```bash
railway logs --follow --service embedding-worker
```

### Остановить процесс

```bash
# Временно
railway vars set OPENAI_EMBEDDING_SERVICE_ENABLED="false"
railway restart

# Или удалить процесс из Procfile
```

---

## ⚠️ Важные Замечания

### 1. API Key

**КРИТИЧНО:** Используйте валидный OpenAI API key. Проверить можно так:

```bash
# Локально
python -c "
import asyncio
from dotenv import load_dotenv
load_dotenv()
from openai_embedding_generator import OpenAIEmbeddingGenerator

async def test():
    gen = OpenAIEmbeddingGenerator()
    result = await gen.test_connection()
    print('✅ Valid' if result else '❌ Invalid')

asyncio.run(test())
"
```

### 2. Worker.py Должен НЕ Генерировать Эмбеддинги

Убедитесь:
```bash
railway vars get ENABLE_LOCAL_EMBEDDINGS
# Должно быть: false
```

Если `true`, worker.py будет пытаться использовать Ollama (которого нет на Railway).

### 3. Два Процесса на Railway

Railway запустит:
- **web:** Telegram бот (основной процесс)
- **embedding-worker:** Миграция эмбеддингов (фоновый процесс)

Оба работают **параллельно**.

---

## 🆘 Troubleshooting

### Проблема: "Incorrect API key"

```bash
# Обновить ключ
railway vars set OPENAI_API_KEY="sk-proj-new-key"
railway restart
```

### Проблема: Backlog не уменьшается

**Проверить:**
```bash
# Процесс запущен?
railway ps

# Логи
railway logs --service embedding-worker --tail 50

# Переменные
railway vars get ENABLE_LOCAL_EMBEDDINGS  # Должно быть false
railway vars get OPENAI_EMBEDDING_SERVICE_ENABLED  # Должно быть true
```

### Проблема: "Rate limit exceeded"

```bash
# Уменьшить batch size
railway vars set OPENAI_EMBEDDING_BATCH_SIZE="50"
railway restart
```

### Проблема: Процесс крашится

```bash
# Проверить логи
railway logs --service embedding-worker --tail 100

# Проверить PG_DSN
railway vars get PG_DSN
```

---

## 📝 Checklist

После деплоя убедитесь:

- [ ] ✅ `railway status` показывает два процесса (web + embedding-worker)
- [ ] ✅ `railway logs` показывает "Starting continuous migration service"
- [ ] ✅ Backlog уменьшается каждую минуту
- [ ] ✅ Нет ошибок "Incorrect API key"
- [ ] ✅ Нет ошибок "Rate limit exceeded"

---

## 🎯 Следующие Шаги

### После завершения backlog (все чанки с эмбеддингами):

1. **Оставить сервис работающим** - будет обрабатывать новые чанки автоматически
2. **Мониторить раз в неделю:** `railway run python check_backlog.py`
3. **Проверять стоимость:** https://platform.openai.com/usage

### Опциональные улучшения:

1. **Добавить алерты** - если backlog > 1000
2. **Логирование в БД** - сохранять статистику миграций
3. **Grafana dashboard** - визуализация прогресса

---

## 📚 Дополнительная Документация

- **Полная инструкция:** [RAILWAY_DEPLOYMENT.md](RAILWAY_DEPLOYMENT.md)
- **Миграция эмбеддингов:** [docs/OPENAI_EMBEDDING_MIGRATION.md](docs/OPENAI_EMBEDDING_MIGRATION.md)
- **Railway docs:** https://docs.railway.app

---

**Версия:** 1.0
**Дата:** 2025-10-03
