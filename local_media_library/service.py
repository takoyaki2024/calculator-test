from __future__ import annotations

import time
from pathlib import Path
from contextlib import closing

from .database import Database
from .models import SourceFolder
from .scanner import SOURCE_MODES, ScanResult, Scanner


class LibraryService:
    def __init__(self, database: Database, scanner: Scanner | None = None,
                 managed_directory: Path | None = None):
        self.database = database
        self.managed_directory = managed_directory.resolve() if managed_directory is not None else None
        self.scanner = scanner or Scanner((self.managed_directory,) if self.managed_directory else ())
        self.revision = 0

    def add_source(self, path: Path, mode: str = "auto") -> SourceFolder:
        if mode not in SOURCE_MODES:
            raise ValueError(mode)
        selected = Path(path).expanduser()
        if selected.is_symlink():
            raise ValueError("シンボリックリンクではなく実フォルダを選択してください")
        resolved = selected.resolve(strict=True)
        if self.managed_directory and (resolved == self.managed_directory or self.managed_directory in resolved.parents):
            raise ValueError("管理データのフォルダはメディアとして登録できません")
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
        with closing(self.database.connect()) as connection:
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
                before = connection.total_changes
                for table in ("manga_works", "images", "videos"):
                    connection.execute(f"UPDATE {table} SET available=0 WHERE source_id=? AND available<>0", (source_id,))
                changed = connection.total_changes != before
                if changed:
                    self.database.refresh_video_works(connection, source_id)
            if changed:
                self.revision += 1
            return 0, 0, 0, 1
        self._store(source_id, result)
        return len(result.mangas), len(result.images), len(result.videos), len(result.errors)

    def _store(self, source_id: int, result: ScanResult) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                "UPDATE sources SET available=1,last_scan_ns=?,last_error=? WHERE id=?",
                (time.time_ns(), "\n".join(result.errors), source_id),
            )
            before = connection.total_changes
            video_changed = False
            existing = {}
            seen = {table: set() for table in ("manga_works", "images", "videos", "manga_pages")}
            for table in ("manga_works", "images", "videos"):
                key = "relative_dir" if table == "manga_works" else "relative_path"
                existing[table] = {row[key]: row for row in connection.execute(
                    f"SELECT * FROM {table} WHERE source_id=?", (source_id,))}
            existing["manga_pages"] = {(row["work_id"], row["relative_path"]): row for row in connection.execute(
                "SELECT p.* FROM manga_pages p JOIN manga_works w ON w.id=p.work_id WHERE w.source_id=?", (source_id,))}
            for work in result.mangas:
                seen["manga_works"].add(work.relative_dir)
                old_work = existing["manga_works"].get(work.relative_dir)
                if old_work is not None and (old_work["title"], old_work["page_count"], old_work["mtime_ns"], old_work["available"]) == (work.title, len(work.pages), work.mtime_ns, 1):
                    work_id = old_work["id"]
                else:
                    connection.execute(
                        "INSERT INTO manga_works(source_id,relative_dir,title,page_count,mtime_ns,available) "
                        "VALUES(?,?,?,?,?,1) ON CONFLICT(source_id,relative_dir) DO UPDATE SET "
                        "title=excluded.title,page_count=excluded.page_count,mtime_ns=excluded.mtime_ns,available=1 "
                        "WHERE title<>excluded.title OR page_count<>excluded.page_count OR mtime_ns<>excluded.mtime_ns OR available<>1",
                        (source_id, work.relative_dir, work.title, len(work.pages), work.mtime_ns),
                    )
                    work_id = connection.execute(
                        "SELECT id FROM manga_works WHERE source_id=? AND relative_dir=?",
                        (source_id, work.relative_dir),
                    ).fetchone()[0]
                for index, page in enumerate(work.pages):
                    seen["manga_pages"].add((work_id, page.relative_path))
                    old = existing["manga_pages"].get((work_id, page.relative_path))
                    if old is not None and (old["page_index"], old["size"], old["mtime_ns"], old["available"]) == (index, page.size, page.mtime_ns, 1):
                        continue
                    connection.execute(
                        "INSERT INTO manga_pages(work_id,relative_path,page_index,size,mtime_ns,available) "
                        "VALUES(?,?,?,?,?,1) ON CONFLICT(work_id,relative_path) DO UPDATE SET "
                        "page_index=excluded.page_index,size=excluded.size,mtime_ns=excluded.mtime_ns,available=1 "
                        "WHERE page_index<>excluded.page_index OR size<>excluded.size OR mtime_ns<>excluded.mtime_ns OR available<>1",
                        (work_id, page.relative_path, index, page.size, page.mtime_ns),
                    )
            for table, items in (("images", result.images), ("videos", result.videos)):
                for item in items:
                    seen[table].add(item.relative_path)
                    title = Path(item.relative_path).stem
                    old = existing[table].get(item.relative_path)
                    if old is not None and (old["title"], old["size"], old["mtime_ns"], old["available"]) == (title, item.size, item.mtime_ns, 1):
                        continue
                    connection.execute(
                        f"INSERT INTO {table}(source_id,relative_path,title,size,mtime_ns,available) "
                        "VALUES(?,?,?,?,?,1) ON CONFLICT(source_id,relative_path) DO UPDATE SET "
                        "title=excluded.title,size=excluded.size,mtime_ns=excluded.mtime_ns,available=1 "
                        "WHERE title<>excluded.title OR size<>excluded.size OR mtime_ns<>excluded.mtime_ns OR available<>1",
                        (source_id, item.relative_path, title, item.size, item.mtime_ns),
                    )
                    if table == "videos":
                        connection.execute("UPDATE videos SET relative_dir=? WHERE source_id=? AND relative_path=?",
                                           (Path(item.relative_path).parent.as_posix(), source_id, item.relative_path))
                        video_changed = True
            # Only complete enumeration may transition genuinely unseen records.
            if not result.errors:
                for table, rows in existing.items():
                    missing = [(row["id"],) for key, row in rows.items()
                               if key not in seen[table] and row["available"]]
                    connection.executemany(f"UPDATE {table} SET available=0 WHERE id=?", missing)
                    if table == "videos" and missing:
                        video_changed = True
            changed = connection.total_changes != before
            if video_changed:
                self.database.refresh_video_works(connection, source_id)
        if changed:
            self.revision += 1
