# Third-party runtime notices

The application depends on PySide6 / Qt 6, distributed under the LGPLv3/GPLv3/commercial terms. The portable build keeps Qt as separate dynamic libraries so users can replace compatible LGPL libraries. Qt source and license information: https://www.qt.io/licensing/open-source-lgpl-obligations

PyInstaller is a build-time dependency distributed under GPLv2 with its bootloader exception, which permits distributing the resulting bundled application: https://pyinstaller.org/en/stable/license.html. Python and SQLite retain their respective licenses.

The project does not bundle a standalone FFmpeg program. Qt Multimedia packages codec libraries supplied by the selected PySide6 distribution; their license notices must remain present in the packaged runtime.
