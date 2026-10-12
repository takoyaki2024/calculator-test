import json
import os
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(not os.environ.get("LOCAL_MEDIA_LIBRARY_EXE"), reason="packaged Windows only")
def test_packaged_startup_and_video_probe(tmp_path):
    executable = os.environ["LOCAL_MEDIA_LIBRARY_EXE"]
    environment = os.environ.copy()
    environment["LOCAL_MEDIA_LIBRARY_ROOT"] = str(tmp_path / "state")
    subprocess.run([executable, "--smoke"], check=True, timeout=20, env=environment)
    report = tmp_path / "report.json"
    subprocess.run([executable, "--video-probe", str(Path("tests/fixtures/baseline.mp4").resolve()),
                    "--probe-report", str(report)], check=True, timeout=35, env=environment)
    assert json.loads(report.read_text(encoding="utf-8"))["result"] == "PASS"
