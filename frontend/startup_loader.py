"""Isolated PyQt6 startup UI. Never import the PyQt5 application here."""

import ctypes
from concurrent.futures import ThreadPoolExecutor
import hmac
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile

from PyQt6.QtCore import QEvent, QObject, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QCloseEvent, QCursor, QFontDatabase, QIcon
from PyQt6.QtNetwork import QHostAddress, QTcpServer
from PyQt6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QPushButton,
    QVBoxLayout, QWidget,
)

from .startup_glass import enable_acrylic
from .startup_visuals import ActivityStrip, GlitchLogo, GlassCard, WindowGlitchEffect, card_region


class StartupWindow(QWidget):
    first_painted = pyqtSignal()

    def __init__(self):
        super().__init__(None, Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowMinimizeButtonHint)
        self.setWindowTitle("SADM Autorouter - Starting")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(360, 144)
        self._finished = False
        self._failed = False
        self._drag_offset = None
        self._glass_initialized = False
        self._progress = 0
        self._first_paint_reported = False
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        card = GlassCard()
        self.card = card
        card.setObjectName("startupCard")
        self.ui_glitch = WindowGlitchEffect(card)
        self.ui_glitch.frameChanged.connect(self._update_shape)
        card.setGraphicsEffect(self.ui_glitch)
        outer.addWidget(card)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 20, 22, 22)
        layout.setSpacing(0)

        header = QHBoxLayout()
        header.setSpacing(12)
        mark = GlitchLogo()
        self.brand_icon = mark
        mark.setObjectName("brandMark")
        mark.setFixedSize(28, 36)
        mark.setAccessibleName("SADM Autorouter Silcrow Icon")
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        resource_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
        self.startup_font_family = "Segoe UI"
        font_path = resource_root / "assets" / "fonts" / "Oxanium-Variable.ttf"
        if font_path.is_file():
            font_id = QFontDatabase.addApplicationFont(str(font_path))
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                self.startup_font_family = families[0]
        icon = QIcon(str(resource_root / "assets" / "icons" / "silcrow.ico"))
        if not icon.isNull():
            mark.setPixmap(icon.pixmap(QSize(27, 34), self.devicePixelRatioF()))
            self.setWindowIcon(icon)
        header.addWidget(mark)
        brand = QLabel("SADM Autorouter")
        self.brand_label = brand
        brand.setObjectName("brand")
        header.addWidget(brand)
        header.addStretch()
        self.minimize_button = QPushButton("—")
        self.minimize_button.setObjectName("minimize")
        self.minimize_button.setFixedSize(24, 24)
        self.minimize_button.setToolTip("Minimize — startup will continue")
        self.minimize_button.setAccessibleName("Minimize Loading Window")
        self.minimize_button.clicked.connect(self.showMinimized)
        header.addWidget(self.minimize_button)
        layout.addLayout(header)
        layout.addSpacing(12)
        self.status = QLabel("Preparing App Files")
        self.status.setObjectName("status")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        self.status.setMinimumHeight(20)
        stage_row = QHBoxLayout()
        stage_row.setSpacing(12)
        stage_row.addWidget(self.status, 1)
        self.percentage = QLabel("0%")
        self.percentage.setObjectName("percentage")
        self.percentage.setFixedWidth(96)
        self.percentage.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.percentage.setToolTip("Estimated startup progress. Some steps take longer than others.")
        self.percentage.setAccessibleName("Estimated Startup Progress: 0%")
        stage_row.addWidget(self.percentage)
        layout.addLayout(stage_row)
        layout.addStretch(1)
        self.progress = ActivityStrip()
        self.progress.setFixedHeight(3)
        self.progress.installEventFilter(self)
        layout.addWidget(self.progress)

        footer = QHBoxLayout()
        footer.addStretch()
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(QApplication.instance().quit)
        self.close_button.hide()
        footer.addWidget(self.close_button)
        layout.addLayout(footer)
        self.setStyleSheet("""
            QWidget { font-family: '__STARTUP_FONT__'; color: #f0f0f6; font-size: 12px; }
            QFrame#startupCard { background: transparent; border: none; }
            QLabel { background: transparent; border: none; }
            QLabel#brandMark { background: transparent; }
            QLabel#brand { font-size: 17px; font-weight: 600; letter-spacing: -0.2px; }
            QLabel#status { color: #aeb2c3; }
            QLabel#percentage { color: #eceaf5; font-size: 36px; font-weight: 500; letter-spacing: -1.25px; }
            QPushButton { background: rgba(153, 159, 185, 25); border: none; border-radius: 7px; padding: 5px 14px; }
            QPushButton:hover { background: rgba(153, 159, 185, 45); }
            QPushButton#minimize { background: transparent; color: #9196a8; padding: 0; font-size: 14px; }
            QPushButton#minimize:hover { background: rgba(153, 159, 185, 25); color: #f0f0f6; }
        """.replace("__STARTUP_FONT__", self.startup_font_family))
        for widget in (card, mark, brand, self.status, self.percentage):
            widget.installEventFilter(self)
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        if screen:
            self.move(screen.availableGeometry().center() - self.rect().center())

    def showEvent(self, event):
        super().showEvent(event)
        if not self._glass_initialized:
            self._glass_initialized = True
            if QApplication.platformName() == "windows":
                self.card.native_backdrop = enable_acrylic(int(self.winId()))
                self.card.update()
        if not self._finished and not self._failed:
            self.ui_glitch.resume()
            self.card.resume()
            self.brand_icon.resume()
            self.progress.resume()

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self._first_paint_reported:
            self._first_paint_reported = True
            # Queue the signal until this paint (including child widgets) ends.
            QTimer.singleShot(0, self.first_painted.emit)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange and hasattr(self, "brand_icon"):
            if self.isMinimized():
                self.ui_glitch.stop()
                self.card.stop()
                self.brand_icon.stop()
                self.progress.stop()
            elif not self._finished and not self._failed:
                self.ui_glitch.resume()
                self.card.resume()
                self.brand_icon.resume()
                self.progress.resume()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_shape()

    def _update_shape(self, frame=None):
        if frame is None:
            frame = getattr(getattr(self, 'ui_glitch', None), 'frame', 0)
        # The native acrylic follows the fractured outline as well as the text.
        self.setMask(card_region(QRectF(self.rect()), frame))

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            if self.windowHandle() and self.windowHandle().startSystemMove():
                self._drag_offset = None
            return True
        if event.type() == QEvent.Type.MouseMove and self._drag_offset is not None:
            if event.buttons() & Qt.MouseButton.LeftButton:
                self.move(event.globalPosition().toPoint() - self._drag_offset)
                return True
        if event.type() == QEvent.Type.MouseButtonRelease:
            self._drag_offset = None
        return super().eventFilter(watched, event)

    def set_stage(self, message, progress=None):
        if not self._failed:
            self.status.setText(message)
            if isinstance(progress, (int, float)) and not isinstance(progress, bool) and 0 <= progress <= 100:
                self._progress = max(self._progress, min(99, int(progress)))
                self.percentage.setText(f"{self._progress}%")
                self.percentage.setAccessibleName(f"Estimated Startup Progress: {self._progress}%")
                self.progress.set_progress(self._progress)

    def show_failure(self, message):
        self._failed = True
        self.ui_glitch.stop()
        self.card.stop()
        self.brand_icon.stop()
        self.progress.stop()
        self.setFixedSize(360, 200)
        self.status.setStyleSheet("color: #dfc1a4;")
        self.status.setText(message)
        self.status.setToolTip(message)
        self.progress.hide()
        self.percentage.hide()
        self.close_button.show()
        self.showNormal()

    def finish(self):
        self._finished = True
        self.ui_glitch.stop()
        self._progress = 100
        self.percentage.setText("100%")
        self.percentage.setAccessibleName("Startup Complete: 100%")
        self.progress.set_progress(100)
        self.card.stop()
        self.brand_icon.stop()
        self.progress.stop()
        self.hide()

    def closeEvent(self, event: QCloseEvent):
        if self._finished or self._failed:
            event.accept()
            if self._failed:
                QApplication.instance().quit()
        else:
            event.ignore()
            self.showMinimized()


class StartupController(QObject):
    def __init__(self, window, command, *, keep_alive=False):
        super().__init__(window)
        self.window = window
        self.command = command
        self.keep_alive = keep_alive
        self.ready = False
        self.failed = False
        self.process = None
        self.log_file = None
        self._started = False
        self._launch_executor = None
        self._launch_future = None
        self.token = secrets.token_hex(24)
        self.buffers = {}
        self.server = QTcpServer(self)
        if not self.server.listen(QHostAddress.SpecialAddress.LocalHost, 0):
            raise RuntimeError("Could not start the local startup-status channel")
        self.server.newConnection.connect(self.accept_connections)
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self.check_process)

    def accept_connections(self):
        while self.server.hasPendingConnections():
            channel = self.server.nextPendingConnection()
            self.buffers[channel] = bytearray()
            channel.readyRead.connect(lambda channel=channel: self.read_message(channel))
            channel.disconnected.connect(lambda channel=channel: self.drop_connection(channel))
            self.read_message(channel)

    def drop_connection(self, channel):
        self.read_message(channel)
        self.buffers.pop(channel, None)
        channel.deleteLater()

    def read_message(self, channel):
        if channel not in self.buffers:
            return
        buffer = self.buffers[channel]
        buffer.extend(bytes(channel.readAll()))
        if len(buffer) > 8192:
            channel.abort()
            return
        while b"\n" in buffer:
            line, _, remainder = buffer.partition(b"\n")
            buffer[:] = remainder
            try:
                payload = json.loads(line)
                token = payload.get("token", "")
                if isinstance(token, str) and token.isascii() and hmac.compare_digest(token, self.token):
                    self.handle_event(payload.get("event"), str(payload.get("message", ""))[:1000], payload.get("progress"))
            except (ValueError, AttributeError):
                continue

    def handle_event(self, event, message, progress=None):
        if self.ready or self.failed:
            return
        if event == "stage":
            self.window.set_stage(message, progress)
        elif event == "ready":
            self.ready = True
            self.server.close()
            self.window.finish()
            if not self.keep_alive:
                QApplication.instance().quit()
        elif event == "error":
            self.failed = True
            self.window.show_failure(message or "Please check the startup log and try again.")

    def start(self):
        if self._started:
            return
        self._started = True
        env = dict(os.environ)
        env["SADM_STARTUP_ENDPOINT"] = f"{self.server.serverPort()}:{self.token}"
        env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
        # The engine must load its own Qt5 plugins, not the launcher's Qt6 ones.
        for key in ("QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH", "QML2_IMPORT_PATH"):
            env.pop(key, None)
        bundle = str(sys._MEIPASS) if sys.platform == "win32" and getattr(sys, "frozen", False) else None
        self._launch_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="SADM-engine-start")
        self._launch_future = self._launch_executor.submit(self._spawn_engine, self.command, env, bundle)
        self.poll_timer.start(50)

    @staticmethod
    def _spawn_engine(command, env, bundle):
        """Keep slow file access, Windows process creation, and scans off Qt's thread."""
        log_file = None
        try:
            log_dir = Path(tempfile.gettempdir()) / "SADM Autorouter"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = open(log_dir / f"startup-{os.getpid()}.log", "ab")
            if bundle is not None:
                ctypes.windll.kernel32.SetDllDirectoryW(None)
            try:
                process = subprocess.Popen(
                    command, env=env, stdout=log_file, stderr=log_file,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                )
            finally:
                if bundle is not None:
                    ctypes.windll.kernel32.SetDllDirectoryW(bundle)
            return process, log_file
        except BaseException:
            if log_file is not None:
                log_file.close()
            raise

    def check_process(self):
        if self._launch_future is not None:
            if not self._launch_future.done():
                return
            future, self._launch_future = self._launch_future, None
            self._launch_executor.shutdown(wait=False)
            self._launch_executor = None
            try:
                self.process, self.log_file = future.result()
            except Exception as exc:
                self.poll_timer.stop()
                self.server.close()
                self.failed = True
                self.window.show_failure(str(exc))
                return
            self.poll_timer.setInterval(200)
        if self.process is None or self.process.poll() is None:
            return
        self.poll_timer.stop()
        self.server.close()
        if self.log_file:
            self.log_file.close()
        if self.ready:
            QApplication.instance().quit()
        elif not self.failed:
            self.failed = True
            self.window.show_failure("The app closed before its window was ready. Please check the startup log.")
