"""
db_manager.py — SQLite connection handling with WAL mode, foreign keys,
and schema-version migration tracking.

Usage:
    with DBManager(db_path) as db:
        rows = db.execute("SELECT * FROM nodes").fetchall()
"""

import sqlite3
from pathlib import Path
from typing import Any

import config


class DBManager:
    """Context manager wrapping a SQLite connection."""

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path or config.DB_PATH)
        self._conn: sqlite3.Connection | None = None

    # ── Context manager ───────────────────────────────────────────────────────

    def __enter__(self) -> "DBManager":
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row          # access cols by name
        self._configure()
        self._ensure_schema()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._conn:
            if exc_type is None:
                self._conn.commit()
            else:
                self._conn.rollback()
            self._conn.close()
            self._conn = None
        return False                                   # do not suppress exceptions

    # ── Configuration ─────────────────────────────────────────────────────────

    def _configure(self) -> None:
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA synchronous = NORMAL")
        self._conn.execute("PRAGMA cache_size = -16000")   # 16 MB page cache

    def _ensure_schema(self) -> None:
        current_ver = self._conn.execute("PRAGMA user_version").fetchone()[0]
        if current_ver < config.DB_VERSION:
            schema_sql = (Path(__file__).parent / "schema.sql").read_text()
            self._conn.executescript(schema_sql)
            self._conn.execute(f"PRAGMA user_version = {config.DB_VERSION}")
            self._conn.commit()

    # ── Public helpers ────────────────────────────────────────────────────────

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("DBManager used outside of 'with' block")
        return self._conn

    def execute(self, sql: str, params: Any = ()) -> sqlite3.Cursor:
        return self.conn.execute(sql, params)

    def executemany(self, sql: str, params_seq) -> sqlite3.Cursor:
        return self.conn.executemany(sql, params_seq)

    def executescript(self, sql: str) -> None:
        self.conn.executescript(sql)

    def commit(self) -> None:
        self.conn.commit()

    def lastrowid(self, cursor: sqlite3.Cursor) -> int:
        return cursor.lastrowid

    def fetchall(self, sql: str, params: Any = ()) -> list[sqlite3.Row]:
        return self.execute(sql, params).fetchall()

    def fetchone(self, sql: str, params: Any = ()) -> sqlite3.Row | None:
        return self.execute(sql, params).fetchone()
