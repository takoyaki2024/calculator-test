from pathlib import Path
import shutil

ROOT = Path(SPECPATH).resolve().parent
OUTPUT = Path(DISTPATH) / "LocalMediaLibrary"
ARCHIVE = Path(DISTPATH) / "LocalMediaLibrary-Windows.zip"
if OUTPUT.exists() or ARCHIVE.exists():
    raise RuntimeError("Refusing to overwrite an existing package output")

a = Analysis(
    [str(ROOT / "local_media_library" / "__main__.py")],
    pathex=[str(ROOT)],
    binaries=[], datas=[], hiddenimports=[], hookspath=[], hooksconfig={},
    runtime_hooks=[], excludes=[], noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name="LocalMediaLibrary",
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=False, disable_windowed_traceback=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="LocalMediaLibrary")
shutil.copy2(ROOT / "README.md", OUTPUT / "README.md")
shutil.copy2(ROOT / "LICENSE", OUTPUT / "LICENSE")
shutil.copy2(ROOT / "THIRD_PARTY_NOTICES.md", OUTPUT / "THIRD_PARTY_NOTICES.md")
(OUTPUT / "data").mkdir()
shutil.make_archive(str(ARCHIVE.with_suffix("")), "zip", str(OUTPUT.parent), OUTPUT.name)
