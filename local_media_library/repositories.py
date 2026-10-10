from __future__ import annotations

from contextlib import closing
from pathlib import Path

from .database import Database
from .models import ImageItem, LibrarySlice, MangaPage, MangaWork, VideoItem, VideoWork
from .sorts import default_registry, video_registry


class _Repository:
    def __init__(self, database: Database):
        self.database = database

    def _read(self, select, tables, alias, query, condition, parameters=(), *, offset=0, limit=None, sorts=None, sort="newest"):
        if offset < 0 or (limit is not None and not 1 <= limit <= 1000):
            raise ValueError("invalid library page")
        where = f" WHERE {condition}"
        values = list(parameters)
        if query:
            where += f" AND contains_title({alias}.title,?)"
            values.append(query)
        order = (sorts or default_registry()).sql_order(sort, alias)
        with closing(self.database.connect()) as connection:
            # Count and page must describe the same committed scan snapshot.
            connection.execute("BEGIN")
            total = connection.execute("SELECT count(*) FROM " + tables + where, values).fetchone()[0]
            sql = select + " FROM " + tables + where + " ORDER BY " + order
            if limit is not None:
                sql += " LIMIT ? OFFSET ?"
                values.extend((limit, offset))
            rows = connection.execute(sql, values).fetchall()
        return rows, total


class MangaRepository(_Repository):
    def get_position(self, work_id: int) -> int:
        with closing(self.database.connect()) as connection:
            row = connection.execute("SELECT last_page FROM manga_works WHERE id=?", (work_id,)).fetchone()
        if row is None:
            raise KeyError(work_id)
        return row[0]

    def page(self, query="", *, offset=0, limit=100, sorts=None, sort="newest", include_missing=False):
        rows, total = self._read(
            "SELECT w.*,s.path root,(SELECT p.relative_path FROM manga_pages p "
            "WHERE p.work_id=w.id AND p.available=1 ORDER BY p.page_index LIMIT 1) cover",
            "manga_works w JOIN sources s ON s.id=w.source_id", "w", query,
            "1" if include_missing else "w.available=1", offset=offset, limit=limit, sorts=sorts, sort=sort)
        items = tuple(MangaWork(r["id"], r["source_id"], r["relative_dir"], r["title"], r["page_count"],
                                Path(r["root"]) / r["cover"] if r["cover"] else None,
                                bool(r["available"]), r["mtime_ns"], bool(r["favorite"]), r["last_page"]) for r in rows)
        return LibrarySlice(items, total)

    def list(self, query="", include_missing=False):
        return self.page(query, limit=None, include_missing=include_missing).items

    def pages(self, work_id: int) -> tuple[MangaPage, ...]:
        with closing(self.database.connect()) as connection:
            rows = connection.execute(
                "SELECT p.*,s.path root FROM manga_pages p JOIN manga_works w ON w.id=p.work_id "
                "JOIN sources s ON s.id=w.source_id WHERE p.work_id=? AND p.available=1 ORDER BY p.page_index",
                (work_id,),
            ).fetchall()
        return tuple(MangaPage(r["id"], work_id, r["relative_path"], Path(r["root"]) / r["relative_path"],
                               r["page_index"], bool(r["available"])) for r in rows)

    def save_position(self, work_id: int, page_index: int) -> None:
        with self.database.transaction() as connection:
            cursor = connection.execute("UPDATE manga_works SET last_page=? WHERE id=?", (max(0, page_index), work_id))
            if cursor.rowcount != 1:
                raise KeyError(work_id)


class ImageRepository(_Repository):
    def page(self, query="", *, offset=0, limit=100, sorts=None, sort="newest", include_missing=False):
        rows, total = self._read("SELECT i.*,s.path root", "images i JOIN sources s ON s.id=i.source_id", "i", query,
                                "1" if include_missing else "i.available=1", offset=offset, limit=limit, sorts=sorts, sort=sort)
        return LibrarySlice(tuple(ImageItem(r["id"], r["source_id"], r["relative_path"], Path(r["root"]) / r["relative_path"],
                                            r["title"], bool(r["available"]), r["size"], r["mtime_ns"], bool(r["favorite"])) for r in rows), total)

    def list(self, query="", include_missing=False):
        return self.page(query, limit=None, include_missing=include_missing).items


class VideoRepository(_Repository):
    @staticmethod
    def _item(row):
        return VideoItem(row["id"], row["source_id"], row["relative_path"], Path(row["root"]) / row["relative_path"],
                         row["title"], bool(row["available"]), row["size"], row["mtime_ns"], row["position_ms"], bool(row["favorite"]))

    def works_page(self, query="", *, offset=0, limit=100, sorts=None, sort="newest"):
        rows, total = self._read(
            "SELECT w.*,s.path root,v.relative_path cover_path,v.size cover_size,v.mtime_ns cover_mtime",
            "video_works w JOIN sources s ON s.id=w.source_id LEFT JOIN videos v ON v.id=w.cover_video_id",
            "w", query, "w.file_count>0", offset=offset, limit=limit, sorts=sorts, sort=sort)
        items = []
        for r in rows:
            path = Path(r["root"]) / r["relative_dir"]
            cover = (VideoItem(r["cover_video_id"], r["source_id"], r["cover_path"], Path(r["root"]) / r["cover_path"],
                               Path(r["cover_path"]).stem, True, r["cover_size"], r["cover_mtime"]) if r["cover_path"] else None)
            items.append(VideoWork(r["source_id"], r["relative_dir"], path, r["title"], r["file_count"], r["mtime_ns"], cover))
        return LibrarySlice(tuple(items), total)

    def works(self, query=""):
        return self.works_page(query, limit=None).items

    def page(self, query="", *, offset=0, limit=100, sorts=None, sort="newest", include_missing=False, work=None):
        condition = "1" if include_missing else "v.available=1"
        parameters = ()
        if work is not None:
            condition += " AND v.source_id=? AND v.relative_dir=?"
            parameters = work
        rows, total = self._read("SELECT v.*,s.path root", "videos v JOIN sources s ON s.id=v.source_id", "v", query,
                                condition, parameters, offset=offset, limit=limit, sorts=sorts, sort=sort)
        return LibrarySlice(tuple(self._item(r) for r in rows), total)

    def in_work(self, source_id, relative_dir, query=""):
        return self.page(query, limit=None, work=(source_id, relative_dir), sorts=video_registry(), sort="natural").items

    def list(self, query="", include_missing=False):
        return self.page(query, limit=None, include_missing=include_missing).items

    def get_position(self, item_id: int) -> int:
        with closing(self.database.connect()) as connection:
            row = connection.execute("SELECT position_ms FROM videos WHERE id=?", (item_id,)).fetchone()
        if row is None:
            raise KeyError(item_id)
        return row[0]

    def save_position(self, item_id: int, position_ms: int) -> None:
        with self.database.transaction() as connection:
            cursor = connection.execute("UPDATE videos SET position_ms=? WHERE id=?", (max(0, position_ms), item_id))
            if cursor.rowcount != 1:
                raise KeyError(item_id)
