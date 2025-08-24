FEEDS_HEADERS = [
    "feed_url","feed_url_canon","lang","status","last_entry_date","last_crawled",
    "no_updates_days","etag","last_modified","health_score","notes","checked_at"
]

RAW_HEADERS = [
    "row_id","source","feed_url","article_url","article_url_canon","url_hash","text_hash",
    "found_at","fetched_at","published_at","language","title","subtitle","authors",
    "section","tags","article_type","clean_text","clean_text_len","full_text_ref",
    "full_text_len","word_count","out_links","category_guess","status",
    "lock_owner","lock_at","processed_at","retries","error_msg","sources_list","aliases","last_seen_rss"
]

INDEX_HEADERS = [
    "url_hash","text_hash","article_url_canon","row_id_raw",
    "first_seen","last_seen","is_duplicate","reason","language","category_guess","rev_n"
]

DIAG_HEADERS = [
    "ts","feeds_active","feeds_inactive","fetch_200","fetch_304","fetch_4xx","fetch_5xx",
    "new_items","new_articles","duplicates_url","duplicates_text","errors","avg_fetch_ms"
]

CONFIG_HEADERS = ["key","value"]
