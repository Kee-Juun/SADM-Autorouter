"""
Reusable PyQt widgets for the SADM Autorouter GUI.

This module contains visual components that are shared across the
PyQt application, extracted from smducar_pyqt.py to keep the main
GUI file slimmer and more focused on orchestration.
"""

import random

from PyQt5.QtCore import (
    Qt,
    QTimer,
    QRect,
    QRectF,
    QEasingCurve,
    QPropertyAnimation,
    pyqtProperty,
)
from PyQt5.QtGui import (
    QPainter,
    QColor,
    QBrush,
    QLinearGradient,
    QPainterPath,
    QPen,
    QFont,
    QPixmap,
)
from PyQt5.QtWidgets import (
    QComboBox,
    QProgressBar,
    QStyle,
    QStyleOptionComboBox,
    QStylePainter,
    QWidget,
    QFrame,
    QLabel,
    QVBoxLayout,
    QPushButton,
    QSizePolicy,
)

from .badge_effects import BadgeEffectLayer, has_badge_effect


class CenteredComboBox(QComboBox):
    """QComboBox that paints the selected text centered inside the control."""

    def paintEvent(self, event):
        painter = QStylePainter(self)
        option = QStyleOptionComboBox()
        self.initStyleOption(option)

        current_text = option.currentText
        option.currentText = ""
        option.subControls = QStyle.SC_ComboBoxFrame | QStyle.SC_ComboBoxEditField
        painter.drawComplexControl(QStyle.CC_ComboBox, option)

        text_rect = self.rect().adjusted(28, 0, -28, 0)
        text_color = QColor(255, 255, 255, 245 if self.isEnabled() else 140)
        painter.setPen(text_color)
        painter.drawText(text_rect, Qt.AlignCenter | Qt.AlignVCenter, current_text)

        arrow_color = QColor(255, 255, 255, 220 if self.isEnabled() else 120)
        painter.setPen(QPen(arrow_color, 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        center_x = self.width() - 17
        center_y = self.height() // 2 + 1
        painter.drawLine(center_x - 4, center_y - 2, center_x, center_y + 2)
        painter.drawLine(center_x, center_y + 2, center_x + 4, center_y - 2)


class PillProgressBar(QProgressBar):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setTextVisible(False)
        self.setFixedHeight(30)
        self.setMinimum(0)
        self.setMaximum(100)
        self.setFont(QFont("Axiforma", 15, QFont.Bold))
        self.setStyleSheet("")  # Remove default QSS for chunk
        self.track_color = QColor("#F5F1E9")
        self.border_color = QColor("#444444")
        self.fill_start_color = QColor("#FF00FF")
        self.fill_mid_color = None
        self.fill_end_color = QColor("#00FFFF")
        self.shimmer_color = QColor(255, 255, 255, 80)

        # Shimmer animation properties
        self.shimmer_position = 0.0  # Position of shimmer (0.0 to 1.0)
        self.shimmer_width = 0.3  # Width of shimmer effect (30% of progress bar)
        self.shimmer_speed = 0.02  # Speed of shimmer movement
        self.shimmer_active = False  # Whether shimmer is currently active
        self.effect_mode = "shimmer"
        self._bubbles = []
        self._bubble_cooldown = random.randint(70, 190)
        self._bubble_burst_remaining = 0
        self._bubble_burst_gap = 0
        self.shimmer_timer = QTimer()
        self.shimmer_timer.timeout.connect(self.update_shimmer)
        self.shimmer_timer.setInterval(16)  # ~60 FPS

        # Set initial value after shimmer timer is created
        self.setValue(0)

    def set_theme_colors(self, track=None, border=None, fill_start=None, fill_mid=None, fill_end=None, shimmer=None):
        """Apply visual theme colors used by the custom painter."""
        if track:
            self.track_color = QColor(track)
        if border:
            self.border_color = QColor(border)
        if fill_start:
            self.fill_start_color = QColor(fill_start)
        self.fill_mid_color = QColor(fill_mid) if fill_mid else None
        if fill_end:
            self.fill_end_color = QColor(fill_end)
        if shimmer:
            self.shimmer_color = QColor(shimmer)
        self.update()

    def set_effect_mode(self, mode):
        """Switch between shimmer and randomized bubble effects."""
        mode = str(mode or "shimmer").lower()
        self.effect_mode = "bubbles" if mode == "bubbles" else "shimmer"
        self._bubbles = []
        self._bubble_cooldown = random.randint(70, 190)
        self._bubble_burst_remaining = 0
        self._bubble_burst_gap = 0
        if self.value() > self.minimum() and self.value() < self.maximum():
            self.start_shimmer()
        else:
            self.stop_shimmer()
        self.update()

    def set_shimmer_speed(self, speed):
        """Set shimmer speed while keeping the original speed as the upper bound."""
        try:
            speed = float(speed)
        except (TypeError, ValueError):
            speed = 0.02
        self.shimmer_speed = max(0.001, min(0.02, speed))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect()
        radius = rect.height() / 2
        # Draw background (ash color)
        painter.setBrush(self.track_color)
        painter.setPen(self.border_color)
        painter.drawRoundedRect(rect, radius, radius)
        # Draw fill (gradient)
        progress = (
            (self.value() - self.minimum()) / (self.maximum() - self.minimum())
            if self.maximum() > self.minimum()
            else 0
        )
        if progress > 0:
            fill_rect = QRectF(rect)
            fill_rect.setWidth(rect.width() * progress)
            grad = QLinearGradient(fill_rect.topLeft(), fill_rect.topRight())
            grad.setColorAt(0, self.fill_start_color)
            if self.fill_mid_color:
                grad.setColorAt(0.52, self.fill_mid_color)
            grad.setColorAt(1, self.fill_end_color)
            painter.setBrush(QBrush(grad))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(fill_rect, radius, radius)
        # No text drawing - we want a clean progress bar without percentage

        # Draw shimmer or bubble effect if active.
        if self.shimmer_active and progress > 0 and self.effect_mode == "shimmer":
            self.draw_shimmer(painter, rect, radius, progress)
        elif self.shimmer_active and progress > 0 and self.effect_mode == "bubbles":
            self.draw_bubbles(painter, rect, radius, progress)
        if self.effect_mode == "bubbles":
            self.draw_test_tube_glass(painter, rect, radius, progress)

    def draw_test_tube_glass(self, painter, rect, radius, progress):
        """Add a restrained glass-tube finish around the XP bar."""
        painter.save()
        painter.setPen(Qt.NoPen)

        top_highlight = QRectF(
            rect.x() + 5,
            rect.y() + 2,
            max(0, rect.width() - 10),
            max(1, rect.height() * 0.28),
        )
        highlight = QLinearGradient(top_highlight.topLeft(), top_highlight.bottomLeft())
        highlight.setColorAt(0, QColor(255, 255, 255, 68))
        highlight.setColorAt(1, QColor(255, 255, 255, 0))
        painter.setBrush(QBrush(highlight))
        painter.drawRoundedRect(top_highlight, radius * 0.65, radius * 0.65)

        if progress > 0:
            fill_width = rect.width() * progress
            bottom_shade = QRectF(rect.x(), rect.center().y(), fill_width, rect.height() * 0.48)
            shade = QLinearGradient(bottom_shade.topLeft(), bottom_shade.bottomLeft())
            shade.setColorAt(0, QColor(0, 0, 0, 0))
            shade.setColorAt(1, QColor(0, 35, 55, 44))
            painter.setBrush(QBrush(shade))
            painter.drawRoundedRect(bottom_shade, radius, radius)

        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(255, 255, 255, 86), 1))
        painter.drawRoundedRect(rect.adjusted(2, 2, -2, -2), max(0, radius - 2), max(0, radius - 2))
        painter.restore()

    def draw_shimmer(self, painter, rect, radius, progress):
        """Draw the shimmer effect on top of the progress fill"""
        # Calculate shimmer position within the filled area
        shimmer_start = self.shimmer_position * rect.width()
        shimmer_end = shimmer_start + (self.shimmer_width * rect.width())

        # Create shimmer gradient
        shimmer_grad = QLinearGradient(shimmer_start, 0, shimmer_end, 0)
        shimmer_grad.setColorAt(0, QColor(255, 255, 255, 0))  # Transparent
        shimmer_grad.setColorAt(0.3, self.shimmer_color)
        shimmer_grad.setColorAt(0.7, self.shimmer_color)
        shimmer_grad.setColorAt(1, QColor(255, 255, 255, 0))  # Transparent

        # Only draw shimmer within the filled area
        fill_width = rect.width() * progress
        if shimmer_start < fill_width:
            # Create a path that clips the shimmer to the pill shape
            # Create the filled area path (pill shape)
            fill_path = QPainterPath()
            fill_rect = QRectF(rect.x(), rect.y(), fill_width, rect.height())
            fill_path.addRoundedRect(fill_rect, radius, radius)

            # Create the shimmer area path
            shimmer_rect = QRectF(
                shimmer_start, rect.y(), self.shimmer_width * rect.width(), rect.height()
            )
            if shimmer_end > fill_width:
                shimmer_rect.setWidth(fill_width - shimmer_start)

            shimmer_path = QPainterPath()
            shimmer_path.addRoundedRect(shimmer_rect, radius, radius)

            # Intersect the paths to clip shimmer to filled area
            clipped_path = fill_path.intersected(shimmer_path)

            # Draw the shimmer with proper clipping
            painter.setBrush(QBrush(shimmer_grad))
            painter.setPen(Qt.NoPen)
            painter.drawPath(clipped_path)

    def draw_bubbles(self, painter, rect, radius, progress):
        """Draw translucent chemical bubbles clipped inside the filled XP tube."""
        fill_width = rect.width() * progress
        if fill_width <= 3:
            return

        fill_path = QPainterPath()
        fill_path.addRoundedRect(QRectF(rect.x(), rect.y(), fill_width, rect.height()), radius, radius)

        painter.save()
        painter.setClipPath(fill_path)
        for bubble in self._bubbles:
            alpha = max(0.0, min(1.0, bubble["life"] / bubble["max_life"]))
            pop = 1.0 - alpha
            x = rect.x() + bubble["x"] * fill_width
            y = rect.y() + bubble["y"] * rect.height()
            r = bubble["radius"] * (1.0 + (0.45 * pop))
            color = bubble["color"]

            fill_color = QColor(color)
            fill_color.setAlphaF(0.16 + (0.32 * alpha))
            edge_color = QColor(color)
            edge_color.setAlphaF(0.38 + (0.42 * alpha))
            shine_color = QColor(255, 255, 255, round(80 + (95 * alpha)))

            painter.setBrush(QBrush(fill_color))
            painter.setPen(QPen(edge_color, max(1, r * 0.18)))
            painter.drawEllipse(QRectF(x - r, y - r, r * 2, r * 2))

            if pop > 0.78:
                ring_color = QColor(color)
                ring_color.setAlphaF(max(0.0, 0.38 * (1.0 - ((pop - 0.78) / 0.22))))
                painter.setBrush(Qt.NoBrush)
                painter.setPen(QPen(ring_color, 1))
                ring_radius = r * (1.2 + (pop * 0.9))
                painter.drawEllipse(QRectF(x - ring_radius, y - ring_radius, ring_radius * 2, ring_radius * 2))
            else:
                painter.setBrush(QBrush(shine_color))
                painter.setPen(Qt.NoPen)
                shine_radius = max(1.0, r * 0.22)
                painter.drawEllipse(
                    QRectF(
                        x - (r * 0.36),
                        y - (r * 0.42),
                        shine_radius,
                        shine_radius,
                    )
                )
        painter.restore()

    def update_shimmer(self):
        """Update shimmer position for animation"""
        if self.shimmer_active and self.effect_mode == "bubbles":
            self.update_bubbles()
            self.update()
        elif self.shimmer_active:
            self.shimmer_position += self.shimmer_speed
            if self.shimmer_position > 1.0:
                self.shimmer_position = -self.shimmer_width  # Reset to start
            self.update()  # Trigger repaint

    def update_bubbles(self):
        """Advance bubbles and occasionally spawn randomized quiet bursts."""
        progress = (
            (self.value() - self.minimum()) / (self.maximum() - self.minimum())
            if self.maximum() > self.minimum()
            else 0
        )
        progress = max(0.0, min(1.0, progress))
        next_bubbles = []
        for bubble in self._bubbles:
            bubble["life"] -= 1
            bubble["x"] += bubble["dx"]
            bubble["y"] += bubble["dy"]
            bubble["radius"] += bubble["growth"]
            if bubble["life"] > 0 and bubble["x"] < 1.03 and 0.03 < bubble["y"] < 0.97:
                next_bubbles.append(bubble)
        self._bubbles = next_bubbles

        if progress <= 0:
            return

        if self._bubble_burst_remaining > 0:
            if self._bubble_burst_gap > 0:
                self._bubble_burst_gap -= 1
                return
            self.spawn_bubble(progress)
            if random.random() < 0.44:
                self.spawn_bubble(progress)
            self._bubble_burst_remaining -= 1
            self._bubble_burst_gap = random.randint(3, 12)
            if self._bubble_burst_remaining <= 0:
                self._bubble_cooldown = random.randint(95, 245)
            return

        self._bubble_cooldown -= 1
        if self._bubble_cooldown <= 0:
            self._bubble_burst_remaining = random.randint(2, 6)
            if progress > 0.75:
                self._bubble_burst_remaining += random.randint(1, 3)
            self._bubble_burst_gap = 0

    def spawn_bubble(self, progress):
        """Create one bubble with randomized size, color, path, and pop timing."""
        if len(self._bubbles) >= 14:
            return
        start_x = random.uniform(0.02, min(0.76, max(0.08, progress - 0.04)))
        colors = (
            QColor("#D9FFF7"),
            QColor("#A9F8FF"),
            QColor("#8AFFD0"),
            QColor("#C7FF8A"),
            QColor("#FFFFFF"),
        )
        life = random.randint(34, 84)
        self._bubbles.append({
            "x": start_x,
            "y": random.uniform(0.34, 0.78),
            "dx": random.uniform(0.0024, 0.0072) * (0.85 + progress),
            "dy": random.uniform(-0.0046, -0.0012),
            "radius": random.uniform(1.4, 3.8),
            "growth": random.uniform(0.004, 0.018),
            "life": life,
            "max_life": life,
            "color": random.choice(colors),
        })

    def start_shimmer(self):
        """Start the shimmer animation"""
        self.shimmer_active = True
        self.shimmer_position = -self.shimmer_width  # Start off-screen
        self.shimmer_timer.start()

    def stop_shimmer(self):
        """Stop the shimmer animation"""
        self.shimmer_active = False
        self.shimmer_timer.stop()
        self.update()  # Final repaint to remove shimmer

    def setValue(self, value):
        """Override setValue to automatically control shimmer animation"""
        old_value = self.value()
        super().setValue(value)

        # Start shimmer when progress begins (value > 0)
        if old_value == 0 and value > 0:
            self.start_shimmer()
        # Stop shimmer when progress completes (value >= maximum) or resets (value == 0)
        elif value >= self.maximum() or value == 0:
            self.stop_shimmer()


class CompactToggle(QWidget):
    def __init__(self, gif_on_path, gif_off_path, initial_state, parent=None, on_toggle=None):
        super().__init__(parent)
        self.on_toggle = on_toggle
        self.state = initial_state

        # Compact dimensions
        self.setFixedSize(60, 30)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        # Animation properties
        self._thumb_position = 32 if initial_state else 2  # Adjusted for better positioning
        self.animation = QPropertyAnimation(self, b"thumb_position")
        self.animation.setDuration(200)  # 200ms animation
        self.animation.setEasingCurve(QEasingCurve.OutCubic)

        # Flag to track programmatic changes
        self._programmatic_change = False

        # Set initial state
        self.set_state(self.state, play_animation=False)

        # Enable mouse tracking for hover effects
        self.setMouseTracking(True)
        self.hovered = False

    def mousePressEvent(self, event):
        if not self.isEnabled():
            event.accept()
            return

        if event.button() == Qt.LeftButton:
            self.play_toggle_animation()

    def enterEvent(self, event):
        self.hovered = True
        self.update()

    def leaveEvent(self, event):
        self.hovered = False
        self.update()

    def play_toggle_animation(self, target_state=None):
        if target_state is not None:
            # Set to specific target state
            target_position = 32 if target_state else 2
        else:
            # Toggle current state
            target_position = 2 if self.state else 32  # Adjusted for better positioning

        self.animation.setStartValue(self._thumb_position)
        self.animation.setEndValue(target_position)
        self.animation.start()

    def get_thumb_position(self):
        return self._thumb_position

    def set_thumb_position(self, position):
        self._thumb_position = position
        self.update()

    def on_animation_finished(self):
        # Determine the new state based on thumb position
        new_state = self._thumb_position > 17  # If thumb is in the right half, it's ON
        self.state = new_state

        # Check if this was a programmatic change
        if self._programmatic_change:
            self._programmatic_change = False
        elif self.on_toggle:
            self.on_toggle(self.state)

    def set_state(self, state, play_animation=False):
        if play_animation:
            # Mark as programmatic change to prevent callback
            self._programmatic_change = True
            self.play_toggle_animation(target_state=state)
        else:
            self.state = state
            self._thumb_position = 32 if state else 2  # Adjusted for better positioning
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Calculate dimensions
        width, height = self.width(), self.height()
        radius = height // 2

        # Background (track)
        if self.state:
            # ON state - gradient background
            gradient = QLinearGradient(0, 0, width, 0)
            gradient.setColorAt(0, QColor("#4CAF50"))  # Green
            gradient.setColorAt(1, QColor("#45A049"))  # Darker green
            painter.setBrush(QBrush(gradient))
            painter.setPen(QPen(QColor("#2E7D32"), 1))  # Dark green border
        else:
            # OFF state - gray background
            painter.setBrush(QBrush(QColor("#E0E0E0")))
            painter.setPen(QPen(QColor("#BDBDBD"), 1))  # Light gray border

        painter.drawRoundedRect(0, 0, width, height, radius, radius)

        # Thumb (sliding circle)
        thumb_size = height - 6  # Slightly smaller for better fit
        thumb_x = self._thumb_position
        thumb_y = 3  # Centered vertically

        # Thumb shadow
        shadow_color = QColor(0, 0, 0, 30)
        painter.setBrush(QBrush(shadow_color))
        painter.drawEllipse(thumb_x + 1, thumb_y + 1, thumb_size, thumb_size)

        # Thumb
        if self.hovered:
            painter.setBrush(QBrush(QColor("#FFFFFF")))
        else:
            painter.setBrush(QBrush(QColor("#F5F5F5")))

        painter.setPen(QPen(QColor("#CCCCCC"), 1))
        painter.drawEllipse(thumb_x, thumb_y, thumb_size, thumb_size)

        # Connect animation finished signal
        if not hasattr(self, "_animation_connected"):
            self.animation.finished.connect(self.on_animation_finished)
            self._animation_connected = True

    # Define the thumb_position property for animation (after methods are defined)
    thumb_position = pyqtProperty(int, get_thumb_position, set_thumb_position)


class FrostedFrame(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.background = None

    def set_background(self, pixmap):
        self.background = pixmap
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if self.background:
            painter.drawPixmap(0, 0, self.background)
        super().paintEvent(event)


class GoldenReplayButton(QPushButton):
    def __init__(self, parent=None):
        super().__init__("⟲", parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(
            """
            QPushButton {
                background-color: transparent;
                font-size: 120px;
                border: none;
                font-weight: bold;
            }
        """
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Shadow layer
        painter.setPen(QPen(QColor(0, 0, 0, 120), 1))
        painter.setFont(QFont("Segoe UI Emoji", 120, QFont.Bold))
        painter.drawText(self.rect().translated(3, 3), Qt.AlignCenter, "⟲")

        # Main icon layer
        color = "#FF8C00" if self.underMouse() else "#FFD700"
        painter.setPen(QColor(color))
        painter.drawText(self.rect(), Qt.AlignCenter, "⟲")


class CustomTooltipWidget(QFrame):
    def __init__(
        self,
        parent=None,
        preview=None,
        emoji=None,
        font_preview_text=None,
        font_family=None,
        reward_id=None,
        reward_type=None,
        name="",
        description="",
        price=None,
        margins=(18, 18, 18, 18),
    ):
        super().__init__(parent)
        self.setObjectName("CustomTooltipWidget")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet(
            """
            #CustomTooltipWidget {
                border-radius: 16px;
                border: 2px solid #A259F7;
            }
        """
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*margins)
        layout.setSpacing(10)
        # Preview
        if preview:
            is_badge_preview = reward_type == "badge" and has_badge_effect(reward_id)
            preview_frame = QFrame()
            preview_frame.setFixedSize(260, 180)
            preview_frame.setStyleSheet("background: transparent; border: none;")

            img_label = QLabel(preview_frame)
            img_label.setGeometry(0, 0, 260, 180)
            pix = QPixmap(preview)
            img_label.setPixmap(
                pix.scaled(260, 180, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
            img_label.setAlignment(Qt.AlignCenter)
            img_label.setStyleSheet("background: transparent; border: none;")

            if is_badge_preview:
                effect_layer = BadgeEffectLayer(preview_frame, reward_id=reward_id)
                effect_layer.setGeometry(0, 0, 260, 180)
                effect_layer.raise_()
                effect_layer.start()
                preview_frame._badge_effect_layer = effect_layer

            layout.addWidget(preview_frame, alignment=Qt.AlignCenter)
        elif font_preview_text:
            family = str(font_family or "Segoe UI").replace('"', "").replace("'", "")
            font_label = QLabel(font_preview_text)
            font_label.setFixedSize(260, 120)
            font_label.setAlignment(Qt.AlignCenter)
            font_label.setWordWrap(True)
            font_label.setFont(QFont(family, 26, QFont.Bold))
            font_label.setStyleSheet(
                f"""
                QLabel {{
                    color: #FFFFFF;
                    font-family: "{family}";
                    font-size: 26px;
                    font-weight: 900;
                    padding: 8px;
                    background: rgba(255, 255, 255, 0.08);
                    border: 1px solid rgba(255, 255, 255, 0.22);
                    border-radius: 14px;
                }}
                """
            )
            layout.addWidget(font_label, alignment=Qt.AlignCenter)
        elif emoji:
            emoji_label = QLabel(emoji)
            emoji_label.setFont(QFont("Segoe UI Emoji", 48, QFont.Bold))
            emoji_label.setAlignment(Qt.AlignCenter)
            if emoji == "❤️":
                emoji_label.setStyleSheet("color: #FF2F40;")
            layout.addWidget(emoji_label)
        # Name
        if name:
            name_label = QLabel(name)
            name_label.setStyleSheet(
                "font-size: 20px; font-weight: bold; color: #FFD700; text-align: center;"
            )
            name_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(name_label)
        # Description
        if description:
            desc_label = QLabel(description)
            desc_label.setStyleSheet(
                "font-size: 14px; color: #CCCCCC; padding: 6px 0px;"
            )
            desc_label.setWordWrap(True)
            layout.addWidget(desc_label)
        # Price
        if price is not None:
            price_label = QLabel(f"💰 {price} coins")
            price_label.setStyleSheet(
                "font-size: 15px; color: #FFD700; font-weight: bold;"
            )
            price_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(price_label)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect()
        color = QColor(162, 89, 247, 235)  # semi-transparent purple
        painter.setBrush(color)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(rect, 16, 16)
        super().paintEvent(event)


class OverlayWidget(QWidget):
    """A simple overlay widget that displays a 'Coming Soon' message."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setStyleSheet('background: rgba(0, 40, 80, 220); border-radius: 8px;')
        self.label = QLabel('Coming Soon 🛠️', self)
        self.label.setStyleSheet('color: #fff; font-size: 20px; font-weight: bold;')
        self.label.setAlignment(Qt.AlignCenter)
    
    def resizeEvent(self, event):
        self.label.setGeometry(0, 0, self.width(), self.height())
        super().resizeEvent(event)

