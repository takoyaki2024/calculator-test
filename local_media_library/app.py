from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from .paths import AppPaths
from .window import MainWindow


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--video-probe", type=Path)
    parser.add_argument("--probe-report", type=Path)
    parser.add_argument("--thumbnail-worker", type=Path)
    parser.add_argument("--thumbnail-cache", type=Path)
    parser.add_argument("--thumbnail-size", type=int)
    parser.add_argument("--thumbnail-mtime", type=int)
    parser.add_argument("--work-cover-probe", type=Path)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if args.thumbnail_worker:
        if args.thumbnail_cache is None or args.thumbnail_size is None or args.thumbnail_mtime is None:
            parser.error("thumbnail worker requires cache and source fingerprint")
        from .work_thumbnails import run_thumbnail_worker
        return run_thumbnail_worker(args.thumbnail_worker, args.thumbnail_cache, args.thumbnail_size, args.thumbnail_mtime)
    if args.work_cover_probe:
        if not args.probe_report:
            parser.error("--probe-report is required with --work-cover-probe")
        from .work_thumbnails import run_work_cover_probe
        return run_work_cover_probe(args.work_cover_probe.resolve(), args.probe_report.resolve())
    if args.video_probe:
        if not args.probe_report:
            parser.error("--probe-report is required with --video-probe")
        from .video_probe import run_probe
        return run_probe(args.video_probe.resolve(), args.probe_report.resolve())
    app = QApplication.instance() or QApplication([sys.argv[0]])
    app.setApplicationName("Local Media Library")
    app.setOrganizationName("LocalMediaLibrary")
    window = MainWindow(AppPaths.discover())
    window.show()
    if args.smoke:
        from PySide6.QtCore import QTimer
        QTimer.singleShot(300, app.quit)
    return app.exec()
