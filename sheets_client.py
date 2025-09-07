import gspread
from google.oauth2.service_account import Credentials

from schema import (
    FEEDS_HEADERS,
    RAW_HEADERS,
    INDEX_HEADERS,
    DIAG_HEADERS,
    CONFIG_HEADERS,
)
from config import SERVICE_ACCOUNT_JSON, SPREADSHEET_ID, SPREADSHEET_TITLE
from utils import now_local_iso

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


class SheetClient:
    def __init__(self):
        creds = Credentials.from_service_account_file(
            SERVICE_ACCOUNT_JSON, scopes=SCOPES
        )
        self.gc = gspread.authorize(creds)
        self.spreadsheet = self._ensure_spreadsheet()
        self._ws = {}

    def _ensure_spreadsheet(self):
        if SPREADSHEET_ID:
            return self.gc.open_by_key(SPREADSHEET_ID)
        try:
            return self.gc.open(SPREADSHEET_TITLE)
        except gspread.SpreadsheetNotFound:
            return self.gc.create(SPREADSHEET_TITLE)

    def ensure_worksheets(self):
        self._ensure_ws_with_headers("Feeds", FEEDS_HEADERS)
        self._ensure_ws_with_headers("Raw", RAW_HEADERS)
        self._ensure_ws_with_headers("ArticlesIndex", INDEX_HEADERS)
        self._ensure_ws_with_headers("Diagnostics", DIAG_HEADERS)
        self._ensure_ws_with_headers("Config", CONFIG_HEADERS)
        self.upsert_config("schema_version", "v1")
        self.upsert_config("created_or_migrated_at", now_local_iso())

    def ws(self, name: str):
        if name in self._ws:
            return self._ws[name]
        try:
            w = self.spreadsheet.worksheet(name)
        except gspread.WorksheetNotFound:
            w = self.spreadsheet.add_worksheet(title=name, rows=1000, cols=50)
        self._ws[name] = w
        return w

    def _ensure_ws_with_headers(self, name, headers):
        ws = self.ws(name)
        values = ws.get_all_values()
        if not values:
            ws.update("A1", [headers])
            ws.freeze(rows=1)
            return
        current = values[0]
        missing = [h for h in headers if h not in current]
        if missing:
            new_header = current + missing
            ws.update("A1", [new_header])

    # Config helpers
    def upsert_config(self, key, value):
        ws = self.ws("Config")
        rows = ws.get_all_values()
        if len(rows) <= 1:
            ws.update("A1", [CONFIG_HEADERS])
            ws.append_row([key, str(value)], value_input_option="RAW")
            return
        for r, row in enumerate(rows[1:], start=2):
            if row and row[0] == key:
                ws.update_cell(r, 2, str(value))
                return
        ws.append_row([key, str(value)], value_input_option="RAW")

    # Feeds upsert
    def upsert_feed(self, feed_row):
        ws = self.ws("Feeds")
        rows = ws.get_all_values()
        header = rows[0] if rows else FEEDS_HEADERS
        if not rows:
            ws.update("A1", [header])
        try:
            i_canon = header.index("feed_url_canon")
        except ValueError:
            raise RuntimeError("Feeds header missing feed_url_canon")
        target = None
        for r, row in enumerate(rows[1:], start=2):
            if len(row) > i_canon and row[i_canon] == feed_row.get("feed_url_canon"):
                target = r
                break
        values = [feed_row.get(h, "") for h in header]
        if target:
            ws.update(f"A{target}", [values])
        else:
            ws.append_row(values, value_input_option="RAW")

    # Raw sheet append/update
    def append_raw_minimal(self, data):
        ws = self.ws("Raw")
        header = ws.row_values(1) or RAW_HEADERS
        row = [data.get(h, "") for h in header]
        ws.append_row(row, value_input_option="RAW")
        last_row = len(ws.get_all_values())
        if "row_id" in header:
            ws.update_cell(last_row, header.index("row_id") + 1, str(last_row))
        return last_row

    def update_raw_row(self, row_id: int, patch):
        ws = self.ws("Raw")
        header = ws.row_values(1)
        for k, v in patch.items():
            if k not in header:
                continue
            col = header.index(k) + 1
            ws.update_cell(row_id, col, v)

    # Index helpers
    def find_row_by_url_hash(self, url_hash: str):
        ws = self.ws("ArticlesIndex")
        rows = ws.get_all_values()
        if len(rows) < 2:
            return None
        header = rows[0]
        try:
            i_hash = header.index("url_hash")
            i_row = header.index("row_id_raw")
        except ValueError:
            return None
        for row in rows[1:]:
            if len(row) > i_hash and row[i_hash] == url_hash:
                rid = row[i_row].strip()
                return int(rid) if rid else None
        return None

    def find_row_by_text_hash(self, text_hash: str):
        ws = self.ws("ArticlesIndex")
        rows = ws.get_all_values()
        if len(rows) < 2:
            return None
        header = rows[0]
        try:
            i_hash = header.index("text_hash")
            i_row = header.index("row_id_raw")
        except ValueError:
            return None
        for row in rows[1:]:
            if len(row) > i_hash and row[i_hash] == text_hash:
                rid = row[i_row].strip()
                return int(rid) if rid else None
        return None

    def upsert_index(self, entry):
        ws = self.ws("ArticlesIndex")
        rows = ws.get_all_values()
        header = rows[0] if rows else INDEX_HEADERS
        if not rows:
            ws.update("A1", [header])
        try:
            i_hash = header.index("url_hash")
        except ValueError:
            i_hash = None
        target = None
        if i_hash is not None and entry.get("url_hash"):
            for r, row in enumerate(rows[1:], start=2):
                if len(row) > i_hash and row[i_hash] == entry["url_hash"]:
                    target = r
                    break
        values = [entry.get(h, "") for h in header]
        if target:
            ws.update(f"A{target}", [values])
        else:
            ws.append_row(values, value_input_option="RAW")
