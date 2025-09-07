# 🧪 Руководство по тестированию миграции

## Быстрая проверка кода

### 1. Проверка синтаксиса и импортов
```bash
# Базовый тест миграции (без БД)
python test_migration.py
```

Этот тест проверяет:
- ✅ Корректность импортов всех модулей
- ✅ Создание PgClient (ошибка без PG_DSN - это нормально)
- ✅ Работу команд main.py --help
- ✅ Совместимость схемы данных
- ✅ Конфигурацию и утилиты

## Полное тестирование с PostgreSQL

### 2. Настройка подключения к Railway PostgreSQL

Получите строку подключения из Railway и установите переменную окружения:

```bash
# Windows (cmd)
set PG_DSN=postgresql://postgres:password@hostname.railway.app:5432/railway?sslmode=require

# Windows (PowerShell)
$env:PG_DSN = "postgresql://postgres:password@hostname.railway.app:5432/railway?sslmode=require"

# Linux/Mac
export PG_DSN="postgresql://postgres:password@hostname.railway.app:5432/railway?sslmode=require"
```

### 3. Тест с реальной базой данных
```bash
python test_with_real_db.py
```

Этот тест выполняет:
- 🔧 Подключение к PostgreSQL
- 🔧 Создание схемы БД (`python main.py ensure`)
- 📡 Добавление тестовых RSS (`python main.py discovery`)
- 📰 Опрос RSS фидов (`python main.py poll`)
- ⚙️ Обработку статей (`python main.py work`)

## Ручное тестирование

### 4. Пошаговый тест команд

```bash
# 1. Создание схемы БД
python main.py ensure
# Ожидается: "OK: worksheets ensured"

# 2. Добавление RSS фида
python main.py discovery --feed "https://feeds.bbci.co.uk/news/rss.xml"
# Ожидается: "OK: discovery finished"

# 3. Опрос RSS (найти новые статьи)
python main.py poll
# Ожидается: "OK: poll finished"

# 4. Обработка статей
python main.py work --worker-id "test-worker"
# Ожидается: "OK: work finished"
```

### 5. Проверка данных в БД

Если у вас есть доступ к PostgreSQL клиенту:

```sql
-- Проверить созданные таблицы
\dt

-- Посмотреть добавленные фиды
SELECT feed_url_canon, status, checked_at FROM feeds;

-- Посмотреть статьи
SELECT article_url_canon, status, title FROM raw LIMIT 10;

-- Проверить конфигурацию
SELECT * FROM config;

-- Проверить диагностику
SELECT ts, level, component, message FROM diagnostics ORDER BY ts DESC LIMIT 10;
```

## Диагностика проблем

### Частые ошибки и решения

**1. ModuleNotFoundError: No module named 'psycopg2'**
```bash
pip install psycopg2-binary
```

**2. ValueError: PG_DSN environment variable is required**
```bash
# Установите переменную окружения PG_DSN
set PG_DSN=postgresql://...
```

**3. psycopg2.OperationalError: connection failed**
- Проверьте строку подключения
- Убедитесь, что PostgreSQL доступен
- Проверьте настройки файрвола

**4. permission denied for table**
- Проверьте права пользователя БД
- Убедитесь, что пользователь может создавать таблицы

## Структура миграции

### Что было изменено:

| Файл | Статус | Изменения |
|------|--------|-----------|
| `pg_client.py` | ✅ НОВЫЙ | Замена `sheets_client.py` |
| `main.py` | ✅ ОБНОВЛЕН | `SheetClient` → `PgClient` |
| `discovery.py` | ✅ ОБНОВЛЕН | Импорт и типы |
| `poller.py` | ✅ ПЕРЕПИСАН | Работа с БД вместо листов |
| `worker.py` | ✅ ПЕРЕПИСАН | Обработка через SQL |
| `schema.py` | ✅ БЕЗ ИЗМЕНЕНИЙ | Совместимость сохранена |
| `config.py` | ✅ БЕЗ ИЗМЕНЕНИЙ | Все настройки актуальны |
| `utils.py` | ✅ БЕЗ ИЗМЕНЕНИЙ | Все функции работают |

### Преимущества миграции:

- 🚀 **Производительность**: Прямые SQL-запросы вместо API
- 🔒 **Надежность**: Нет лимитов API и сетевых зависимостей  
- 📈 **Масштабируемость**: PostgreSQL поддерживает большие объемы
- 🔍 **Аналитика**: Возможность сложных SQL-запросов
- 💰 **Стоимость**: Нет квот Google Sheets API

## Следующие шаги

После успешного тестирования:

1. Сделайте резервную копию текущих данных из Google Sheets
2. Настройте production переменную PG_DSN
3. Запустите миграцию: `python main.py ensure`
4. Импортируйте существующие данные (если нужно)
5. Настройте регулярное выполнение команд poll и work
6. Мониторьте таблицу `diagnostics` на предмет ошибок

## Поддержка

Если возникают проблемы:

1. Запустите `python test_migration.py` для базовой диагностики
2. Проверьте переменную окружения PG_DSN
3. Убедитесь в доступности PostgreSQL БД
4. Проверьте логи в таблице `diagnostics`