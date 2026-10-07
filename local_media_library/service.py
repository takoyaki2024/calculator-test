from __future__ import annotations

import time
from pathlib import Path

from .database import Database
from .models import SourceFolder
from .scanner import SOURCE_MODES, ScanResult, Scanner


class LibraryService:
    def __init__(self, database: Database, scanner: Scanner | None = None):
        self.database = database
        self.scanner = scanner or Scanner()

    def add_source(self, path: Path, mode: str = "auto") -> SourceFolder:
        if mode not in SOURCE_MODES:
            raise ValueError(mode)
        selected = Path(path).expanduser()
        if selected.is_symlink():
            raise ValueError("シンボリックリンクではなく実フォルダを選択してください")
        resolved = selected.resolve(strict=True)
        if not resolved.is_dir():
            raise ValueError("通常のフォルダを選択してください")
        with self.database.transaction() as connection:
            connection.execute(
                "INSERT INTO sources(path, mode, available) VALUES(?,?,1) "
                "ON CONFLICT(path) DO UPDATE SET mode=excluded.mode",
                (str(resolved), mode),
            )
            row = connection.execute("SELECT * FROM sources WHERE path=?", (str(resolved),)).fetchone()
        return SourceFolder(row["id"], resolved, row["mode"], bool(row["available"]))

    def sources(self) -> tuple[SourceFolder, ...]:
        with self.database.connect() as connection:
            rows = connection.execute("SELECT * FROM sources ORDER BY path COLLATE NOCASE").fetchall()
        return tuple(SourceFolder(r["id"], Path(r["path"]), r["mode"], bool(r["available"])) for r in rows)

    def scan_all(self) -> dict[int, tuple[int, int, int, int]]:
        results = {}
        for source in self.sources():
            results[source.id] = self.scan_source(source.id)
        return results

    def scan_source(self, source_id: int) -> tuple[int, int, int, int]:
        source = next((item for item in self.sources() if item.id == source_id), None)
        if source is None:
            raise KeyError(source_id)
        try:
            result = self.scanner.scan(source.path, source.mode)
        except (OSError, ValueError) as exc:
            with self.database.transaction() as connection:
                connection.execute("UPDATE sources SET available=0,last_error=? WHERE id=?", (str(exc), source_id))
                for table in ("manga_works", "images", "videos"):
                    connection.execute(f"UPDATE {table} SET available=0 WHERE source_id=?", (source_id,))
            return 0, 0, 0, 1
        self._store(source_id, result)
        return len(result.mangas), len(result.images), len(result.videos), len(result.errors)

    def _store(self, source_id: int, result: ScanResult) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                "UPDATE sources SET available=1,last_scan_ns=?,last_error=? WHERE id=?",
                (time.time_ns(), "\n".join(result.errors), source_id),
            )
            # A partial enumeration must not make an inaccessible subtree look deleted.
            # Only a complete scan is authoritative for missing-file transitions.
            if not result.errors:
                for table in ("manga_works", "images", "videos"):
                    connection.execute(f"UPDATE {table} SET available=0 WHERE source_id=?", (source_id,))
                connection.execute(
                    "UPDATE manga_pages SET available=0 WHERE work_id IN "
                    "(SELECT id FROM manga_works WHERE source_id=?)", (source_id,)
                )
            for work in result.mangas:
                connection.execute(
                    "INSERT INTO manga_works(source_id,relative_dir,title,page_count,mtime_ns,available) "
                    "VALUES(?,?,?,?,?,1) ON CONFLICT(source_id,relative_dir) DO UPDATE SET "
                    "title=excluded.title,page_count=excluded.page_count,mtime_ns=excluded.mtime_ns,available=1",
                    (source_id, work.relative_dir, work.title, len(work.pages), work.mtime_ns),
                )
                work_id = connection.execute(
                    "SELECT id FROM manga_works WHERE source_id=? AND relative_dir=?",
                    (source_id, work.relative_dir),
                ).fetchone()[0]
                for index, page in enumerate(work.pages):
                    connection.execute(
                        "INSERT INTO manga_pages(work_id,relative_path,page_index,size,mtime_ns,available) "
                        "VALUES(?,?,?,?,?,1) ON CONFLICT(work_id,relative_path) DO UPDATE SET "
                        "page_index=excluded.page_index,size=excluded.size,mtime_ns=excluded.mtime_ns,available=1",
                        (work_id, page.relative_path, index, page.size, page.mtime_ns),
                    )
            for table, items in (("images", result.images), ("videos", result.videos)):
                for item in items:
                    title = Path(item.relative_path).stem
                    connection.execute(
                        f"INSERT INTO {table}(source_id,relative_path,title,size,mtime_ns,available) "
                        "VALUES(?,?,?,?,?,1) ON CONFLICT(source_id,relative_path) DO UPDATE SET "
                        "title=excluded.title,size=excluded.size,mtime_ns=excluded.mtime_ns,available=1",
                        (source_id, item.relative_path, title, item.size, item.mtime_ns),
                    )
