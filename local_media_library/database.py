from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from .natural import natural_key

APPLICATION_ID = 0x4C4D4C31
SCHEMA_VERSION = 3

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
 relative_dir TEXT NOT NULL DEFAULT '.',
 UNIQUE(source_id, relative_path)
);
CREATE TABLE IF NOT EXISTS video_works(
 id INTEGER PRIMARY KEY, source_id INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
 relative_dir TEXT NOT NULL, title TEXT NOT NULL, file_count INTEGER NOT NULL,
 mtime_ns INTEGER NOT NULL, cover_video_id INTEGER REFERENCES videos(id),
 UNIQUE(source_id, relative_dir)
);
CREATE INDEX IF NOT EXISTS manga_available ON manga_works(available);
CREATE INDEX IF NOT EXISTS image_available ON images(available);
CREATE INDEX IF NOT EXISTS video_available ON videos(available);
"""

QUERY_INDEXES = """
CREATE INDEX IF NOT EXISTS manga_cover ON manga_pages(work_id,available,page_index);
CREATE INDEX IF NOT EXISTS manga_newest ON manga_works(available,mtime_ns,title COLLATE CASEFOLD,id);
CREATE INDEX IF NOT EXISTS manga_title ON manga_works(available,title COLLATE CASEFOLD,id);
CREATE INDEX IF NOT EXISTS image_newest ON images(available,mtime_ns,title COLLATE CASEFOLD,id);
CREATE INDEX IF NOT EXISTS image_title ON images(available,title COLLATE CASEFOLD,id);
CREATE INDEX IF NOT EXISTS video_folder ON videos(source_id,relative_dir,available);
CREATE INDEX IF NOT EXISTS video_newest ON videos(available,mtime_ns,title COLLATE CASEFOLD,id);
CREATE INDEX IF NOT EXISTS video_title ON videos(available,title COLLATE CASEFOLD,id);
CREATE INDEX IF NOT EXISTS video_work_newest ON video_works(mtime_ns,title COLLATE CASEFOLD,id);
CREATE INDEX IF NOT EXISTS video_work_title ON video_works(title COLLATE CASEFOLD,id);
"""


def _compare(a, b):
    return (a > b) - (a < b)


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
        connection.create_collation("CASEFOLD", lambda a, b: _compare(a.casefold(), b.casefold()))
        connection.create_collation("NATURAL_ORDER", lambda a, b: _compare(natural_key(a), natural_key(b)))
        connection.create_function("contains_title", 2, lambda title, query: query.casefold() in title.casefold(), deterministic=True)
        connection.create_function("parent_dir", 1, lambda path: Path(path).parent.as_posix(), deterministic=True)
        connection.create_function("work_title", 2, lambda root, directory: (Path(root) / directory).name or str(Path(root) / directory), deterministic=True)
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
                video_columns = {r[1] for r in connection.execute("PRAGMA table_info(videos)")}
                if video_columns and "relative_dir" not in video_columns:
                    migration += "ALTER TABLE videos ADD COLUMN relative_dir TEXT NOT NULL DEFAULT '.';UPDATE videos SET relative_dir=parent_dir(relative_path);"
                connection.executescript(
                    "BEGIN IMMEDIATE;\n" + SCHEMA +
                    "\n" + migration + QUERY_INDEXES +
                    f"\nPRAGMA application_id={APPLICATION_ID};"
                    f"\nPRAGMA user_version={SCHEMA_VERSION};"
                )
                if version < 3:
                    for source in connection.execute("SELECT id FROM sources").fetchall():
                        self.refresh_video_works(connection, source[0])
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")
        connection.close()

    @staticmethod
    def refresh_video_works(connection, source_id):
        """Rebuild only a changed source, inside the same scan transaction."""
        connection.execute("UPDATE video_works SET file_count=0,cover_video_id=NULL WHERE source_id=?", (source_id,))
        connection.execute(
            "INSERT INTO video_works(source_id,relative_dir,title,file_count,mtime_ns,cover_video_id) "
            "SELECT v.source_id,v.relative_dir,work_title(s.path,v.relative_dir),count(*),max(v.mtime_ns),min(v.id) "
            "FROM videos v JOIN sources s ON s.id=v.source_id WHERE v.source_id=? AND v.available=1 "
            "GROUP BY v.source_id,v.relative_dir "
            "ON CONFLICT(source_id,relative_dir) DO UPDATE SET title=excluded.title,file_count=excluded.file_count,"
            "mtime_ns=excluded.mtime_ns,cover_video_id=excluded.cover_video_id", (source_id,))

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
