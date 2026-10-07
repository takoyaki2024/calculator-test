import ast
from pathlib import Path


def imports(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    values = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            values.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            values.append(node.module)
    return values


def test_runtime_has_no_network_downloader_or_analytics_imports():
    forbidden = ("requests", "urllib", "httpx", "aiohttp", "socket", "fastapi", "flask", "analytics", "sentry")
    for path in Path("local_media_library").glob("*.py"):
        used = imports(path)
        assert not [name for name in used if name.split(".")[0] in forbidden], path


def test_ui_does_not_import_database_or_sqlite():
    for name in ("pages.py", "manga_reader.py", "image_viewer.py", "video_player.py"):
        used = imports(Path("local_media_library") / name)
        assert "sqlite3" not in used
        assert "local_media_library.database" not in used
