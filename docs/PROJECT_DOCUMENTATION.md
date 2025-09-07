# Проектная документация — NewsPipeline (до LLM)

## 1. Назначение и цели
**NewsPipeline** — система автоматизированного сбора англоязычных новостей через RSS, парсинга статей и сохранения структурированных данных в Google Sheets.
**Цели:**
- Автоматически находить и регистрировать актуальные RSS (EN, обновлялись за последние 7 дней).
- Регулярно опрашивать активные фиды с учётом ETag/Last-Modified.
- Исключать дубликаты (по `url_hash` и `text_hash`) и не записывать повторно.
- Для каждой статьи извлекать **полный текст** (full_text) и **очищенный текст** (clean_text), а также метаданные.
- Подготовить данные к последующей LLM-аналитике (краткие смысловые выжимки, ключевые слова и т. п.).

## 2. Область применения
- Редакции, аналитики, маркетинг, риск- и бренд-мониторинг.
- Ранжирование и отбор новостей по рубрикам (politics/sports/other) до LLM.
- Подготовка датасетов для обучения/оценки downstream-моделей.

## 3. Пользовательские сценарии (Use cases)
1) **Администратор** настраивает сервис-аккаунт, создаёт Google Sheets и добавляет RSS-ленты.
2) **Сервис** по расписанию выполняет discovery/poll/work и пополняет таблицу свежими статьями.
3) **Аналитик** просматривает лист Raw, фильтрует/экспортирует данные.
4) (Фаза 2) **LLM-воркер** обрабатывает `stored`-записи, пишет результат в отдельный лист `Analyses`.

## 4. Нефункциональные требования
- **Надёжность:** идемпотентность, статусы и блокировки (locks) на уровне строк.
- **Масштабируемость:** параллельные воркеры, лимиты на батчи и частоту.
- **Производительность:** ограничение количества элементов с каждого фида, агрессивное дедуплирование.
- **Наблюдаемость:** лист `Diagnostics` (метрики) + логи, подсчёты дублей, ошибок.
- **Безопасность:** сервис-аккаунт, минимум прав; full_text хранится локально/в облаке.
- **Удобство:** все вставки в Sheets — append в конец; точечные обновления по `row_id`.

## 5. Архитектура (высокий уровень)
**Слои:**
- **Discovery** — добавление RSS в лист `Feeds` (EN + свежесть ≤ 7 дней).
- **Poller** — опрос активных RSS, создание записей в `Raw` со `status=pending` (анти-дубли по URL).
- **Worker (Parser)** — загрузка HTML, извлечение текстов и мета, рубрикация, запись в `Raw` и `ArticlesIndex`.
- **Index/Dedup** — лист `ArticlesIndex` для поиска дублей по `url_hash`/`text_hash`.
- **Storage** — Google Sheets + файловое хранилище `full_text_ref` (полный текст).
- **Scheduler** — cron/systemd.
- **Monitoring** — лист `Diagnostics`, логи.

## 6. Компоненты и файлы
- `main.py` — CLI/оркестр (ensure/discovery/poll/work).
- `discovery.py` — добавление RSS: EN + свежесть; upsert в `Feeds`.
- `poller.py` — опрос RSS: ETag/Last-Modified, складывание новых элементов в `Raw (pending)`.
- `worker.py` — парсинг HTML, извлечение full/clean, метаданные, рубрикация, запись в `Raw`, upsert в `ArticlesIndex`.
- `sheets_client.py` — создание книги и листов, операции append/update/upsert, поиск в индексе.
- `utils.py` — канонизация URL, хэши, даты, JSON, сохранение `full_text`.
- `schema.py` — заголовки листов.
- `config.py` — настройки окружения.
- `requirements.txt` — зависимости.

## 7. Схемы данных (Google Sheets)
### 7.1 Листы
- **Feeds** — реестр RSS.
- **Raw** — статьи (1 строка = 1 основная статья).
- **ArticlesIndex** — быстрый поиск по ключам.
- **Diagnostics** — агрегаты/счётчики (опционально).
- **Config** — схема/метаданные/курсоры.

### 7.2 Поля
**Feeds:** `feed_url, feed_url_canon, lang, status, last_entry_date, last_crawled, no_updates_days, etag, last_modified, health_score, notes, checked_at`

**Raw:**  
`row_id, source, feed_url, article_url, article_url_canon, url_hash, text_hash, found_at, fetched_at, published_at, language, title, subtitle, authors, section, tags, article_type, clean_text, clean_text_len, full_text_ref, full_text_len, word_count, out_links, category_guess, status, lock_owner, lock_at, processed_at, retries, error_msg, sources_list, aliases, last_seen_rss`

**ArticlesIndex:**  
`url_hash, text_hash, article_url_canon, row_id_raw, first_seen, last_seen, is_duplicate, reason, language, category_guess, rev_n`

### 7.3 Статусы `Raw.status`
- `pending` → ожидает парсинга.
- `processing` → строка залочена воркером.
- `stored` → спарсено и записано.
- `duplicate` → дубль по URL или по тексту.
- `error` → ошибка сети/парсинга.
- `skipped` → отброшено политикой/лимитами.

## 8. Рабочие потоки (workflow)
### 8.1 Discovery
1. Канонизация введённого RSS-URL.
2. Загрузка и парсинг фида.
3. Проверка свежести (≤7 дней) и языка (EN).
4. Upsert в `Feeds(status=active)`.

### 8.2 Poll
1. GET с `If-None-Match`/`If-Modified-Since`.
2. Для каждого элемента: выбрать лучший `link`, канонизировать в `article_url_canon`.
3. Посчитать `url_hash` и проверить в `ArticlesIndex`.
4. Если новый — добавить строку в `Raw` (`status=pending`), иначе обновить RSS-поля у существующей.

### 8.3 Worker
1. Взять `pending` без `lock_owner`, проставить `processing/lock_*`.
2. Скачать HTML, учесть редирект `final_url` и обновить `article_url_canon/url_hash`.
3. Извлечь `full_text` (в файл, путь → `full_text_ref`) и `clean_text` (в Sheets, обрезка по лимиту).
4. Посчитать `text_hash` и сверить на дубликаты.
5. Извлечь метаданные: `title, published_at, authors, section, tags, language, out_links`.
6. Эвристическая рубрикация: `article_type`, `category_guess`.
7. Обновить строку в `Raw` (`stored`) и upsert в `ArticlesIndex`.

## 9. Анти-дубли
- **По URL**: `url_hash` (канонический URL). Если найден — не создаём новую строку.
- **По тексту**: `text_hash` (очищенный текст). Если найден другой `row_id_raw` — помечаем `duplicate`, в основной добавляем `aliases`.
- **Версионирование** (опционально): новый `text_hash` при том же `url_hash` → инкремент `rev_n` и хранение дельт.

## 10. Конфигурация
Переменные окружения и параметры в `config.py`:
- `SPREADSHEET_ID` или `SPREADSHEET_TITLE`
- `GOOGLE_SERVICE_ACCOUNT_JSON`
- `FULLTEXT_DIR`
- `FRESH_DAYS_LIMIT` (по умолчанию 7)
- `MAX_ITEMS_PER_FEED_PER_POLL` (например, 20)
- `PENDING_BATCH_SIZE` (например, 100)
- `CLEAN_TEXT_SHEETS_LIMIT` (например, 20000)

## 11. Установка и запуск
```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

export GOOGLE_SERVICE_ACCOUNT_JSON=service_account.json
export SPREADSHEET_TITLE="NewsPipeline"
export FULLTEXT_DIR="./storage/articles"

python main.py ensure
python main.py discovery --feed "https://feeds.bbci.co.uk/news/rss.xml" --feed "https://www.reuters.com/rssFeed/worldNews"
python main.py poll
python main.py work --worker-id my-worker
```

## 12. Эксплуатация (Runbook)
**Рекомендуемое расписание (cron):**
- `discovery` — 1× в день утром.
- `poll` — каждые 3–6 часов.
- `work` — каждые 2–5 минут (небольшими батчами).

**Типовые сбои и решения:**
- Много `error` → проверить таймауты, User-Agent, блокировки сайтов, квоты Sheets.
- Много `duplicate` → проверить канонизацию URL и нормализацию текста.
- Пустой `full_text` → сайты на JS/paywall; возможны доработки (рендеринг, иные экстракторы).

## 13. Тестирование
**Функциональные тесты:**
- Добавление EN-фида со свежими записями → строка в `Feeds(active)`.
- `poll` без новостей → отсутствуют новые строки в `Raw`, фиксируется 304.
- `work` по `pending` → статус `stored`, заполнены поля.
- Повторный `poll/work` одной и той же новости → нет дублей.

**Краевые случаи:**
- Редирект меняет `article_url_canon`.
- Два URL с одинаковым контентом → дубль по `text_hash`.
- Нет даты публикации → сохраняется пусто или из RSS.

**Нагрузочные:** 1k–5k статей/день, оценка времени на статью и пропускной способности Sheets.

## 14. Ограничения и риски
- Нет автоматической проверки `robots.txt`.
- JS-heavy сайты и paywalls могут ухудшать извлечение текста.
- Возможны редкие ложные совпадения `text_hash`.
- Квоты/лимиты Google Sheets (скорость записи, размер ячеек).

## 15. Дорожная карта
- Лист `Analyses`: LLM-краткие выжимки, тональность, ключевые слова, тематика/топики.
- Сигналы популярности: внешние ссылки, репосты, упоминания брендов.
- Near-duplicate кластеризация (shingling/MinHash).
- Миграция из Sheets в БД (Postgres/BigQuery), дельта-экспорт.
- Архивация full_text и политики ретеншна.
- Оповещения/вебхуки (триггеры).

## 16. Интерфейсы (CLI)
- `python main.py ensure`
- `python main.py discovery --feed "<rss1>" --feed "<rss2>"`
- `python main.py poll`
- `python main.py work --worker-id my-worker`

## 17. Словарь терминов
- **article_url_canon** — канонизированный URL статьи.
- **url_hash** — SHA-256 от `article_url_canon`.
- **text_hash** — SHA-256 от нормализованного `clean_text`.
- **full_text_ref** — путь/ключ к полному тексту (файл/облако).
- **category_guess** — простая рубрика (politics/sports/other).

---

© NewsPipeline Docs
