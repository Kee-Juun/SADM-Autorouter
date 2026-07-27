"""
PyQt Animations Module

Contains animation classes for the SADM Auto-Router application.
"""

import logging
import random
import math

from PyQt5.QtCore import QObject, QTimer, QPropertyAnimation, QEasingCurve, QAbstractAnimation, Qt, QRect
from PyQt5.QtWidgets import QLabel
from PyQt5.QtGui import QColor, QImage, QPainter, QPixmap
from PyQt5.QtWidgets import QGraphicsDropShadowEffect


class IntroAnimation(QObject):
    """Handles video game-style intro animations for the silcrow header"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.current_animation = None
        self.animation_timers = []
        self.is_running = False
        self.on_complete_callback = None
        
    def start_intro_sequence(self, header_label, on_complete=None):
        """Start the intro animation sequence"""
        try:
            if self.is_running:
                logging.warning("Intro animation already running, skipping")
                return
                
            self.is_running = True
            self.on_complete_callback = on_complete
            self.header_label = header_label
            if self.parent and hasattr(self.parent, '_stop_header_badge_bob'):
                self.parent._stop_header_badge_bob()
            if self.parent and hasattr(self.parent, '_stop_header_badge_motion'):
                self.parent._stop_header_badge_motion()
            
            # Store original properties
            self.original_geometry = header_label.geometry()
            self.original_opacity = header_label.windowOpacity()
            
            # Start the sequence - go straight to glitch effect
            self._start_glitch_effect()
            
        except Exception as e:
            logging.error(f"Failed to start intro animation: {e}")
            self._cleanup_and_complete()
    

    
    def _start_glitch_effect(self):
        """Run a corrupted chromatic glitch over the silcrow header."""
        try:
            # Show the original header
            self.header_label.setWindowOpacity(1.0)
            self.header_label.setGeometry(self.original_geometry)
            
            # Store original movie for restoration
            if hasattr(self.header_label, 'movie'):
                self.original_movie = self.header_label.movie()
            
            # Create overlays in the same parent as the header so they sit above it.
            self.glitch_parent = self.header_label.parentWidget() or self.parent
            self.glitch_overlays = []
            for i in range(42):
                overlay = QLabel(self.glitch_parent)
                overlay.setGeometry(self.original_geometry)
                overlay.setAlignment(Qt.AlignCenter)
                overlay.setStyleSheet("background: transparent;")
                overlay.setAttribute(Qt.WA_TransparentForMouseEvents, True)
                overlay.hide()
                self.glitch_overlays.append(overlay)
            
            # Start glitch effect
            self.glitch_frame_count = 0
            self.glitch_hold_frames = 0
            self.glitch_mode_offset = random.randint(0, 6)
            self.glitch_profile = random.choice(("rgb", "fracture", "pixel", "console", "mixed"))
            self.glitch_freeze_chance = random.uniform(0.16, 0.32)
            self.glitch_dropout_chance = random.uniform(0.05, 0.13)
            self.glitch_interval_palette = random.choice((
                (20, 24, 28, 36, 74, 118),
                (18, 22, 31, 48, 92, 146),
                (26, 34, 40, 66, 112, 176),
            ))
            self.glitch_timer = QTimer()
            self.glitch_timer.timeout.connect(self._apply_corrupted_glitch_frame)
            self.glitch_timer.start(random.choice(self.glitch_interval_palette))
            
            # Schedule end of glitch effect
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(self._finish_glitch)
            timer.start(1500)
            self.animation_timers.append(timer)
            
        except Exception as e:
            logging.error(f"Glitch effect failed: {e}")
            self._cleanup_and_complete()

    def _apply_corrupted_glitch_frame(self):
        """Apply displaced icon slices, RGB leaks, and tear strips."""
        try:
            self.glitch_frame_count += 1
            if hasattr(self, 'glitch_timer'):
                self.glitch_timer.setInterval(self._next_glitch_interval())

            if self.glitch_hold_frames > 0:
                self.glitch_hold_frames -= 1
                self._jitter_visible_glitch_overlays()
                return

            snapshot = self._capture_header_snapshot()
            if not snapshot or snapshot.isNull():
                return

            self._reset_glitch_frame()
            mode = (self.glitch_frame_count + self.glitch_mode_offset) % 7
            profile = getattr(self, 'glitch_profile', 'mixed')
            heavy = mode in (0, 2, 5) or profile in ("rgb", "fracture")
            self.header_label.hide()

            if random.random() < getattr(self, 'glitch_dropout_chance', 0.08):
                self._show_signal_dropout()
                self.glitch_hold_frames = random.choice((1, 2, 3))
                return

            if profile in ("rgb", "mixed", "console") or mode in (0, 3, 6):
                self._show_rgb_ghosts(snapshot, heavy=heavy)
            if profile in ("pixel", "fracture", "mixed") or mode in (0, 2, 5):
                self._show_icon_slice_stutter(snapshot, heavy=heavy)
            if profile == "fracture" or mode in (1, 4):
                self._show_icon_split(snapshot, heavy=True)
            if profile == "fracture" or mode in (0, 2, 5, 6):
                self._show_tear_slices(snapshot, heavy=True)

            self._show_rgb_leaks(heavy=heavy or profile == "rgb" or mode in (1, 4))
            self._show_loose_pixels(snapshot, heavy=heavy or profile == "pixel" or mode in (1, 6))
            self._show_console_noise(heavy=heavy or profile == "console" or mode in (1, 5))

            if random.random() < getattr(self, 'glitch_freeze_chance', 0.22):
                self.glitch_hold_frames = random.choice((1, 1, 2, 3))

        except Exception as e:
            logging.error(f"Corrupted glitch frame failed: {e}")

    def _next_glitch_interval(self):
        """Pick an uneven frame interval so the glitch feels laggy."""
        palette = getattr(self, 'glitch_interval_palette', (22, 28, 36, 92, 140))
        if random.random() < 0.18:
            return random.choice((86, 112, 146, 188, 230))
        return random.choice(palette)

    def _jitter_visible_glitch_overlays(self):
        """Nudge a held glitch frame without fully redrawing it."""
        try:
            self.header_label.hide()
            for overlay in getattr(self, 'glitch_overlays', []):
                if not overlay.isVisible():
                    continue
                if random.random() < 0.22:
                    overlay.hide()
                    continue
                geometry = QRect(overlay.geometry())
                geometry.translate(random.choice((-5, -2, 0, 3, 6)), random.choice((-2, 0, 1, 2)))
                overlay.setGeometry(geometry)
                overlay.setWindowOpacity(random.uniform(0.72, 1.0))
                overlay.raise_()
        except Exception as e:
            logging.error(f"Glitch hold jitter failed: {e}")

    def _show_signal_dropout(self):
        """Show a short frozen dropout frame with sparse scanline damage."""
        try:
            for index in range(random.randint(3, 7)):
                overlay = self.glitch_overlays[index]
                width = int(self.original_geometry.width() * random.uniform(0.28, 1.08))
                height = random.randint(3, 14)
                x = self.original_geometry.left() + random.randint(-42, 46)
                y = self.original_geometry.top() + random.randint(0, max(1, self.original_geometry.height() - height))
                color = random.choice((
                    "rgba(0, 0, 0, 210)",
                    "rgba(0, 245, 255, 138)",
                    "rgba(255, 38, 132, 124)",
                    "rgba(248, 250, 252, 92)",
                ))

                overlay.clear()
                overlay.setText("")
                overlay.setGeometry(x, y, width, height)
                overlay.setStyleSheet(f"background-color: {color}; border-radius: 0px;")
                overlay.setWindowOpacity(1.0)
                overlay.show()
                overlay.raise_()

        except Exception as e:
            logging.error(f"Signal dropout glitch failed: {e}")

    def _capture_header_snapshot(self):
        """Capture the current header frame for sliced glitch overlays."""
        try:
            self.header_label.setStyleSheet("")
            self.header_label.setGeometry(self.original_geometry)
            self.header_label.setWindowOpacity(1.0)
            self.header_label.show()
            return self._mask_dark_background(self.header_label.grab())
        except Exception as e:
            logging.error(f"Header snapshot failed: {e}")
            return None

    def _mask_dark_background(self, source):
        """Remove near-black background so glitch layers follow the icon shape."""
        try:
            image = source.toImage().convertToFormat(QImage.Format_ARGB32)
            for y in range(image.height()):
                for x in range(image.width()):
                    color = image.pixelColor(x, y)
                    if color.red() < 12 and color.green() < 12 and color.blue() < 14:
                        color.setAlpha(0)
                        image.setPixelColor(x, y, color)
            return QPixmap.fromImage(image)
        except Exception as e:
            logging.error(f"Dark background mask failed: {e}")
            return source

    def _tinted_pixmap(self, source, color):
        """Create a color-channel copy of the captured icon."""
        tinted = QPixmap(source.size())
        tinted.fill(Qt.transparent)

        painter = QPainter(tinted)
        painter.drawPixmap(0, 0, source)
        painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
        painter.fillRect(tinted.rect(), color)
        painter.end()
        return tinted

    def _show_rgb_ghosts(self, snapshot, heavy=False):
        """Show displaced RGB channel copies of the full icon."""
        try:
            channels = (
                (0, QColor(0, 245, 255, 190), -18 if heavy else -10, -2),
                (1, QColor(255, 38, 132, 170), 18 if heavy else 10, 2),
                (2, QColor(126, 255, 212, 120), random.choice((-8, 8)), 0),
            )

            for overlay_index, color, offset_x, offset_y in channels:
                overlay = self.glitch_overlays[overlay_index]
                target = QRect(self.original_geometry)
                target.translate(offset_x + random.randint(-4, 4), offset_y + random.randint(-2, 2))
                overlay.clear()
                overlay.setPixmap(self._tinted_pixmap(snapshot, color))
                overlay.setScaledContents(True)
                overlay.setGeometry(target)
                overlay.setStyleSheet("background: transparent;")
                overlay.setWindowOpacity(0.9 if heavy else 0.72)
                overlay.show()
                overlay.raise_()

        except Exception as e:
            logging.error(f"RGB ghost glitch failed: {e}")

    def _show_icon_slice_stutter(self, snapshot, heavy=False):
        """Render several thin displaced strips from the icon."""
        try:
            source_width = snapshot.width()
            source_height = snapshot.height()
            slice_count = 8 if heavy else 5

            for index in range(slice_count):
                overlay = self.glitch_overlays[5 + index]
                strip_height = random.randint(6, 18 if heavy else 12)
                source_y = random.randint(0, max(0, source_height - strip_height))
                target_y = self.original_geometry.top() + int(
                    self.original_geometry.height() * (source_y / max(1, source_height))
                )
                offset_x = random.choice((-1, 1)) * random.randint(10, 44 if heavy else 28)
                stretch = random.randint(0, 20 if heavy else 10)

                overlay.clear()
                overlay.setPixmap(snapshot.copy(QRect(0, source_y, source_width, strip_height)))
                overlay.setScaledContents(True)
                overlay.setGeometry(
                    self.original_geometry.left() + offset_x,
                    target_y + random.randint(-2, 2),
                    self.original_geometry.width() + stretch,
                    strip_height + random.randint(0, 3),
                )
                overlay.setStyleSheet("background: transparent;")
                overlay.setWindowOpacity(1.0)
                overlay.show()
                overlay.raise_()

        except Exception as e:
            logging.error(f"Icon slice stutter failed: {e}")

    def _show_loose_pixels(self, snapshot, heavy=False):
        """Scatter loose pixel blocks and tiny captured fragments."""
        try:
            source_width = snapshot.width()
            source_height = snapshot.height()
            pixel_count = 9 if heavy else 7
            colors = (
                "rgba(0, 245, 255, 180)",
                "rgba(255, 38, 132, 170)",
                "rgba(255, 255, 255, 150)",
                "rgba(126, 255, 212, 150)",
            )

            for index in range(pixel_count):
                overlay = self.glitch_overlays[27 + index]
                block_w = random.randint(8, 28 if heavy else 18)
                block_h = random.randint(6, 22 if heavy else 14)
                x = self.original_geometry.left() + random.randint(-24, self.original_geometry.width() + 16)
                y = self.original_geometry.top() + random.randint(0, max(1, self.original_geometry.height() - block_h))

                overlay.clear()
                if random.random() < 0.55:
                    source_x = random.randint(0, max(0, source_width - block_w))
                    source_y = random.randint(0, max(0, source_height - block_h))
                    overlay.setPixmap(snapshot.copy(QRect(source_x, source_y, block_w, block_h)))
                    overlay.setScaledContents(True)
                    overlay.setStyleSheet("background: transparent;")
                else:
                    overlay.setText("")
                    overlay.setStyleSheet(f"background-color: {random.choice(colors)}; border-radius: 0px;")

                overlay.setGeometry(x, y, block_w, block_h)
                overlay.setWindowOpacity(1.0)
                overlay.show()
                overlay.raise_()

        except Exception as e:
            logging.error(f"Loose pixel glitch failed: {e}")

    def _show_console_noise(self, heavy=False):
        """Add DOS-console style character noise and scanline fragments."""
        try:
            colors = (
                "#00F5FF",
                "#FF2684",
                "#7EFFD4",
                "#F8FAFC",
            )
            strip_count = 6 if heavy else 4

            for index in range(strip_count):
                overlay = self.glitch_overlays[36 + index]
                width = int(self.original_geometry.width() * random.uniform(0.42, 1.08))
                height = random.randint(14, 24 if heavy else 18)
                x = self.original_geometry.left() + random.randint(-36 if heavy else -20, 44 if heavy else 24)
                y = self.original_geometry.top() + random.randint(0, max(1, self.original_geometry.height() - height))
                pixmap = QPixmap(width, height)
                pixmap.fill(Qt.transparent)

                painter = QPainter(pixmap)
                painter.fillRect(0, 0, width, height, QColor(0, 0, 0, 170))
                cell_width = random.randint(5, 8)
                for cell_x in range(3, max(4, width - 4), cell_width):
                    if random.random() < 0.22:
                        continue
                    color = QColor(random.choice(colors))
                    color.setAlpha(random.randint(120, 230))
                    cell_top = random.randint(2, max(2, height // 3))
                    cell_height = random.randint(3, max(4, height - cell_top - 1))
                    if random.random() < 0.45:
                        painter.fillRect(cell_x, cell_top, 2, cell_height, color)
                    elif random.random() < 0.7:
                        painter.fillRect(cell_x, cell_top, cell_width - 2, 2, color)
                        painter.fillRect(cell_x, min(height - 3, cell_top + cell_height), cell_width - 2, 2, color)
                    else:
                        painter.fillRect(cell_x, cell_top, 2, 2, color)
                        painter.fillRect(cell_x + 3, cell_top + 4, 2, 2, color)
                        painter.fillRect(cell_x + 1, min(height - 3, cell_top + 8), 3, 2, color)
                painter.end()

                overlay.clear()
                overlay.setPixmap(pixmap)
                overlay.setGeometry(x, y, width, height)
                overlay.setScaledContents(False)
                overlay.setStyleSheet("background: transparent;")
                overlay.setWindowOpacity(0.95)
                overlay.show()
                overlay.raise_()

        except Exception as e:
            logging.error(f"Console noise glitch failed: {e}")

    def _show_icon_split(self, snapshot, heavy=False):
        """Split the captured header into two displaced pieces."""
        try:
            if not snapshot or snapshot.isNull():
                return

            source_width = snapshot.width()
            source_height = snapshot.height()
            if source_width <= 1 or source_height <= 1:
                return

            self.header_label.hide()
            horizontal_split = self.glitch_frame_count % 4 != 0
            displacement = random.randint(24, 44) if heavy else random.randint(14, 26)
            vertical_jitter = random.randint(-6, 6)

            if horizontal_split:
                split_y = random.randint(int(source_height * 0.42), int(source_height * 0.58))
                top_height = split_y
                bottom_height = source_height - split_y
                target_top_height = int(self.original_geometry.height() * (top_height / source_height))
                target_bottom_height = self.original_geometry.height() - target_top_height
                pieces = (
                    (
                        3,
                        QRect(0, 0, source_width, top_height),
                        QRect(
                            self.original_geometry.left() - displacement,
                            self.original_geometry.top() + vertical_jitter,
                            self.original_geometry.width(),
                            target_top_height,
                        ),
                    ),
                    (
                        4,
                        QRect(0, split_y, source_width, bottom_height),
                        QRect(
                            self.original_geometry.left() + displacement,
                            self.original_geometry.top() + target_top_height - vertical_jitter,
                            self.original_geometry.width(),
                            target_bottom_height,
                        ),
                    ),
                )
            else:
                split_x = random.randint(int(source_width * 0.43), int(source_width * 0.57))
                left_width = split_x
                right_width = source_width - split_x
                target_left_width = int(self.original_geometry.width() * (left_width / source_width))
                target_right_width = self.original_geometry.width() - target_left_width
                pieces = (
                    (
                        3,
                        QRect(0, 0, left_width, source_height),
                        QRect(
                            self.original_geometry.left() - displacement,
                            self.original_geometry.top() + vertical_jitter,
                            target_left_width,
                            self.original_geometry.height(),
                        ),
                    ),
                    (
                        4,
                        QRect(split_x, 0, right_width, source_height),
                        QRect(
                            self.original_geometry.left() + target_left_width + displacement,
                            self.original_geometry.top() - vertical_jitter,
                            target_right_width,
                            self.original_geometry.height(),
                        ),
                    ),
                )

            for overlay_index, source_rect, target_rect in pieces:
                overlay = self.glitch_overlays[overlay_index]
                overlay.clear()
                overlay.setPixmap(snapshot.copy(source_rect))
                overlay.setScaledContents(True)
                overlay.setGeometry(target_rect)
                overlay.setStyleSheet("background: transparent;")
                overlay.setWindowOpacity(1.0)
                overlay.show()
                overlay.raise_()

        except Exception as e:
            logging.error(f"Icon split glitch failed: {e}")

    def _show_rgb_leaks(self, heavy=False):
        """Draw displaced RGB leakage bars around the header."""
        try:
            colors = (
                "rgba(0, 245, 255, 118)",
                "rgba(255, 38, 132, 102)",
                "rgba(126, 255, 212, 72)",
            )
            leak_count = 7 if heavy else 4

            for index in range(leak_count):
                overlay = self.glitch_overlays[13 + index]
                height = random.randint(4, 16 if heavy else 9)
                width = int(self.original_geometry.width() * random.uniform(0.52, 1.18))
                x = self.original_geometry.left() + random.randint(
                    -48 if heavy else -24,
                    max(1, self.original_geometry.width() - width + (48 if heavy else 24)),
                )
                y = self.original_geometry.top() + random.randint(
                    8,
                    max(9, self.original_geometry.height() - 10),
                )
                direction = -1 if index % 2 else 1
                x += direction * random.randint(22, 72 if heavy else 42)

                overlay.clear()
                overlay.setGeometry(x, y, width, height)
                overlay.setStyleSheet(f"background-color: {colors[index % len(colors)]}; border-radius: 1px;")
                overlay.setWindowOpacity(1.0)
                overlay.show()
                overlay.raise_()

        except Exception as e:
            logging.error(f"RGB leak glitch failed: {e}")

    def _show_tear_slices(self, snapshot, heavy=False):
        """Tear thin strips from the captured header and offset them."""
        try:
            if not snapshot or snapshot.isNull():
                return

            source_width = snapshot.width()
            source_height = snapshot.height()
            tear_count = 6 if heavy else 3

            for index in range(tear_count):
                overlay = self.glitch_overlays[20 + index]
                strip_height = random.randint(6, 22 if heavy else 13)
                source_y = random.randint(0, max(0, source_height - strip_height))
                target_y = self.original_geometry.top() + int(
                    self.original_geometry.height() * (source_y / max(1, source_height))
                )
                offset_x = random.choice((-1, 1)) * random.randint(30 if heavy else 18, 76 if heavy else 42)
                squeeze = random.randint(0, 24 if heavy else 12)

                overlay.clear()
                overlay.setPixmap(snapshot.copy(QRect(0, source_y, source_width, strip_height)))
                overlay.setScaledContents(True)
                overlay.setGeometry(
                    self.original_geometry.left() + offset_x,
                    target_y,
                    max(1, self.original_geometry.width() - squeeze),
                    strip_height,
                )
                overlay.setStyleSheet("background: transparent;")
                overlay.setWindowOpacity(0.96)
                overlay.show()
                overlay.raise_()

        except Exception as e:
            logging.error(f"Tear slice glitch failed: {e}")

    def _reset_glitch_frame(self):
        """Reset the header after a glitch pulse."""
        try:
            # Hide all glitch overlays
            if hasattr(self, 'glitch_overlays'):
                for overlay in self.glitch_overlays:
                    overlay.hide()
            
            # Reset header to normal
            self.header_label.setStyleSheet("")
            self.header_label.setGeometry(self.original_geometry)
            self.header_label.setWindowOpacity(1.0)
            self.header_label.show()
            
        except Exception as e:
            logging.error(f"Reset glitch frame failed: {e}")
    
    def _finish_glitch(self):
        """Finish glitch effect and complete animation"""
        try:
            # Stop glitch timer
            if hasattr(self, 'glitch_timer'):
                self.glitch_timer.stop()
                delattr(self, 'glitch_timer')
            
            # Remove glitch overlays
            if hasattr(self, 'glitch_overlays'):
                for overlay in self.glitch_overlays:
                    overlay.deleteLater()
                delattr(self, 'glitch_overlays')
            
            # Ensure header is in final normal state
            self.header_label.setStyleSheet("")
            self.header_label.setGeometry(self.original_geometry)
            self.header_label.setWindowOpacity(1.0)
            self.header_label.show()
            
            # Complete the animation
            self._cleanup_and_complete()
            
        except Exception as e:
            logging.error(f"Finish glitch failed: {e}")
            self._cleanup_and_complete()
    
    def _add_glow_effect(self):
        """Add a glowing shadow effect during animation"""
        try:
            glow_effect = QGraphicsDropShadowEffect(self.header_label)
            glow_effect.setBlurRadius(30)
            glow_effect.setColor(QColor(0, 255, 255, 150))  # Cyan glow
            glow_effect.setOffset(0, 0)
            self.header_label.setGraphicsEffect(glow_effect)
            
            # Animate glow intensity
            glow_anim = QPropertyAnimation(glow_effect, b"blurRadius")
            glow_anim.setDuration(800)
            glow_anim.setStartValue(5)
            glow_anim.setEndValue(30)
            glow_anim.setEasingCurve(QEasingCurve.OutCubic)
            glow_anim.start()
            
        except Exception as e:
            logging.error(f"Glow effect failed: {e}")
    
    def _add_color_flash(self):
        """Add a brief color flash effect"""
        try:
            # Create a temporary overlay for color flash
            flash_overlay = QLabel(self.header_label)
            flash_overlay.setGeometry(self.header_label.rect())
            flash_overlay.setStyleSheet("background-color: rgba(255, 255, 0, 0.3); border-radius: 10px;")
            flash_overlay.show()
            
            # Animate flash
            flash_anim = QPropertyAnimation(flash_overlay, b"windowOpacity")
            flash_anim.setDuration(200)
            flash_anim.setStartValue(0.3)
            flash_anim.setEndValue(0.0)
            flash_anim.setEasingCurve(QEasingCurve.OutCubic)
            flash_anim.finished.connect(flash_overlay.deleteLater)
            flash_anim.start()
            
        except Exception as e:
            logging.error(f"Color flash failed: {e}")
    
    def _finish_intro(self):
        """Complete the intro sequence"""
        try:
            # Remove glow effect
            if self.header_label.graphicsEffect():
                self.header_label.setGraphicsEffect(None)
            
            # Ensure final position and opacity
            self.header_label.setGeometry(self.original_geometry)
            self.header_label.setWindowOpacity(1.0)
            
            # Animation completed - header is now in normal state
            
            # Schedule cleanup
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(self._cleanup_and_complete)
            timer.start(500)
            self.animation_timers.append(timer)
            
        except Exception as e:
            logging.error(f"Finish intro failed: {e}")
            self._cleanup_and_complete()
    
    def _add_sparkle_effect(self):
        """Add final sparkle particles"""
        try:
            # Create sparkle particles around the header
            for i in range(8):
                sparkle = QLabel(self.parent)
                sparkle.setText("✨")
                sparkle.setStyleSheet("color: #FFD700; font-size: 16px; background: transparent;")
                sparkle.setAlignment(Qt.AlignCenter)
                
                # Position around header
                angle = (i * 45) * (3.14159 / 180)  # Convert to radians
                radius = 60
                x = self.original_geometry.center().x() + int(radius * math.cos(angle)) - 8
                y = self.original_geometry.center().y() + int(radius * math.sin(angle)) - 8
                sparkle.move(x, y)
                sparkle.show()
                
                # Animate sparkle
                sparkle_anim = QPropertyAnimation(sparkle, b"windowOpacity")
                sparkle_anim.setDuration(800)
                sparkle_anim.setStartValue(1.0)
                sparkle_anim.setEndValue(0.0)
                sparkle_anim.setEasingCurve(QEasingCurve.OutCubic)
                sparkle_anim.finished.connect(sparkle.deleteLater)
                sparkle_anim.start()
                
        except Exception as e:
            logging.error(f"Sparkle effect failed: {e}")
    
    def _cleanup_and_complete(self):
        """Clean up all animations and complete the sequence"""
        try:
            # Stop all timers
            for timer in self.animation_timers:
                if timer.isActive():
                    timer.stop()
            self.animation_timers.clear()
            
            # Stop current animation
            if self.current_animation and self.current_animation.state() == QAbstractAnimation.Running:
                self.current_animation.stop()
            
            # Reset header to normal state
            if hasattr(self, 'header_label') and self.header_label:
                self.header_label.setGeometry(self.original_geometry)
                self.header_label.setWindowOpacity(1.0)
                self.header_label.show()
                if self.header_label.graphicsEffect():
                    self.header_label.setGraphicsEffect(None)
            
            # Mark as complete
            self.is_running = False
            
            # Call completion callback
            if self.on_complete_callback:
                try:
                    self.on_complete_callback()
                except Exception as e:
                    logging.error(f"Completion callback failed: {e}")
                    
        except Exception as e:
            logging.error(f"Cleanup failed: {e}")
            self.is_running = False
    
    def stop_intro(self):
        """Force stop the intro animation"""
        self._cleanup_and_complete()


