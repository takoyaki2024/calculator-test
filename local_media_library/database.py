from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

APPLICATION_ID = 0x4C4D4C31
SCHEMA_VERSION = 2

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources(
 id INTEGER PRIMARY KEY, path TEXT NOT NULL UNIQUE, mode TEXT NOT NULL,
 available INTEGER NOT NULL DEFAULT 0, last_scan_ns INTEGER,
 last_error TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS manga_works(
 id INTEGER PRIMARY KEY, source_id INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
 relative_dir TEXT NOT NULL, title TEXT NOT NULL, page_count INTEGER NOT NULL,
 mtime_ns INTEGER NOT NULL, available INTEGER NOT NULL DEFAULT 1,
 favorite INTEGER NOT NULL DEFAULT 0, last_page INTEGER NOT NULL DEFAULT 0,
 UNIQUE(source_id, relative_dir)
);
CREATE TABLE IF NOT EXISTS manga_pages(
 id INTEGER PRIMARY KEY, work_id INTEGER NOT NULL REFERENCES manga_works(id) ON DELETE CASCADE,
 relative_path TEXT NOT NULL, page_index INTEGER NOT NULL, size INTEGER NOT NULL,
 mtime_ns INTEGER NOT NULL, available INTEGER NOT NULL DEFAULT 1,
 UNIQUE(work_id, relative_path)
);
CREATE TABLE IF NOT EXISTS images(
 id INTEGER PRIMARY KEY, source_id INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
 relative_path TEXT NOT NULL, title TEXT NOT NULL, size INTEGER NOT NULL,
 mtime_ns INTEGER NOT NULL, available INTEGER NOT NULL DEFAULT 1,
 favorite INTEGER NOT NULL DEFAULT 0, UNIQUE(source_id, relative_path)
);
CREATE TABLE IF NOT EXISTS videos(
 id INTEGER PRIMARY KEY, source_id INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
 relative_path TEXT NOT NULL, title TEXT NOT NULL, size INTEGER NOT NULL,
 mtime_ns INTEGER NOT NULL, available INTEGER NOT NULL DEFAULT 1,
 position_ms INTEGER NOT NULL DEFAULT 0, favorite INTEGER NOT NULL DEFAULT 0,
 UNIQUE(source_id, relative_path)
);
CREATE INDEX IF NOT EXISTS manga_available ON manga_works(available);
CREATE INDEX IF NOT EXISTS image_available ON images(available);
CREATE INDEX IF NOT EXISTS video_available ON videos(available);
"""


class Database:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=15000")
        return connection

    def _initialize(self) -> None:
        with self.connect() as connection:
            app_id = connection.execute("PRAGMA application_id").fetchone()[0]
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if app_id not in (0, APPLICATION_ID):
                raise RuntimeError("別のアプリのデータベースです")
            if version > SCHEMA_VERSION:
                raise RuntimeError("新しいバージョンのデータベースです")
            try:
                migration = "ALTER TABLE manga_works ADD COLUMN last_page INTEGER NOT NULL DEFAULT 0;" if version == 1 else ""
                connection.executescript(
                    "BEGIN IMMEDIATE;\n" + SCHEMA +
                    "\n" + migration +
                    f"\nPRAGMA application_id={APPLICATION_ID};"
                    f"\nPRAGMA user_version={SCHEMA_VERSION};\nCOMMIT;"
                )
            except Exception:
                connection.rollback()
                raise
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")

    @contextmanager
    def transaction(self):
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
