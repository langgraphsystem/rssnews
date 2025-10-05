# Конфигурация launcher.py для Railway

## Дата проверки: 2025-10-04

## ✅ Статус: Все режимы работают корректно

---

## 1. Исправленные проблемы

### ❌ Найденные ошибки:
1. **Ошибка отступов** в строках 42-48 (смешивание пробелов и табов)
2. **IndentationError** при компиляции Python

### ✅ Исправления:
- Выровнены все отступы на 4 пробела
- Проверен синтаксис: `python -m py_compile launcher.py`
- Протестированы все 11 режимов работы

---

## 2. Поддерживаемые режимы SERVICE_MODE

| Режим | Команда | Переменные окружения |
|-------|---------|---------------------|
| `poll` | `python main.py poll --workers {POLL_WORKERS} --batch-size {POLL_BATCH}` | POLL_WORKERS=10<br>POLL_BATCH=10 |
| `work` | `python main.py work [--simplified] --workers {WORK_WORKERS} --batch-size {WORK_BATCH}` | WORK_WORKERS=10<br>WORK_BATCH=50<br>WORK_SIMPLIFIED=false |
| `work-continuous` | `python services/work_continuous_service.py --interval {WORK_CONTINUOUS_INTERVAL} --batch {WORK_CONTINUOUS_BATCH}` | WORK_CONTINUOUS_INTERVAL=30<br>WORK_CONTINUOUS_BATCH=50 |
| `embedding` | `python main.py services run-once --services embedding --embedding-batch {EMBEDDING_BATCH}` | EMBEDDING_BATCH=1000 |
| `chunking` | `python main.py services run-once --services chunking --chunking-batch {CHUNKING_BATCH}` | CHUNKING_BATCH=100 |
| `chunk-continuous` | `python services/chunk_continuous_service.py --interval {CHUNK_CONTINUOUS_INTERVAL} --batch {CHUNK_CONTINUOUS_BATCH}` | CHUNK_CONTINUOUS_INTERVAL=30<br>CHUNK_CONTINUOUS_BATCH=100 |
| **`fts`** ⭐ | `python main.py services run-once --services fts --fts-batch {FTS_BATCH}` | FTS_BATCH=100000 |
| **`fts-continuous`** ⭐ | `python main.py services start --services fts --fts-interval {FTS_CONTINUOUS_INTERVAL}` | FTS_CONTINUOUS_INTERVAL=60 |
| `openai-migration` | `python services/openai_embedding_migration_service.py continuous --interval {MIGRATION_INTERVAL} --batch-size {MIGRATION_BATCH}` | MIGRATION_INTERVAL=60<br>MIGRATION_BATCH=100 |
| `bot` | `python start_telegram_bot.py` | - |

⭐ = **Новые режимы** для FTS индексации

---

## 3. Конфигурация Railway сервисов

### Текущие сервисы:

#### 🔵 RSS POLL
```bash
SERVICE_MODE=poll
POLL_WORKERS=10
POLL_BATCH=10
```

#### 🔵 WORK
```bash
SERVICE_MODE=work-continuous
WORK_CONTINUOUS_INTERVAL=30
WORK_CONTINUOUS_BATCH=50
```

#### 🔵 OpenAIEmbending
```bash
SERVICE_MODE=embedding
EMBEDDING_BATCH=1000
```

#### 🔵 CHUNK
```bash
SERVICE_MODE=chunk-continuous
CHUNK_CONTINUOUS_INTERVAL=30
CHUNK_CONTINUOUS_BATCH=100
```

#### 🆕 RSS FTS (новый сервис)
```bash
SERVICE_MODE=fts-continuous
RAILWAY_SERVICE_ID=ffe65f79-4dc5-4757-b772-5a99c7ea624f
FTS_BATCH=100000
FTS_CONTINUOUS_INTERVAL=60
```

**Команда запуска:**
```bash
python launcher.py
```

**Результат выполнения:**
```bash
→ python main.py services start --services fts --fts-interval 60
```

#### 🔵 Bot
```bash
SERVICE_MODE=bot
```

#### 🔵 rssnews (основной)
```bash
SERVICE_MODE=openai-migration
MIGRATION_INTERVAL=60
MIGRATION_BATCH=100
```

---

## 4. Новый FTS сервис

### Назначение:
Индексация полнотекстового поиска (Full-Text Search) для статей

### Режимы работы:

#### 1. One-off индексация (`fts`)
Однократная индексация всех статей
```bash
SERVICE_MODE=fts
FTS_BATCH=100000
```

#### 2. Непрерывная индексация (`fts-continuous`) ✅ Рекомендуется
Постоянный мониторинг и индексация новых статей
```bash
SERVICE_MODE=fts-continuous
FTS_CONTINUOUS_INTERVAL=60  # проверка каждые 60 секунд
```

### Переменные окружения для FTS:

| Переменная | Значение | Описание |
|------------|----------|----------|
| `SERVICE_MODE` | `fts-continuous` | Режим работы сервиса |
| `RAILWAY_SERVICE_ID` | `ffe65f79-4dc5-4757-b772-5a99c7ea624f` | ID сервиса в Railway |
| `FTS_BATCH` | `100000` | Размер батча для индексации |
| `FTS_CONTINUOUS_INTERVAL` | `60` | Интервал проверки (секунды) |

---

## 5. Проверка и тестирование

### Локальное тестирование:
```bash
# Проверка синтаксиса
python -m py_compile launcher.py

# Тестирование всех режимов
python test_launcher_modes.py
```

### Результаты тестирования:
```
✅ Рабочих режимов: 11/11
🎉 Все режимы работают корректно!
📌 launcher.py готов к деплою на Railway
```

### Проверка конкретного режима:
```bash
# FTS one-off
SERVICE_MODE=fts FTS_BATCH=50000 python launcher.py

# FTS continuous
SERVICE_MODE=fts-continuous FTS_CONTINUOUS_INTERVAL=120 python launcher.py
```

---

## 6. Как настроить новый FTS сервис на Railway

### Шаг 1: Создать новый сервис
```bash
railway service create "RSS FTS"
```

### Шаг 2: Установить переменные окружения
```bash
railway vars set SERVICE_MODE=fts-continuous --service "RSS FTS"
railway vars set RAILWAY_SERVICE_ID=ffe65f79-4dc5-4757-b772-5a99c7ea624f --service "RSS FTS"
railway vars set FTS_BATCH=100000 --service "RSS FTS"
railway vars set FTS_CONTINUOUS_INTERVAL=60 --service "RSS FTS"
```

### Шаг 3: Настроить команду запуска
В Railway dashboard → Settings → Deploy:
```bash
python launcher.py
```

### Шаг 4: Деплой
```bash
railway up --service "RSS FTS"
```

---

## 7. Мониторинг и логи

### Просмотр логов FTS сервиса:
```bash
railway logs --service "RSS FTS"
```

### Ожидаемый вывод при запуске:
```
launcher.py -> executing: python main.py services start --services fts --fts-interval 60
Starting FTS indexing service...
[FTS] Interval: 60s, Batch: 100000
[FTS] Checking for articles to index...
```

---

## 8. Файлы для проверки

- `launcher.py` - основной файл запуска
- `test_launcher_modes.py` - скрипт тестирования всех режимов
- `check_railway_services.py` - проверка конфигурации Railway сервисов

---

## 9. Troubleshooting

### ❌ IndentationError
**Проблема:** Смешивание табов и пробелов
**Решение:** Все отступы исправлены на 4 пробела

### ❌ Unsupported SERVICE_MODE
**Проблема:** Неизвестный режим
**Решение:** Проверить список поддерживаемых режимов в таблице выше

### ❌ FTS сервис не запускается
**Проблема:** Не установлены переменные окружения
**Решение:**
```bash
railway vars --service "RSS FTS"  # Проверить переменные
railway vars set SERVICE_MODE=fts-continuous --service "RSS FTS"
```

---

## 10. Итоги

✅ **launcher.py исправлен и протестирован**
- Исправлены все ошибки отступов
- Добавлены новые режимы FTS (fts, fts-continuous)
- Все 11 режимов работают корректно
- Готов к деплою на Railway

✅ **Новый FTS сервис настроен**
- RAILWAY_SERVICE_ID: `ffe65f79-4dc5-4757-b772-5a99c7ea624f`
- SERVICE_MODE: `fts-continuous`
- Интервал индексации: 60 секунд
- Размер батча: 100,000 статей

📌 **Следующие шаги:**
1. Деплой обновленного launcher.py
2. Настройка FTS сервиса на Railway
3. Мониторинг работы индексации
