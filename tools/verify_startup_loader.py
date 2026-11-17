"""Verify the isolated PyQt6 UI and its real separate Qt5 process handoff."""
import argparse
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import time

options = argparse.ArgumentParser(description=__doc__)
options.add_argument('--offscreen', action='store_true')
options.add_argument('--record-preview', action='store_true', help='Record only the startup widget, with a transparent surround.')
options.add_argument('--native-capture', action='store_true', help='Capture the compositor inside the loader bounds; no extra backdrop.')
args = options.parse_args()
if args.offscreen:
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
(root / "output" / "startup-check").mkdir(parents=True, exist_ok=True)
tempfile.tempdir = str(root / "output" / "startup-check")
from PyQt6.QtCore import QPoint, QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFontInfo, QImage, QPainter, QPixmap
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QLabel
from frontend.startup_loader import StartupController, StartupWindow
from frontend.startup_visuals import WindowGlitchEffect, card_region, glitch_slices, panel_path

app = QApplication([])
app.setQuitOnLastWindowClosed(False)

# Regress the dark-band bug on a translucent surface at desktop display scales.
for scale in (1, 1.5, 2):
    sample = QPixmap(int(240*scale), int(120*scale))
    sample.setDevicePixelRatio(scale)
    sample.fill(QColor(28, 28, 35, 140))
    painter = QPainter(sample)
    painter.fillRect(QRectF(80, 35, 35, 25), Qt.GlobalColor.white)
    painter.end()
    for frame in range(1, 6):
        rendered = WindowGlitchEffect.render_frame(sample, frame).toImage()
        for band, _ in glitch_slices(QRectF(0, 0, 240, 120), frame):
            color = rendered.pixelColor(int(180*scale), int(band.center().y()*scale))
            assert color.alpha() == 140, 'A glitch slice added opacity to the glass'
            assert max(abs(a-b) for a, b in zip(color.getRgb()[:3], (28, 28, 35))) <= 2, \
                'A glitch slice darkened the background'
        colored_edges = sum(
            max(rendered.pixelColor(x, y).getRgb()[:3]) - min(rendered.pixelColor(x, y).getRgb()[:3]) > 60
            for y in range(int(38*scale), int(56*scale))
            for x in range(int(70*scale), int(125*scale)))
        assert colored_edges > 20, 'Glitch content has no RGB separation'
print('PASS: RGB edges stay coloured and glass opacity is preserved at 100/150/200% scaling', flush=True)

window = StartupWindow()
window.show()
QTest.qWait(100)
assert window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
assert window.brand_label.text() == 'SADM Autorouter'
assert window.startup_font_family == 'Oxanium'
assert QFontInfo(window.percentage.font()).family() == 'Oxanium', 'Bundled startup font fell back'
assert window.percentage.fontMetrics().horizontalAdvance('100%') <= window.percentage.width(), \
    'The large percentage is clipped in the new font'
assert window.brand_icon.text() == '' and not window.brand_icon.pixmap().isNull()
assert window.windowOpacity() == 1.0, 'Text should stay opaque; only the glass surface is translucent'
paint = window.grab().toImage()
dpr = paint.devicePixelRatio()
assert 0 < paint.pixelColor(int(window.width()*.5*dpr), int(window.height()*.7*dpr)).alpha() < 240, \
    'An opaque paint layer is hiding the glass surface'
assert window.width() <= 360 and window.height() <= 150
assert QApplication.topLevelWidgets() == [window], 'The loader created an extra backdrop window'
assert not any('DRAG TO MOVE' in label.text() or 'TO MINIMIZE' in label.text()
               for label in window.findChildren(QLabel))
window.grab().save(str(root / 'output/startup-check' / (
    'qt6-minimal-window-offscreen.png' if args.offscreen else 'qt6-minimal-window.png')))
def capture_preview():
    if not args.native_capture or args.offscreen:
        return window.grab().toImage()
    rect = window.frameGeometry()
    shot = window.screen().grabWindow(0, rect.x(), rect.y(), rect.width(), rect.height()).toImage()
    # The screen crop includes the desktop in the rounded cutouts. Remove only
    # that exterior so the exported preview contains the startup card alone.
    outline = QImage(shot.size(), QImage.Format.Format_ARGB32_Premultiplied)
    outline.setDevicePixelRatio(shot.devicePixelRatio())
    outline.fill(Qt.GlobalColor.transparent)
    painter = QPainter(outline)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setClipRegion(window.mask())
    painter.fillPath(panel_path(QRectF(window.rect()).adjusted(1, 1, -1, -1)), Qt.GlobalColor.white)
    painter.end()
    shot = shot.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    painter = QPainter(shot)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
    painter.drawImage(QPointF(0, 0), outline)
    painter.end()
    return shot


if args.native_capture and not args.offscreen:
    window.raise_()
    window.activateWindow()
    QTest.qWait(300)
    capture_preview().save(str(root / 'output/startup-check/qt6-minimal-native.png'))
    print('Native Acrylic request accepted:', window.card.native_backdrop, flush=True)
if args.record_preview:
    window.set_stage('Loading Fonts', 70)
    import io
    from PIL import Image
    from PyQt6.QtCore import QBuffer, QIODevice
    frames = []
    frame_times = []
    record_until = time.monotonic() + 6
    while time.monotonic() < record_until:
        # Capture only the rounded startup card, including a complete sheen pass.
        encoded = QBuffer()
        encoded.open(QIODevice.OpenModeFlag.WriteOnly)
        capture_preview().save(encoded, 'PNG')
        frames.append(Image.open(io.BytesIO(bytes(encoded.data()))).convert('RGBA'))
        frame_times.append(time.monotonic())
        QTest.qWait(50)
    durations = [max(20, round((end-start)*1000))
                 for start, end in zip(frame_times, frame_times[1:])] + [50]
    frames[0].save(str(root / 'output/startup-check/qt6-startup-rgb-fracture.gif'),
                   save_all=True, append_images=frames[1:], duration=durations, loop=0, disposal=2)
    frames[0].save(str(root / 'output/startup-check/qt6-startup-rgb-fracture.webp'),
                   save_all=True, append_images=frames[1:], duration=durations, loop=0, lossless=True)
window.card.start_sheen()
window.brand_icon.start_burst()
normal_shape = window.mask()
window.ui_glitch.start_burst()
QTest.qWait(45)
assert window.brand_icon.frame > 0
assert window.ui_glitch.frame > 0 and window.ui_glitch.isEnabled()
assert window.mask() != normal_shape, 'The card outline did not distort during the glitch'
assert window.card.sheen_animation.state() == window.card.sheen_animation.State.Running
window.card.sheen_animation.setCurrentTime(1200)
QTest.qWait(30)
window.grab().save(str(root / 'output/startup-check' / (
    'qt6-rgb-fracture-offscreen.png' if args.offscreen else 'qt6-rgb-fracture.png')))
if args.native_capture and not args.offscreen:
    capture_preview().save(str(root / 'output/startup-check/qt6-sheen-peak-native.png'))
assert window.status.text() == ('Loading Fonts' if args.record_preview else 'Preparing App Files'), \
    'Decorative animation changed operational status'
QTest.qWait(250)
assert window.brand_icon.frame == 0
assert window.ui_glitch.frame == 0 and not window.ui_glitch.isEnabled()
assert window.mask() == normal_shape, 'The card outline did not recover after the glitch'
window.ui_glitch.start_burst()
QTest.mouseClick(window.minimize_button, Qt.MouseButton.LeftButton)
QTest.qWait(100)
assert window.isMinimized()
assert not window.ui_glitch.delay.isActive() and not window.ui_glitch.frames.isActive()
assert not window.ui_glitch.isEnabled()
assert window.mask() == card_region(QRectF(window.rect())), 'Minimize left a corrupted card outline'
assert not window.brand_icon.burst_timer.isActive() and not window.progress.timer.isActive()
assert not window.card.sheen_delay.isActive()
assert window.card.sheen_animation.state() == window.card.sheen_animation.State.Stopped
assert window.progress.transition.state() == window.progress.transition.State.Stopped
window.set_stage("Loading Fonts")
assert window.isMinimized(), "Status update restored the minimized window"
window.showNormal()
QTest.qWait(100)
assert not window.isMinimized()
assert window.ui_glitch.delay.isActive()
assert window.card.sheen_delay.isActive()

# Fallback dragging is exercised offscreen, where startSystemMove is absent.
if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
    before = window.pos()
    QTest.mousePress(window.brand_label, Qt.MouseButton.LeftButton, pos=QPoint(10, 10))
    QTest.mouseMove(window.brand_label, QPoint(50, 35))
    QTest.mouseRelease(window.brand_label, Qt.MouseButton.LeftButton, pos=QPoint(50, 35))
    assert window.pos() != before, "Dragging did not move the loader"

controller = StartupController(window, [sys.executable, str(root / "tests/fixtures/startup_qt5_probe.py")], keep_alive=True)

def send(token, event, message, progress=None):
    with socket.create_connection(("127.0.0.1", controller.server.serverPort())) as channel:
        channel.sendall((json.dumps(dict(token=token,event=event,message=message,progress=progress))+'\n').encode())
    QTest.qWait(100)

send("wrong-token", "stage", "Unauthorized")
assert window.status.text() == "Loading Fonts"
send(controller.token, "stage", "Loading Images", 79)
assert window.status.text() == "Loading Images"
assert window.percentage.text() == '79%' and window.progress.value == 79
for estimate in (5, None, True, '90', -1, float('nan'), float('inf')):
    send(controller.token, 'stage', 'Loading Images', estimate)
    assert window.percentage.text() == '79%', 'Progress moved backward or accepted invalid input'
send(controller.token, 'stage', 'Applying Your Theme', 100)
assert window.percentage.text() == '99%', 'Startup claimed completion before the UI was ready'
print("PASS: PyQt6 layout, minimize/restore, dragging, live status, and authenticated IPC", flush=True)
controller.start()
deadline = time.monotonic() + 25
while not controller.ready and not controller.failed and time.monotonic() < deadline:
    QTest.qWait(50)
assert controller.ready and not controller.failed, window.status.text()
assert not window.isVisible(), "Loader stayed visible after the Qt5 window became ready"
assert not window.ui_glitch.isEnabled()
assert not window.ui_glitch.delay.isActive() and not window.ui_glitch.frames.isActive()
assert not window.brand_icon.burst_timer.isActive() and not window.progress.timer.isActive()
assert not window.card.sheen_delay.isActive()
assert window.card.sheen_animation.state() == window.card.sheen_animation.State.Stopped
assert window.percentage.text() == '100%' and window.progress.value == 100
while (controller.process is None or controller.process.poll() is None) and time.monotonic() < deadline:
    QTest.qWait(50)
assert controller.process is not None and controller.process.returncode == 0
assert not any(name == "PyQt5" or name.startswith("PyQt5.") for name in sys.modules)
print("PASS: actual separate Qt5 UI handoff, automatic loader close, and Qt binding isolation", flush=True)

failed_window = StartupWindow()
failed_window.show()
failed_controller = StartupController(failed_window, [str(root / "missing-test-engine.exe")])
failed_controller.start()
deadline = time.monotonic() + 5
while not failed_controller.failed and time.monotonic() < deadline:
    QTest.qWait(20)
assert failed_controller.failed and failed_window.close_button.isVisible()
assert not failed_window.progress.isVisible()
assert not failed_window.percentage.isVisible()
assert not failed_window.card.sheen_delay.isActive()
assert not failed_window.ui_glitch.delay.isActive() and not failed_window.ui_glitch.isEnabled()
failed_window.grab().save(str(root / "output/startup-check/qt6-loading-error.png"))
print("PASS: startup failure stays visible with a working Close control", flush=True)
failed_window.close()
window.finish()
