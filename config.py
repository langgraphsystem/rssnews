import os

# === ОБЩИЕ НАСТРОЙКИ ===
TZ = "America/Chicago"
FRESH_DAYS_LIMIT = 7  # правило 7 дней для активных RSS
MAX_ITEMS_PER_FEED_PER_POLL = 20
PENDING_BATCH_SIZE = 100  # сколько строк за раз воркер лочит и обрабатывает
LOCK_TTL_MINUTES = 30
CLEAN_TEXT_SHEETS_LIMIT = 20000  # символов; безопасный трим для Google Sheets

# === GOOGLE SHEETS ===
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "")
SPREADSHEET_TITLE = os.getenv("SPREADSHEET_TITLE", "NewsPipeline")
SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "service_account.json")

# === ХРАНИЛИЩЕ ПОЛНОГО ТЕКСТА ===
FULLTEXT_DIR = os.getenv("FULLTEXT_DIR", "./storage/articles")  # файлы .txt по url_hash

# === ФИЛЬТРАЦИЯ/КАНОНИЗАЦИЯ ===
TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "gclid",
    "fbclid",
    "mc_cid",
    "mc_eid",
    "yclid",
    "vero_id",
    "rb_clickid",
    "ref",
    "ref_src",
}
REMOVE_PATH_SUFFIXES = {"/amp", "/index.html", "/index.htm"}

# === РУБРИКАЦИЯ (до LLM) ===
POLITICS_KEYS = {
    "government",
    "election",
    "senate",
    "parliament",
    "congress",
    "policy",
    "bill",
    "minister",
    "cabinet",
    "president",
    "presidency",
    "diplomacy",
    "sanctions",
    "ceasefire",
    "regulator",
    "supreme court",
    "white house",
    "kremlin",
    "eu commission",
    "parliamentary",
}
SPORTS_KEYS = {
    "match",
    "game",
    "player",
    "coach",
    "league",
    "cup",
    "tournament",
    "goal",
    "score",
    "transfer",
    "nba",
    "nfl",
    "mlb",
    "nhl",
    "fifa",
    "uefa",
    "olympics",
    "grand slam",
}


def load_config():
    """Load configuration from environment variables and constants"""
    return {
        'tz': TZ,
        'fresh_days_limit': FRESH_DAYS_LIMIT,
        'max_items_per_feed_per_poll': MAX_ITEMS_PER_FEED_PER_POLL,
        'pending_batch_size': PENDING_BATCH_SIZE,
        'lock_ttl_minutes': LOCK_TTL_MINUTES,
        'clean_text_sheets_limit': CLEAN_TEXT_SHEETS_LIMIT,
        'spreadsheet_id': SPREADSHEET_ID,
        'spreadsheet_title': SPREADSHEET_TITLE,
        'service_account_json': SERVICE_ACCOUNT_JSON,
        'fulltext_dir': FULLTEXT_DIR,
        'tracking_params': TRACKING_PARAMS,
        'remove_path_suffixes': REMOVE_PATH_SUFFIXES,
        'politics_keys': POLITICS_KEYS,
        'sports_keys': SPORTS_KEYS,
    }
