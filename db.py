import json
import os
import sqlite3
import threading
from datetime import datetime

DB_PATH = os.getenv("BOT_DB_PATH") or "bot_data.sqlite3"

_conn = None
_lock = threading.Lock()


def _connect():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # Better concurrency for bots with multiple tasks.
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db():
    global _conn
    with _lock:
        if _conn is None:
            _conn = _connect()
        _conn.execute(
            """
            CREATE TABLE IF NOT EXISTS kv (
              k TEXT PRIMARY KEY,
              v TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """
        )
        _conn.commit()


def _ensure():
    if _conn is None:
        init_db()


def _now_iso():
    return datetime.utcnow().isoformat()


def has_key(key: str) -> bool:
    _ensure()
    with _lock:
        row = _conn.execute("SELECT 1 FROM kv WHERE k = ?", (key,)).fetchone()
        return row is not None


def _scoped_key(key: str, scope: str | int) -> str:
    return f"{key}::guild:{scope}"


def has_key_scoped(key: str, scope: str | int) -> bool:
    return has_key(_scoped_key(key, scope))


def get_raw(key: str):
    _ensure()
    with _lock:
        row = _conn.execute("SELECT v FROM kv WHERE k = ?", (key,)).fetchone()
        return row["v"] if row else None


def set_raw(key: str, value: str):
    _ensure()
    with _lock:
        _conn.execute(
            "INSERT INTO kv (k, v, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(k) DO UPDATE SET v = excluded.v, updated_at = excluded.updated_at",
            (key, value, _now_iso()),
        )
        _conn.commit()


def delete_key(key: str):
    _ensure()
    with _lock:
        _conn.execute("DELETE FROM kv WHERE k = ?", (key,))
        _conn.commit()


def migrate_from_file_if_needed(key: str, file_path: str):
    """
    If DB key is missing and a JSON file exists, load it once and store in DB.
    Leaves the file on disk (non-destructive migration).
    """
    if has_key(key):
        return
    if not file_path or not os.path.exists(file_path):
        return
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return
    try:
        set_json(key, data)
    except Exception:
        return


def get_json(key: str, default, migrate_file: str | None = None):
    """
    Read JSON value from DB.
    - `default` defines the expected type (dict/list/etc).
    - If missing, returns `default`.
    - If `migrate_file` is set, will auto-migrate from that JSON file into DB on first read.
    """
    if migrate_file:
        migrate_from_file_if_needed(key, migrate_file)

    raw = get_raw(key)
    if raw is None:
        return default
    try:
        value = json.loads(raw)
    except Exception:
        return default
    if not isinstance(value, type(default)):
        return default
    return value


def get_json_scoped(key: str, scope: str | int, default, migrate_file: str | None = None):
    """
    Read JSON value from DB scoped to a guild/server.
    Falls back to global key (optionally migrated from file) if scoped key missing
    and the global value is a dict that contains this guild id.
    """
    scoped = _scoped_key(key, scope)
    raw = get_raw(scoped)
    if raw is not None:
        try:
            value = json.loads(raw)
            return value if isinstance(value, type(default)) else default
        except Exception:
            return default

    # Fallback to global value for one-time migration.
    global_val = get_json(key, default, migrate_file=migrate_file)
    if isinstance(global_val, dict):
        v = global_val.get(str(scope))
        if v is not None:
            set_json(scoped, v)
            return v
    return default


def set_json_scoped(key: str, scope: str | int, value):
    set_json(_scoped_key(key, scope), value)


def set_json(key: str, value):
    set_raw(key, json.dumps(value, ensure_ascii=False))


def stats():
    """Return basic DB health info for diagnostics."""
    _ensure()
    with _lock:
        row = _conn.execute(
            "SELECT COUNT(*) AS cnt, MAX(updated_at) AS last_updated FROM kv"
        ).fetchone()
        cnt = int(row["cnt"]) if row and row["cnt"] is not None else 0
        last_updated = row["last_updated"] if row else None

    exists = os.path.exists(DB_PATH)
    size_bytes = os.path.getsize(DB_PATH) if exists else 0
    return {
        "path": DB_PATH,
        "exists": exists,
        "size_bytes": size_bytes,
        "keys": cnt,
        "last_updated": last_updated,
    }
