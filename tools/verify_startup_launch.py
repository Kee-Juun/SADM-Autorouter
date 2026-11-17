"""Regress slow Windows process creation before the splash's first paint."""
import argparse
from pathlib import Path
import sys
import tempfile
import threading
import time
from unittest.mock import patch

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--offscreen', action='store_true')
args = parser.parse_args()
if args.offscreen:
    import os
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
output = root / 'output/startup-check'
output.mkdir(parents=True, exist_ok=True)
tempfile.tempdir = str(output)

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication
from frontend import startup_loader

app = QApplication([])
app.setQuitOnLastWindowClosed(False)
window = startup_loader.StartupWindow()
controller = startup_loader.StartupController(
    window, [sys.executable, str(root / 'tests/fixtures/startup_qt5_probe.py')], keep_alive=True)
painted = threading.Event()
entered_spawn = threading.Event()
release_spawn = threading.Event()
launch_threads = []
original_popen = startup_loader.subprocess.Popen

def slow_popen(*command, **options):
    launch_threads.append(threading.get_ident())
    assert painted.is_set(), 'The engine launched before the splash painted'
    entered_spawn.set()
    if not release_spawn.wait(8):
        raise RuntimeError('The slow-launch check did not release the test engine')
    return original_popen(*command, **options)

window.first_painted.connect(painted.set)
window.first_painted.connect(controller.start)
ticks = []
heartbeat = QTimer()
heartbeat.timeout.connect(lambda: ticks.append(time.monotonic()))
heartbeat.start(20)

with patch.object(startup_loader.subprocess, 'Popen', side_effect=slow_popen):
    try:
        # This is the real entrypoint order; do not force paint with QWidget.grab.
        window.show()
        deadline = time.monotonic() + 3
        while not entered_spawn.is_set() and time.monotonic() < deadline:
            QTest.qWait(20)
        assert entered_spawn.is_set(), 'Engine launch never began'
        assert launch_threads == [launch_threads[0]] and launch_threads[0] != threading.get_ident()
        controller.start()  # Duplicate triggers must not spawn a second engine.
        phase = window.progress.phase
        tick_count = len(ticks)
        QTest.qWait(160)
        assert len(ticks) > tick_count + 2, 'The UI event loop froze during process creation'
        assert window.progress.phase != phase, 'Loading animation froze during process creation'
        assert controller.process is None and window.isVisible()
        assert window.percentage.text() == '0%'

        if not args.offscreen:
            window.raise_()
            window.activateWindow()
            QTest.qWait(100)
            rect = window.frameGeometry()
            image = window.screen().grabWindow(0, rect.x(), rect.y(), rect.width(), rect.height()).toImage()
            image.save(str(output / 'qt6-slow-launch-first-frame.png'))
            scale = image.devicePixelRatio()
            title = window.brand_label.geometry()
            bright = sum(
                min(image.pixelColor(x, y).red(), image.pixelColor(x, y).green(), image.pixelColor(x, y).blue()) > 180
                for y in range(int(title.top()*scale), int((title.bottom()+1)*scale))
                for x in range(int(title.left()*scale), int((title.right()+1)*scale)))
            assert bright > 100, 'The real Windows splash was blank before process creation finished'
            print(f'PASS: actual first frame contains {bright} bright title pixels before engine launch completes', flush=True)

        QTest.mouseClick(window.minimize_button, Qt.MouseButton.LeftButton)
        QTest.qWait(80)
        assert window.isMinimized(), 'Minimize was blocked by process creation'
        window.showNormal()
        QTest.qWait(80)
        assert not window.isMinimized()
        release_spawn.set()
        deadline = time.monotonic() + 25
        while not controller.ready and not controller.failed and time.monotonic() < deadline:
            QTest.qWait(30)
        assert controller.ready and not controller.failed, window.status.text()
        assert not window.isVisible() and window.percentage.text() == '100%'
        while (controller.process is None or controller.process.poll() is None) and time.monotonic() < deadline:
            QTest.qWait(30)
        assert controller.process is not None and controller.process.returncode == 0
        assert len(launch_threads) == 1
        print('PASS: first paint precedes engine launch; slow process creation keeps animation/minimize responsive; real Qt5 handoff closes cleanly', flush=True)
    finally:
        release_spawn.set()
        heartbeat.stop()
        window.finish()
