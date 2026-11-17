"""Small, native-painted glass surfaces and quiet startup animation."""
import random

from PyQt6.QtCore import QEasingCurve, QElapsedTimer, QPointF, QRectF, Qt, QTimer, QVariantAnimation, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QRegion
from PyQt6.QtWidgets import QFrame, QGraphicsEffect, QLabel, QWidget


def panel_path(rect):
    path = QPainterPath()
    path.addRoundedRect(rect, 14, 14)
    return path


def glitch_slices(rect, frame):
    """Disjoint slices shared by the rendered card and its native window shape."""
    patterns = (
        (0, 4, 0, -4, 0, 3, 0),
        (1, -3, 0, 3, -1, -4, 0),
        (-1, 5, 1, -3, 0, 4, 0),
        (0, -2, -1, 4, 0, -3, 1),
        (0, 2, 0, -2, 0, 2, 0),
    )
    boundaries = [rect.top() + round(rect.height()*part)
                  for part in (0, .22, .34, .65, .77, .83, .90, 1)]
    for index, dx in enumerate(patterns[frame-1]):
        yield QRectF(rect.left(), boundaries[index], rect.width(),
                     boundaries[index+1]-boundaries[index]), dx


def card_region(rect, frame=0):
    source = QRegion(panel_path(rect).toFillPolygon().toPolygon())
    if not frame:
        return source
    result = QRegion()
    for band, dx in glitch_slices(rect, frame):
        result = result.united(source.translated(dx, 0).intersected(QRegion(band.toAlignedRect())))
    return result.intersected(QRegion(rect.toAlignedRect()))


class WindowGlitchEffect(QGraphicsEffect):
    """Briefly distort the rendered card and every child, leaving their data live."""
    frameChanged = pyqtSignal(int)

    def __init__(self, widget):
        super().__init__(widget)
        self.frame = 0
        self._played = False
        self.delay = QTimer(self)
        self.delay.setSingleShot(True)
        self.delay.timeout.connect(self.start_burst)
        self.frames = QTimer(self)
        self.frames.setInterval(35)
        self.frames.timeout.connect(self.advance_burst)
        self.setEnabled(False)

    def resume(self):
        if not self.delay.isActive() and not self.frames.isActive():
            self.delay.start(random.randint(9000, 15000) if self._played else 2800)

    def start_burst(self):
        self.delay.stop()
        widget = self.parent()
        if not widget.isVisible() or widget.window().isMinimized():
            return
        self._played = True
        self.frame = 1
        self.frameChanged.emit(self.frame)
        self.setEnabled(True)
        self.frames.start()
        self.update()

    def advance_burst(self):
        self.frame += 1
        if self.frame > 5:
            self.stop()
            widget = self.parent()
            if widget.isVisible() and not widget.window().isMinimized():
                self.delay.start(random.randint(9000, 15000))
        else:
            self.frameChanged.emit(self.frame)
            self.update()

    def stop(self):
        self.delay.stop()
        self.frames.stop()
        self.frame = 0
        self.setEnabled(False)
        self.frameChanged.emit(0)

    @staticmethod
    def render_frame(image, frame):
        """Separate actual RGB channels, then replace each glass slice once."""
        rect = QRectF(QPointF(), image.deviceIndependentSize())
        # Separate colour from opacity: adding translucent channel images would
        # add the charcoal alpha three times and recreate the dark-band bug.
        rgb = image.toImage().convertToFormat(QImage.Format.Format_RGB32)
        combined = QImage(image.size(), QImage.Format.Format_RGB32)
        combined.setDevicePixelRatio(image.devicePixelRatio())
        combined.fill(Qt.GlobalColor.black)
        compose = QPainter(combined)
        compose.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        separation = (2, -2, 3, -2, 1)[frame-1]
        for color, dx in ((Qt.GlobalColor.red, separation), (Qt.GlobalColor.green, 0),
                          (Qt.GlobalColor.blue, -separation)):
            channel = rgb.copy()
            tint = QPainter(channel)
            tint.setCompositionMode(QPainter.CompositionMode.CompositionMode_Multiply)
            tint.fillRect(rect, color)
            tint.end()
            compose.drawImage(QPointF(dx, 0), channel)
        compose.end()

        split = QPixmap(image.size())
        split.setDevicePixelRatio(image.devicePixelRatio())
        split.fill(Qt.GlobalColor.transparent)
        mask = QPainter(split)
        mask.drawImage(QPointF(), combined)
        mask.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        mask.drawPixmap(QPointF(), image)
        mask.end()

        distorted = QPixmap(image.size())
        distorted.setDevicePixelRatio(image.devicePixelRatio())
        distorted.fill(Qt.GlobalColor.transparent)
        painter = QPainter(distorted)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        for band, dx in glitch_slices(rect, frame):
            painter.setClipRect(band)
            painter.drawPixmap(QPointF(dx, 0), split)
        painter.end()
        return distorted

    def draw(self, painter):
        if not self.frame:
            self.drawSource(painter)
            return
        image, offset = self.sourcePixmap(Qt.CoordinateSystem.LogicalCoordinates,
                                          QGraphicsEffect.PixmapPadMode.NoPad)
        if image.isNull():
            self.drawSource(painter)
            return
        origin = QPointF(offset) if offset is not None else QPointF()
        painter.save()
        painter.setOpacity(1)
        painter.drawPixmap(origin, self.render_frame(image, self.frame))
        painter.restore()


class GlassCard(QFrame):
    def __init__(self):
        super().__init__()
        self.native_backdrop = False
        self._sheen_phase = None
        self._has_sheened = False
        self.sheen_delay = QTimer(self)
        self.sheen_delay.setSingleShot(True)
        self.sheen_delay.timeout.connect(self.start_sheen)
        self.sheen_animation = QVariantAnimation(self)
        self.sheen_animation.setStartValue(0.0)
        self.sheen_animation.setEndValue(1.0)
        self.sheen_animation.setDuration(2400)
        self.sheen_animation.setEasingCurve(QEasingCurve.Type.InOutSine)
        self.sheen_animation.valueChanged.connect(self._set_sheen_phase)
        self.sheen_animation.finished.connect(self._finish_sheen)

    def _set_sheen_phase(self, value):
        self._sheen_phase = value
        self.update()

    def start_sheen(self):
        self.sheen_delay.stop()
        if not self.isVisible() or self.window().isMinimized():
            return
        self._has_sheened = True
        self.sheen_animation.start()

    def _finish_sheen(self):
        self._sheen_phase = None
        self.update()
        if self.isVisible() and not self.window().isMinimized():
            self.sheen_delay.start(random.randint(8000, 13000))

    def resume(self):
        if not self.sheen_delay.isActive() and self.sheen_animation.state() != QVariantAnimation.State.Running:
            self.sheen_delay.start(random.randint(8000, 13000) if self._has_sheened else 1100)

    def stop(self):
        self.sheen_delay.stop()
        self.sheen_animation.stop()
        self._sheen_phase = None
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(.5, .5, -.5, -.5)
        shape = panel_path(r)
        fill = QLinearGradient(r.topLeft(), r.bottomRight())
        # The console uses charcoal at partial alpha. Keep this tint light
        # enough for the system's frosted backdrop to remain visible underneath.
        fill.setColorAt(0, QColor(28, 28, 35, 118 if self.native_backdrop else 190))
        fill.setColorAt(1, QColor(24, 24, 32, 150 if self.native_backdrop else 208))
        p.fillPath(shape, fill)
        if self._sheen_phase is not None:
            # A broad, feathered reflection passes beneath all child widgets.
            # Transparent ends and eased motion keep it from becoming a stripe.
            width = self.width() * .62
            overscan = self.height() * .5
            x = -width - overscan + self._sheen_phase * (self.width() + width + 2*overscan)
            sheen = QLinearGradient(x, 0, x + width, overscan)
            sheen.setColorAt(0, QColor(91, 222, 229, 0))
            sheen.setColorAt(.28, QColor(91, 222, 229, 0))
            sheen.setColorAt(.44, QColor(91, 222, 229, 12))
            sheen.setColorAt(.56, QColor(164, 139, 237, 16))
            sheen.setColorAt(.7, QColor(230, 157, 222, 9))
            sheen.setColorAt(1, QColor(230, 157, 222, 0))
            p.fillPath(shape, sheen)
        # One continuous, softly lit rim gives the glass depth without decoration.
        rim = QLinearGradient(r.topLeft(), r.bottomRight())
        rim.setColorAt(0, QColor(235, 237, 255, 32))
        rim.setColorAt(.45, QColor(205, 210, 232, 14))
        rim.setColorAt(1, QColor(180, 171, 214, 23))
        p.setPen(QPen(rim, 1))
        p.drawPath(shape)


class GlitchLogo(QLabel):
    def __init__(self):
        super().__init__()
        self.frame = 0
        self._ghosts = []
        self.burst_timer = QTimer(self)
        self.burst_timer.setSingleShot(True)
        self.burst_timer.timeout.connect(self.start_burst)
        self.frame_timer = QTimer(self)
        self.frame_timer.setInterval(35)
        self.frame_timer.timeout.connect(self.advance_burst)

    def setPixmap(self, pixmap):
        super().setPixmap(pixmap)
        self._ghosts = []
        for color in ('#49edfa', '#fa59dc'):
            ghost = QPixmap(pixmap.size())
            ghost.setDevicePixelRatio(pixmap.devicePixelRatio())
            ghost.fill(Qt.GlobalColor.transparent)
            p = QPainter(ghost)
            p.drawPixmap(0, 0, pixmap)
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
            p.fillRect(ghost.rect(), QColor(color))
            p.end()
            self._ghosts.append(ghost)

    def resume(self):
        if not self.burst_timer.isActive() and not self.frame_timer.isActive():
            self.burst_timer.start(1800 if not getattr(self, '_played', False) else random.randint(7000, 11000))

    def stop(self):
        self.burst_timer.stop()
        self.frame_timer.stop()
        self.frame = 0
        self.update()

    def start_burst(self):
        self.burst_timer.stop()
        if not self.isVisible() or self.window().isMinimized():
            return
        self._played = True
        self.frame = 1
        self.frame_timer.start()
        self.update()

    def advance_burst(self):
        self.frame += 1
        if self.frame > 4:
            self.frame_timer.stop()
            self.frame = 0
            self.burst_timer.start(random.randint(7000, 11000))
        self.update()

    def paintEvent(self, event):
        if not self.frame or not self._ghosts:
            return super().paintEvent(event)
        p = QPainter(self)
        image = self.pixmap()
        size = image.deviceIndependentSize()
        x, y = (self.width()-size.width())/2, (self.height()-size.height())/2
        shift = (1, -1, 1.5, -.5)[self.frame-1]
        p.setOpacity(.28)
        p.drawPixmap(QPointF(x-1, y), self._ghosts[0])
        p.drawPixmap(QPointF(x+1, y), self._ghosts[1])
        p.setOpacity(1)
        p.drawPixmap(QPointF(x, y), image)
        p.setClipRect(QRectF(x-2, y+size.height()*.43, size.width()+4, 2))
        p.drawPixmap(QPointF(x+shift, y), image)


class ActivityStrip(QWidget):
    """A milestone-based fill with a soft moving highlight."""
    def __init__(self):
        super().__init__()
        self.phase = 0.0
        self.value = 0
        self._paint_value = 0.0
        self.transition = QVariantAnimation(self)
        self.transition.setDuration(320)
        self.transition.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.transition.valueChanged.connect(self._set_paint_value)
        self.clock = QElapsedTimer()
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self.advance)
        self.setAccessibleName('Preparing app files')

    def _set_paint_value(self, value):
        self._paint_value = value
        self.update()

    def set_progress(self, value):
        self.value = min(100, max(0, int(value)))
        self.setAccessibleName(f'Estimated startup progress: {self.value}%')
        self.transition.stop()
        if self.isVisible() and self.timer.isActive():
            self.transition.setStartValue(self._paint_value)
            self.transition.setEndValue(float(self.value))
            self.transition.start()
        else:
            self._set_paint_value(float(self.value))

    def advance(self):
        self.phase = (self.clock.elapsed() % 1900) / 1900
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        track = QPainterPath()
        track.addRoundedRect(QRectF(self.rect()), self.height()/2, self.height()/2)
        p.fillPath(track, QColor(215, 220, 244, 20))
        p.setClipPath(track)
        if self.value:
            completed = QPainterPath()
            completed.addRoundedRect(QRectF(0, 0, self.width()*self._paint_value/100, self.height()),
                                     self.height()/2, self.height()/2)
            tint = QLinearGradient(0, 0, self.width(), 0)
            tint.setColorAt(0, QColor(128, 207, 210, 175))
            tint.setColorAt(1, QColor(184, 170, 238, 210))
            p.fillPath(completed, tint)
            p.setClipPath(completed, Qt.ClipOperation.IntersectClip)
        width = self.width() * .48
        x = self.phase * (self.width() + width) - width
        sweep = QLinearGradient(x, 0, x + width, 0)
        sweep.setColorAt(0, QColor(128, 207, 210, 0))
        sweep.setColorAt(.4, QColor(128, 207, 210, 180))
        sweep.setColorAt(.7, QColor(184, 170, 238, 240))
        sweep.setColorAt(1, QColor(184, 170, 238, 0))
        p.fillRect(QRectF(x, 0, width, self.height()), sweep)

    def resume(self):
        self.clock.start()
        self.timer.start()

    def stop(self):
        self.timer.stop()
        self.transition.stop()
        self._set_paint_value(float(self.value))
