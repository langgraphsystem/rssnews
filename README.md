# NewsPipeline (до LLM)

Пайплайн: RSS → Google Sheets → Парсинг статей (full/clean) → Индекс дублей.

## Быстрый старт

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

export GOOGLE_SERVICE_ACCOUNT_JSON=service_account.json
export SPREADSHEET_TITLE="NewsPipeline"
export FULLTEXT_DIR="./storage/articles"
```

```bash
python main.py ensure
python main.py discovery --feed "https://feeds.bbci.co.uk/news/rss.xml" --feed "https://www.reuters.com/rssFeed/worldNews"
python main.py poll
python main.py work --worker-id my-worker
```

## Вкладки в Google Sheets

- **Feeds** — реестр фидов (EN, обновления ≤ 7 дней)
- **Raw** — статьи: метаданные, `clean_text` (обрезан), `full_text_ref`, статусы
- **ArticlesIndex** — ключи `url_hash`, `text_hash` → `row_id_raw`, флаги дублей

## Анти-дубли

- На RSS: по `url_hash` (канонический URL)
- На статье: по `text_hash` (очищенный текст)

## Хранилище полного текста

Полный текст пишется в `FULLTEXT_DIR/YYYY/MM/DD/<url_hash>.txt`, а в Sheets кладётся путь (`full_text_ref`).

## Настройки

См. `config.py`.
