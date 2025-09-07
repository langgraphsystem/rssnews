# RSS News Pipeline (PostgreSQL)

Система сбора новостей по RSS, извлечения контента из HTML и дедупликации по URL/тексту с сохранением в PostgreSQL. Подходит для последующей аналитики (RAG/LLM), мониторинга и построения витрин.

## Требования
- Python 3.11+
- PostgreSQL 13+ (доступ по DSN)
- Сетевая доступность источников новостей

## Быстрый старт

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

# Укажите строку подключения к PostgreSQL (пример)
export PG_DSN="postgresql://user:pass@localhost:5432/rssnews"

python main.py ensure
python main.py discovery --feed "https://feeds.bbci.co.uk/news/rss.xml" --feed "https://www.reuters.com/rssFeed/worldNews"
python main.py poll
python main.py work --worker-id my-worker
```

Для PowerShell:
```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:PG_DSN = "postgresql://user:pass@localhost:5432/rssnews"
python main.py ensure
```

Логи пишутся в `logs/rssnews.log` (каталог создаётся автоматически).

## Команды CLI
- `python main.py ensure` — создать/проверить схему БД.
- `python main.py discovery --feed <url> [--lang en --category news]` — добавить RSS‑ленты (EN по умолчанию).
- `python main.py poll [--limit N --batch-size 10 --workers 10]` — опрос активных фидов с поддержкой ETag/Last‑Modified, первичная запись статей в `raw(status=pending)`.
- `python main.py work [--batch-size 50 --workers 10 --worker-id id]` — загрузка HTML, извлечение текста/метаданных, дедуп по тексту, статусы `stored/partial/duplicate/error`.
- `python main.py flush-queue [--limit 10]` — обработка очереди повторных HTTP‑запросов (устаревший алиас `--max-retries` поддерживается и трактуется как `--limit`).
- `python main.py stats [--detailed]` — сводная статистика по системе.

## Конфигурация
- `PG_DSN` (обязательно): строка подключения к PostgreSQL, например `postgresql://user:pass@host:5432/dbname`.
- Логи: файл `logs/rssnews.log` + вывод в консоль.
- Параметры производительности управляются флагами CLI (`--batch-size`, `--workers`).

## Архитектура и поток данных
1) `discovery` — регистрация фидов (приоритет EN, фильтрация по свежести записей).
2) `poll` — опрос фидов, парсинг RSS, запись новых статей в `raw` как `pending` (анти‑дубли по URL‑хэшу: SHA‑256 от канонического URL).
3) `work` — HTTP загрузка HTML, извлечение контента/метаданных, нормализация, дедуп по `text_hash`, обновление статуса и индекса.
4) Диагностика — логирование и данные в таблице `diagnostics`.

## Модель данных (PostgreSQL)
- `feeds` — источники RSS: URL, язык/категория, ETag/Last‑Modified, даты активности, статус.
- `raw` — статьи: оригинальные и канонические URL, `url_hash` (SHA‑256 от канонизированного URL, см. `utils/url.py`), метаданные, `full_text`, `text_hash`, показатели качества, `status` и причины ошибок.
- `articles_index` — кросс‑временной индекс по `url_hash`/`text_hash` для дедупликации.
- `diagnostics`, `config` — служебные таблицы.

Примечание: очередь ретраев HTTP хранится в `storage/queue/retry_queue.json`. Для многопроцессной эксплуатации рекомендуем вынести её в Redis/БД.

## Отладка и типовые проблемы
- Подключение к БД: проверьте `PG_DSN`, доступность хоста/порта и права пользователя.
- 429/5xx от источников: элементы попадают в очередь ретраев, смотрите `flush-queue` и логи.
- Много `partial/error`: возможны JS/paywall‑страницы или жесткие анти‑бот фильтры; усилите экстракторы при необходимости.
- Дубликаты: проверяйте нормализацию URL и тексты (см. `utils/url.py`, `utils/text.py`).

## Документация и материалы
- Детальная проектная документация: `docs/PROJECT_DOCUMENTATION.md`.
- Продакшн‑архитектура (PostgreSQL, диагностика, чанкинг): `docs/PRODUCTION_ARCHITECTURE.md`.

## Project Scope & Goals
- End-to-end RSS ingestion → normalized articles for RAG
- Deterministic URL/text dedup and consistent canonicalization
- Bounded latency and error rates with retries/backoff
- Pre‑RAG interfaces for chunks and embeddings
- Подробнее: `docs/GOALS_AND_SCOPE.md`

## Config & .env
- Пример окружения: `.env.example`
- Полная справка по переменным: `docs/CONFIG_REFERENCE.md`

## Data Contracts (pre‑RAG)
- Основные таблицы и индексы: `docs/DATA_CONTRACTS.md`

### URL hash convention
- We compute `url_hash_v2 = sha256(canonical_url)`.
- Canonicalization rules live in `utils/url.py::canonicalize_url()`.
- All producers/consumers must use the same function to avoid duplicate drift.
- During migration we match duplicates by `url_hash_v2 OR url_hash`. After backfill completes,
  new inserts and lookups must use `url_hash_v2` only.

### Flush retry queue
`rssnews flush-queue --limit 100`
*(the old flag `--max-retries` remains as alias for compatibility)*

## Legacy (Google Sheets)
Ранний вариант проекта использовал Google Sheets как хранилище. Он устарел и не используется в текущей версии. Если требуется совместимость или миграция, смотрите архивные материалы в репозитории и проектную документацию.
