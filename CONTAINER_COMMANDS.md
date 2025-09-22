# 🐳 Container Commands for RSS News System

## ❌ Неправильно
```bash
python /app/system_stats_reporter.py
# Ошибка: No such file or directory
```

## ✅ Правильно (Проверено!)

### 1. Отправка отчета в Telegram ⭐
```bash
python main.py report --send-telegram
```

### 2. Обычный отчет (без Telegram) ⭐
```bash
python main.py report
```

### 3. Отчет с настройками
```bash
python main.py report --send-telegram --period-hours 24 --format markdown
```

### 4. Статистика системы
```bash
python main.py stats
```

### 5. Обработка статей
```bash
python main.py work
```

### 6. Сервисы (chunking, FTS, embedding)
```bash
python main.py services start
python main.py services run-once --services embedding
python main.py services status
```

## 🔧 Переменные окружения

Убедитесь, что в контейнере установлены:

```bash
PG_DSN=postgres://user:pass@host:port/db
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrSTUvwxyz
TELEGRAM_CHAT_ID=12345678
ENABLE_LOCAL_CHUNKING=true
ENABLE_LOCAL_EMBEDDINGS=true
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5-coder:3b
```

## 📋 Доступные команды

```bash
python main.py --help
```

Основные команды:
- `ensure` - создать/проверить схему БД
- `discovery` - добавить RSS фиды
- `poll` - собрать новые статьи
- `work` - обработать статьи
- `stats` - показать статистику
- `report` - сгенерировать отчет
- `services` - управление сервисами
- `db` - операции с БД

## 🐛 Устранение проблем

### Файл не найден
- Убедитесь, что рабочая директория `/app`
- Проверьте, что все файлы скопированы в контейнер

### Переменные окружения
- Проверьте `python main.py stats` для диагностики
- Убедитесь, что PG_DSN доступен

### Сервисы
- Используйте `python main.py services status` для проверки