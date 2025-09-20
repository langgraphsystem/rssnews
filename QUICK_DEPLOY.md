# ⚡ LlamaIndex: Быстрое развёртывание

**Карточка для печати — используй вместо длинного чеклиста**

---

## 🚀 За 10 минут до продакшна

### 1️⃣ Подготовка (2 мин)
```bash
# Установка
python setup_llamaindex.py

# Добавить в .env:
GEMINI_API_KEY=your-gemini-key
PINECONE_API_KEY=your-pinecone-key
PINECONE_INDEX=rssnews-embeddings
```

### 2️⃣ Применение схемы (1 мин)
```bash
psql $PG_DSN -f llamaindex_schema.sql
```

### 3️⃣ Тестирование (5 мин)
```bash
# Проверка системы
python main.py llamaindex-monitor

# Тест на 10 статьях
python main.py llamaindex-ingest --limit 10

# Тест всех пресетов
python main.py llamaindex-query "test query" --preset qa
python main.py llamaindex-query "weekly digest" --preset digest
```

### 4️⃣ Развёртывание (2 мин)
```bash
# Автоматическое развёртывание
python deploy_llamaindex.py

# ИЛИ ручное поэтапное:
python main.py llamaindex-legacy enable --components retrieval synthesis  # Включить только chunking
python main.py llamaindex-migrate backfill --limit 1000                   # Бэкфилл
python main.py llamaindex-legacy disable                                  # Полное включение
```

---

## 🔥 Критические команды

### ✅ Статус проверка
```bash
python main.py llamaindex-monitor
```

### 🚨 Экстренный откат
```bash
python main.py llamaindex-legacy enable
# ИЛИ
python deploy_llamaindex.py --emergency-rollback
```

### 📊 Быстрая проверка качества
```bash
# Сравнить результаты
python main.py llamaindex-query "AI news" --preset qa
python main.py rag "AI news"  # legacy
```

---

## 📋 Go/No-Go критерии

**✅ Готов к продакшну, если:**
- [ ] `llamaindex-monitor` показывает 0 ошибок
- [ ] Все 4 пресета отвечают за <5 секунд
- [ ] Cost estimate < $1.00 на 100 запросов
- [ ] Качество ≥ legacy системы

**❌ НЕ запускать, если:**
- [ ] API ключи не работают
- [ ] Ошибки в imports
- [ ] Превышение budget limits
- [ ] Latency > 10 секунд

---

## 🎯 4 команды для production

```bash
# 1. Обработка новых статей (замена Stage 6-7)
python main.py llamaindex-ingest --limit 100

# 2. Умные запросы
python main.py llamaindex-query "query" --preset qa|digest|shorts|ideas

# 3. Миграция данных
python main.py llamaindex-migrate backfill --limit 5000

# 4. Мониторинг
python main.py llamaindex-monitor
```

---

## 🔧 Troubleshooting в 1 команду

| Проблема | Команда |
|----------|---------|
| Imports не работают | `pip install -r requirements_llamaindex.txt` |
| API недоступен | Проверить `.env` ключи |
| Медленные запросы | Включить legacy: `llamaindex-legacy enable` |
| Высокие costs | Снизить limits в БД |
| Низкое качество | Откат: `llamaindex-legacy enable` |

---

## 💡 Сценарии использования

### 📰 Новостные дайджесты
```bash
python main.py llamaindex-query "Tech news this week" --preset digest --max-sources 15
```

### 🎥 Идеи для видео
```bash
python main.py llamaindex-query "Crypto trends" --preset shorts --max-sources 8
```

### 🔍 Исследования
```bash
python main.py llamaindex-query "Future of AI" --preset ideas --max-sources 20
```

### ❓ Быстрые ответы
```bash
python main.py llamaindex-query "What is GPT-5?" --preset qa --max-sources 5
```

---

## 📊 Ожидаемые метрики (production)

- **Latency**: 1-3 сек (qa), 2-5 сек (digest/ideas)
- **Качество**: +30% vs legacy chunking
- **Cost**: $0.05-0.20 за запрос (зависит от preset)
- **Cache hit**: 20-40% при повторных запросах
- **Success rate**: >98%

---

## 🚨 SLA и escalation

- **Критичный incident**: >5% error rate за 5 минут
- **Откат SLA**: <2 минуты до legacy mode
- **Escalation**: error rate >10% = немедленный откат

---

**🎯 Готово! Система в продакшне!** 🚀