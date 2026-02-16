import threading
from datetime import datetime

import psycopg2
import psycopg2.extras as extras

# Neon PostgreSQL connection (as requested).
DB_URL = "postgresql://neondb_owner:npg_xig0brACE6hc@ep-lucky-sound-aixg6u42-pooler.c-4.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"

_conn = None
_lock = threading.Lock()


def _connect():
    return psycopg2.connect(DB_URL)


def init_db():
    global _conn
    with _lock:
        if _conn is None or _conn.closed:
            _conn = _connect()
        cur = _conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
              k TEXT NOT NULL,
              guild_id BIGINT NULL,
              v JSONB NOT NULL,
              updated_at TIMESTAMPTZ NOT NULL,
              PRIMARY KEY (k, guild_id)
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS settings_updated_at_idx ON settings (updated_at)")
        cur.execute("CREATE INDEX IF NOT EXISTS settings_guild_idx ON settings (guild_id)")
        _conn.commit()
        cur.close()


def _ensure():
    if _conn is None or _conn.closed:
        init_db()


def _now():
    return datetime.utcnow()


def has_setting(k: str, guild_id: int | None = None) -> bool:
    _ensure()
    with _lock:
        cur = _conn.cursor()
        if guild_id is None:
            cur.execute("SELECT 1 FROM settings WHERE k = %s AND guild_id IS NULL", (k,))
        else:
            cur.execute("SELECT 1 FROM settings WHERE k = %s AND guild_id = %s", (k, guild_id))
        row = cur.fetchone()
        cur.close()
        return row is not None


def get_setting(k: str, guild_id: int | None, default):
    _ensure()
    with _lock:
        cur = _conn.cursor()
        if guild_id is None:
            cur.execute("SELECT v FROM settings WHERE k = %s AND guild_id IS NULL", (k,))
        else:
            cur.execute("SELECT v FROM settings WHERE k = %s AND guild_id = %s", (k, guild_id))
        row = cur.fetchone()
        cur.close()
        return row[0] if row else default


def set_setting(k: str, guild_id: int | None, value):
    _ensure()
    with _lock:
        cur = _conn.cursor()
        if guild_id is None:
            cur.execute(
                """
                INSERT INTO settings (k, guild_id, v, updated_at)
                VALUES (%s, NULL, %s, %s)
                ON CONFLICT (k, guild_id)
                DO UPDATE SET v = EXCLUDED.v, updated_at = EXCLUDED.updated_at
                """,
                (k, extras.Json(value), _now()),
            )
        else:
            cur.execute(
                """
                INSERT INTO settings (k, guild_id, v, updated_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (k, guild_id)
                DO UPDATE SET v = EXCLUDED.v, updated_at = EXCLUDED.updated_at
                """,
                (k, guild_id, extras.Json(value), _now()),
            )
        _conn.commit()
        cur.close()


def delete_setting(k: str, guild_id: int | None = None):
    _ensure()
    with _lock:
        cur = _conn.cursor()
        if guild_id is None:
            cur.execute("DELETE FROM settings WHERE k = %s AND guild_id IS NULL", (k,))
        else:
            cur.execute("DELETE FROM settings WHERE k = %s AND guild_id = %s", (k, guild_id))
        _conn.commit()
        cur.close()


def stats():
    _ensure()
    with _lock:
        cur = _conn.cursor()
        cur.execute("SELECT COUNT(*) FROM settings")
        count = cur.fetchone()[0]
        cur.close()
    return {
        "path": "postgres",
        "size_bytes": 0,
        "keys": count,
        "updated_at": _now().isoformat()
    }
