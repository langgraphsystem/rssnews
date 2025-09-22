# 🤖 RSS News Telegram Reporting System

Автоматическая система отправки отчетов о состоянии RSS News агрегатора в Telegram.

## 🚀 Возможности

- ✅ **Полная статистика системы**: фиды, статьи, чанки, эмбеддинги
- 🤖 **LLM анализ**: автоматические инсайты и рекомендации
- 📱 **Telegram интеграция**: отправка отчетов в бот
- ⏰ **Планировщик**: автоматические отчеты по расписанию
- 🔄 **Умное разбиение**: длинные сообщения разбиваются на части

## 📁 Файлы системы

- `system_stats_reporter.py` - основной модуль сбора статистики
- `schedule_reports.py` - планировщик автоматических отчетов
- `telegram_setup.md` - подробная инструкция по настройке

## ⚙️ Быстрая настройка

### 1. Создание Telegram бота

1. Найдите [@BotFather](https://t.me/BotFather) в Telegram
2. Отправьте `/newbot`
3. Следуйте инструкциям для создания бота
4. Сохраните полученный токен

### 2. Получение Chat ID

1. Отправьте `/start` боту [@userinfobot](https://t.me/userinfobot)
2. Получите ваш Chat ID

### 3. Установка переменных окружения

```bash
# Windows
set TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrSTUvwxyz
set TELEGRAM_CHAT_ID=12345678

# Linux/Mac
export TELEGRAM_BOT_TOKEN="123456789:ABCdefGHIjklMNOpqrSTUvwxyz"
export TELEGRAM_CHAT_ID="12345678"
```

## 🎯 Использование

### Разовый отчет
```bash
python system_stats_reporter.py
```

### Тестовый отчет
```bash
python schedule_reports.py --test
```

### Автоматические отчеты
```bash
# Запуск планировщика (каждые 6 часов)
python schedule_reports.py
```

## 📊 Пример отчета

```
🤖 RSS News System Report
📅 2025-09-21 22:46

📡 FEEDS
• Active: 118/118
• Healthy (24h): 118

📰 ARTICLES
• Total: 12,033
• Recent (24h): 189

🧩 CHUNKS
• Total: 152,031
• Recent (24h): 179
• Avg per article: 13.53

🧠 EMBEDDINGS
• Completed: 120
• Pending: 151,911
• Completion: 0.08%
• Dimensions: 3072

⚙️ SERVICES
• Manager: 🔴
• LLM: 🟢

🤖 AI INSIGHTS
System health analysis with recommendations...
```

## 🔧 Настройка расписания

Отредактируйте `schedule_reports.py`:

```python
# Каждые 6 часов (по умолчанию)
schedule.every(6).hours.do(lambda: asyncio.run(self.send_scheduled_report()))

# Ежедневно в 9:00
schedule.every().day.at("09:00").do(lambda: asyncio.run(self.send_scheduled_report()))

# Каждые 12 часов
schedule.every(12).hours.do(lambda: asyncio.run(self.send_scheduled_report()))
```

## 🐛 Устранение неполадок

### Отчет не отправляется
- Проверьте токен бота и Chat ID
- Убедитесь, что бот не заблокирован

### Сообщения обрезаются
- Система автоматически разбивает длинные сообщения
- Максимум 4000 символов на сообщение

### LLM анализ недоступен
- Проверьте, запущен ли Ollama
- Убедитесь, что модель qwen2.5-coder:3b загружена

## 🔒 Безопасность

- **Никогда не коммитьте токены** в git
- Используйте переменные окружения
- Ограничьте доступ к Chat ID

## 🚀 Автоматизация

### Windows Task Scheduler
1. Откройте Task Scheduler
2. Create Basic Task
3. Trigger: Daily или с нужной периодичностью
4. Action: Start a program
5. Program: `python`
6. Arguments: `D:\path\to\rssnews\schedule_reports.py`

### Linux Cron
```bash
# Каждые 6 часов
0 */6 * * * cd /path/to/rssnews && python schedule_reports.py --test

# Ежедневно в 9:00
0 9 * * * cd /path/to/rssnews && python system_stats_reporter.py
```

## 📈 Расширение функциональности

Систему можно легко расширить:

- 📊 Добавить графики и диаграммы
- 🔔 Настроить алерты при ошибках
- 📧 Добавить email уведомления
- 🌐 Создать веб-дашборд
- 📱 Поддержка других мессенджеров

## 💡 Советы

1. **Тестируйте регулярно**: запускайте `--test` для проверки
2. **Мониторьте размер**: большие базы могут генерировать длинные отчеты
3. **Настройте время**: избегайте отправки в неподходящее время
4. **Проверяйте логи**: следите за ошибками в консоли

---

🎉 **Готово!** Ваша RSS News система теперь будет автоматически отправлять отчеты в Telegram!