@echo off
setlocal
cd /d "%~dp0"
py -3.11 -m pip install -e ".[dev]" || exit /b 1
py -3.11 -m PyInstaller --clean --noconfirm packaging\local_media_library.spec || exit /b 1
echo Built dist\LocalMediaLibrary-Windows.zip
