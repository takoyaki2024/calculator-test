from __future__ import annotations

from PySide6.QtCore import QUrl, Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout, QWidget

from .models import VideoItem
from .repositories import VideoRepository


class VideoPlayer(QWidget):
    back_requested = Signal()

    def __init__(self, repository: VideoRepository):
        super().__init__()
        self.repository = repository
        self.item: VideoItem | None = None
        self.ready = False
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(0.8)
        self.video = QVideoWidget()
        self.escape = QShortcut(QKeySequence(Qt.Key.Key_Escape), self.video)
        self.escape.activated.connect(lambda: self.video.setFullScreen(False))
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video)
        self.player.positionChanged.connect(self._position_changed)
        self.player.durationChanged.connect(lambda value: self.seek.setRange(0, max(0, value)))
        self.player.mediaStatusChanged.connect(self._status_changed)
        self.player.errorOccurred.connect(lambda _error, message: self.message.setText(message or "再生できません"))
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        back = QPushButton("← 一覧")
        back.clicked.connect(self.back)
        top.addWidget(back)
        self.title = QLabel()
        top.addWidget(self.title, 1)
        layout.addLayout(top)
        layout.addWidget(self.video, 1)
        controls = QHBoxLayout()
        self.play_button = QPushButton("再生")
        self.play_button.clicked.connect(self.toggle)
        controls.addWidget(self.play_button)
        self.seek = QSlider(Qt.Orientation.Horizontal)
        self.seek.sliderMoved.connect(self.player.setPosition)
        controls.addWidget(self.seek, 1)
        fullscreen = QPushButton("全画面")
        fullscreen.clicked.connect(lambda: self.video.setFullScreen(True))
        controls.addWidget(fullscreen)
        volume = QSlider(Qt.Orientation.Horizontal)
        volume.setRange(0, 100)
        volume.setValue(80)
        volume.valueChanged.connect(lambda value: self.audio.setVolume(value / 100))
        controls.addWidget(volume)
        layout.addLayout(controls)
        self.message = QLabel()
        layout.addWidget(self.message)
        self.save_timer = QTimer(self, interval=5000)
        self.save_timer.timeout.connect(self.save_position)

    def open_item(self, item: VideoItem) -> None:
        self.stop()
        self.item = item
        if not item.path.is_file() or item.path.is_symlink():
            self.message.setText("動画ファイルが見つかりません")
            return
        self.ready = False
        self.title.setText(item.title)
        self.message.setText("読み込み中…")
        self.player.setSource(QUrl.fromLocalFile(str(item.path)))
        self.player.play()
        self.play_button.setText("一時停止")

    def _status_changed(self, status) -> None:
        if status in (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia):
            if not self.ready and self.item:
                self.player.setPosition(self.item.position_ms)
                self.ready = True
                self.message.clear()
                self.save_timer.start()
        elif status == QMediaPlayer.MediaStatus.InvalidMedia:
            self.message.setText("この動画形式またはCodecを再生できません")

    def toggle(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            self.play_button.setText("再生")
            self.save_position()
        else:
            self.player.play()
            self.play_button.setText("一時停止")

    def _position_changed(self, position: int) -> None:
        if not self.seek.isSliderDown():
            self.seek.setValue(position)

    def save_position(self) -> None:
        if self.item and self.ready:
            position = self.player.position()
            duration = self.player.duration()
            if duration > 0 and position >= duration - 1000:
                position = 0
            self.repository.save_position(self.item.id, position)

    def back(self) -> None:
        self.stop()
        self.back_requested.emit()

    def stop(self) -> None:
        self.save_position()
        self.save_timer.stop()
        self.player.stop()
        self.player.setSource(QUrl())
        self.ready = False

    def enter_fullscreen(self) -> None:
        self.video.setFullScreen(True)

    def leave_fullscreen(self) -> None:
        self.video.setFullScreen(False)

    def closeEvent(self, event) -> None:
        self.stop()
        super().closeEvent(event)
