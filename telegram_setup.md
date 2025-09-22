# Telegram Bot Setup

## 1. Создание бота

1. Отправьте `/start` боту [@BotFather](https://t.me/BotFather)
2. Выполните команду `/newbot`
3. Введите имя бота (например: RSS News Reporter)
4. Введите username бота (например: @rssnews_reporter_bot)
5. Получите токен бота (например: `123456789:ABCdefGHIjklMNOpqrSTUvwxyz`)

## 2. Получение Chat ID

Есть несколько способов:

### Способ 1: Через @userinfobot
1. Перейдите к [@userinfobot](https://t.me/userinfobot)
2. Отправьте `/start`
3. Получите ваш Chat ID

### Способ 2: Через API
1. Отправьте любое сообщение вашему боту
2. Перейдите в браузере: `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
3. Найдите `"chat":{"id":12345678}` - это ваш Chat ID

## 3. Настройка переменных окружения

```bash
# Windows
set TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrSTUvwxyz
set TELEGRAM_CHAT_ID=12345678

# Linux/Mac
export TELEGRAM_BOT_TOKEN="123456789:ABCdefGHIjklMNOpqrSTUvwxyz"
export TELEGRAM_CHAT_ID="12345678"
```

## 4. Тестирование

Запустите:
```bash
python system_stats_reporter.py
```

Если настройки корректны, отчет будет отправлен в Telegram.

## 5. Автоматизация

Добавьте в cron (Linux/Mac) или Task Scheduler (Windows):
```bash
# Отправка отчета каждые 6 часов
0 */6 * * * cd /path/to/rssnews && python system_stats_reporter.py
```

## Примечания

- Токен бота держите в секрете
- Chat ID можно получить для группы, если хотите отправлять в групповой чат
- Бот должен быть добавлен в группу с правами отправки сообщений