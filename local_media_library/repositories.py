from __future__ import annotations

from pathlib import Path

from .database import Database
from .models import ImageItem, MangaPage, MangaWork, VideoItem


class _Repository:
    def __init__(self, database: Database):
        self.database = database

    @staticmethod
    def _matches(title: str, query: str) -> bool:
        return query.casefold() in title.casefold()


class MangaRepository(_Repository):
    def list(self, query: str = "", include_missing: bool = False) -> tuple[MangaWork, ...]:
        sql = ("SELECT w.*,s.path root,(SELECT p.relative_path FROM manga_pages p "
               "WHERE p.work_id=w.id AND p.available=1 ORDER BY p.page_index LIMIT 1) cover "
               "FROM manga_works w JOIN sources s ON s.id=w.source_id")
        if not include_missing:
            sql += " WHERE w.available=1"
        with self.database.connect() as connection:
            rows = connection.execute(sql).fetchall()
        items = []
        for row in rows:
            cover_path = Path(row["root"]) / row["cover"] if row["cover"] else None
            item = MangaWork(row["id"], row["source_id"], row["relative_dir"], row["title"],
                             row["page_count"], cover_path, bool(row["available"]), row["mtime_ns"],
                             bool(row["favorite"]), row["last_page"])
            if self._matches(item.title, query):
                items.append(item)
        return tuple(items)

    def pages(self, work_id: int) -> tuple[MangaPage, ...]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT p.*,s.path root FROM manga_pages p JOIN manga_works w ON w.id=p.work_id "
                "JOIN sources s ON s.id=w.source_id WHERE p.work_id=? AND p.available=1 ORDER BY p.page_index",
                (work_id,),
            ).fetchall()
        return tuple(MangaPage(r["id"], work_id, r["relative_path"], Path(r["root"]) / r["relative_path"],
                               r["page_index"], bool(r["available"])) for r in rows)

    def save_position(self, work_id: int, page_index: int) -> None:
        with self.database.transaction() as connection:
            cursor = connection.execute(
                "UPDATE manga_works SET last_page=? WHERE id=?", (max(0, page_index), work_id)
            )
            if cursor.rowcount != 1:
                raise KeyError(work_id)


class ImageRepository(_Repository):
    def list(self, query: str = "", include_missing: bool = False) -> tuple[ImageItem, ...]:
        sql = "SELECT i.*,s.path root FROM images i JOIN sources s ON s.id=i.source_id"
        if not include_missing:
            sql += " WHERE i.available=1"
        with self.database.connect() as connection:
            rows = connection.execute(sql).fetchall()
        items = [ImageItem(r["id"], r["source_id"], r["relative_path"], Path(r["root"]) / r["relative_path"],
                           r["title"], bool(r["available"]), r["size"], r["mtime_ns"], bool(r["favorite"])) for r in rows]
        return tuple(item for item in items if self._matches(item.title, query))


class VideoRepository(_Repository):
    def list(self, query: str = "", include_missing: bool = False) -> tuple[VideoItem, ...]:
        sql = "SELECT v.*,s.path root FROM videos v JOIN sources s ON s.id=v.source_id"
        if not include_missing:
            sql += " WHERE v.available=1"
        with self.database.connect() as connection:
            rows = connection.execute(sql).fetchall()
        items = [VideoItem(r["id"], r["source_id"], r["relative_path"], Path(r["root"]) / r["relative_path"],
                           r["title"], bool(r["available"]), r["size"], r["mtime_ns"], r["position_ms"],
                           bool(r["favorite"])) for r in rows]
        return tuple(item for item in items if self._matches(item.title, query))

    def save_position(self, item_id: int, position_ms: int) -> None:
        with self.database.transaction() as connection:
            cursor = connection.execute("UPDATE videos SET position_ms=? WHERE id=?", (max(0, position_ms), item_id))
            if cursor.rowcount != 1:
                raise KeyError(item_id)
