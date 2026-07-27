"""
Tetris Game Module

Contains the TetrisGame class for the SADM Auto-Router application.
"""

import os
import random
import math
import logging
from datetime import datetime
from pathlib import Path

from PyQt5.QtWidgets import (
    QMainWindow, QPushButton, QLabel, QMessageBox, QDialog
)
from PyQt5.QtCore import (
    Qt, QTimer, QBasicTimer, QEvent, QPoint, QPropertyAnimation, QRect, QSize
)
from PyQt5.QtGui import (
    QPainter, QColor, QPen, QFont, QPixmap, QMovie
)
from PyQt5.QtWidgets import QGraphicsDropShadowEffect

# Import from other modules
from core.smducar_config import resource_path
from .pyqt_widgets import GoldenReplayButton
from .pyqt_dialogs import ModernConfirmDialog, NotificationPopup
from utils.rewards import load_user_rewards, save_user_rewards

# Define asset paths (same as in smducar_pyqt.py)
ASSETS_DIR = Path(resource_path("assets"))
IMAGES_DIR = ASSETS_DIR / "images"
GIFS_DIR = ASSETS_DIR / "gifs"

class TetrisGame(QMainWindow):
    HIGHSCORE_FILE = str(Path("assets/scores/tetris_highscore.txt"))

    def __init__(self):
        super().__init__()
        self.high_score = self.load_high_score()
        self.new_high_score = False
        self.initUI()
        self.combo_popup = None
        self.combo_animation = None
        self.consecutive_clears = 0
        self.held_piece = None
        self.can_hold = True
        self.next_piece = self.new_piece()
        self.explosion_particles = []  # Store explosion particles
        self.explosion_timer = QTimer(self)
        self.explosion_timer.timeout.connect(self.update_explosion)
        self.explosion_timer.setInterval(16)  # ~60 FPS
        
        # Confetti system for coin rewards
        self.confetti_particles = []
        self.confetti_timer = QTimer(self)
        self.confetti_timer.timeout.connect(self.update_confetti)
        self.confetti_timer.setInterval(16)  # ~60 FPS
        
        self.game_over = False
        self.ghost_piece = None
        self.ghost_piece_pos = None
        self.show_ghost = True  # Toggle for ghost piece visibility
        self.spin_detection_enabled = True  # Enable spin detection
        self.last_action = 'none'  # Track last action for SRS spin detection
        
        # Track the last coin milestone shown to prevent duplicates
        self.last_coin_milestone_shown = 0

        # Load piece images
        self.piece_images = {
            'I': QPixmap(str(IMAGES_DIR / "i piece.jpg")),
            'O': QPixmap(str(IMAGES_DIR / "o piece.jpg")),
            'T': QPixmap(str(IMAGES_DIR / "t piece.jpg")),
            'S': QPixmap(str(IMAGES_DIR / "s piece.jpg")),
            'Z': QPixmap(str(IMAGES_DIR / "z piece.jpg")),
            'J': QPixmap(str(IMAGES_DIR / "j piece.jpg")),
            'L': QPixmap(str(IMAGES_DIR / "l piece.jpg"))
        }

    def initUI(self):
        self.setWindowTitle('Tetris')
        self.setFixedSize(800, 800)
        self.setStyleSheet("background-color: #2D2D2D;")

        # Game board dimensions
        self.BOARD_WIDTH = 10
        self.BOARD_HEIGHT = 20
        self.BLOCK_SIZE = 35

        # Calculate game area position
        self.GAME_AREA_X = 50
        self.GAME_AREA_Y = 50

        # Calculate info panel position
        self.INFO_PANEL_X = self.GAME_AREA_X + (self.BOARD_WIDTH * self.BLOCK_SIZE) + 40
        self.INFO_PANEL_Y = 50

        # Initialize game state
        self.board = [[0 for _ in range(self.BOARD_WIDTH)] for _ in range(self.BOARD_HEIGHT)]
        self.current_piece = self.new_piece()
        self.next_piece = self.new_piece()
        self.game_over = False
        self.score = 0
        self.level = 1
        self.lines_cleared = 0
        self.consecutive_clears = 0
        self.held_piece = None
        self.can_hold = True
        self.start_time = datetime.now()
        self.clearing_rows = []
        self.clear_timer = QTimer(self)
        self.clear_timer.timeout.connect(self.update_clear_animation)
        self.clear_timer.setInterval(100)  # Reduced to 100ms for faster flash

        # Create info button
        self.info_btn = QPushButton("(i)", self)
        self.info_btn.setStyleSheet("""
            QPushButton {
                color: white;
                background: transparent;
                border: none;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                color: #00FFFF;
            }
        """)
        self.info_btn.setCursor(Qt.PointingHandCursor)
        self.info_btn.clicked.connect(self.show_instructions)
        self.info_btn.setGeometry(770, 10, 20, 20)
        self.info_btn.setFocusPolicy(Qt.NoFocus)
        self.info_btn.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.info_btn.installEventFilter(self)

        # Create reset high score button (small and hard to accidentally click)
        self.reset_highscore_btn = QPushButton("🗑", self)
        self.reset_highscore_btn.setStyleSheet("""
            QPushButton {
                color: #FF6B6B;
                background: transparent;
                border: none;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                color: #FF4444;
                background-color: rgba(255, 68, 68, 0.1);
                border-radius: 2px;
            }
        """)
        self.reset_highscore_btn.setCursor(Qt.PointingHandCursor)
        self.reset_highscore_btn.clicked.connect(self.reset_high_score)
        self.reset_highscore_btn.setGeometry(770, 35, 20, 20)
        self.reset_highscore_btn.setFocusPolicy(Qt.NoFocus)
        self.reset_highscore_btn.setToolTip("Reset High Score (requires confirmation)")

        # Set up timer for piece movement
        self.timer = QBasicTimer()
        self.timer.start(400, self)

        # Add Pause button
        self.pause_btn = QPushButton("Pause", self)
        self.pause_btn.setGeometry(self.INFO_PANEL_X, self.INFO_PANEL_Y + 400, 200, 45)
        self.pause_btn.setStyleSheet("""
            QPushButton {
                background-color: #FFD700;
                color: #2D2D2D;
                border: none;
                border-radius: 5px;
                font-size: 16px;
                font-weight: bold;
                padding: 8px 16px;
                min-height: 45px;
            }
            QPushButton:hover {
                background-color: #FFEC80;
            }
        """)
        self.pause_btn.clicked.connect(self.toggle_pause)
        self.pause_btn.show()

        # Add large golden ⟲ button for Play Again (mobile game style)
        self.replay_btn = GoldenReplayButton(self)
        self.replay_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #FFD700;
                font-size: 120px;
                border: none;
                font-weight: bold;
            }
            QPushButton:hover {
                color: #FFF380;
            }
        """)
        self.replay_btn.setCursor(Qt.PointingHandCursor)
        self.replay_btn.setGeometry(self.GAME_AREA_X + self.BOARD_WIDTH * self.BLOCK_SIZE // 2 - 80, self.GAME_AREA_Y + self.BOARD_HEIGHT * self.BLOCK_SIZE // 2 - 100, 160, 200)
        self.replay_btn.clicked.connect(self.reset_game)
        self.replay_btn.hide()
        
        # Override paint event for shadow effect
        def paintEvent(event):
            painter = QPainter(self.replay_btn)
            painter.setRenderHint(QPainter.Antialiasing)
            
            # Draw shadow
            painter.setPen(QPen(QColor(0, 0, 0, 120), 1))
            painter.setFont(QFont("Segoe UI Emoji", 120, QFont.Bold))
            shadow_rect = self.replay_btn.rect().translated(3, 3)
            painter.drawText(shadow_rect, Qt.AlignCenter, "⟲")
            
            # Draw main icon
            color = "#FF8C00" if self.replay_btn.underMouse() else "#FFD700"
            painter.setPen(QColor(color))
            painter.drawText(self.replay_btn.rect(), Qt.AlignCenter, "⟲")
            
            painter.end()
        
        # Start the game
        self.show()

        # Enable mouse tracking on the main window and central widget
        self.setMouseTracking(True)
        if self.centralWidget():
            self.centralWidget().setMouseTracking(True)

    def changeEvent(self, event):
        """Handle window state changes to auto-pause when Tetris window loses focus"""
        super().changeEvent(event)
        if event.type() == QEvent.WindowStateChange or event.type() == QEvent.ActivationChange:
            if not self.isActiveWindow():
                # Auto-pause the game when window loses focus (if game is running and not already paused/over)
                if not hasattr(self, 'is_paused') or not self.is_paused:
                    if not self.game_over and self.timer.isActive():
                        self.toggle_pause()

    def new_piece(self):
        # SRS Tetromino definitions with all rotation states
        self.srs_pieces = {
            'I': {
                'shapes': [
                    [[0, 0, 0, 0], [1, 1, 1, 1], [0, 0, 0, 0], [0, 0, 0, 0]],  # 0
                    [[0, 0, 1, 0], [0, 0, 1, 0], [0, 0, 1, 0], [0, 0, 1, 0]],  # R
                    [[0, 0, 0, 0], [0, 0, 0, 0], [1, 1, 1, 1], [0, 0, 0, 0]],  # 2
                    [[0, 1, 0, 0], [0, 1, 0, 0], [0, 1, 0, 0], [0, 1, 0, 0]]   # L
                ],
                'kicks': {
                    '0->R': [(0, 0), (-2, 0), (1, 0), (-2, -1), (1, 2)],
                    'R->2': [(0, 0), (-1, 0), (2, 0), (-1, 2), (2, -1)],
                    '2->L': [(0, 0), (2, 0), (-1, 0), (2, 1), (-1, -2)],
                    'L->0': [(0, 0), (1, 0), (-2, 0), (1, -2), (-2, 1)],
                    '0->L': [(0, 0), (1, 0), (1, -1), (0, 2), (1, 2)],
                    'L->2': [(0, 0), (2, 0), (-1, 0), (2, 1), (-1, -2)],
                    '2->R': [(0, 0), (1, 0), (-2, 0), (1, -2), (-2, 1)],
                    'R->0': [(0, 0), (-2, 0), (1, 0), (-2, -1), (1, 2)]
                }
            },
            'O': {
                'shapes': [
                    [[1, 1], [1, 1]]  # O piece doesn't rotate
                ],
                'kicks': {}  # No kicks needed for O piece
            },
            'T': {
                'shapes': [
                    [[0, 1, 0], [1, 1, 1], [0, 0, 0]],  # 0
                    [[0, 1, 0], [0, 1, 1], [0, 1, 0]],  # R
                    [[0, 0, 0], [1, 1, 1], [0, 1, 0]],  # 2
                    [[0, 1, 0], [1, 1, 0], [0, 1, 0]]   # L
                ],
                'kicks': {
                    '0->R': [(0, 0), (-1, 0), (-1, 1), (0, -2), (-1, -2)],
                    'R->2': [(0, 0), (1, 0), (1, -1), (0, 2), (1, 2)],
                    '2->L': [(0, 0), (1, 0), (1, 1), (0, -2), (1, -2)],
                    'L->0': [(0, 0), (-1, 0), (-1, -1), (0, 2), (-1, 2)],
                    '0->L': [(0, 0), (1, 0), (1, -1), (0, 2), (1, 2)],
                    'L->2': [(0, 0), (-1, 0), (-1, 1), (0, -2), (-1, -2)],
                    '2->R': [(0, 0), (-1, 0), (-1, -1), (0, 2), (-1, 2)],
                    'R->0': [(0, 0), (1, 0), (1, 1), (0, -2), (1, -2)]
                }
            },
            'L': {
                'shapes': [
                    [[0, 0, 1], [1, 1, 1], [0, 0, 0]],  # 0
                    [[0, 1, 0], [0, 1, 0], [0, 1, 1]],  # R
                    [[0, 0, 0], [1, 1, 1], [1, 0, 0]],  # 2
                    [[1, 1, 0], [0, 1, 0], [0, 1, 0]]   # L
                ],
                'kicks': {
                    '0->R': [(0, 0), (-1, 0), (-1, 1), (0, -2), (-1, -2)],
                    'R->2': [(0, 0), (1, 0), (1, -1), (0, 2), (1, 2)],
                    '2->L': [(0, 0), (1, 0), (1, 1), (0, -2), (1, -2)],
                    'L->0': [(0, 0), (-1, 0), (-1, -1), (0, 2), (-1, 2)],
                    '0->L': [(0, 0), (1, 0), (1, -1), (0, 2), (1, 2)],
                    'L->2': [(0, 0), (-1, 0), (-1, 1), (0, -2), (-1, -2)],
                    '2->R': [(0, 0), (-1, 0), (-1, -1), (0, 2), (-1, 2)],
                    'R->0': [(0, 0), (1, 0), (1, 1), (0, -2), (1, -2)]
                }
            },
            'J': {
                'shapes': [
                    [[1, 0, 0], [1, 1, 1], [0, 0, 0]],  # 0
                    [[0, 1, 1], [0, 1, 0], [0, 1, 0]],  # R
                    [[0, 0, 0], [1, 1, 1], [0, 0, 1]],  # 2
                    [[0, 1, 0], [0, 1, 0], [1, 1, 0]]   # J
                ],
                'kicks': {
                    '0->R': [(0, 0), (-1, 0), (-1, 1), (0, -2), (-1, -2)],
                    'R->2': [(0, 0), (1, 0), (1, -1), (0, 2), (1, 2)],
                    '2->L': [(0, 0), (1, 0), (1, 1), (0, -2), (1, -2)],
                    'L->0': [(0, 0), (-1, 0), (-1, -1), (0, 2), (-1, 2)],
                    '0->L': [(0, 0), (1, 0), (1, -1), (0, 2), (1, 2)],
                    'L->2': [(0, 0), (-1, 0), (-1, 1), (0, -2), (-1, -2)],
                    '2->R': [(0, 0), (-1, 0), (-1, -1), (0, 2), (-1, 2)],
                    'R->0': [(0, 0), (1, 0), (1, 1), (0, -2), (1, -2)]
                }
            },
            'S': {
                'shapes': [
                    [[0, 1, 1], [1, 1, 0], [0, 0, 0]],  # 0
                    [[0, 1, 0], [0, 1, 1], [0, 0, 1]],  # R
                    [[0, 0, 0], [0, 1, 1], [1, 1, 0]],  # 2
                    [[1, 0, 0], [1, 1, 0], [0, 1, 0]]   # L
                ],
                'kicks': {
                    '0->R': [(0, 0), (-1, 0), (-1, 1), (0, -2), (-1, -2)],
                    'R->2': [(0, 0), (1, 0), (1, -1), (0, 2), (1, 2)],
                    '2->L': [(0, 0), (1, 0), (1, 1), (0, -2), (1, -2)],
                    'L->0': [(0, 0), (-1, 0), (-1, -1), (0, 2), (-1, 2)],
                    '0->L': [(0, 0), (1, 0), (1, -1), (0, 2), (1, 2)],
                    'L->2': [(0, 0), (-1, 0), (-1, 1), (0, -2), (-1, -2)],
                    '2->R': [(0, 0), (-1, 0), (-1, -1), (0, 2), (-1, 2)],
                    'R->0': [(0, 0), (1, 0), (1, 1), (0, -2), (1, -2)]
                }
            },
            'Z': {
                'shapes': [
                    [[1, 1, 0], [0, 1, 1], [0, 0, 0]],  # 0
                    [[0, 0, 1], [0, 1, 1], [0, 1, 0]],  # R
                    [[0, 0, 0], [1, 1, 0], [0, 1, 1]],  # 2
                    [[0, 1, 0], [1, 1, 0], [1, 0, 0]]   # L
                ],
                'kicks': {
                    '0->R': [(0, 0), (-1, 0), (-1, 1), (0, -2), (-1, -2)],
                    'R->2': [(0, 0), (1, 0), (1, -1), (0, 2), (1, 2)],
                    '2->L': [(0, 0), (1, 0), (1, 1), (0, -2), (1, -2)],
                    'L->0': [(0, 0), (-1, 0), (-1, -1), (0, 2), (-1, 2)],
                    '0->L': [(0, 0), (1, 0), (1, -1), (0, 2), (1, 2)],
                    'L->2': [(0, 0), (-1, 0), (-1, 1), (0, -2), (-1, -2)],
                    '2->R': [(0, 0), (-1, 0), (-1, -1), (0, 2), (-1, 2)],
                    'R->0': [(0, 0), (1, 0), (1, 1), (0, -2), (1, -2)]
                }
            }
        }
        
        piece_type = random.choice(list(self.srs_pieces.keys()))
        print(f"Generated piece: {piece_type}")  # <- Add this line here 👈

        return {
            'shape': self.srs_pieces[piece_type]['shapes'][0],  # Start with rotation 0
            'type': piece_type,
            'rotation': 0,  # Track rotation state (0, 1, 2, 3)
            'x': self.BOARD_WIDTH // 2 - 2,  # Center horizontally
            'y': 0
        }

    def timerEvent(self, event):
        if event.timerId() == self.timer.timerId():
            # Check for level up every 5 minutes
            current_time = datetime.now()
            minutes_played = (current_time - self.start_time).total_seconds() / 60
            new_level = min(10, 1 + int(minutes_played / 5))  # Max level 10

            if new_level > self.level:
                self.level = new_level
                # Increase speed (decrease timer interval)
                new_interval = max(100, 400 - (self.level - 1) * 40)  # Start at 400ms, decrease by 40ms per level
                self.timer.start(new_interval, self)

            if not self.move_piece_down():
                self.freeze_piece()
                self.clear_lines()
                self.current_piece = self.next_piece
                self.next_piece = self.new_piece()
                if self.check_collision():
                    self.game_over = True
                    self.timer.stop()
                    logging.info(f"Game Over - Final Score: {self.score}, Level: {self.level}")
                    self.game_over_check_high_score()
            self.update()  # Update display after piece movement
        else:
            super().timerEvent(event)

    def move_piece_down(self):
        self.current_piece['y'] += 1
        if self.check_collision():
            self.current_piece['y'] -= 1
            return False
        self.last_action = 'move'  # Track successful movement
        self.update()
        return True

    def check_collision(self, piece=None, x=None, y=None):
        # If no parameters provided, use current piece
        if piece is None:
            piece = self.current_piece
            x = piece['x']
            y = piece['y']

        for y_offset, row in enumerate(piece['shape']):
            for x_offset, cell in enumerate(row):
                if cell:
                    board_x = x + x_offset
                    board_y = y + y_offset
                    if (board_x < 0 or board_x >= self.BOARD_WIDTH or
                            board_y >= self.BOARD_HEIGHT or
                            (board_y >= 0 and self.board[board_y][board_x])):
                        return True
        return False

    def freeze_piece(self):
        # Detect spin before freezing
        is_spin, spin_bonus = self.detect_spin(
            self.current_piece['type'], 
            self.current_piece['rotation'], 
            self.current_piece['x'], 
            self.current_piece['y']
        )
        
        # Freeze the piece
        for y, row in enumerate(self.current_piece['shape']):
            for x, cell in enumerate(row):
                if cell:
                    board_x = self.current_piece['x'] + x
                    board_y = self.current_piece['y'] + y
                    # Only freeze pieces that are within the board boundaries
                    if 0 <= board_y < self.BOARD_HEIGHT and 0 <= board_x < self.BOARD_WIDTH:
                        self.board[board_y][board_x] = 1
        
        # Award spin bonus points
        if is_spin and spin_bonus > 0:
            spin_points = spin_bonus * 10 * self.level  # Scale with level
            self.score += spin_points
            self.show_spin_popup(self.current_piece['type'], spin_bonus)
            logging.info(f"{self.current_piece['type']}-SPIN! +{spin_points} points")
            
            # Check and update high score
            self.check_and_update_high_score()

    def get_level_requirement(self, level):
        """Returns the number of lines needed to reach the specified level"""
        return (level - 1) * 10  # For level 1, returns 0. For level 2, returns 10, etc.

    def show_combo_popup(self, combo_multiplier):
        if self.combo_popup is not None:
            if self.combo_animation is not None:
                self.combo_animation.stop()
                self.combo_animation.deleteLater()
            self.combo_popup.deleteLater()
            self.combo_popup = None
            self.combo_animation = None

        # Define combo messages and colors
        combo_messages = {
            2: ("COOL! 😎", "#00C4FF", 48),  # Sunglasses emoji
            3: ("MANIAC! 😡", "#66FF00", 48),
            4: ("SAVAGE! 😈", "#FFA500", 48),
            5: ("DOMINATING! 👹", "#FFD700", 36),  # Smaller font for longer text
            6: ("GODLIKE! 👽", "#EE4B2B", 48),
            7: ("OVERPOWERED! 💀", "#EDEDED", 32)  # Even smaller font for longest text
        }

        # Get message and color based on combo level (cap at 7)
        combo_level = min(combo_multiplier, 7)
        message, color, font_size = combo_messages[combo_level]

        self.combo_popup = QLabel(self)
        self.combo_popup.setText(message)
        self.combo_popup.setStyleSheet(f"""
            QLabel {{
                color: {color};
                font-size: {font_size}px;
                font-weight: bold;
                background: transparent;
            }}
        """)
        self.combo_popup.setAlignment(Qt.AlignCenter)

        # Add shadow effect to combo popup
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(0, 0, 0, 180))  # Semi-transparent black
        shadow.setOffset(3, 3)
        self.combo_popup.setGraphicsEffect(shadow)

        # Position popup in the center of the game area
        popup_x = self.GAME_AREA_X + (self.BOARD_WIDTH * self.BLOCK_SIZE) // 2 - 200
        popup_y = self.GAME_AREA_Y + (self.BOARD_HEIGHT * self.BLOCK_SIZE) // 2 - 40
        self.combo_popup.setGeometry(popup_x, popup_y, 400, 80)
        
        # Always keep coin animation behind popups/messages
        if hasattr(self, 'current_coin_animation') and self.current_coin_animation is not None:
            self.current_coin_animation.lower()
        self.combo_popup.raise_()
        
        self.combo_popup.show()  # Explicitly show the popup

        # Create fade animation
        self.combo_animation = QPropertyAnimation(self.combo_popup, b"windowOpacity")
        self.combo_animation.setDuration(1000)
        self.combo_animation.setStartValue(1.0)
        self.combo_animation.setEndValue(0.0)
        self.combo_animation.finished.connect(self.cleanup_combo_popup)
        self.combo_animation.start()

    def cleanup_combo_popup(self):
        if self.combo_popup is not None:
            self.combo_popup.deleteLater()
            self.combo_popup = None
        if self.combo_animation is not None:
            self.combo_animation.deleteLater()
            self.combo_animation = None

    def update_clear_animation(self):
        self.clearing_rows = []  # Clear the rows immediately
        self.clear_timer.stop()
        self.update()

    def clear_lines(self):
        lines_cleared = 0
        y = self.BOARD_HEIGHT - 1
        while y >= 0:
            if all(self.board[y]):
                lines_cleared += 1
                self.clearing_rows.append(y)
                for y2 in range(y, 0, -1):
                    self.board[y2] = self.board[y2 - 1][:]
                self.board[0] = [0] * self.BOARD_WIDTH
            else:
                y -= 1

        if lines_cleared > 0:
            self.consecutive_clears += 1
            base_points = 2 * lines_cleared

            if self.consecutive_clears >= 2:
                combo_multiplier = self.consecutive_clears
                self.show_combo_popup(combo_multiplier)
                self.score += base_points * combo_multiplier
                logging.info(f"Combo x{combo_multiplier}! Score: {base_points * combo_multiplier}")
            else:
                self.score += base_points
                logging.info(f"Single clear! Score: {base_points}")

            self.lines_cleared += lines_cleared
            self.clear_timer.start()

            # Earthquake shake effect
            self.shake_window()

            # Check for level up
            while self.lines_cleared >= self.get_level_requirement(self.level + 1):
                self.level += 1
                new_interval = max(100, 400 - (self.level - 1) * 40)  # Decrease interval by 40ms per level
                self.timer.start(new_interval, self)
                logging.info(f"Level up! Now at level {self.level}")

            # Check and update high score in real time
            self.check_and_update_high_score()
        else:
            if self.consecutive_clears > 0:
                logging.info(f"Combo ended at x{self.consecutive_clears}")
            self.consecutive_clears = 0

        # Check for score checkpoint bonus
        self.check_score_checkpoint()
        self.update()

    def check_and_update_high_score(self):
        if self.score > self.high_score:
            self.high_score = self.score
            self.save_high_score()
            self.new_high_score = True
            self.update()  # Redraw to show new high score
        else:
            self.new_high_score = False

    def check_score_checkpoint(self):
        """Check if score has reached a checkpoint and clear a bonus line if it has"""
        checkpoint = 50
        if self.score >= checkpoint and self.score % checkpoint == 0:
            # Find the lowest non-empty row
            for y in range(self.BOARD_HEIGHT - 1, -1, -1):
                if any(self.board[y]):  # If row has any blocks
                    # Clear this row
                    self.clearing_rows.append(y)
                    # Move all rows above down
                    for y2 in range(y, 0, -1):
                        self.board[y2] = self.board[y2 - 1][:]
                    self.board[0] = [0] * self.BOARD_WIDTH
                    # Add points for the bonus clear
                    self.score += 2  # Same as normal line clear
                    logging.info(f"Score checkpoint bonus! Cleared a line at {self.score} points")
                    # Check and update high score in real time
                    self.check_and_update_high_score()
                    break
            self.clear_timer.start()
        
        # Check for coin milestones during gameplay (every 20 points, starting at 100 points)
        if self.score >= 100:
            # Calculate current milestone (round down to nearest 20)
            current_milestone = (self.score // 20) * 20
            
            # Get the previous score (initialize if not exists)
            if not hasattr(self, 'previous_score'):
                self.previous_score = 0
            
            # Calculate previous milestone based on actual previous score
            previous_milestone = (self.previous_score // 20) * 20
            
            # Check if we just crossed a milestone
            if current_milestone > previous_milestone:
                coins_earned = current_milestone // 20
                logging.info(f"[TETRIS] Score: {self.score}, Previous score: {self.previous_score}, Current milestone: {current_milestone}, Previous milestone: {previous_milestone}, Coins: {coins_earned}")
                
                # Check if we've already shown this milestone to prevent duplicates
                if not hasattr(self, 'last_coin_milestone_shown'):
                    logging.info(f"First milestone, initializing last_coin_milestone_shown")
                    self.last_coin_milestone_shown = 0
                
                if coins_earned > self.last_coin_milestone_shown:
                    self.last_coin_milestone_shown = coins_earned
                    logging.info(f"[TETRIS] Coin milestone reached! Score: {self.score}, Milestone: {current_milestone}, Coins: {coins_earned}")
                    # Show quick coin bounce animation during gameplay (no notification popup)
                    self.show_coin_bounce_animation(coins_earned)
                else:
                    logging.info(f"[TETRIS] Milestone already shown: {coins_earned} <= {self.last_coin_milestone_shown}")
            else:
                logging.info(f"[TETRIS] No milestone crossed: {current_milestone} <= {previous_milestone}")
            
            # Update previous score for next check
            self.previous_score = self.score

    def closeEvent(self, event):
        # Ask for confirmation before closing
        if not self.game_over:
            confirm_dialog = ModernConfirmDialog('Exit Tetris', 'Are you sure you want to exit? Your current game will be lost.', self)
            reply = confirm_dialog.exec_()
            if reply == QDialog.Rejected:
                event.ignore()
                return
        
        # Clean up resources when window is closed
        try:
            if hasattr(self, 'timer'):
                self.timer.stop()
            if hasattr(self, 'clear_timer'):
                self.clear_timer.stop()
            if hasattr(self, 'explosion_timer'):
                self.explosion_timer.stop()
            self.cleanup_combo_popup()
        except Exception as e:
            logging.error(f"Error during cleanup")
        super().closeEvent(event)


    def keyPressEvent(self, event):
        # Always allow Ctrl to toggle pause/unpause
        if event.key() == Qt.Key_Control:
            self.toggle_pause()
            return
            
        # Check if coin popup is active - if so, let it handle spacebar
        if hasattr(self, 'coin_popup') and self.coin_popup and self.coin_popup.hasFocus():
            # Let the popup handle the key event
            self.coin_popup.keyPressEvent(event)
            return
            
        # Handle space bar for restart when game over
        if event.key() == Qt.Key_Space and self.game_over:
            self.reset_game()
            return
            
        # Allow spacebar to unpause when game is paused
        if hasattr(self, 'is_paused') and self.is_paused:
            if event.key() == Qt.Key_Space:
                self.toggle_pause()
                return
            return  # Ignore all other keys if paused
        if event.key() == Qt.Key_Escape:
            # Don't allow Escape to close the game - just ignore it
            event.accept()
            return
        elif event.key() == Qt.Key_Left:
            # Move piece left
            self.current_piece['x'] -= 1
            if self.check_collision():
                self.current_piece['x'] += 1
            else:
                self.last_action = 'move'  # Track successful movement
            self.update()
        elif event.key() == Qt.Key_Right:
            # Move piece right
            self.current_piece['x'] += 1
            if self.check_collision():
                self.current_piece['x'] -= 1
            else:
                self.last_action = 'move'  # Track successful movement
            self.update()
        elif event.key() == Qt.Key_Down:
            # Move piece down faster
            if not self.move_piece_down():
                self.freeze_piece()
                self.clear_lines()
                self.current_piece = self.next_piece
                self.next_piece = self.new_piece()
                if self.check_collision():
                    self.game_over = True
                    self.timer.stop()
                    logging.info(f"Game Over - Final Score: {self.score}, Level: {self.level}")
                    self.game_over_check_high_score()
        elif event.key() == Qt.Key_Up:
            # Rotate piece
            self.rotate_piece()
        elif event.key() == Qt.Key_Z:
            # Rotate piece counterclockwise
            self.rotate_piece_counterclockwise()
        elif event.key() == Qt.Key_Space:
            # Hard drop (only when not game over)
            if not self.game_over:
                self.hard_drop()
        elif event.key() == Qt.Key_Shift:
            # Hold piece
            self.hold_piece()
        elif event.key() == Qt.Key_R:
            # Toggle reposition mode with 'R' key
            if hasattr(self, 'reposition_mode') and self.reposition_mode:
                self.exit_reposition_mode()
            else:
                self.enter_reposition_mode()
            event.accept()
        else:
            super().keyPressEvent(event)
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Draw game area border
        border_rect = QRect(
            self.GAME_AREA_X - 2,
            self.GAME_AREA_Y - 2,
            self.BOARD_WIDTH * self.BLOCK_SIZE + 4,
            self.BOARD_HEIGHT * self.BLOCK_SIZE + 4
        )
        painter.setPen(QPen(QColor("#6E40C0"), 2))
        painter.drawRect(border_rect)

        # Draw blocks
        for y in range(self.BOARD_HEIGHT):
            for x in range(self.BOARD_WIDTH):
                if self.board[y][x]:
                    if y in self.clearing_rows:
                        color = QColor("#00AE8D")
                        self.create_explosion(x, y)
                    elif self.game_over:
                        color = QColor("#FF69B4")
                    else:
                        color = QColor("#6E40C0")
                    self.draw_block(painter, x, y, color)

        # Draw explosion particles
        for p in self.explosion_particles:
            painter.setPen(Qt.NoPen)
            if p['is_spark'] and p['life'] > 15:  # Sparks only appear briefly at the start
                # Draw electric spark in blue
                painter.setBrush(QColor(0, 150, 255, int(p['life'] * 12.75)))  # #0096FF with fade
            else:
                # Draw main explosion particle in green
                painter.setBrush(QColor(102, 255, 0, int(p['life'] * 12.75)))  # #66FF00 with fade
            painter.drawEllipse(
                int(p['x'] - p['size'] // 2),
                int(p['y'] - p['size'] // 2),
                int(p['size']),
                int(p['size'])
            )

        # Draw confetti particles
        for p in self.confetti_particles:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(p['color']))
            
            # Save painter state for rotation
            painter.save()
            painter.translate(p['x'], p['y'])
            painter.rotate(p['rotation'])
            
            size = int(p['size'])
            if p['shape'] == 'circle':
                painter.drawEllipse(-size//2, -size//2, size, size)
            elif p['shape'] == 'square':
                painter.drawRect(-size//2, -size//2, size, size)
            elif p['shape'] == 'triangle':
                points = [QPoint(0, -size//2), QPoint(-size//2, size//2), QPoint(size//2, size//2)]
                painter.drawPolygon(points)
            
            painter.restore()

        # Draw ghost piece
        if self.show_ghost and not self.game_over:
            ghost_pos = self.get_ghost_piece_position()
            if ghost_pos:
                for x, y in ghost_pos:
                    self.draw_block(painter, x, y, None)  # None indicates ghost piece

        # Draw current piece
        if not self.game_over:
            for y, row in enumerate(self.current_piece['shape']):
                for x, cell in enumerate(row):
                    if cell:
                        self.draw_block(
                            painter,
                            self.current_piece['x'] + x,
                            self.current_piece['y'] + y,
                            QColor("#00FFFF")
                        )

        # Draw score and level
        painter.setPen(QColor("white"))
        painter.setFont(QFont("Arial", 16))
        painter.drawText(self.INFO_PANEL_X, self.INFO_PANEL_Y, f"Score: {self.score}")
        painter.drawText(self.INFO_PANEL_X, self.INFO_PANEL_Y + 40, f"Level: {self.level}")
        # Draw high score
        painter.setFont(QFont("Arial", 14, QFont.Bold))
        painter.setPen(QColor("#FFD700"))
        painter.drawText(self.INFO_PANEL_X, self.INFO_PANEL_Y + 70, f"High Score: {self.high_score}")
        if self.game_over and self.new_high_score:
            painter.setFont(QFont("Arial", 18, QFont.Bold))
            painter.setPen(QColor("#FFD700"))
            painter.drawText(self.GAME_AREA_X, self.GAME_AREA_Y + (self.BOARD_HEIGHT * self.BLOCK_SIZE) // 2 + 40,
                             self.BOARD_WIDTH * self.BLOCK_SIZE, 40,
                             Qt.AlignCenter, "NEW HIGH SCORE!")

        # Draw next piece preview with smaller blocks
        painter.setPen(QColor("white"))
        painter.drawText(self.INFO_PANEL_X, self.INFO_PANEL_Y + 100, "Next:")
        next_piece_x = self.INFO_PANEL_X + 20
        next_piece_y = self.INFO_PANEL_Y + 130
        preview_block_size = 20
        next_piece_width = max(len(row) for row in self.next_piece['shape'])
        next_piece_height = len(self.next_piece['shape'])

        # Center the next piece preview
        next_piece_x += (4 - next_piece_width) * preview_block_size // 2

        for y, row in enumerate(self.next_piece['shape']):
            for x, cell in enumerate(row):
                if cell:
                    painter.fillRect(
                        next_piece_x + x * preview_block_size,
                        next_piece_y + y * preview_block_size,
                        preview_block_size - 1,
                        preview_block_size - 1,
                        QColor("#00FFFF")
                    )

        # Draw held piece preview with smaller blocks
        painter.setPen(QColor("white"))
        painter.drawText(self.INFO_PANEL_X, self.INFO_PANEL_Y + 250, "Hold:")  # Reduced vertical spacing
        hold_piece_x = self.INFO_PANEL_X + 20
        hold_piece_y = self.INFO_PANEL_Y + 280  # Reduced vertical spacing

        if self.held_piece:
            hold_piece_width = max(len(row) for row in self.held_piece['shape'])
            hold_piece_height = len(self.held_piece['shape'])

            # Center the held piece preview
            hold_piece_x += (4 - hold_piece_width) * preview_block_size // 2

            for y, row in enumerate(self.held_piece['shape']):
                for x, cell in enumerate(row):
                    if cell:
                        painter.fillRect(
                            hold_piece_x + x * preview_block_size,
                            hold_piece_y + y * preview_block_size,
                            preview_block_size - 1,
                            preview_block_size - 1,
                            QColor("#00FFFF")
                        )

        # Show replay button when game over (no demotivating text)
        if self.game_over:
            self.replay_btn.show()
        else:
            self.replay_btn.hide()
        if hasattr(self, 'is_paused') and self.is_paused:
            # Draw semi-transparent background overlay
            overlay_rect = QRect(self.GAME_AREA_X, self.GAME_AREA_Y, 
                               self.BOARD_WIDTH * self.BLOCK_SIZE, 
                               self.BOARD_HEIGHT * self.BLOCK_SIZE)
            painter.fillRect(overlay_rect, QColor(0, 0, 0, 180))  # Semi-transparent black
            
            # Draw pause icon with golden color
            painter.setPen(QColor("#FFD700"))
            painter.setFont(QFont("Segoe UI Emoji", 64, QFont.Bold))
            icon_rect = QRect(self.GAME_AREA_X, self.GAME_AREA_Y + self.BOARD_HEIGHT * self.BLOCK_SIZE // 2 - 60,
                             self.BOARD_WIDTH * self.BLOCK_SIZE, 120)
            painter.drawText(icon_rect, Qt.AlignCenter, "⏸️")

    def draw_block(self, painter, x, y, color):
        if color is None:  # For ghost piece
            painter.setPen(QPen(QColor("#6E40C0"), 1, Qt.DashLine))
            painter.setBrush(QColor(110, 64, 192, 50))  # Semi-transparent purple
        else:
            painter.setPen(Qt.NoPen)
            painter.setBrush(color)

        painter.drawRect(
            self.GAME_AREA_X + x * self.BLOCK_SIZE,
            self.GAME_AREA_Y + y * self.BLOCK_SIZE,
            self.BLOCK_SIZE - 1,
            self.BLOCK_SIZE - 1
        )

    def show_instructions(self):
        instructions = QMessageBox(self)
        instructions.setWindowTitle("Tetris Instructions")
        instructions.setText("""
        <h3>Controls:</h3>
        • Left/Right Arrow: Move piece<br>
        • Up Arrow: Rotate piece<br>
        • Down Arrow: Drop piece faster<br>
        • Space: Instant drop<br>
        • Shift: Hold/Use piece<br><br>

        <h3>Scoring:</h3>
        • Base: 2 points per line<br>
        • Combo: x2 for 2 consecutive clears<br>
        • Combo: x3 for 3 consecutive clears<br>
        • Combo: x4 for 4 consecutive clears<br><br>

        <h3>Level Requirements:</h3>
        • Level 1: Start<br>
        • Level 2: 10 lines<br>
        • Level 3: 20 lines<br>
        • Level 4: 40 lines<br>
        • Level 5+: +20 lines each<br><br>

        <h3>Level Effects:</h3>
        • Each level increases falling speed<br>
        • No effect on scoring
        """)
        instructions.setStyleSheet("""
            QMessageBox {
                background-color: #2D2D2D;
                color: white;
            }
            QMessageBox QLabel {
                color: white;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton {
                background-color: #6E40C0;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #5a33a1;
            }
            QPushButton:pressed {
                background-color: #4a2a8a;
            }
            QMessageBox QPushButton {
                background-color: #6E40C0;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
                min-width: 80px;
            }
            QMessageBox QPushButton:hover {
                background-color: #5a33a1;
            }
            QMessageBox QPushButton:pressed {
                background-color: #4a2a8a;
            }
        """)
        instructions.exec_()

    def hold_piece(self):
        if not self.can_hold:
            return

        if self.held_piece is None:
            # First hold
            self.held_piece = {
                'shape': [row[:] for row in self.current_piece['shape']],
                'type': self.current_piece['type'],
                'rotation': self.current_piece['rotation'],
                'x': self.BOARD_WIDTH // 2 - 2,
                'y': 0
            }
            self.current_piece = self.next_piece
            self.next_piece = self.new_piece()
            self.can_hold = False
        else:
            # Use held piece
            temp = {
                'shape': [row[:] for row in self.current_piece['shape']],
                'type': self.current_piece['type'],
                'rotation': self.current_piece['rotation'],
                'x': self.BOARD_WIDTH // 2 - 2,
                'y': 0
            }
            self.current_piece = {
                'shape': [row[:] for row in self.held_piece['shape']],
                'type': self.held_piece['type'],
                'rotation': self.held_piece['rotation'],
                'x': self.BOARD_WIDTH // 2 - 2,
                'y': 0
            }
            self.held_piece = temp
            self.can_hold = False

        # Check for collision after holding
        if self.check_collision():
            self.game_over = True
            self.timer.stop()

        self.update()

    def rotate_piece(self):
        """Rotate the current piece clockwise with SRS wall kicks"""
        if self.game_over:
            return
            
        # Get the current piece type and rotation
        piece_type = self.current_piece['type']
        current_rotation = self.current_piece['rotation']
        
        # O piece doesn't rotate
        if piece_type == 'O':
            return
            
        # Calculate new rotation (0->1->2->3->0)
        new_rotation = (current_rotation + 1) % 4
        
        # Get the new shape
        new_shape = self.srs_pieces[piece_type]['shapes'][new_rotation]
        
        # Try basic rotation first
        temp_piece = {
            'shape': new_shape,
            'type': piece_type,
            'rotation': new_rotation,
            'x': self.current_piece['x'],
            'y': self.current_piece['y']
        }
        
        if not self.check_collision(temp_piece, temp_piece['x'], temp_piece['y']):
            # Basic rotation works
            self.current_piece = temp_piece
            self.last_action = 'rotate'  # Track successful rotation
            self.update()
            return
            
        # Try wall kicks
        kick_key = f"{current_rotation}->{new_rotation}"
        if kick_key in self.srs_pieces[piece_type]['kicks']:
            kicks = self.srs_pieces[piece_type]['kicks'][kick_key]
            
            for dx, dy in kicks:
                temp_piece['x'] = self.current_piece['x'] + dx
                temp_piece['y'] = self.current_piece['y'] + dy
                
                if not self.check_collision(temp_piece, temp_piece['x'], temp_piece['y']):
                    # Wall kick successful
                    self.current_piece = temp_piece
                    self.last_action = 'rotate'  # Track successful rotation
                    self.update()
                    return
        
        # Rotation failed
        self.last_action = 'none'

    def rotate_piece_counterclockwise(self):
        """Rotate the current piece counterclockwise with SRS wall kicks"""
        if self.game_over:
            return
            
        # Get the current piece type and rotation
        piece_type = self.current_piece['type']
        current_rotation = self.current_piece['rotation']
        
        # O piece doesn't rotate
        if piece_type == 'O':
            return
            
        # Calculate new rotation (0->3->2->1->0)
        new_rotation = (current_rotation - 1) % 4
        
        # Get the new shape
        new_shape = self.srs_pieces[piece_type]['shapes'][new_rotation]
        
        # Try basic rotation first
        temp_piece = {
            'shape': new_shape,
            'type': piece_type,
            'rotation': new_rotation,
            'x': self.current_piece['x'],
            'y': self.current_piece['y']
        }
        
        if not self.check_collision(temp_piece, temp_piece['x'], temp_piece['y']):
            # Basic rotation works
            self.current_piece = temp_piece
            self.last_action = 'rotate'  # Track successful rotation
            self.update()
            return
            
        # Try wall kicks
        kick_key = f"{current_rotation}->{new_rotation}"
        if kick_key in self.srs_pieces[piece_type]['kicks']:
            kicks = self.srs_pieces[piece_type]['kicks'][kick_key]
            
            for dx, dy in kicks:
                temp_piece['x'] = self.current_piece['x'] + dx
                temp_piece['y'] = self.current_piece['y'] + dy
                
                if not self.check_collision(temp_piece, temp_piece['x'], temp_piece['y']):
                    # Wall kick successful
                    self.current_piece = temp_piece
                    self.last_action = 'rotate'  # Track successful rotation
                    self.update()
                    return
        
        # Rotation failed
        self.last_action = 'none'

    def detect_spin(self, piece_type, rotation, x, y):
        """Official SRS-style spin detection for all pieces"""
        if not self.spin_detection_enabled or not hasattr(self, 'last_action'):
            return False, 0

        # Only check for spin if the last action was a rotation
        if self.last_action != 'rotate':
            return False, 0

        # Try moving the piece left, right, and down; if all collide, it's a spin
        immobile = True
        for dx, dy in [(-1, 0), (1, 0), (0, 1)]:
            test_piece = {
                'shape': self.srs_pieces[piece_type]['shapes'][rotation],
                'type': piece_type,
                'rotation': rotation,
                'x': x + dx,
                'y': y + dy
            }
            if not self.check_collision(test_piece, test_piece['x'], test_piece['y']):
                immobile = False
                break
        if not immobile:
            return False, 0

        # SRS: T-spin, I-spin, L/J/S/Z-spin bonuses
        spin_bonus = 0
        if piece_type == 'T':
            spin_bonus = 3  # T-spin
        elif piece_type == 'I':
            spin_bonus = 3  # I-spin
        elif piece_type in ['L', 'J', 'S', 'Z']:
            spin_bonus = 2  # L/J/S/Z-spin
        else:
            spin_bonus = 0
        return True, spin_bonus

    def show_spin_popup(self, piece_type, spin_bonus):
        """Show a popup for spin achievements"""
        spin_messages = {
            'T': {3: "T-SPIN DOUBLE! 🔥", 4: "T-SPIN TRIPLE! 💥"},
            'S': {2: "S-SPIN! ⚡"},
            'Z': {2: "Z-SPIN! ⚡"},
            'L': {2: "L-SPIN! 🔥"},
            'J': {2: "J-SPIN! 🔥"},
            'I': {3: "I-SPIN! 🌟"}
        }
        
        if piece_type in spin_messages and spin_bonus in spin_messages[piece_type]:
            message = spin_messages[piece_type][spin_bonus]
            
            # Create spin popup
            spin_popup = QLabel(self)
            spin_popup.setText(message)
            spin_popup.setStyleSheet(f"""
                QLabel {{
                    color: #FFD700;
                    font-size: 24px;
                    font-weight: bold;
                    background: rgba(0, 0, 0, 0.8);
                    border: 2px solid #FFD700;
                    border-radius: 10px;
                    padding: 10px;
                }}
            """)
            spin_popup.setAlignment(Qt.AlignCenter)
            
            # Position popup
            popup_x = self.GAME_AREA_X + (self.BOARD_WIDTH * self.BLOCK_SIZE) // 2 - 150
            popup_y = self.GAME_AREA_Y + (self.BOARD_HEIGHT * self.BLOCK_SIZE) // 2 - 30
            spin_popup.setGeometry(popup_x, popup_y, 300, 60)
            spin_popup.raise_()
            spin_popup.show()
            
            # Animate and remove
            QTimer.singleShot(2000, spin_popup.deleteLater)

    def hard_drop(self):
        if self.game_over:
            return

        # Move piece down until collision
        while not self.check_collision(self.current_piece, self.current_piece['x'], self.current_piece['y'] + 1):
            self.current_piece['y'] += 1

        # Lock the piece in place
        self.freeze_piece()
        self.clear_lines()
        self.current_piece = self.next_piece
        self.next_piece = self.new_piece()
        self.current_piece['x'] = self.BOARD_WIDTH // 2 - 2
        self.current_piece['y'] = 0
        self.can_hold = True

        if self.check_collision(self.current_piece, self.current_piece['x'], self.current_piece['y']):
            self.game_over = True
            self.timer.stop()

        self.update()

    def get_ghost_piece_position(self):
        if not self.current_piece:
            return None

        # Create a copy of the current piece
        ghost_piece = {
            'shape': [row[:] for row in self.current_piece['shape']],
            'type': self.current_piece['type']
        }
        ghost_x = self.current_piece['x']
        ghost_y = self.current_piece['y']

        # Move the ghost piece down until it collides
        while not self.check_collision(ghost_piece, ghost_x, ghost_y + 1):
            ghost_y += 1

        # Return the final position of the ghost piece
        return [(x + ghost_x, y + ghost_y) for y, row in enumerate(ghost_piece['shape'])
                for x, cell in enumerate(row) if cell]

    def reset_game(self):
        """Reset the current game instance instead of creating a new window"""
        # Clear any active coin popup
        if hasattr(self, 'coin_popup') and self.coin_popup:
            self.coin_popup.deleteLater()
            self.coin_popup = None
        
        # Reset game state
        self.board = [[0] * 10 for _ in range(20)]
        self.current_piece = self.new_piece()
        self.next_piece = self.new_piece()
        self.held_piece = None
        self.can_hold = True
        self.score = 0
        self.lines_cleared = 0
        self.level = 1
        self.game_over = False
        self.paused = False
        self.consecutive_clears = 0
        self.start_time = datetime.now()
        self.clearing_rows = []
        self.explosion_particles = []
        self.last_action = 'none'  # Reset last action for SRS spin detection
        self.last_coin_milestone_shown = 0
        self.previous_score = 0
        
        # Reset timer with initial speed
        self.timer.stop()
        self.timer.start(400, self)
        
        # Hide replay button
        self.replay_btn.hide()
        
        # Ensure window has focus
        self.activateWindow()
        self.raise_()
        
        # Update display
        self.update()
        
        logging.info("Game reset successfully")

    def update_explosion(self):
        # Update and remove expired particles
        self.explosion_particles = [p for p in self.explosion_particles if p['life'] > 0]
        for p in self.explosion_particles:
            p['x'] += p['dx']
            p['y'] += p['dy']
            p['life'] -= 1
            p['size'] *= 0.95  # Shrink particles
        if not self.explosion_timer.isActive():
            self.explosion_timer.start()
        self.update()

    def update_confetti(self):
        # Update and remove expired confetti particles
        self.confetti_particles = [p for p in self.confetti_particles if p['life'] > 0]
        for p in self.confetti_particles:
            p['x'] += p['dx']
            p['y'] += p['dy']
            p['dx'] *= 0.99  # Air resistance
            p['dy'] += 0.2   # Gravity
            p['life'] -= 1
            p['rotation'] += p['rotation_speed']
        if not self.confetti_particles:
            self.confetti_timer.stop()
        self.update()

    def create_explosion(self, x, y):
        # Create particles for explosion effect
        for _ in range(8):  # 8 particles per block
            angle = random.uniform(0, 2 * 3.14159)
            speed = random.uniform(2, 5)
            self.explosion_particles.append({
                'x': x * self.BLOCK_SIZE + self.GAME_AREA_X + self.BLOCK_SIZE // 2,
                'y': y * self.BLOCK_SIZE + self.GAME_AREA_Y + self.BLOCK_SIZE // 2,
                'dx': math.cos(angle) * speed,
                'dy': math.sin(angle) * speed,
                'life': 20,  # Particle lifetime
                'size': self.BLOCK_SIZE // 2,
                'is_spark': random.random() < 0.3  # 30% chance of being a spark
            })
        if not self.explosion_timer.isActive():
            self.explosion_timer.start()

    def create_confetti_explosion(self):
        # Create confetti particles for coin reward celebration
        confetti_colors = ['#FFD700', '#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7', '#DDA0DD', '#98D8C8']
        
        for _ in range(50):  # 50 confetti pieces
            # Start from top of game area
            start_x = random.uniform(self.GAME_AREA_X, self.GAME_AREA_X + self.BOARD_WIDTH * self.BLOCK_SIZE)
            start_y = self.GAME_AREA_Y - 20  # Start above the game area
            
            self.confetti_particles.append({
                'x': start_x,
                'y': start_y,
                'dx': random.uniform(-3, 3),  # Horizontal velocity
                'dy': random.uniform(2, 6),   # Downward velocity
                'life': random.randint(120, 180),  # Longer life for confetti
                'color': random.choice(confetti_colors),
                'size': random.uniform(3, 8),
                'rotation': random.uniform(0, 360),
                'rotation_speed': random.uniform(-5, 5),
                'shape': random.choice(['circle', 'square', 'triangle'])
            })
        
        if not self.confetti_timer.isActive():
            self.confetti_timer.start()

    def load_high_score(self):
        # Ensure the scores directory exists
        scores_dir = Path(self.HIGHSCORE_FILE).parent
        scores_dir.mkdir(parents=True, exist_ok=True)
        if os.path.exists(self.HIGHSCORE_FILE):
            with open(self.HIGHSCORE_FILE, "r") as f:
                try:
                    return int(f.read().strip())
                except Exception:
                    return 0
        return 0

    def save_high_score(self):
        # Ensure the scores directory exists
        scores_dir = Path(self.HIGHSCORE_FILE).parent
        scores_dir.mkdir(parents=True, exist_ok=True)
        with open(self.HIGHSCORE_FILE, "w") as f:
            f.write(str(self.high_score))

    def game_over_check_high_score(self):
        # Check and save high score
        if self.score > self.high_score:
            self.high_score = self.score
            self.save_high_score()
            self.new_high_score = True
        else:
            self.new_high_score = False
        
        # Award coins for Tetris game (1 coin per 20 points, minimum 100 points)
        if self.score >= 100:
            try:
                rewards = load_user_rewards()
                # Award 1 coin per 20 points (rounded down)
                coins_earned = self.score // 20
                old_coins = rewards.get('coins', 0)
                rewards['coins'] = old_coins + coins_earned
                save_user_rewards(rewards)
                logging.info(f"[TETRIS] Awarded {coins_earned} coins for score {self.score}. Total coins: {old_coins} -> {rewards['coins']}")
                
                # Show notification popup for coin reward only at game over
                if hasattr(self, 'show_notification_popup') and self.game_over:
                    self.show_notification_popup(
                        f"<div style='text-align:center;'>"
                        f"<span style='font-size:40px; font-weight:bold; color:#FFD700;'>+{coins_earned} coins! 🪙</span><br>"
                        f"</div>"
                    )
            except Exception as e:
                logging.error(f"Failed to award Tetris coins: {e}")

    def reset_high_score(self):
        """Reset the high score with confirmation dialog"""
        # Show confirmation dialog to prevent accidental reset
        confirm_box = QMessageBox(self)
        confirm_box.setWindowTitle("Reset High Score")
        confirm_box.setText(f"Are you sure you want to reset the high score?\n\nCurrent High Score: {self.high_score}\n\nThis action cannot be undone!")
        confirm_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        confirm_box.setDefaultButton(QMessageBox.No)  # Default to "No" to prevent accidental clicks
        confirm_box.setStyleSheet("""
            QMessageBox {
                background-color: #2D2D2D;
                color: white;
            }
            QMessageBox QLabel {
                color: white;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton {
                background-color: #6E40C0;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #5a33a1;
            }
            QPushButton:pressed {
                background-color: #4a2a8a;
            }
        """)
        
        reply = confirm_box.exec_()
        
        if reply == QMessageBox.Yes:
            # Reset high score
            self.high_score = 0
            self.save_high_score()
            
            # Show confirmation with same styling
            success_box = QMessageBox(self)
            success_box.setWindowTitle("High Score Reset")
            success_box.setText("High score has been reset to 0.")
            success_box.setStandardButtons(QMessageBox.Ok)
            success_box.setStyleSheet("""
                QMessageBox {
                    background-color: #2D2D2D;
                    color: white;
                }
                QMessageBox QLabel {
                    color: white;
                    font-size: 12px;
                    font-weight: bold;
                }
                QPushButton {
                    background-color: #6E40C0;
                    color: white;
                    border: none;
                    padding: 8px 16px;
                    border-radius: 4px;
                    font-weight: bold;
                    min-width: 80px;
                }
                QPushButton:hover {
                    background-color: #5a33a1;
                }
                QPushButton:pressed {
                    background-color: #4a2a8a;
                }
            """)
            success_box.exec_()
            
            # Update the display
            self.update()

    def shake_window(self, duration=200, shake_range=8, shakes=12):
        """Shake the entire Tetris window for a short earthquake effect."""
        if hasattr(self, '_shaking') and self._shaking:
            return  # Prevent overlapping shakes
        self._shaking = True
        self._shake_positions = []
        self._shake_index = 0
        self._original_pos = self.pos()
        for _ in range(shakes):
            dx = random.randint(-shake_range, shake_range)
            dy = random.randint(-shake_range, shake_range)
            self._shake_positions.append(self._original_pos + QPoint(dx, dy))
        self._shake_positions.append(self._original_pos)  # Return to original
        self._shake_timer = QTimer(self)
        self._shake_timer.setInterval(duration // shakes)
        def do_shake():
            if self._shake_index < len(self._shake_positions):
                self.move(self._shake_positions[self._shake_index])
                self._shake_index += 1
            else:
                self._shake_timer.stop()
                self._shaking = False
        self._shake_timer.timeout.connect(do_shake)
        self._shake_timer.start()

    def toggle_pause(self):
        """Toggle pause state of the Tetris game"""
        if not hasattr(self, 'is_paused'):
            self.is_paused = False
        if not self.is_paused:
            self.timer.stop()
            self.is_paused = True
            self.pause_btn.setText("Resume")
            self.update()
        else:
            # Resume with current level speed
            new_interval = max(100, 400 - (self.level - 1) * 40)
            self.timer.start(new_interval, self)
            self.is_paused = False
            self.pause_btn.setText("Pause")
            self.update()


    def show_notification_popup(self, text, duration=3000):
        # Remove any existing notification
        if hasattr(self, '_notification_popup') and self._notification_popup:
            self._notification_popup.hide()
            self._notification_popup.deleteLater()
            self._notification_popup = None
        popup = NotificationPopup(self, text)
        popup.adjustSize()
        # Set main window as transient parent for stacking (optional, but helps on some platforms)
        popup.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        popup.setAttribute(Qt.WA_TranslucentBackground)
        popup.show()
        logging.debug("Notification popup shown.")
        
        popup.raise_()  # Force to top of stacking order
        popup.activateWindow()  # Try to bring to front
        # Center in the main window using rect().center()
        main_rect = self.rect()
        main_center = self.mapToGlobal(main_rect.center())
        popup_geom = popup.frameGeometry()
        x = main_center.x() - popup_geom.width() // 2
        y = main_center.y() - popup_geom.height() // 2
        popup.move(x, y)
        self._notification_popup = popup
        # Dismiss logic: if 'Congratulations' in text, require click to dismiss; else auto-hide
        def hide_popup():
            if hasattr(self, '_notification_popup') and self._notification_popup == popup:
                self._notification_popup.hide()
                self._notification_popup.deleteLater()
                self._notification_popup = None
                # For congratulations popup, let the popup handle the restart logic
                # For other popups, update header and repaint
                if 'Congratulations' not in text:
                    if hasattr(self, 'update_header_image'):
                        self.update_header_image()
                    self.repaint()
        
        # For congratulations popup, let the popup handle the restart logic
        # For other popups, auto-hide after duration
        if 'Congratulations' not in text:
            QTimer.singleShot(duration, hide_popup)

    def show_coin_bounce_animation(self, coins_earned):
        """Show a quick coin bounce animation during gameplay (NO notification popup)"""
        # Create coin animation label with GIF
        coin_label = QLabel(self)
        coin_label.setAlignment(Qt.AlignCenter)
        
        # Load and set the coin GIF
        coin_gif_path = str(GIFS_DIR / "coin.gif")
        coin_movie = QMovie(coin_gif_path)
        coin_movie.setSpeed(800)  # 6x FPS (increase for even faster)
        coin_label.setMovie(coin_movie)
        
        # Position in the center of the game area
        coin_x = self.GAME_AREA_X + (self.BOARD_WIDTH * self.BLOCK_SIZE) // 2 - 50
        coin_y = self.GAME_AREA_Y + (self.BOARD_HEIGHT * self.BLOCK_SIZE) // 2 - 50
        coin_label.setGeometry(coin_x, coin_y, 100, 100)
        
        # Store reference to coin label for layering management
        self.current_coin_animation = coin_label
        
        # Always keep coin animation behind popups/messages
        coin_label.lower()
        coin_label.show()
        
        # Start the GIF animation
        coin_movie.start()
        
        # Set initial opacity to 0 (invisible)
        coin_label.setWindowOpacity(0.0)
        
        # Create fade in animation
        fade_in_animation = QPropertyAnimation(coin_label, b"windowOpacity")
        fade_in_animation.setDuration(500)  # 0.5 seconds to fade in
        fade_in_animation.setStartValue(0.0)
        fade_in_animation.setEndValue(1.0)
        
        # Create fade out animation
        fade_out_animation = QPropertyAnimation(coin_label, b"windowOpacity")
        fade_out_animation.setDuration(500)  # 0.5 seconds to fade out
        fade_out_animation.setStartValue(1.0)
        fade_out_animation.setEndValue(0.0)
        
        # Start fade in immediately
        fade_in_animation.start()
        
        # Start fade out after 4.5 seconds (total 5 seconds on screen)
        QTimer.singleShot(1000, fade_out_animation.start)
        
        logging.debug(f"[Tetris] Coin animation started")
        
        # Clean up after animation
        def cleanup():
            coin_label.deleteLater()
            self.current_coin_animation = None
        QTimer.singleShot(1500, cleanup)


from PyQt5.QtCore import pyqtSignal

