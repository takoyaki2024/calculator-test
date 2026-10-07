"""Automated decode/control probe; not proof of visible or audible real-device output."""
from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

from PySide6.QtCore import QTimer, qVersion
from PySide6.QtMultimedia import QAudioBufferOutput, QMediaPlayer
from PySide6.QtWidgets import QApplication

from .database import Database
from .repositories import VideoRepository
from .scanner import Scanner
from .service import LibraryService
from .video_player import VideoPlayer


def run_probe(source: Path, report: Path) -> int:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    result = {
        "qt": qVersion(), "result": "FAIL", "video_frames": 0, "audio_buffers": 0,
        "pause": False, "seek": False, "resume": False, "fullscreen_state": False,
        "visible_display_verified": False, "audible_output_verified": False,
        "probe_stage": "initializing",
    }
    report.parent.mkdir(parents=True, exist_ok=True)

    def checkpoint() -> None:
        report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    checkpoint()
    with tempfile.TemporaryDirectory(prefix="local-media-probe-") as temporary:
        database = Database(Path(temporary) / "library.sqlite3")
        service = LibraryService(database, Scanner())
        repository = VideoRepository(database)
        folder = service.add_source(source.parent, "video")
        service.scan_source(folder.id)
        item = next((value for value in repository.list() if value.path.resolve() == source), None)
        if item is None:
            result["error"] = "fixture was not discovered"
            checkpoint()
        else:
            player = VideoPlayer(repository)
            audio = QAudioBufferOutput(player)
            player.player.setAudioBufferOutput(audio)
            player.video.videoSink().videoFrameChanged.connect(
                lambda frame: result.update(video_frames=result["video_frames"] + 1) if frame.isValid() else None
            )
            audio.audioBufferReceived.connect(
                lambda buffer: result.update(audio_buffers=result["audio_buffers"] + 1)
                if buffer.isValid() and buffer.sampleCount() else None
            )
            player.player.errorOccurred.connect(lambda _error, message: result.update(error=message or "media error"))
            player.resize(640, 400)
            player.show()
            start = time.monotonic()
            state = {"name": "play"}
            result["probe_stage"] = "play"
            checkpoint()
            timer = QTimer(interval=30)

            def finish(error=None):
                if error:
                    result["error"] = str(error)
                result["probe_stage"] = "finished"
                checkpoint()
                timer.stop()
                player.stop()
                player.close()
                app.quit()

            def poll():
                try:
                    if result.get("error"):
                        finish(result["error"])
                    elif time.monotonic() - start > 25:
                        finish(f"timeout during {state['name']}")
                    elif state["name"] == "play":
                        if result["video_frames"] >= 2 and result["audio_buffers"] >= 1 and player.player.position() >= 700:
                            assert player.player.hasVideo() and player.player.hasAudio() and player.player.isSeekable()
                            player.player.pause()
                            state.update(name="pause", at=player.player.position(), since=time.monotonic())
                            result["probe_stage"] = "pause"
                            checkpoint()
                    elif state["name"] == "pause" and time.monotonic() - state["since"] > 0.3:
                        assert player.player.playbackState() == QMediaPlayer.PlaybackState.PausedState
                        assert abs(player.player.position() - state["at"]) < 180
                        result["pause"] = True
                        player.player.setPosition(2500)
                        state["name"] = "seek"
                        result["probe_stage"] = "seek"
                        checkpoint()
                    elif state["name"] == "seek" and abs(player.player.position() - 2500) < 250:
                        result["seek"] = True
                        player.save_position()
                        assert repository.list()[0].position_ms >= 2250
                        state.update(name="resume", frames=result["video_frames"])
                        result["probe_stage"] = "resume"
                        checkpoint()
                        player.open_item(repository.list()[0])
                    elif state["name"] == "resume":
                        if player.ready and player.player.position() >= 2250 and result["video_frames"] > state["frames"]:
                            result["resume"] = True
                            result["probe_stage"] = "fullscreen-enter"
                            checkpoint()
                            player.enter_fullscreen()
                            assert player.video.isFullScreen()
                            result["probe_stage"] = "fullscreen-leave"
                            checkpoint()
                            player.leave_fullscreen()
                            assert not player.video.isFullScreen()
                            result["fullscreen_state"] = True
                            result["result"] = "PASS"
                            result["probe_stage"] = "pass"
                            checkpoint()
                            finish()
                except Exception as exc:
                    finish(f"{type(exc).__name__}: {exc}")

            player.open_item(item)
            timer.timeout.connect(poll)
            timer.start()
            app.exec()
    checkpoint()
    return 0 if result["result"] == "PASS" else 1
