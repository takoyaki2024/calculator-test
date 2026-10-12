"""Core's read-only, bounded catalog boundary for a future/local mobile UI."""
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from .database import Database
from .repositories import ImageRepository, MangaRepository, VideoRepository
from .sorts import default_registry, video_registry


@dataclass(frozen=True)
class FileReference:
    root: Path
    relative_path: str
    size: int
    mtime_ns: int
    kind: str


class MobileCatalog:
    def __init__(self, database: Database):
        self.database = database
        self.mangas = MangaRepository(database)
        self.images = ImageRepository(database)
        self.videos = VideoRepository(database)

    def library(self, category, query='', sort='newest', offset=0, work=None):
        if category not in ('manga', 'image', 'video') or len(query) > 200 or not 0 <= offset <= 1000000:
            raise ValueError('invalid query')
        if sort not in {option.key for option in default_registry().options()}:
            raise ValueError('invalid sort')
        if category == 'video' and work is None:
            rows, total = self.videos._read('SELECT w.id,w.title,w.file_count,w.cover_video_id',
                'video_works w', 'w', query, 'w.file_count>0', offset=offset, limit=24, sort=sort)
            items = [dict(id=r['id'], title=r['title'], count=r['file_count'],
                          thumb=f"/thumb/video/{r['cover_video_id']}" if r['cover_video_id'] else None,
                          type='work') for r in rows]
        elif category == 'video':
            with closing(self.database.connect()) as c:
                row = c.execute('SELECT source_id,relative_dir,title FROM video_works WHERE id=? AND file_count>0', (work,)).fetchone()
            if row is None:
                raise KeyError(work)
            page = self.videos.page(query, work=(row['source_id'], row['relative_dir']), offset=offset, limit=24,
                                    sorts=video_registry(), sort='natural')
            total = page.total
            items = [dict(id=x.id, title=x.title, thumb=f'/thumb/video/{x.id}', type='video') for x in page.items]
        else:
            repo = self.mangas if category == 'manga' else self.images
            page = repo.page(query, sort=sort, sorts=default_registry(), offset=offset, limit=24)
            total = page.total
            items = [dict(id=x.id, title=x.title, count=x.page_count if category == 'manga' else 1,
                          thumb=f'/thumb/{category}/{x.id}', type=category) for x in page.items]
        return dict(items=items, total=total, offset=offset, limit=24)

    def reference(self, category, item_id, index=0):
        if item_id <= 0 or index < 0:
            raise KeyError(item_id)
        with closing(self.database.connect()) as c:
            if category == 'manga':
                row = c.execute('SELECT s.path root,p.relative_path,p.size,p.mtime_ns FROM manga_pages p '
                    'JOIN manga_works w ON w.id=p.work_id JOIN sources s ON s.id=w.source_id '
                    'WHERE w.id=? AND w.available=1 AND p.available=1 ORDER BY p.page_index LIMIT 1 OFFSET ?',
                    (item_id, index)).fetchone()
            elif category in ('image', 'video'):
                table = 'images' if category == 'image' else 'videos'
                row = c.execute(f'SELECT s.path root,p.relative_path,p.size,p.mtime_ns FROM {table} p '
                    'JOIN sources s ON s.id=p.source_id WHERE p.id=? AND p.available=1', (item_id,)).fetchone()
            else:
                raise KeyError(category)
        if row is None:
            raise KeyError(item_id)
        return FileReference(Path(row['root']), row['relative_path'], row['size'], row['mtime_ns'], category)
