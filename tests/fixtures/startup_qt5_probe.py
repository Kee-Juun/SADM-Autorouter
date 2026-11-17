"""Test-only Qt5 engine window; never imports routing, config, or email code."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from core.startup_progress import close_startup, report_startup
report_startup("Loading Interface Libraries", 5)
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication, QLabel
report_startup("Building Your Workspace", 80)
app = QApplication([])
window = QLabel("Startup Handoff Test — no routing or email")
window.setWindowTitle("Autorouter Startup Test")
window.resize(320, 90)
window.show()
QTimer.singleShot(350, close_startup)
QTimer.singleShot(1000, app.quit)
app.exec_()
