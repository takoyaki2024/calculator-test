"""Desktop control for optional mobile module. No listener before explicit ON."""
from PySide6.QtCore import QTimer, Qt
from PySide6.QtNetwork import QNetworkInterface, QAbstractSocket
from PySide6.QtWidgets import (QComboBox, QFileDialog, QHBoxLayout, QLabel, QMessageBox,
                               QPushButton, QVBoxLayout, QWidget)

from ..mobile_catalog import MobileCatalog
from .server import MobileServer, private_address


class MobileSettings(QWidget):
    def __init__(self, database, managed):
        super().__init__()
        self.controller = MobileServer(MobileCatalog(database), managed)
        layout = QVBoxLayout(self)
        heading = QLabel('iPhoneから閲覧 — 自宅内限定')
        heading.setObjectName('heading')
        layout.addWidget(heading)
        description = QLabel('初期状態はOFFです。ONの間だけ、PCで許可した1台に保存済みメディアを公開します。\n'
                             'HTTPSで暗号化。外部サービス・自動変換は使いません。接続許可はOFF・終了時に失効します。')
        description.setWordWrap(True)
        layout.addWidget(description)
        controls = QHBoxLayout()
        self.address = QComboBox()
        for interface in QNetworkInterface.allInterfaces():
            if not interface.flags() & QNetworkInterface.InterfaceFlag.IsUp:
                continue
            for entry in interface.addressEntries():
                ip = entry.ip()
                if ip.protocol() == QAbstractSocket.NetworkLayerProtocol.IPv4Protocol and private_address(ip.toString()):
                    self.address.addItem(f'{interface.humanReadableName()} — {ip.toString()}', ip.toString())
        controls.addWidget(self.address, 1)
        self.start_button = QPushButton('スマホ閲覧をON')
        self.start_button.clicked.connect(self.start)
        controls.addWidget(self.start_button)
        self.stop_button = QPushButton('OFF・全接続を解除')
        self.stop_button.clicked.connect(self.stop)
        self.stop_button.setEnabled(False)
        controls.addWidget(self.stop_button)
        layout.addLayout(controls)
        self.state = QLabel('OFF')
        self.state.setWordWrap(True)
        self.state.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.state)
        instructions = QLabel('初回：PCとiPhoneを同じ自宅Wi-Fiへ接続 → 専用証明書をiPhoneに設定 → SafariでHTTPSの閲覧先を開く。\n'
            'Windowsの許可画面が出た場合は、プライベートネットワークだけを許可してください。\n'
            'iPhone：設定 → 一般 → VPNとデバイス管理で証明書をインストール → 一般 → 情報 → 証明書信頼設定。\n'
            '証明書を信頼する前に、下のSHA-256と証明書の指紋が一致することを確認してください。\n'
            '証明書警告を無視して閲覧する運用はしないでください。IP変更時は専用証明書の再設定が必要です。')
        instructions.setWordWrap(True)
        layout.addWidget(instructions)
        certificate_controls = QHBoxLayout()
        self.export_button = QPushButton('公開証明書を保存')
        self.export_button.clicked.connect(self.export_certificate)
        self.bootstrap_button = QPushButton('初回証明書の取得を5分だけ開く')
        self.bootstrap_button.clicked.connect(self.bootstrap)
        self.close_bootstrap_button = QPushButton('証明書の取得を閉じる')
        self.close_bootstrap_button.clicked.connect(self.close_bootstrap)
        for button in (self.export_button, self.bootstrap_button, self.close_bootstrap_button):
            certificate_controls.addWidget(button)
            button.setEnabled(False)
        layout.addLayout(certificate_controls)
        self.certificate_label = QLabel('')
        self.certificate_label.setWordWrap(True)
        self.certificate_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.certificate_label)
        self.pending = QLabel('')
        layout.addWidget(self.pending)
        approval = QHBoxLayout()
        self.approve_button = QPushButton('iPhoneの確認番号が一致：許可')
        self.approve_button.clicked.connect(self.approve)
        self.approve_button.setEnabled(False)
        approval.addWidget(self.approve_button)
        self.reject_button = QPushButton('拒否・接続を閉じる')
        self.reject_button.clicked.connect(self.stop)
        approval.addWidget(self.reject_button)
        layout.addLayout(approval)
        self.timer = QTimer(self, interval=500)
        self.timer.timeout.connect(self.poll)

    def start(self):
        address = self.address.currentData()
        if not address:
            self.state.setText('自宅内のIPv4アドレスがありません。ネットワーク接続後、アプリを開き直してください。')
            return
        try:
            origin = self.controller.start(address)
        except Exception:
            self.controller.stop()
            self.state.setText('開始できません。選択した接続・ポートの使用状態・証明書保存先の権限を確認してください。')
            return
        self.origin = origin
        self.state.setText(f'閲覧先：{origin}\n接続コード：{self.controller.auth.code}（5分有効・入力最大5回）')
        self.address.setEnabled(False)
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.export_button.setEnabled(True)
        self.bootstrap_button.setEnabled(True)
        self.certificate_label.setText('証明書 SHA-256：\n' + self.controller.fingerprint)
        self.timer.start()

    def poll(self):
        if not self.controller.server:
            return
        auth = self.controller.auth
        challenge = auth.pending_challenge()
        self.approve_button.setEnabled(bool(challenge))
        if challenge:
            self.pending.setText(f'iPhoneから接続申請：確認番号 {challenge}。同じ番号がiPhoneに表示されている場合だけ許可してください。')
        elif auth.sessions:
            self.pending.setText('1台のiPhoneに閲覧を許可しています。OFFで解除できます。')
        else:
            self.pending.setText('接続申請待ち。コードが期限切れ・入力上限の場合はOFF→ONで作り直せます。')
        self.close_bootstrap_button.setEnabled(self.controller.bootstrap is not None)
        self.bootstrap_button.setEnabled(self.controller.bootstrap is None)

    def approve(self):
        try:
            self.controller.auth.approve()
            self.state.setText(f'閲覧先：{self.origin}\n接続コードは失効済み。閲覧許可は最長8時間、OFF・終了で解除されます。')
            self.poll()
        except PermissionError:
            self.pending.setText('申請が期限切れです。OFF→ONで再接続してください。')

    def stop(self):
        self.timer.stop()
        self.controller.stop()
        self.state.setText('OFF — 接続許可をすべて解除しました。')
        self.pending.clear()
        self.certificate_label.clear()
        self.address.setEnabled(True)
        self.start_button.setEnabled(True)
        for button in (self.stop_button, self.export_button, self.bootstrap_button, self.close_bootstrap_button, self.approve_button):
            button.setEnabled(False)

    def bootstrap(self):
        try:
            url = self.controller.open_bootstrap()
            self.certificate_label.setText('証明書取得先（5分のみ・公開証明書だけ）：\n' + url +
                                          '\n証明書 SHA-256：\n' + self.controller.fingerprint)
            self.poll()
        except OSError:
            QMessageBox.warning(self, '証明書の取得', '取得用ポートを開けません。公開証明書を保存して転送する方法も使えます。')

    def close_bootstrap(self):
        self.controller.close_bootstrap()
        self.certificate_label.setText('証明書 SHA-256：\n' + self.controller.fingerprint)
        self.poll()

    def export_certificate(self):
        filename, _ = QFileDialog.getSaveFileName(self, '公開証明書を保存', 'LocalMediaLibrary.cer', 'Certificate (*.cer)')
        if filename:
            try:
                from pathlib import Path
                Path(filename).write_bytes(self.controller.ca_file.read_bytes())
            except OSError:
                QMessageBox.warning(self, '証明書を保存できません', '保存先を確認してください。')
