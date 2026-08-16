import sys
import os
from openpyxl import load_workbook
from pathlib import Path
import json
import logging
import threading
import getpass
import random
import math
from PyQt5.QtGui import QMovie, QColor, QPen, QLinearGradient
from PyQt5.QtCore import QThread, QPropertyAnimation, QPoint, QEasingCurve, QBasicTimer, QRect, QSize, QEvent, QTimer, QObject, QAbstractAnimation, pyqtProperty, QCoreApplication
from PyQt5.QtGui import QCursor
from PyQt5.QtWidgets import QGraphicsDropShadowEffect, QApplication, QWidget, QLabel, QPushButton, QProgressBar, \
    QVBoxLayout, QHBoxLayout, QCheckBox, QMessageBox, QSizePolicy, QMenu, QAction, QWidgetAction, QFrame, QMainWindow, \
    QSpacerItem, QScrollArea, QPlainTextEdit, QGroupBox, QSpinBox, QComboBox
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFontDatabase, QFont, QPixmap, QPainter, QIcon, QBrush, QImage, QPainterPath
from PyQt5.QtWidgets import QGraphicsOpacityEffect, QGraphicsBlurEffect
from core.smducar import (
    create_folders, generate_excel, open_excel_file,
    setup_logging, get_latest_excel_file, read_mapping_data,
    load_config, CaseLawRouter, filter_mapping_data,
    split_username
)
from core.smducar_workflow import run_automation_workflow
from core.critical_error_notifier import notify_critical_error
from core.rerun_status import finalize_rerun_ready_statuses
import win32gui
import win32con
import pythoncom
from win32com.shell import shell, shellcon
import uuid
from utils.rewards import (
    CUSTOM_WALLPAPER_ID,
    REWARDS,
    award_run_rewards,
    format_reward_summary,
    get_custom_wallpaper_path,
    get_level_progress,
    get_reward_display_name,
    get_reward_icon,
    get_reward_image_filename,
    get_visual_settings,
    load_user_rewards,
    reset_user_rewards,
    save_user_rewards,
    xp_to_next_level,
)
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from collections import defaultdict
from datetime import datetime
from core.smducar import error_log_entries as global_error_log_entries
from PyQt5.QtGui import QTextBlock, QTextCursor
from PyQt5.QtWidgets import QProgressBar
from PyQt5.QtGui import QPainter, QColor, QBrush, QFont, QLinearGradient
from PyQt5.QtCore import QRectF, Qt

# Shared widgets extracted to a dedicated module
from .pyqt_widgets import (
    PillProgressBar,
    CenteredComboBox,
    CompactToggle,
    FrostedFrame,
    GoldenReplayButton,
    CustomTooltipWidget,
    OverlayWidget,
)

from .badge_effects import BadgeEffectLayer, BadgeMechanicalAnimator, has_badge_effect, has_badge_motion

# Dialog classes extracted to a dedicated module
from .pyqt_dialogs import (
    LogConsoleWindow,
    NotificationPopup,
    ModernMessageBox,
    ModernConfirmDialog,
    ShopDialog,
    InventoryDialog,
)

# Tetris game extracted to a dedicated module
from .pyqt_tetris import TetrisGame

# Logging formatters, handlers, and setup extracted to a dedicated module
from .pyqt_logging import install_qt_message_filter, setup_logging, QtLogHandler

# Animation classes extracted to a dedicated module
from .pyqt_animations import IntroAnimation

# Threading classes extracted to a dedicated module
from .pyqt_threading import WorkerThread

# Set up logging
log_file = setup_logging()

# The actual app title will be set dynamically based on mode in the main window
logging.info("Launching Auto-Router application.")

import re
import glob

# Import resource_path from config module
from core.smducar_config import resource_path

# Define asset paths
ASSETS_DIR = Path(resource_path("assets"))
IMAGES_DIR = ASSETS_DIR / "images"
GIFS_DIR = ASSETS_DIR / "gifs"
FONTS_DIR = ASSETS_DIR / "fonts"
CONFIG_DIR = Path(resource_path("config"))
ICONS_DIR = ASSETS_DIR / "icons"
BACKGROUND_LABEL_OBJECT_NAME = "AppBackgroundLabel"

# Keep the avatar smaller than its container so the Silcrow GIF and equipped
# achievement badges have room for bounce frames, shadows, and glitch overlays.
HEADER_AVATAR_DIM = 250
HEADER_CONTAINER_HEIGHT = 270

# Import utility functions from pyqt_utils module
from .pyqt_utils import (
    match_counsel_files,
    group_files_by_docket,
    get_main_and_counsel_files,
    categorize_dar_document_for_processing,
    should_process_dar_document_automatically,
    extract_decision_date_from_filename,
    extract_source_detail_from_filename,
)

# Import extract_docket_number from utils module (more comprehensive version)
from core.smducar_utils import extract_docket_number


# Removed functions (now imported from modules):
# - resource_path -> smducar_config.resource_path
# - extract_docket_number -> smducar_utils.extract_docket_number
# - match_counsel_files -> pyqt_utils.match_counsel_files
# - group_files_by_docket -> pyqt_utils.group_files_by_docket
# - get_main_and_counsel_files -> pyqt_utils.get_main_and_counsel_files
# - categorize_dar_document_for_processing -> pyqt_utils.categorize_dar_document_for_processing
# - should_process_dar_document_automatically -> pyqt_utils.should_process_dar_document_automatically
# - extract_decision_date_from_filename -> pyqt_utils.extract_decision_date_from_filename
# - extract_source_detail_from_filename -> pyqt_utils.extract_source_detail_from_filename

# Removed functions (now imported from modules):
# - resource_path -> smducar_config.resource_path
# - extract_docket_number -> smducar_utils.extract_docket_number
# - match_counsel_files -> pyqt_utils.match_counsel_files
# - group_files_by_docket -> pyqt_utils.group_files_by_docket
# - get_main_and_counsel_files -> pyqt_utils.get_main_and_counsel_files
# - categorize_dar_document_for_processing -> pyqt_utils.categorize_dar_document_for_processing
# - should_process_dar_document_automatically -> pyqt_utils.should_process_dar_document_automatically
# - extract_decision_date_from_filename -> pyqt_utils.extract_decision_date_from_filename
# - extract_source_detail_from_filename -> pyqt_utils.extract_source_detail_from_filename

# All utility functions have been moved to pyqt_utils.py module

# Removed: group_files_by_docket -> pyqt_utils.group_files_by_docket

# Removed: get_main_and_counsel_files -> pyqt_utils.get_main_and_counsel_files

# Removed: categorize_dar_document_for_processing -> pyqt_utils.categorize_dar_document_for_processing

# Removed: should_process_dar_document_automatically -> pyqt_utils.should_process_dar_document_automatically

# Removed: extract_source_detail_from_filename -> pyqt_utils.extract_source_detail_from_filename

# Note: get_full_username and clean_display_name are kept here because they have
# PyQt-specific logic (Outlook integration) that differs from smducar_user versions

def get_full_username():
    # Try to get display name from Outlook account first
    try:
        import win32com.client
        outlook = win32com.client.Dispatch("Outlook.Application")
        namespace = outlook.GetNamespace("MAPI")
        current_user = namespace.CurrentUser
        if current_user and current_user.Name:
            return current_user.Name  # Outlook display name
    except Exception as e:
        logging.info(f"Could not get Outlook display name")
    # Fallback to previous logic
    try:
        full_name = os.environ.get("USER_FULLNAME")
        if full_name:
            return full_name
        import ctypes
        GetUserNameEx = ctypes.windll.secur32.GetUserNameExW
        NameDisplay = 3  # NameDisplay = Full name
        size = ctypes.pointer(ctypes.c_ulong(0))
        GetUserNameEx(NameDisplay, None, size)
        name_buffer = ctypes.create_unicode_buffer(size.contents.value)
        if GetUserNameEx(NameDisplay, name_buffer, size):
            return name_buffer.value
        return getpass.getuser()
    except Exception as e:
        logging.warning(f"Could not extract full name")
        return getpass.getuser()


# Example output (if Outlook account display name is 'Kevin John'):
# get_full_username() -> 'Kevin John'


def clean_display_name(full_name):
    try:
        if ',' in full_name:
            full_name = full_name.split(',', 1)[1].strip()
        if '(' in full_name:
            full_name = full_name.split('(')[0].strip()
        # If only one word or camel case, split it
        if len(full_name.split()) == 1:
            full_name = split_username(full_name)
        return full_name
    except Exception:
        return full_name


class SMDUSAPGui(QMainWindow):
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(str, int, int)  # batch, current, total
    status_signal = pyqtSignal(str)
    router_mode_signal = pyqtSignal(str, str)
    final_success_signal = pyqtSignal(str, int, int, int, int, int, int)
    error_signal = pyqtSignal(str)

    def apply_frosted_glass_background(self):
        self.settings_menu.hide()  # Avoid flicker
        self.settings_menu.adjustSize()
        self.settings_menu.repaint()

        full_pixmap = self.grab()
        offset = self.settings_menu.pos()
        size = self.settings_menu.size()

        cropped = full_pixmap.copy(offset.x(), offset.y(), size.width(), size.height())

        # Create blurred image
        blurred = QImage(size, QImage.Format_ARGB32_Premultiplied)
        blurred.fill(Qt.transparent)

        label = QLabel()
        label.setPixmap(cropped)
        blur = QGraphicsBlurEffect()
        blur.setBlurRadius(40)  # Stronger blur
        label.setGraphicsEffect(blur)
        label.resize(size)

        painter = QPainter(blurred)
        label.render(painter)
        painter.end()

        # Apply dark tint over blur
        painter = QPainter(blurred)
        painter.setRenderHint(QPainter.Antialiasing)
        tint = QColor(45, 45, 45, 220)  # Try 240 for less transparency
        painter.fillRect(blurred.rect(), tint)
        painter.end()

        # Set as background on FrostedFrame
        self.settings_menu.set_background(QPixmap.fromImage(blurred))


    class NotificationPopup(QDialog):
        def __init__(self, parent, text):
            super().__init__(parent)
            self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
            self.setAttribute(Qt.WA_TranslucentBackground)
            self.setAttribute(Qt.WA_ShowWithoutActivating)
            self.setModal(True)

            self.radius = 20
            self.shadow_thickness = 12
            self.bg_color = QColor(128, 0, 200, 200)  # Purple, semi-transparent

            layout = QVBoxLayout(self)
            layout.setContentsMargins(self.shadow_thickness, self.shadow_thickness,
                                    self.shadow_thickness, self.shadow_thickness)

            label = QLabel(text, self)
            label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet("""
                color: white;
                font-size: 15px;
                font-weight: bold;
                padding: 24px 36px;
                background: transparent;
            """)
            label.setWordWrap(True)
            layout.addWidget(label)
            self.setLayout(layout)
            self.adjustSize()

            self.setWindowOpacity(0.0)

            self.fade_anim = QPropertyAnimation(self, b"windowOpacity")
            self.fade_anim.setDuration(400)
            self.fade_anim.setStartValue(0.0)
            self.fade_anim.setEndValue(1.0)
            self.fade_anim.setEasingCurve(QEasingCurve.InOutQuad)
            self.fade_anim.start()

          # Expand window to include space for shadow
            extra = self.shadow_thickness
            self.resize(self.width() + extra * 2, self.height() + extra * 2)

            # Handle mouse press for congratulations popup
            if 'Congratulations' in text:
                self.mousePressEvent = lambda event: self.handle_congratulations_click()
            else:
                self.mousePressEvent = lambda event: self.accept()
        
        def handle_congratulations_click(self):
            """Handle click on congratulations popup to restart the app"""
            try:
                import sys
                from PyQt5.QtCore import QCoreApplication, QProcess
                from PyQt5.QtCore import QTimer
                
                # Close the popup first
                self.accept()
                
                # Restart the app after a short delay
                QTimer.singleShot(100, lambda: QProcess.startDetached(sys.executable, sys.argv))
                QCoreApplication.quit()
                
            except Exception as e:
                logging.error(f"Error restarting app: {e}")
                # Fallback: just close the popup
                self.accept()

        def paintEvent(self, event):
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)

            rect = self.rect().adjusted(
                self.shadow_thickness // 2,
                self.shadow_thickness // 2,
                -self.shadow_thickness // 2,
                -self.shadow_thickness // 2
            )

            # Draw soft shadow manually
            shadow_color = QColor(0, 0, 0)  # pure black

            # Draw background rectangle
            painter.setBrush(self.bg_color)
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(rect, self.radius, self.radius)


    def create_shadow_effect(self, color=Qt.black, blur_radius=8, x_offset=1, y_offset=1):
        shadow = QGraphicsDropShadowEffect()
        shadow.setColor(color)
        shadow.setBlurRadius(blur_radius)
        shadow.setOffset(x_offset, y_offset)
        return shadow

    def apply_shadow(self, widget, color=Qt.black, blur=8, x_offset=1, y_offset=1):
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(blur)
        shadow.setColor(color)
        shadow.setOffset(x_offset, y_offset)
        widget.setGraphicsEffect(shadow)

    def set_initial_greeting(self):
        try:
            from core.smducar import get_full_username, clean_display_name
            full_name = get_full_username()
            display_name = clean_display_name(full_name)
        except:
            display_name = "Beautiful"

        # Determine greeting based on current hour
        hour = datetime.now().hour
        if (hour < 6):
            greeting = "Good morning"
        elif hour < 12:
            greeting = "Good morning"
        elif hour < 17:
            greeting = "Good afternoon"
        elif hour < 18:
            greeting = "Good evening"
        else:
            greeting = "Good evening"

        # Set personalized welcome message
        self.progress_label.setText(f"{greeting}, {display_name}!")

    def stop_greeting_updates(self):
        """Stop time-based greeting refreshes while progress text is being used."""
        if self.greeting_timer and self.greeting_timer.isActive():
            self.greeting_timer.stop()

    def start_greeting_updates(self):
        """Restart idle greeting refreshes after automation has returned to idle."""
        if self.greeting_timer and not self.greeting_timer.isActive():
            self.greeting_timer.start(60000)

    def _connect_button(self, button, handler):
        """Replace a QPushButton click handler without depending on its previous state."""
        try:
            button.clicked.disconnect()
        except Exception:
            pass
        button.clicked.connect(handler)

    def _sync_run_buttons(self):
        """Keep Generate/Run controls consistent with the current automation state."""
        running = bool(getattr(self, "is_running", False))

        generate_btn = getattr(self, "generate_btn", None)
        if generate_btn:
            generate_btn.setText("Generate")
            generate_btn.setEnabled(not running)
            generate_btn.setCursor(Qt.ArrowCursor if running else Qt.PointingHandCursor)
            generate_btn.setToolTip(
                "Generate is locked while automation is running."
                if running
                else "Create a fresh mapping sheet."
            )
            if not running:
                self._connect_button(generate_btn, self.on_generate)

        run_btn = getattr(self, "run_btn", None)
        if run_btn:
            run_btn.setText("Reset" if running else "Run")
            run_btn.setEnabled(True)
            run_btn.setCursor(Qt.PointingHandCursor)
            run_btn.setToolTip(
                "Stop the active automation run."
                if running
                else "Start processing the current mapping sheet."
            )
            self._connect_button(run_btn, self.on_reset if running else self.on_run)

    def _append_log_to_console(self, msg):
        if hasattr(self, 'log_console_window') and self.log_console_window:
            self.log_console_window.append_text(msg)        

    def __init__(self):
        super().__init__()

        self.log_signal.connect(self._append_log_to_console)
        self.status_signal.connect(self.set_progress_status)
        self.progress_signal.connect(self.handle_progress_update)
        self.router_mode_signal.connect(self.handle_router_mode_update)
        self.error_signal.connect(self.handle_worker_error)

        # --- Add QtLogHandler for GUI log window ---
        qt_handler = QtLogHandler(self)
        qt_handler.setLevel(logging.DEBUG)
        qt_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logging.getLogger().addHandler(qt_handler)
        self._qt_log_handler = qt_handler

        self.final_success_signal.connect(self.handle_success)
        
        # Set up frameless window for custom title bar
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setFixedSize(400, 520)  # Increased height to accommodate title bar
        self.setWindowIcon(QIcon(str(ICONS_DIR / "silcrow.ico")))
        self.reposition_mode = False
        
        # Window dragging variables
        self._drag_pos = None
        
        # Ensure frameless window is applied
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        
        # Note: Shadow effects can cause UpdateLayeredWindowIndirect errors with frameless windows
        # Using CSS-based shadow instead for better compatibility

        self._automation_completed = False
        self._success_message_shown = False
        self._success_message_dismissed = True
        self._last_success_log_time = None
        
        
        # Set up idle messages (before initUI)
        self.idle_messages = [
            "You're not burned out — you're just running a vintage version of yourself.",
            "Productivity is just procrastination with better PR.",
            "If you were more productive, you'd be a threat.",
            "Don't worry, I confuse myself too.",
            "Every time you open Outlook, a tiny part of your soul evaporates to heaven.",
            "You're the reason the 'Are you still there?' prompt exists.",
            "You don't have imposter syndrome. You're actually doing five jobs.",
            "Work-life balance achieved by letting both sides down equally.",
            "You're one more tab away from accidentally solving quantum physics.",
            "Energy levels: somewhere between 'thriving' and 'Wi-Fi in airplane mode.'",
            "You're not multitasking—you're just doing everything eventually.",
            "You're not zoning out — you're downloading updates from the void.",
            "Career advice: fake it, make it, then immediately log off.",
            "You bring 'chaotic good but with tabs open' energy.",
            "That wasn't a mistake. It was an unscheduled plot twist.",
            "You are Groot. And you do deserve PTO.",
            "Reminder: You're not paid enough to dream about work.",
            "Today's vibe: spreadsheet in the front, existential crisis in the back.",
            "You didn't forget. Your brain just archived it in 'meh.zip'.",
            "The project isn't behind. It's marinating.",
            "Your aura is 'I get things done, but also don't ask how.'",
            "Current mood: contributing quietly and judging loudly.",
            "You're doing amazing, sweetie — emotionally, technically, spiritually unhinged.",
            "You're not late — you're arriving with dramatic timing.",
            "You're the reason this place functions, and the reason the coffee's always gone.",
            "No thoughts. Just vibes, caffeine, and one cursed Webstar ticket.",
            "Somewhere between burnout and brilliance lies your to-do list.",
            "You're not lazy. You're operating at 'existence is effort' mode.",
            "You don't need a break. You need to ascend.",
            "Out of office in spirit, if not in policy.",
            "Your workflow is best described as 'high-functioning feral.'",
            "Team alignment achieved via mutual sarcasm and low expectations.",
            "Your skillset: multitasking, microdosing chaos, and managing weird vibes.",
            "You've got Monday energy in a Thursday body.",
            "Please hold — your last shred of motivation is reconnecting.",
            "You deserve a raise just for surviving this shift.",
            "Work isn't your passion — it's your weird little hobby you can't quit.",
            "You give off 'accidentally competent with flair' energy.",
            "Be the reason HR double-checks their policies.",
            "Every time you smile on a Teams call, a lie gets its wings.",
            "You are the drama. And also the emotional support coffee buddy.",
            "Productivity hack: just keep doing things until someone tells you to stop.",
            "You're one vague email away from a mysterious sabbatical.",
            "You bring balance to the Force — and by Force, we mean unread Outlook emails.",
            "Just because you're spiraling doesn't mean you're not efficient.",
            "Your legacy? Leaving behind folders no one understands.",
            "You're the human version of a '¯\\_(ツ)_/¯' but make it functional.",
            "In case no one told you today: you're holding this whole circus together.",
            "You're not just winging it — you've built an entire career aviary.",
            "Some call it procrastination. You call it *pre-chaotic incubation.*",
            "You're basically productivity jazz: no plan, all improvisation.",
            "Nothing says 'I'm coping' like updating your font preferences.",
            "Burnout? More like, brilliantly overcooked.",
            "Your 'I understand' face deserves an Oscar.",
            "They don't pay you to care. And somehow, you still do.",
            "Running on caffeine, ambition, and a single functioning brain cell.",
            "Not all heroes wear capes. Some just hit 'Reply All' and hit 'Away'.",
            "Your out-of-office reply is just an energy state now.",
            "Your deliverables are 50% panic and 50% black magic.",
            "This isn't burnout — this is your final form.",
            "Yes, you read that email. No, you didn't absorb it.",
            "Current focus: surviving today with just enough professionalism to pass HR.",
            "You deserve PTO just for interpreting vague instructions correctly.",
            "You're not overworked. You're just highly plot-relevant.",
            "Behind every 'No worries!' is a balled fist and some hairloss.",
            "Every spreadsheet hides a scream. Yours just harmonizes better.",
            "This isn't work—it's a very elaborate simulation to test your patience.",
            "You weren't hired. You were summoned during a staffing ritual.",
            "You don't have imposter syndrome. You're just deeply overqualified to tolerate this.",
            "Your mind is sharp. Too bad the Wi-Fi isn't.",
            "Professionalism: faking clarity while Googling the acronym they just used.",
            "Just a few more 'per my last email's before you ascend.",
            "Everyone's relying on you, mostly because you never visibly panic.",
            "Your calendar is a tapestry of chaos and thinly veiled dread.",
            "You're basically corporate duct tape: invisible, essential, and holding it all together.",
            "HR would cry if they knew how you really get things done.",
            "You bring the kind of calm that concerns your supervisor.",
            "There's no 'I' in team, but there's one in 'I did everything myself.'",
            "Caffeine and quiet rage: your two strongest credentials."
        ]

        self.idle_message_queue = []

        # Load fonts and config
        self.load_fonts()
        self.config = self.load_config()
        
        # Set initial title and application name based on mode
        app_title = self.get_app_title()
        self.setWindowTitle(app_title)
        from PyQt5.QtCore import QCoreApplication
        QCoreApplication.setApplicationName(app_title)
        
        # Initialize UI
        self.initUI()
        
        # Sync the title bar mode dropdown after UI creation.
        self.refresh_mode_display()
        
        # Initialize automation state
        self.is_running = False
        self.worker_thread = None
        self.minimal_mode = False
        self.header_visible = True
        self.notification_badge = None
        self._pending_success_messagebox = None
        self._success_message_shown = False
        self._automation_completed = False
        self._success_box = None
        self._notification_popup = None
        self._pending_minimal_mode = False
        self._reset_timer = None
        
        # Set initial greeting
        self.set_initial_greeting()

        # Timer to dynamically update greeting every minute
        self.greeting_timer = QTimer(self)
        self.greeting_timer.timeout.connect(self.set_initial_greeting)
        self.greeting_timer.start(60000)  # 60,000 ms = 1 minute

        # Timer for idle messages (only during automation)
        self.idle_timer = QTimer(self)
        self.idle_timer.timeout.connect(self.update_idle_message)
        self.idle_timer.setInterval(30000)  # 30 seconds
                
        self.background_offset_x = 0
        self.background_offset_y = 0

        # Initialize intro animation
        self.intro_animation = IntroAnimation(self)
        
        # Enter minimal mode by default and show the window
        self.enter_minimal_mode()
        self.show()
        self.center_on_screen()

        # Ensure the window icon is set after showing the window and entering minimal mode
        app_icon = QIcon(str(ICONS_DIR / "silcrow.ico"))
        self.setWindowIcon(app_icon)
        # Use a timer to ensure the icon is set after the window is fully shown
        QTimer.singleShot(100, lambda: self.setWindowIcon(app_icon))
        # Additional icon setting after fade animation starts
        QTimer.singleShot(300, lambda: self.setWindowIcon(app_icon))
        # Fade in on launch
        self.setWindowOpacity(0.0)
        self.fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self.fade_anim.setDuration(400)
        self.fade_anim.setStartValue(0.0)
        self.fade_anim.setEndValue(1.0)
        self.fade_anim.start()

        self.apply_equipped_rewards()
        self.update_level_display()

    def load_fonts(self):
        self._loaded_reward_font_paths = set()
        self.axiforma_id = QFontDatabase.addApplicationFont(str(FONTS_DIR / "Kastelov - Axiforma ExtraBold.otf"))
        self.brightness_id = QFontDatabase.addApplicationFont(str(FONTS_DIR / "Brightness.ttf"))

        axiforma_families = QFontDatabase.applicationFontFamilies(self.axiforma_id)
        self.axiforma_family = axiforma_families[0] if axiforma_families else "Arial"

        bright_families = QFontDatabase.applicationFontFamilies(self.brightness_id)
        self.brightness_family = bright_families[0] if bright_families else "Arial"
        self.default_ui_font_family = self.axiforma_family
        self.active_ui_font_family = self.default_ui_font_family

    def _font_qss_family(self):
        family = str(getattr(self, "active_ui_font_family", self.axiforma_family)).replace("'", "")
        return f"'{family}', 'Segoe UI', Arial, sans-serif"

    def _resolve_reward_font_family(self, reward_id):
        """Resolve a reward font to an installed or bundled family."""
        default_family = getattr(self, "default_ui_font_family", "Arial")
        if not reward_id:
            return default_family

        reward = REWARDS.get(reward_id, {})
        font_path = reward.get("font_path")
        if font_path:
            resolved_path = Path(resource_path(os.path.join("assets", str(font_path))))
            if resolved_path.exists() and str(resolved_path) not in self._loaded_reward_font_paths:
                font_id = QFontDatabase.addApplicationFont(str(resolved_path))
                self._loaded_reward_font_paths.add(str(resolved_path))
                families = QFontDatabase.applicationFontFamilies(font_id)
                if families and not reward.get("font_family"):
                    return families[0]

        candidates = []
        for value in [reward.get("font_family")] + list(reward.get("font_fallbacks", [])) + [default_family, "Segoe UI", "Arial"]:
            if value and value not in candidates:
                candidates.append(str(value))

        available = set(QFontDatabase().families())
        for candidate in candidates:
            if candidate in available:
                return candidate
        return candidates[0] if candidates else default_family

    def _active_ui_font(self, size=10, weight=QFont.Normal):
        return QFont(getattr(self, "active_ui_font_family", self.axiforma_family), size, weight)

    def _apply_equipped_font(self, font_reward_id):
        """Apply the equipped font to user-facing UI surfaces."""
        self.active_ui_font_family = self._resolve_reward_font_family(font_reward_id)
        QApplication.instance().setFont(self._active_ui_font(10))
        self.setFont(self._active_ui_font(10))

        font_targets = (
            ("mode_combo", 13, QFont.DemiBold),
            ("generate_btn", 12, QFont.Bold),
            ("run_btn", 12, QFont.Bold),
            ("level_triangle_btn", 16, QFont.Bold),
            ("settings_btn", 16, QFont.Bold),
            ("level_title_label", 10, QFont.Bold),
            ("level_xp_label", 8, QFont.Bold),
            ("level_coins_label", 8, QFont.Bold),
            ("level_docs_label", 8, QFont.Bold),
            ("idle_label", 10, QFont.Bold),
            ("progress_label", 10, QFont.Bold),
        )
        for attr, size, weight in font_targets:
            widget = getattr(self, attr, None)
            if widget:
                widget.setFont(self._active_ui_font(size, weight))

        settings_menu = getattr(self, "settings_menu", None)
        if settings_menu:
            for widget in settings_menu.findChildren((QLabel, QPushButton, QSpinBox)):
                widget.setFont(self._active_ui_font(9 if isinstance(widget, QLabel) else 11, QFont.Bold))
    
    def on_headless_toggle(self, state):
        self.config["headless"] = state
        self.auto_save_config()

    def on_console_toggle(self, state):
        if state:
            if not self.log_console_window:
                self.log_console_window = LogConsoleWindow(self)
                self.log_console_window.setObjectName("log_console_window")
            self.log_console_window.show()
            self.log_console_window.raise_()
            self.log_console_window.activateWindow()
        else:
            if self.log_console_window:
                self.log_console_window.hide()
        self.config["show_console"] = state
        self.auto_save_config()
        
        # Update the toggle's visual state to match (only if not already in sync)
        if hasattr(self, 'console_toggle') and self.console_toggle.state != state:
            self.console_toggle.set_state(state, play_animation=True)

    def on_parallel_routers_toggle(self, state):
        self.config["parallel_routers_enabled"] = state
        self.config["parallel_lni_limit"] = 0
        self._update_parallel_router_controls()
        self.auto_save_config()

    def on_parallel_router_instances_changed(self, value):
        self.config["parallel_router_instances"] = max(1, min(int(value), 6))
        self.config["parallel_lni_limit"] = 0
        self.auto_save_config()

    def _update_parallel_router_controls(self):
        running = bool(getattr(self, "is_running", False))
        toggle = getattr(self, "parallel_routers_toggle", None)
        if toggle:
            toggle.setEnabled(not running)

        self.config["parallel_lni_limit"] = 0
        enabled = bool(self.config.get("parallel_routers_enabled", False)) and not running
        for attr in ("parallel_router_instances_spin",):
            widget = getattr(self, attr, None)
            if widget:
                widget.setEnabled(enabled)

    def _update_run_locked_controls(self):
        running = bool(getattr(self, "is_running", False))
        self._sync_run_buttons()

        mode_combo = getattr(self, "mode_combo", None)
        if mode_combo:
            mode_combo.setEnabled(not running)
            mode_combo.setCursor(Qt.ArrowCursor if running else Qt.PointingHandCursor)
            mode_combo.setToolTip(
                "Router mode is locked while automation is running."
                if running
                else "Select which autorouter mode to run."
            )
        self._update_parallel_router_controls()


    def get_mode_options(self):
        return [
            ("smd", "SMD Autorouter"),
            ("dar", "DAR Autoruter"),
            ("mspb", "MSPB Autorouter"),
            ("itc", "ITC Autorouter"),
            ("irsplr", "IRSPLR Autorouter"),
            ("ohtax0", "OHTAX0 Autorouter"),
            ("mnsutb", "MNSUTB Autorouter"),
        ]

    def get_current_mode(self):
        return self.config.get("mode", "dar" if self.config.get("dar_mode", False) else "smd")

    def refresh_mode_display(self):
        app_title = self.get_app_title()
        self.setWindowTitle(app_title)
        QCoreApplication.setApplicationName(app_title)

        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_title)
        except Exception as e:
            logging.warning(f"Failed to update Windows app ID: {e}")

        mode_combo = getattr(self, "mode_combo", None)
        if mode_combo:
            current_mode = self.get_current_mode()
            previous_block_state = mode_combo.blockSignals(True)
            try:
                index = mode_combo.findData(current_mode)
                if index >= 0:
                    mode_combo.setCurrentIndex(index)
            finally:
                mode_combo.blockSignals(previous_block_state)

    def _set_router_mode_config(self, mode):
        """Update router mode config without touching Qt widgets."""
        self.config["mode"] = mode
        self.config["dar_mode"] = mode == "dar"
        self.auto_save_config()

    def handle_router_mode_update(self, mode, source):
        """Apply worker-requested mode UI changes safely on the Qt main thread."""
        self.refresh_mode_display()
        logging.info(f"Router mode set to {mode.upper()} via {source}.")

    def handle_worker_error(self, message):
        """Release the UI when the automation workflow reports a blocking error."""
        logging.error(message)
        self.is_running = False
        self._update_run_locked_controls()
        self.start_greeting_updates()
        ModernMessageBox("Automation Error", str(message), "error", self).exec_()

    def set_router_mode(self, mode, source="manual", allow_while_running=False):
        valid_modes = {mode_key for mode_key, _ in self.get_mode_options()}
        if mode not in valid_modes:
            logging.warning(f"Ignored unknown router mode: {mode}")
            self.refresh_mode_display()
            return

        if getattr(self, "is_running", False) and not allow_while_running:
            logging.info("Mode switch ignored because automation is running.")
            self.refresh_mode_display()
            return

        previous_mode = self.get_current_mode()
        self._set_router_mode_config(mode)
        self.refresh_mode_display()

        if previous_mode != mode:
            logging.info(f"Router mode set to {mode.upper()} via {source}.")

    def on_mode_combo_changed(self, index):
        mode_combo = getattr(self, "mode_combo", None)
        if not mode_combo or index < 0:
            return
        mode = mode_combo.itemData(index)
        if mode:
            self.set_router_mode(mode, source="dropdown")


    def load_config(self):
        try:
            with open('config/config.json', 'r') as f:
                config = json.load(f)
                if "show_console" not in config:
                    config["show_console"] = False  # Default to hidden
                if "dar_mode" not in config:
                    config["dar_mode"] = False  # Default to SMD Mode
                if "mode" not in config:
                    config["mode"] = "dar" if config.get("dar_mode", False) else "smd"
                config["dar_mode"] = config.get("mode") == "dar"
                config["parallel_routers_enabled"] = config.get(
                    "parallel_routers_enabled",
                    config.get("mspb_parallel_enabled", False)
                )
                config["parallel_lni_limit"] = 0
                try:
                    parallel_router_instances = int(config.get(
                        "parallel_router_instances",
                        config.get("mspb_parallel_workers", 2)
                    ) or 2)
                except (TypeError, ValueError):
                    parallel_router_instances = 2
                config["parallel_router_instances"] = max(1, min(parallel_router_instances, 6))
                config["critical_error_email_enabled"] = config.get("critical_error_email_enabled", True)
                config["run_summary_email_enabled"] = config.get("run_summary_email_enabled", True)
                config["critical_error_developer_email"] = config.get(
                    "critical_error_developer_email",
                    "kevinjohn.libuna@reedelsevier.com"
                )
                config["critical_error_user_email"] = config.get("critical_error_user_email", "")
                
                # Respect the saved console state
                # config["show_console"] is already loaded from the saved config
                
                return config
        except:
            return {
                "headless": False,
                "show_console": False,
                "dar_mode": False,
                "mode": "smd",
                "parallel_routers_enabled": False,
                "parallel_lni_limit": 0,
                "parallel_router_instances": 2,
                "critical_error_email_enabled": True,
                "run_summary_email_enabled": True,
                "critical_error_developer_email": "kevinjohn.libuna@reedelsevier.com",
                "critical_error_user_email": "",
            }  # Default config

    def get_app_title(self):
        """Get the appropriate app title based on current mode"""
        current_mode = self.config.get("mode", "dar" if self.config.get("dar_mode", False) else "smd")
        
        logging.info(f"get_app_title called - mode: {current_mode}")
        
        if current_mode == "mspb":
            logging.info("Returning MSPB Autorouter")
            return "MSPB Autorouter"
        if current_mode == "itc":
            logging.info("Returning ITC Autorouter")
            return "ITC Autorouter"
        if current_mode == "irsplr":
            logging.info("Returning IRSPLR Autorouter")
            return "IRSPLR Autorouter"
        if current_mode == "ohtax0":
            logging.info("Returning OHTAX0 Autorouter")
            return "OHTAX0 Autorouter"
        if current_mode == "mnsutb":
            logging.info("Returning MNSUTB Autorouter")
            return "MNSUTB Autorouter"
        if current_mode == "dar":
            logging.info("Returning DAR Autoruter")
            return "DAR Autoruter"
        logging.info("Returning SMD Autorouter")
        return "SMD Autorouter"

    def get_success_title(self):
        """Return a generic title; the final headline is decided dynamically in handle_success."""
        current_mode = self.config.get("mode", "dar" if self.config.get("dar_mode", False) else "smd")
        
        if current_mode == "mspb":
            return "MSPB Documents Auto-Routed"
        if current_mode == "itc":
            return "ITC Documents Auto-Routed"
        if current_mode == "irsplr":
            return "IRSPLR Documents Auto-Routed"
        if current_mode == "ohtax0":
            return "OHTAX0 Documents Auto-Routed"
        if current_mode == "mnsutb":
            return "MNSUTB Documents Auto-Routed"
        if current_mode == "dar":
            return "DAR Documents Auto-Routed"
        return "SMD USAP Documents Auto-Routed"

    def auto_detect_mode_from_filenames(self, df):
        """Auto-detect mode from filenames in the Excel data"""
        try:
            from core.smducar import detect_mode
            
            # Count modes in the filenames
            mode_counts = {"smd": 0, "dar": 0, "mspb": 0, "itc": 0, "irsplr": 0, "ohtax0": 0, "mnsutb": 0, "unknown": 0}
            
            for _, row in df.iterrows():
                filename = str(row.get("FileName", "")).strip()
                if filename and filename.lower() != "nan":
                    detected_mode = detect_mode(filename)
                    mode_counts[detected_mode] = mode_counts.get(detected_mode, 0) + 1
            
            # Determine the most common mode
            most_common_mode = max(mode_counts, key=mode_counts.get)
            
            # Only auto-detect if we have a clear majority
            total_files = sum(mode_counts.values())
            if total_files > 0 and mode_counts[most_common_mode] > total_files * 0.5:
                current_mode = self.config.get("mode", "dar" if self.config.get("dar_mode", False) else "smd")
                target_mode = most_common_mode
                if most_common_mode in {"dar", "smd", "mspb", "itc", "irsplr", "ohtax0", "mnsutb"} and target_mode != current_mode:
                    self._set_router_mode_config(target_mode)
                    self.router_mode_signal.emit(target_mode, "auto-detection")
                    logging.info(f"Auto-detected {most_common_mode.upper()} mode from {mode_counts[most_common_mode]}/{total_files} files")
        except Exception as e:
            logging.warning(f"Error auto-detecting mode: {e}")

    def get_success_message(self, user_name, counsel_success, main_success, counsel_already, main_already, error_log_entries=None, counsel_timeout=0, main_timeout=0):
        """Get the appropriate success message based on current mode, with simplified readable layout."""
        current_mode = self.config.get("mode", "dar" if self.config.get("dar_mode", False) else "smd")
        
        if current_mode == "mspb":
            app_name = "MSPB"
            process_name = "MSPB"
        elif current_mode == "itc":
            app_name = "ITC"
            process_name = "ITC"
        elif current_mode == "irsplr":
            app_name = "IRSPLR"
            process_name = "IRSPLR"
        elif current_mode == "ohtax0":
            app_name = "OHTAX0"
            process_name = "OHTAX0"
        elif current_mode == "mnsutb":
            app_name = "MNSUTB"
            process_name = "MNSUTB"
        elif current_mode == "dar":
            app_name = "DAR"
            process_name = "DAR"
        else:
            app_name = "SMD"
            process_name = "SMD USAP"
        
        # If everything failed with errors and nothing was successful or already processed,
        # show the dedicated error summary per UX.
        total_success = (counsel_success or 0) + (main_success or 0)
        total_already = (counsel_already or 0) + (main_already or 0)
        num_errors = len(error_log_entries) if error_log_entries else 0

        def summary_closer():
            if total_success > 0 and total_already > 0:
                return f"New routing finished; already handled rows were skipped, {user_name}!"
            if total_success > 0:
                return f"Fresh routing complete, {user_name}!"
            return f"No new routing needed, {user_name}!"

        if num_errors > 0 and total_success == 0 and total_already == 0:
            lines = [f"{app_name} Auto-Routing Summary:", "", "Errors:"]
            shown = 0
            for entry in (error_log_entries or [])[:10]:
                filename = entry.get('File Name', 'Unknown File')
                lni = entry.get('LNI', 'Unknown LNI')
                lines.append(f"• {filename} - {lni}")
                shown += 1
            remaining = num_errors - shown
            if remaining > 0:
                lines.append("")
                lines.append(f"...and {remaining} other documents.")
            lines.append("")
            lines.append("It's okay. Check and try again.")
            return "\n".join(lines)

        if total_success == 0 and total_already == 0:
            return "\n".join([
                f"{app_name} Auto-Routing Summary:",
                "",
                "No unfinished rows found for this run.",
                "",
                summary_closer(),
            ])

        # Otherwise show the compact success/processed/timeout summary.
        if current_mode == "mspb":
            lines = [f"{app_name} Auto-Routing Summary:"]
            if (main_success or 0) > 0:
                lines.append("")
                lines.append("Successfully auto-routed:")
                lines.append(f"MSPB: {main_success}")
            lines.append("")
            lines.append("Already processed:")
            lines.append(f"MSPB: {main_already}")
            lines.append("")
            lines.append(summary_closer())
            return "\n".join(lines)

        if current_mode == "itc":
            lines = [f"{app_name} Auto-Routing Summary:"]
            if (main_success or 0) > 0:
                lines.append("")
                lines.append("Successfully auto-routed:")
                lines.append(f"ITC: {main_success}")
            lines.append("")
            lines.append("Already processed:")
            lines.append(f"ITC: {main_already}")
            if (main_timeout or 0) > 0:
                lines.append("")
                lines.append("Timeout issues:")
                lines.append(f"ITC: {main_timeout}")
            lines.append("")
            lines.append(summary_closer())
            return "\n".join(lines)

        if current_mode == "irsplr":
            lines = [f"{app_name} Auto-Routing Summary:"]
            if (main_success or 0) > 0:
                lines.append("")
                lines.append("Successfully auto-routed:")
                lines.append(f"IRSPLR: {main_success}")
            lines.append("")
            lines.append("Already processed:")
            lines.append(f"IRSPLR: {main_already}")
            if (main_timeout or 0) > 0:
                lines.append("")
                lines.append("Timeout issues:")
                lines.append(f"IRSPLR: {main_timeout}")
            lines.append("")
            lines.append(summary_closer())
            return "\n".join(lines)

        if current_mode == "ohtax0":
            lines = [f"{app_name} Auto-Routing Summary:"]
            if (main_success or 0) > 0:
                lines.append("")
                lines.append("Successfully auto-routed:")
                lines.append(f"OHTAX0: {main_success}")
            lines.append("")
            lines.append("Already processed:")
            lines.append(f"OHTAX0: {main_already}")
            if (main_timeout or 0) > 0:
                lines.append("")
                lines.append("Timeout issues:")
                lines.append(f"OHTAX0: {main_timeout}")
            lines.append("")
            lines.append(summary_closer())
            return "\n".join(lines)

        if current_mode == "mnsutb":
            lines = [f"{app_name} Auto-Routing Summary:"]
            if (main_success or 0) > 0:
                lines.append("")
                lines.append("Successfully auto-routed:")
                lines.append(f"MNSUTB: {main_success}")
            lines.append("")
            lines.append("Already processed:")
            lines.append(f"MNSUTB: {main_already}")
            if (main_timeout or 0) > 0:
                lines.append("")
                lines.append("Timeout issues:")
                lines.append(f"MNSUTB: {main_timeout}")
            lines.append("")
            lines.append(summary_closer())
            return "\n".join(lines)

        lines = [f"{app_name} Auto-Routing Summary:"]

        if (counsel_success or 0) > 0 or (main_success or 0) > 0:
            lines.append("")
            lines.append("Successfully auto-routed:")
            if (counsel_success or 0) > 0:
                lines.append(f"Counsel: {counsel_success}")
            if (main_success or 0) > 0:
                lines.append(f"Main Opinion: {main_success}")

        lines.append("")
        lines.append("Already processed:")
        lines.append(f"Counsel: {counsel_already}")
        lines.append(f"Main Opinion: {main_already}")

        if (counsel_timeout or 0) > 0 or (main_timeout or 0) > 0:
            lines.append("")
            lines.append("Timeout issues:")
            if (counsel_timeout or 0) > 0:
                lines.append(f"Counsel: {counsel_timeout}")
            if (main_timeout or 0) > 0:
                lines.append(f"Main Opinion: {main_timeout}")

        lines.append("")
        lines.append(summary_closer())
        return "\n".join(lines)

    def styled_button(self, text, on_click, width=160, height=40):
        btn = QPushButton(text)
        btn.setFont(self._active_ui_font(12, QFont.Bold))
        btn.setFixedSize(width, height)
        btn.setContentsMargins(0, 0, 0, 0)
        btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        btn.setStyleSheet("""
            QPushButton {
                background-color: #6E40C0;
                color: white;
                border-radius: 8px;
                padding: 0px;
                text-align: center;
                vertical-align: middle;
            }
            QPushButton:hover {
                background-color: #5a33a1;
            }
        """)
        btn.clicked.connect(on_click)
        return btn

    def _theme_palette(self, skin):
        palettes = {
            None: {
                "title_start": "rgba(162, 89, 247, 0.46)",
                "title_mid": "rgba(255, 79, 163, 0.34)",
                "title_end": "rgba(0, 224, 255, 0.42)",
                "panel": "rgba(45, 45, 45, 0.62)",
                "panel_border": "#FFD700",
                "text": "#FFFFFF",
                "muted": "rgba(255, 255, 255, 0.72)",
                "accent": "#FFD700",
                "accent_2": "#00E0FF",
                "button_start": "#6E40C0",
                "button_end": "#8B5CF6",
                "button_hover": "#5A33A1",
                "button_hover_border": "#D9B8FF",
                "menu_bg": "rgba(31, 22, 48, 0.94)",
                "menu_hover": "rgba(0, 224, 255, 0.22)",
                "progress_track": "#F5F1E9",
                "progress_border": "#444444",
                "progress_start": "#FF00FF",
                "progress_end": "#00FFFF",
            },
            "ui_skin_blue": {
                "title_start": "rgba(29, 78, 216, 0.72)",
                "title_mid": "rgba(14, 165, 233, 0.46)",
                "title_end": "rgba(125, 211, 252, 0.42)",
                "panel": "rgba(15, 35, 73, 0.72)",
                "panel_border": "#93C5FD",
                "text": "#EAF6FF",
                "muted": "rgba(191, 219, 254, 0.78)",
                "accent": "#BAE6FD",
                "accent_2": "#38BDF8",
                "button_start": "#1D4ED8",
                "button_end": "#0EA5E9",
                "button_hover": "#2563EB",
                "button_hover_border": "#BAE6FD",
                "menu_bg": "rgba(12, 33, 70, 0.95)",
                "menu_hover": "rgba(56, 189, 248, 0.24)",
                "progress_track": "#DCEBFF",
                "progress_border": "#1D4ED8",
                "progress_start": "#1D4ED8",
                "progress_end": "#38BDF8",
            },
            "ui_skin_ocean": {
                "title_start": "rgba(8, 47, 73, 0.76)",
                "title_mid": "rgba(20, 184, 166, 0.48)",
                "title_end": "rgba(103, 232, 249, 0.42)",
                "panel": "rgba(8, 51, 68, 0.72)",
                "panel_border": "#67E8F9",
                "text": "#ECFEFF",
                "muted": "rgba(207, 250, 254, 0.76)",
                "accent": "#A7F3D0",
                "accent_2": "#22D3EE",
                "button_start": "#0E7490",
                "button_end": "#14B8A6",
                "button_hover": "#0891B2",
                "button_hover_border": "#A7F3D0",
                "menu_bg": "rgba(7, 54, 66, 0.95)",
                "menu_hover": "rgba(45, 212, 191, 0.24)",
                "progress_track": "#D9FFFB",
                "progress_border": "#0E7490",
                "progress_start": "#0E7490",
                "progress_end": "#67E8F9",
            },
            "ui_skin_midnight_clerk": {
                "title_start": "rgba(17, 24, 39, 0.86)",
                "title_mid": "rgba(67, 56, 202, 0.50)",
                "title_end": "rgba(148, 163, 184, 0.35)",
                "panel": "rgba(15, 23, 42, 0.78)",
                "panel_border": "#818CF8",
                "text": "#F8FAFC",
                "muted": "rgba(203, 213, 225, 0.78)",
                "accent": "#C4B5FD",
                "accent_2": "#60A5FA",
                "button_start": "#1F2937",
                "button_end": "#4F46E5",
                "button_hover": "#3730A3",
                "button_hover_border": "#C4B5FD",
                "menu_bg": "rgba(15, 23, 42, 0.96)",
                "menu_hover": "rgba(99, 102, 241, 0.26)",
                "progress_track": "#E2E8F0",
                "progress_border": "#312E81",
                "progress_start": "#312E81",
                "progress_end": "#60A5FA",
            },
            "ui_skin_courtroom_noir": {
                "title_start": "rgba(23, 23, 23, 0.88)",
                "title_mid": "rgba(120, 53, 15, 0.52)",
                "title_end": "rgba(200, 164, 93, 0.38)",
                "panel": "rgba(28, 25, 23, 0.78)",
                "panel_border": "#C8A45D",
                "text": "#FFF7ED",
                "muted": "rgba(245, 222, 179, 0.72)",
                "accent": "#FACC15",
                "accent_2": "#B91C1C",
                "button_start": "#27272A",
                "button_end": "#92400E",
                "button_hover": "#78350F",
                "button_hover_border": "#FACC15",
                "menu_bg": "rgba(28, 25, 23, 0.96)",
                "menu_hover": "rgba(200, 164, 93, 0.22)",
                "progress_track": "#FFF4D6",
                "progress_border": "#78350F",
                "progress_start": "#78350F",
                "progress_end": "#FACC15",
            },
            "ui_skin_aurora_desk": {
                "title_start": "rgba(31, 138, 112, 0.62)",
                "title_mid": "rgba(110, 64, 192, 0.50)",
                "title_end": "rgba(255, 138, 179, 0.44)",
                "panel": "rgba(19, 49, 61, 0.72)",
                "panel_border": "#8CF5FF",
                "text": "#F7FEFF",
                "muted": "rgba(224, 242, 254, 0.78)",
                "accent": "#A7F3D0",
                "accent_2": "#F0ABFC",
                "button_start": "#1F8A70",
                "button_end": "#A855F7",
                "button_hover": "#6E40C0",
                "button_hover_border": "#FFB8D5",
                "menu_bg": "rgba(22, 43, 58, 0.94)",
                "menu_hover": "rgba(240, 171, 252, 0.22)",
                "progress_track": "#E0FDFB",
                "progress_border": "#1F8A70",
                "progress_start": "#1F8A70",
                "progress_end": "#FF8AB3",
            },
        }
        return palettes.get(skin, palettes[None])

    def _button_style(self, palette):
        return f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {palette['button_start']}, stop:1 {palette['button_end']});
                font-family: {self._font_qss_family()};
                color: {palette['text']};
                border-radius: 8px;
                border: 1px solid rgba(255, 255, 255, 0.28);
                padding: 0px;
                text-align: center;
                vertical-align: middle;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {palette['button_hover']};
                border: 1px solid {palette.get('button_hover_border', 'rgba(255, 255, 255, 0.52)')};
            }}
            QPushButton:disabled {{
                background: rgba(255, 255, 255, 0.10);
                color: rgba(255, 255, 255, 0.42);
                border: 1px solid rgba(255, 255, 255, 0.16);
            }}
        """

    def _round_icon_button_style(self, palette, danger=False):
        hover = "rgba(255, 79, 163, 0.42)" if danger else palette["menu_hover"]
        border = "#FF8AB3" if danger else palette["panel_border"]
        return f"""
            QPushButton {{
                background: rgba(255, 255, 255, 0.12);
                font-family: {self._font_qss_family()};
                border: 1px solid rgba(255, 255, 255, 0.25);
                border-radius: 12px;
                color: {palette['text']};
                font-size: 12px;
                font-weight: bold;
                padding: 5px 8px;
                margin: 0px;
                min-width: 20px;
                max-width: 20px;
                min-height: 20px;
                max-height: 20px;
            }}
            QPushButton:hover {{
                background: {hover};
                border: 1px solid {border};
            }}
        """

    def _mode_combo_style(self, palette):
        return f"""
            QComboBox {{
                font-family: {self._font_qss_family()};
                color: {palette['text']};
                font-size: 13px;
                font-weight: 600;
                margin: 0;
                padding: 6px 30px 6px 30px;
                background: rgba(255, 255, 255, 0.15);
                border-radius: 12px;
                border: 1px solid {palette['panel_border']};
                selection-background-color: {palette['menu_hover']};
            }}
            QComboBox:hover {{
                background: {palette['menu_hover']};
                border: 1px solid {palette['accent']};
                color: {palette['text']};
            }}
            QComboBox:focus {{
                border: 1px solid {palette['accent_2']};
                background: rgba(255, 255, 255, 0.18);
            }}
            QComboBox:disabled {{
                color: rgba(255, 255, 255, 0.55);
                background: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.16);
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 24px;
                border: none;
                background: transparent;
            }}
            QComboBox::down-arrow {{
                image: none;
                width: 0px;
                height: 0px;
            }}
            QComboBox QAbstractItemView {{
                color: {palette['text']};
                background: {palette['menu_bg']};
                border: 1px solid {palette['panel_border']};
                border-radius: 8px;
                padding: 4px;
                outline: 0;
                selection-background-color: {palette['menu_hover']};
                selection-color: white;
            }}
        """

    def _settings_menu_style(self, palette):
        return f"""
            QFrame#SettingsMenuFrame {{
                background-color: transparent;
                border: 1px solid {palette['panel_border']};
                border-radius: 6px;
                padding: 8px;
            }}
            QPushButton {{
                background-color: transparent;
                font-family: {self._font_qss_family()};
                color: {palette['text']};
                border: none;
                text-align: left;
                padding: 6px 12px;
                font-size: 15px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {palette['menu_hover']};
                color: {palette['accent']};
            }}
            QLabel {{
                font-family: {self._font_qss_family()};
                color: {palette['text']};
            }}
        """

    def _level_info_panel_style(self, palette):
        return f"""
            QFrame#LevelInfoPanel {{
                background-color: {palette['panel']};
                border: 2px solid {palette['panel_border']};
                border-radius: 8px;
            }}
            QLabel#LevelInfoTitle {{
                font-family: {self._font_qss_family()};
                color: {palette['accent']};
                font-size: 14px;
                font-weight: bold;
                background: transparent;
            }}
            QLabel#LevelInfoRow {{
                font-family: {self._font_qss_family()};
                color: {palette['text']};
                font-size: 11px;
                font-weight: bold;
                background: transparent;
            }}
            QLabel#LevelInfoMuted {{
                font-family: {self._font_qss_family()};
                color: {palette['muted']};
                font-size: 10px;
                font-weight: bold;
                background: transparent;
            }}
        """

    def _apply_level_info_panel_style(self, palette=None):
        palette = palette or getattr(self, "_active_theme_palette", self._theme_palette(None))
        if hasattr(self, "level_info_panel"):
            self.level_info_panel.setStyleSheet(self._level_info_panel_style(palette))
        self._apply_level_xp_gradient()

    def _blend_hex_color(self, start_hex, end_hex, amount):
        """Blend two hex colors for progress-aware XP bar gradients."""
        amount = max(0.0, min(1.0, float(amount or 0)))
        start = start_hex.lstrip("#")
        end = end_hex.lstrip("#")
        channels = []
        for index in range(0, 6, 2):
            start_value = int(start[index:index + 2], 16)
            end_value = int(end[index:index + 2], 16)
            channels.append(round(start_value + ((end_value - start_value) * amount)))
        return "#{:02X}{:02X}{:02X}".format(*channels)

    def _level_xp_gradient_colors(self, progress):
        """Return a brighter royal-blue-to-green gradient as XP nears full."""
        progress = max(0.0, min(1.0, float(progress or 0)))
        stops = (
            (0.00, ("#2F48B8", "#243AA8", "#1677E8", "#00A96B")),
            (0.25, ("#1E8DEB", "#3156D8", "#00A8FF", "#00C980")),
            (0.50, ("#16D7B4", "#4169E1", "#00C2FF", "#00E676")),
            (0.75, ("#35F38F", "#2F6BFF", "#00E5FF", "#39FF8A")),
            (0.95, ("#78FFB1", "#4D74FF", "#33F4FF", "#7CFF5B")),
            (1.00, ("#A5FFD0", "#5A7DFF", "#55FBFF", "#9DFF62")),
        )
        for index, (stop, colors) in enumerate(stops):
            if progress <= stop:
                previous_stop, previous_colors = stops[max(0, index - 1)]
                span = max(0.001, stop - previous_stop)
                local_progress = (progress - previous_stop) / span
                return tuple(
                    self._blend_hex_color(previous_color, color, local_progress)
                    for previous_color, color in zip(previous_colors, colors)
                )
        return stops[-1][1]

    def _apply_level_xp_gradient(self, progress=None):
        if not hasattr(self, "level_xp_bar") or not hasattr(self.level_xp_bar, "set_theme_colors"):
            return
        if progress is None:
            value = self.level_xp_bar.value()
            maximum = max(1, self.level_xp_bar.maximum())
            progress = value / maximum
        progress = max(0.0, min(1.0, float(progress or 0)))
        border, fill_start, fill_mid, fill_end = self._level_xp_gradient_colors(progress)
        self.level_xp_bar.set_theme_colors(
            track="rgba(18, 18, 28, 0.88)",
            border=border,
            fill_start=fill_start,
            fill_mid=fill_mid,
            fill_end=fill_end,
            shimmer="#E7FFF6",
        )
        if hasattr(self.level_xp_bar, "set_shimmer_speed"):
            self.level_xp_bar.set_shimmer_speed(0.006 + (0.014 * progress))
        if hasattr(self.level_xp_bar, "set_effect_mode") and getattr(self.level_xp_bar, "effect_mode", None) != "bubbles":
            self.level_xp_bar.set_effect_mode("bubbles")

    def _apply_level_button_style(self, expanded=False):
        palette = getattr(self, "_active_theme_palette", self._theme_palette(None))
        color = palette["accent"] if expanded else palette["text"]
        hover = palette["accent_2"] if expanded else palette["accent"]
        if hasattr(self, "level_triangle_btn"):
            self.level_triangle_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    color: {color};
                    border: none;
                    font-weight: bold;
                    padding: 0px;
                    margin: 0px;
                }}
                QPushButton:hover {{
                    color: {hover};
                }}
            """)

    def _apply_ui_theme(self, skin):
        """Apply purchased theme colors to concrete widgets with inline styles."""
        palette = self._theme_palette(skin)
        self._active_theme_palette = palette

        if hasattr(self, "central_widget"):
            self.central_widget.setStyleSheet(f"""
                QWidget#CentralWidget {{
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 rgba(0, 0, 0, 0.04),
                        stop:0.75 rgba(0, 0, 0, 0.01),
                        stop:1 rgba(0, 0, 0, 0.08));
                    border-radius: 25px;
                    border: none;
                }}
            """)
        if hasattr(self, "title_bar"):
            self.title_bar.setStyleSheet(f"""
                QWidget#TitleBar {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 {palette['title_start']},
                        stop:0.5 {palette['title_mid']},
                        stop:1 {palette['title_end']});
                    border-radius: 15px;
                    border: none;
                }}
            """)
        if hasattr(self, "mode_combo"):
            self.mode_combo.setStyleSheet(self._mode_combo_style(palette))
        if hasattr(self, "generate_btn"):
            self.generate_btn.setStyleSheet(self._button_style(palette))
        if hasattr(self, "run_btn"):
            self.run_btn.setStyleSheet(self._button_style(palette))
        if hasattr(self, "minimize_btn"):
            self.minimize_btn.setStyleSheet(self._round_icon_button_style(palette))
        if hasattr(self, "close_btn"):
            self.close_btn.setStyleSheet(self._round_icon_button_style(palette, danger=True))
        if hasattr(self, "settings_btn"):
            self.settings_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    border: none;
                    color: {palette['text']};
                    padding: 0px;
                    margin: 0px;
                }}
                QPushButton:hover {{
                    color: {palette['accent']};
                }}
            """)
        if hasattr(self, "settings_menu"):
            self.settings_menu.setStyleSheet(self._settings_menu_style(palette))
        self._apply_level_info_panel_style(palette)
        if hasattr(self, "idle_label"):
            self.idle_label.setStyleSheet(f"color: {palette['text']};")
        if hasattr(self, "progress_label"):
            self.progress_label.setStyleSheet(f"color: {palette['text']}; background-color: transparent;")
        if hasattr(self, "progress_bar") and hasattr(self.progress_bar, "set_theme_colors"):
            self.progress_bar.set_theme_colors(
                track=palette["progress_track"],
                border=palette["progress_border"],
                fill_start=palette["progress_start"],
                fill_end=palette["progress_end"],
            )
        self._apply_level_button_style(expanded=getattr(self, "level_info_visible", False))

    def reset_bot_ui(self):
        # Cancel any pending reset timer
        if hasattr(self, '_reset_timer') and self._reset_timer is not None:
            self._reset_timer.stop()
            self._reset_timer = None
        # Close the success message box if still open
        if hasattr(self, '_success_box') and self._success_box is not None:
            self._success_box.close()
            self._success_box = None
        # Reset completion/messagebox flags
        self._pending_success_messagebox = None
        # Stop the worker thread if it's running
        if self.worker_thread and self.worker_thread.isRunning():
            if hasattr(self.worker_thread, "request_stop"):
                self.worker_thread.request_stop()
            self.worker_thread.terminate()
            self.worker_thread.wait()
            logging.info("Process terminated during reset. Starting fresh.")
        # Stop and hide the GIF animation
        self.processing_gif_movie.stop()
        self.processing_gif.hide()
        self.gif_anim.stop()
        # Reset progress visuals
        self.progress_bar.setValue(0)
        # Reset header avatar while respecting any equipped achievement badge.
        self._apply_header_avatar()
        self.header_image.show()
        self.idle_label.hide()
        self.header_visible = True
        # Exit minimal mode if active
        if self.minimal_mode:
            self.exit_minimal_mode()
            logging.info(f"Toggled Default Mode.")
        # Restore idle controls and greeting after the progress bar is cleared.
        self.is_running = False
        self.start_greeting_updates()
        self.set_initial_greeting()
        self._update_run_locked_controls()
        self.apply_visual_settings_to_current_state()

    def initUI(self):
        # Create central widget
        self.central_widget = QWidget(self)
        self.central_widget.setObjectName("CentralWidget")
        self.central_widget.setStyleSheet("""
            QWidget#CentralWidget {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(0, 0, 0, 0.05),
                    stop:0.8 rgba(0, 0, 0, 0.02),
                    stop:1 rgba(0, 0, 0, 0.08));
                border-radius: 25px;
                border: none;
                /* Subtle depth effect using gradient background */
            }
        """)
        self.setCentralWidget(self.central_widget)
        self.central_widget.mouseDoubleClickEvent = self.header_area_double_click
        self.layout = QVBoxLayout(self.central_widget)
        
        # Custom title bar
        title_bar = QWidget()
        self.title_bar = title_bar
        title_bar.setObjectName("TitleBar")
        title_bar.setStyleSheet("""
            QWidget#TitleBar {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(162, 89, 247, 0.4),
                    stop:0.5 rgba(255, 79, 163, 0.3),
                    stop:1 rgba(0, 224, 255, 0.4));
                border-radius: 15px;
                border: none;
            }
        """)
        title_bar.setFixedHeight(50)
        
        title_bar_layout = QHBoxLayout(title_bar)
        title_bar_layout.setContentsMargins(15, 5, 10, 5)  # Reduced right margin to bring buttons closer to edge
        title_bar_layout.setSpacing(5)  # Reduced spacing between elements
        
        # Router mode selector (center)
        mode_combo = CenteredComboBox(self)
        self.mode_combo = mode_combo
        for mode_key, mode_label in self.get_mode_options():
            mode_combo.addItem(mode_label, mode_key)
        mode_combo.setFixedWidth(260)
        mode_combo.setFixedHeight(34)
        mode_combo.setCursor(Qt.PointingHandCursor)
        mode_combo.setToolTip("Select which autorouter mode to run.")
        mode_combo.setStyleSheet("""
            QComboBox {
                color: rgba(255, 255, 255, 0.96);
                font-size: 13px;
                font-weight: 600;
                margin: 0;
                padding: 6px 30px 6px 30px;
                background: rgba(255, 255, 255, 0.15);
                border-radius: 12px;
                border: 1px solid rgba(255, 255, 255, 0.3);
                selection-background-color: rgba(0, 224, 255, 0.35);
            }
            QComboBox:hover {
                background: rgba(110, 64, 192, 0.32);
                border: 1px solid rgba(110, 64, 192, 0.65);
                color: rgba(255, 255, 255, 1.0);
            }
            QComboBox:focus {
                border: 1px solid rgba(0, 224, 255, 0.65);
                background: rgba(255, 255, 255, 0.18);
            }
            QComboBox:disabled {
                color: rgba(255, 255, 255, 0.55);
                background: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.16);
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 24px;
                border: none;
                background: transparent;
            }
            QComboBox::down-arrow {
                image: none;
                width: 0px;
                height: 0px;
            }
            QComboBox QAbstractItemView {
                color: rgba(255, 255, 255, 0.96);
                background: rgba(31, 22, 48, 0.96);
                border: 1px solid rgba(255, 255, 255, 0.28);
                border-radius: 8px;
                padding: 4px;
                outline: 0;
                selection-background-color: rgba(0, 224, 255, 0.28);
                selection-color: white;
            }
        """)
        mode_combo.currentIndexChanged.connect(self.on_mode_combo_changed)
        
        # Add shadow effect to the mode selector
        title_shadow = QGraphicsDropShadowEffect()
        title_shadow.setBlurRadius(8)
        title_shadow.setColor(QColor(0, 0, 0, 100))
        title_shadow.setOffset(2, 2)
        mode_combo.setGraphicsEffect(title_shadow)
        
        # Add stretch to center the selector
        title_bar_layout.addStretch()
        title_bar_layout.addWidget(mode_combo, 0, Qt.AlignCenter)
        title_bar_layout.addStretch()
        
        # Window control buttons (right side)
        minimize_btn = QPushButton("─")
        self.minimize_btn = minimize_btn
        minimize_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.1);
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 12px;
                color: rgba(255, 255, 255, 0.9);
                font-size: 12px;
                font-weight: bold;
                padding: 5px 8px;
                margin: 0px;
                min-width: 20px;
                max-width: 20px;
                min-height: 20px;
                max-height: 20px;
            }
            QPushButton:hover {
                background: rgba(0, 224, 255, 0.3);
                border: 1px solid rgba(0, 224, 255, 0.5);
            }
            QPushButton:pressed {
                background: rgba(0, 224, 255, 0.5);
            }
        """)
        minimize_btn.clicked.connect(self.showMinimized)
        minimize_btn.setFixedHeight(20)
        
        # Add shadow effect to minimize button
        minimize_shadow = QGraphicsDropShadowEffect()
        minimize_shadow.setBlurRadius(4)
        minimize_shadow.setColor(QColor(0, 0, 0, 80))
        minimize_shadow.setOffset(1, 1)
        minimize_btn.setGraphicsEffect(minimize_shadow)
        
        title_bar_layout.addWidget(minimize_btn, 0, Qt.AlignVCenter)
        
        close_btn = QPushButton("✕")
        self.close_btn = close_btn
        close_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.1);
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 12px;
                color: rgba(255, 255, 255, 0.9);
                font-size: 12px;
                font-weight: bold;
                padding: 5px 8px;
                margin: 0px;
                min-width: 20px;
                max-width: 20px;
                min-height: 20px;
                max-height: 20px;
            }
            QPushButton:hover {
                background: rgba(255, 79, 163, 0.4);
                border: 1px solid rgba(255, 79, 163, 0.6);
            }
            QPushButton:pressed {
                background: rgba(255, 79, 163, 0.6);
            }
        """)
        close_btn.clicked.connect(self.close)
        close_btn.setFixedHeight(20)
        
        # Add shadow effect to close button
        close_shadow = QGraphicsDropShadowEffect()
        close_shadow.setBlurRadius(4)
        close_shadow.setColor(QColor(0, 0, 0, 80))
        close_shadow.setOffset(1, 1)
        close_btn.setGraphicsEffect(close_shadow)
        
        title_bar_layout.addWidget(close_btn, 0, Qt.AlignVCenter)
        
        # Add title bar to main layout
        self.layout.addWidget(title_bar)
        
        # Background image
        bg_label = QLabel(self.central_widget)
        bg_label.setObjectName(BACKGROUND_LABEL_OBJECT_NAME)
        bg_label.mouseDoubleClickEvent = self.header_area_double_click
        pixmap = QPixmap(str(IMAGES_DIR / "autotestbg.jpg")).scaled(self.size(), Qt.KeepAspectRatioByExpanding)
        bg_label.setPixmap(pixmap)
        bg_label.setGeometry(0, 50, 400, 470)  # Adjusted y position to account for title bar
        bg_label.lower()  # Ensure background is at the very bottom

        # Main layout
        self.layout.setContentsMargins(0, 0, 0, 20)  # Remove top margin since we have title bar
        self.layout.setSpacing(2)

        # Top bar with settings button
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(20, 0, 20, 0)  # Add left/right margins to the top bar
        
        # Level info triangle button (left side)
        self.level_triangle_btn = QPushButton("▾")
        self.level_triangle_btn.setFixedSize(45, 35)  # Made wider: 45x35 instead of 35x35
        self.level_triangle_btn.setFont(QFont(self.axiforma_family, 16))  # Increased font size for better visibility
        self.level_triangle_btn.setCursor(Qt.PointingHandCursor)
        self.level_triangle_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: white;
                border: none;
                font-weight: bold;
                padding: 0px;
                margin: 0px;
            }
            QPushButton:hover {
                color: #FFA500;
            }
        """)
        # Add enhanced shadow effect to the triangle button
        shadow = QGraphicsDropShadowEffect(self.level_triangle_btn)
        shadow.setBlurRadius(12)  # Increased blur for softer shadow
        shadow.setColor(QColor(0, 0, 0, 150))  # Darker shadow with more opacity
        shadow.setOffset(3, 3)  # Slightly larger offset for more depth
        self.level_triangle_btn.setGraphicsEffect(shadow)
        
        self.level_triangle_btn.setAttribute(Qt.WA_Hover, True)
        self.level_triangle_btn.setMouseTracking(True)
        self.level_triangle_btn.installEventFilter(self)

        self.level_triangle_btn.clicked.connect(
            lambda: not self.level_info_visible and self.toggle_level_info()
        )
        top_bar.addWidget(self.level_triangle_btn)        
        # Level info panel as floating tooltip (not in main layout)
        self.level_info_panel = QFrame(self)
        self.level_info_panel.setObjectName("LevelInfoPanel")
        self.level_info_panel.setFixedWidth(235)
        self.level_info_panel.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.level_info_layout = QVBoxLayout(self.level_info_panel)
        self.level_info_layout.setContentsMargins(12, 10, 12, 10)
        self.level_info_layout.setSpacing(6)

        self.level_title_label = QLabel("Level 0")
        self.level_title_label.setObjectName("LevelInfoTitle")
        self.level_title_label.setAlignment(Qt.AlignCenter)
        self.level_info_layout.addWidget(self.level_title_label)

        self.level_xp_label = QLabel("XP: 0 | 0 to next")
        self.level_xp_label.setObjectName("LevelInfoRow")
        self.level_xp_label.setAlignment(Qt.AlignCenter)
        self.level_info_layout.addWidget(self.level_xp_label)

        self.level_xp_bar = PillProgressBar(self.level_info_panel)
        self.level_xp_bar.setObjectName("LevelXpBar")
        self.level_xp_bar.setRange(0, 100)
        self.level_xp_bar.setValue(0)
        self.level_xp_bar.setTextVisible(False)
        if hasattr(self.level_xp_bar, "set_effect_mode"):
            self.level_xp_bar.set_effect_mode("bubbles")
        self.level_xp_bar.setFixedHeight(12)
        self.level_xp_bar.setFixedWidth(205)
        self.level_info_layout.addWidget(self.level_xp_bar)

        self.level_coins_label = QLabel("Coins: 0")
        self.level_coins_label.setObjectName("LevelInfoRow")
        self.level_coins_label.setAlignment(Qt.AlignCenter)
        self.level_info_layout.addWidget(self.level_coins_label)

        self.level_docs_label = QLabel("Fresh Docs: 0")
        self.level_docs_label.setObjectName("LevelInfoMuted")
        self.level_docs_label.setAlignment(Qt.AlignCenter)
        self.level_info_layout.addWidget(self.level_docs_label)

        self._apply_level_info_panel_style()
        self.level_info_panel.hide()
        self.level_info_visible = False
        
        top_bar.addStretch()
        
        self.settings_btn = QPushButton("☰")
        self.settings_btn.setFixedSize(35, 35)
        self.settings_btn.setFont(QFont(self.axiforma_family, 16))
        self.settings_btn.setCursor(Qt.PointingHandCursor)
        self.settings_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                color: white;
                padding: 0px;
                margin: 0px;
            }
            QPushButton:hover {
                color: #5066FA;
            }
        """)
        self.settings_btn.setAttribute(Qt.WA_Hover, True)
        self.settings_btn.setMouseTracking(True)
        self.settings_btn.installEventFilter(self)
        self.settings_btn.clicked.connect(self.toggle_settings_menu)

        top_bar.addWidget(self.settings_btn)
        self.layout.addLayout(top_bar)

        # Create settings menu
        self.settings_menu = FrostedFrame(self)
        self.settings_menu.setObjectName("SettingsMenuFrame")
        self.settings_menu.setAttribute(Qt.WA_TranslucentBackground)
        self.settings_menu.setWindowFlags(Qt.FramelessWindowHint | Qt.Popup)

        self.settings_menu.setStyleSheet("""
            QFrame#SettingsMenuFrame {
                background-color: transparent;
                border: 1px solid rgba(100, 100, 100, 150);
                border-radius: 6px;
                padding: 8px;
            }
            QPushButton {
                background-color: transparent;
                color: white;
                border: none;
                text-align: left;
                padding: 6px 12px;
                font-size: 15px;
                font-weight: bold;
            }

            QPushButton:hover {
                background-color: rgba(61, 61, 61, 150);
                color: cyan;
            }

            QLabel {
                color: white;
            }
        """)


        self.settings_menu.setFrameShape(QFrame.StyledPanel)
        self.settings_menu.setFrameShadow(QFrame.Raised)
        self.settings_menu.hide()
        self.settings_menu_visible = False
        self.settings_menu.setMouseTracking(True)
        self.settings_menu.installEventFilter(self)

        menu_layout = QVBoxLayout(self.settings_menu)
        menu_layout.setContentsMargins(8, 2, 8, 2)
        menu_layout.setSpacing(8)  # Reduced spacing between items

        # --- Headless Mode Toggle with Label ---
        gif_on_path = os.path.join("assets", "gifs", "toggle_on_gif.gif")
        gif_off_path = os.path.join("assets", "gifs", "toggle_off_gif.gif")
        headless_row = QHBoxLayout()
        headless_row.setContentsMargins(12, 4, 12, 4)
        headless_row.setSpacing(8)  # Add space between label and toggle

        headless_label = QLabel("Headless Mode")
        headless_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        headless_label.setFont(QFont(self.axiforma_family, 9))  # Slightly larger font for toggle labels

        self.headless_toggle = CompactToggle(
            gif_on_path,
            gif_off_path,
            self.config.get("headless", False),
            parent=self,
            on_toggle=self.on_headless_toggle
        )

        headless_row.addWidget(headless_label, alignment=Qt.AlignVCenter)
        headless_row.addWidget(self.headless_toggle, alignment=Qt.AlignVCenter)
        menu_layout.addLayout(headless_row)

        # --- Show Console Toggle with Label ---
        console_row = QHBoxLayout()
        console_row.setContentsMargins(12, 4, 12, 4)
        console_row.setSpacing(8)  # Add space between label and toggle
        console_label = QLabel("Show Console")
        console_label.setFont(QFont(self.axiforma_family, 9))  # Slightly larger font for toggle labels
        self.console_toggle = CompactToggle(
            gif_on_path,  # Use the same GIFs as headless toggle
            gif_off_path,
            self.config.get("show_console", False),
            parent=self,
            on_toggle=self.on_console_toggle
        )
        self.log_console_window = None
        console_row.addWidget(console_label, alignment=Qt.AlignVCenter)
        console_row.addWidget(self.console_toggle, alignment=Qt.AlignVCenter)
        menu_layout.addLayout(console_row)
        
        # Restore console state from saved config
        if self.config.get("show_console", False):
            # Use QTimer to delay the console show until after UI is fully initialized
            QTimer.singleShot(100, lambda: self.on_console_toggle(True))

        # --- Parallel Router Controls ---
        parallel_routers_row = QHBoxLayout()
        parallel_routers_row.setContentsMargins(12, 4, 12, 4)
        parallel_routers_row.setSpacing(8)
        parallel_routers_label = QLabel("Parallel Routers")
        parallel_routers_label.setFont(QFont(self.axiforma_family, 9))
        self.parallel_routers_toggle = CompactToggle(
            gif_on_path,
            gif_off_path,
            self.config.get("parallel_routers_enabled", False),
            parent=self,
            on_toggle=self.on_parallel_routers_toggle
        )
        parallel_routers_row.addWidget(parallel_routers_label, alignment=Qt.AlignVCenter)
        parallel_routers_row.addWidget(self.parallel_routers_toggle, alignment=Qt.AlignVCenter)
        menu_layout.addLayout(parallel_routers_row)

        spin_style = """
            QSpinBox {
                background-color: rgba(255, 255, 255, 0.10);
                color: white;
                border: 1px solid rgba(255, 255, 255, 0.20);
                border-radius: 4px;
                padding: 2px 6px;
                min-width: 58px;
            }
            QSpinBox:disabled {
                color: rgba(255, 255, 255, 0.35);
                background-color: rgba(255, 255, 255, 0.04);
            }
        """

        parallel_instances_row = QHBoxLayout()
        parallel_instances_row.setContentsMargins(12, 0, 12, 4)
        parallel_instances_row.setSpacing(8)
        parallel_instances_label = QLabel("Router Instances")
        parallel_instances_label.setFont(QFont(self.axiforma_family, 8))
        self.parallel_router_instances_spin = QSpinBox()
        self.parallel_router_instances_spin.setRange(1, 6)
        self.parallel_router_instances_spin.setValue(int(self.config.get("parallel_router_instances", 2) or 2))
        self.parallel_router_instances_spin.setStyleSheet(spin_style)
        self.parallel_router_instances_spin.valueChanged.connect(self.on_parallel_router_instances_changed)
        parallel_instances_row.addWidget(parallel_instances_label, alignment=Qt.AlignVCenter)
        parallel_instances_row.addWidget(self.parallel_router_instances_spin, alignment=Qt.AlignVCenter)
        menu_layout.addLayout(parallel_instances_row)
        self._update_parallel_router_controls()



        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        menu_layout.addWidget(separator)

        # Shop button
        shop_btn = QPushButton("Shop")
        shop_btn.setFont(QFont(self.axiforma_family, 15))
        shop_btn.clicked.connect(self.open_shop_dialog)
        menu_layout.addWidget(shop_btn)

        # Inventory button
        inventory_btn = QPushButton("Inventory")
        inventory_btn.setFont(QFont(self.axiforma_family, 15))
        inventory_btn.clicked.connect(self.open_inventory_dialog)
        menu_layout.addWidget(inventory_btn)

        # View Folder button
        view_folder_btn = QPushButton("View Folder")
        view_folder_btn.setFont(QFont(self.axiforma_family, 15))
        view_folder_btn.clicked.connect(self.open_resources_folder)
        menu_layout.addWidget(view_folder_btn)

        # Add a spacer to push items to the top
        menu_layout.addItem(QSpacerItem(20, 20, QSizePolicy.Minimum, QSizePolicy.Expanding))
        
        # Create a container for the header
        self.header_container = QWidget()
        self.header_container.setFixedSize(400, HEADER_CONTAINER_HEIGHT)
        self.header_container.setMouseTracking(True)  # Enable mouse tracking for hover detection
        self.header_container.setStyleSheet("""
            QWidget {
                background: transparent;
                border: none;
            }
        """)
        header_layout = QVBoxLayout(self.header_container)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(0)
        header_layout.setAlignment(Qt.AlignCenter)

        # Silcrow Header GIF
        self.header_image = QLabel()
        self.header_image.setAlignment(Qt.AlignCenter)
        self.header_image.setFixedSize(HEADER_AVATAR_DIM, HEADER_AVATAR_DIM)
        self.header_image.setMouseTracking(True)
        self.header_image.mouseDoubleClickEvent = self.toggle_minimal_mode
        self.header_visible = True
        
        # Load and scale the header GIF
        self.header_movie = QMovie(str(GIFS_DIR / "silcrow.gif"))
        self.header_movie.setScaledSize(QSize(HEADER_AVATAR_DIM, HEADER_AVATAR_DIM))
        self.header_image.setMovie(self.header_movie)
        self.header_movie.start()
        
        # Add shadow effect to header image
        self.apply_shadow(self.header_image, color=Qt.darkCyan, blur=12, x_offset=2, y_offset=2)
        header_layout.addWidget(self.header_image, 0, Qt.AlignCenter)
        self.header_image.raise_()  # Ensure header image is on top

        # Idle message label
        initial_message = random.choice(self.idle_messages)
        self.idle_label = QLabel(initial_message)
        self.idle_label.setFont(QFont(self.axiforma_family, 10))
        self.idle_label.setStyleSheet("color: white;")
        self.idle_label.setAlignment(Qt.AlignCenter)
        self.idle_label.setWordWrap(True)
        self.idle_label.setFixedWidth(380)  # Increased width to use more of the 400px container
        self.idle_label.setMinimumHeight(40)  # Minimum height for single line messages
        self.idle_label.setMaximumHeight(150)  # Increased max height to allow 3-4 lines of text
        self.idle_label.hide()
        self.idle_label.mouseDoubleClickEvent = self.toggle_minimal_mode
        self.idle_label.setMouseTracking(True)  # Enable mouse tracking for hover detection
        # Add shadow effect to idle messages
        self.apply_shadow(self.idle_label, color=Qt.black, blur=10, x_offset=2, y_offset=2)
        header_layout.addWidget(self.idle_label, 0, Qt.AlignCenter)

        # Add header container to main layout and let the layout handle centering
        self.layout.addWidget(self.header_container, 0, Qt.AlignCenter)
        self.header_container.raise_()  # Ensure header container is on top of other widgets

        # 🔁 Processing GIF
        self.processing_gif = QLabel(self.central_widget)
        self.processing_gif.setFixedSize(230, 180)
        self.processing_gif.setAlignment(Qt.AlignCenter)
        self.processing_gif.setStyleSheet("""
            QLabel {
                background: transparent;
                border: none;
            }
        """)
        self.processing_gif_movie = QMovie(str(GIFS_DIR / "processing.gif"))
        self.processing_gif_movie.setScaledSize(self.processing_gif.size())
        self.processing_gif.setMovie(self.processing_gif_movie)

        # Apply shadow to GIF
        self.apply_shadow(self.processing_gif, blur=15, x_offset=5, y_offset=5, color=QColor(48, 25, 52, 180))

        x = int((self.width() - self.processing_gif.width()) / 4)
        y = int((self.height() - self.processing_gif.height()) / 2.5)
        self.processing_gif.move(x, y)
        self.processing_gif.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.processing_gif.hide()
        self.processing_gif.raise_()

        # === Warp animation logic begins here ===
        margin = 30
        y = self.height() // 2 - 80

        start_x = -self.processing_gif.width() - margin
        end_x = self.width() + margin

        self.gif_anim = QPropertyAnimation(self.processing_gif, b"pos")
        self.gif_anim.setDuration(12000)
        self.gif_anim.setStartValue(QPoint(start_x, y))
        self.gif_anim.setEndValue(QPoint(end_x, y))
        self.gif_anim.setEasingCurve(QEasingCurve.InOutSine)
        self.gif_anim.setLoopCount(-1)
        # === Warp animation logic ends here ===

        # Buttons
        btn_row = QHBoxLayout()
        self.generate_btn = self.styled_button("Generate", self.on_generate, width=150, height=40)
        self.apply_shadow(self.generate_btn)
        self.run_btn = self.styled_button("Run", self.on_run, width=150, height=40)
        self.apply_shadow(self.run_btn)
        btn_row.addWidget(self.generate_btn)
        btn_row.addWidget(self.run_btn)
        self.layout.addLayout(btn_row)

        # Add some spacing between buttons and progress bar
        self.layout.addSpacing(15)

        # Progress Bar
        self.progress_bar = PillProgressBar(self.central_widget)
        self.progress_bar.setFixedWidth(380)  # Make slightly shorter for better aesthetics
        self.progress_bar.setVisible(True)
        self.progress_label = QLabel("", self.progress_bar)
        self.progress_label.setAlignment(Qt.AlignCenter)
        self.progress_label.setStyleSheet("color: white; background-color: transparent;")
        self.progress_label.setFont(QFont(self.axiforma_family, 10, QFont.Bold))
        self.apply_shadow(self.progress_label, blur=6, x_offset=0, y_offset=1)
        self.progress_label.setGeometry(self.progress_bar.rect())
        self.progress_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.progress_bar.resizeEvent = lambda event: self.progress_label.setGeometry(self.progress_bar.rect())
        
        # Center the progress bar with equal margins on both sides
        progress_row = QHBoxLayout()
        progress_row.addStretch()
        progress_row.addWidget(self.progress_bar)
        progress_row.addStretch()
        self.layout.addLayout(progress_row)

        # After creating self.header_container and self.header_image:
        self.header_container.mouseDoubleClickEvent = self.header_area_double_click
        self.header_image.mouseDoubleClickEvent = self.header_area_double_click

        # Add this after menu creation
        self._settings_menu_timer = QTimer(self)
        self._settings_menu_timer.setInterval(100)
        self._settings_menu_timer.timeout.connect(self._check_settings_menu_mouse)

        # Enable mouse tracking on the main window and central widget
        self.setMouseTracking(True)
        if self.centralWidget():
            self.centralWidget().setMouseTracking(True)

    def set_progress_status(self, message):
        friendly_statuses = {
            "Loading Resources...": ("Loading Resources...", None),
            "Initializing Browser...": ("Preparing Browser...", None),
            "Counsel Batch Started": ("Processing Counsel Batch...", 0),
            "Main Opinion Batch Started": ("Processing Main Opinion Batch...", 0),
            "MSPB Batch Started": ("Processing MSPB Batch...", 0),
            "MSPB Parallel Batch Started": ("Processing MSPB Parallel Batch...", 0),
            "ITC Batch Started": ("Processing ITC Batch...", 0),
            "IRSPLR Batch Started": ("Processing IRSPLR Batch...", 0),
            "OHTAX0 Batch Started": ("Processing OHTAX0 Batch...", 0),
            "MNSUTB Batch Started": ("Processing MNSUTB Batch...", 0),
            "Success!": ("Automation Complete!", 100),
            "Completed": ("Completed", 100),
        }
        batch_prefixes = {
            "Counsel Batch Started": "Counsel Processed",
            "Main Opinion Batch Started": "Main Opinion Processed",
            "MSPB Batch Started": "MSPB Processed",
            "MSPB Parallel Batch Started": "MSPB Processed",
            "ITC Batch Started": "ITC Processed",
            "IRSPLR Batch Started": "IRSPLR Processed",
            "OHTAX0 Batch Started": "OHTAX0 Processed",
            "MNSUTB Batch Started": "MNSUTB Processed",
        }

        if message in friendly_statuses:
            label_text, progress_value = friendly_statuses[message]
            if message in batch_prefixes:
                self.batch_label_prefix = batch_prefixes[message]
                self.start_processing_gif()
            self.progress_label.setText(label_text)
            if progress_value is not None:
                self.progress_bar.setValue(progress_value)
            if message == "Completed":
                self.processing_gif_movie.stop()
                self.processing_gif.hide()
            return

        allowed_progress_prefixes = (
            "Counsel Processed",
            "Main Opinion Processed",
            "MSPB Processed",
            "ITC Processed",
            "IRSPLR Processed",
            "OHTAX0 Processed",
            "MNSUTB Processed",
        )
        if any(str(message).startswith(prefix) for prefix in allowed_progress_prefixes):
            try:
                current, total = map(int, message.split(":")[1].strip().split("/"))
                self.progress_label.setText(message)
                percent = int((current / total) * 100) if total > 0 else 0
                self.progress_bar.setValue(percent)
            except (ValueError, IndexError):
                self.progress_label.setText(message)
        else:
            logging.debug(f"Ignored backend-only status for UI progress bar: {message}")

    def handle_progress_update(self, batch, current, total):
        if batch == "counsel":
            self.progress_label.setText(f"Counsel Processed: {current}/{total}")
            percent = int((current / total) * 100) if total > 0 else 0
            self.progress_bar.setValue(percent)
        elif batch == "mspb":
            self.progress_label.setText(f"MSPB Processed: {current}/{total}")
            percent = int((current / total) * 100) if total > 0 else 0
            self.progress_bar.setValue(percent)
        elif batch == "itc":
            self.progress_label.setText(f"ITC Processed: {current}/{total}")
            percent = int((current / total) * 100) if total > 0 else 0
            self.progress_bar.setValue(percent)
        elif batch == "irsplr":
            self.progress_label.setText(f"IRSPLR Processed: {current}/{total}")
            percent = int((current / total) * 100) if total > 0 else 0
            self.progress_bar.setValue(percent)
        elif batch == "ohtax0":
            self.progress_label.setText(f"OHTAX0 Processed: {current}/{total}")
            percent = int((current / total) * 100) if total > 0 else 0
            self.progress_bar.setValue(percent)
        elif batch == "mnsutb":
            self.progress_label.setText(f"MNSUTB Processed: {current}/{total}")
            percent = int((current / total) * 100) if total > 0 else 0
            self.progress_bar.setValue(percent)
        elif batch == "main":
            self.progress_label.setText(f"Main Opinion Processed: {current}/{total}")
            percent = int((current / total) * 100) if total > 0 else 0
        self.progress_bar.setValue(percent)

    def start_processing_gif(self):
        if getattr(self, 'minimal_mode', False):
            self._show_minimal_header_only()
            return
        if self._quiet_run_mode_enabled():
            logging.info("Quiet Run Mode active; skipping decorative processing GIF/message startup.")
            self.show_automation_ui()
            return
        self.processing_gif_movie.start()
        self.gif_anim.start()
        # Centralized all UI switching logic into show_automation_ui
        self.show_automation_ui()

    def show_automation_ui(self):
        if getattr(self, 'minimal_mode', False):
            self._show_minimal_header_only()
            return

        # Hide header GIF
        if hasattr(self, 'header_image'):
            self.header_image.hide()

        if self._quiet_run_mode_enabled():
            if hasattr(self, 'idle_timer') and self.idle_timer.isActive():
                self.idle_timer.stop()
            if hasattr(self, 'processing_gif_movie'):
                self.processing_gif_movie.stop()
            if hasattr(self, 'gif_anim') and self.gif_anim.state() == QAbstractAnimation.Running:
                self.gif_anim.stop()
            if hasattr(self, 'idle_label'):
                self._stop_widget_fade(self.idle_label)
                self.idle_label.hide()
            if hasattr(self, 'processing_gif'):
                self._stop_widget_fade(self.processing_gif)
                self.processing_gif.hide()
            self.header_visible = False
            logging.info("Quiet Run Mode active; decorative run visuals hidden.")
            return

        # Set up and show idle label
        if hasattr(self, 'idle_label'):
            initial_message = self.get_next_idle_message()
            self.idle_label.setText(initial_message)

            self.fade_widget(self.idle_label, fade_in=True)
            self.idle_label.show()

        # Start the idle timer
        self.idle_timer.start()

        # Show and raise the processing GIF
        if hasattr(self, 'processing_gif'):
            self.fade_widget(self.processing_gif, fade_in=True)
            self.processing_gif.show()
            self.processing_gif.raise_()  # Ensure processing.gif is in front

            self.header_visible = False

        # Handle pending minimal mode
        if hasattr(self, '_pending_minimal_mode') and self._pending_minimal_mode:
            self._pending_minimal_mode = False
            self.enter_minimal_mode()
            logging.info(f"Toggled Minimal Mode.")

    def stop_processing_gif(self):
        #logging.info("stop_processing_gif called - starting cleanup")
        if hasattr(self, 'gif_anim'):
            self.gif_anim.stop()
        if hasattr(self, 'processing_gif_movie'):
            self.processing_gif_movie.stop()
        if hasattr(self, 'processing_gif'):
            self.processing_gif.hide()
        if hasattr(self, 'idle_label'):
            self.idle_label.hide()
        # Fade out idle messages and processing.gif, fade in header GIF
        self.show_header_gif_only()
        # Restore header after processing
        if not self.header_visible:
            if hasattr(self, 'header_image'):
                self._apply_header_avatar()
                self.header_image.show()
                logging.info("Header avatar shown")
            if hasattr(self, 'idle_label'):
                self.idle_label.hide()
            self.header_visible = True
            if hasattr(self, 'idle_timer'):
                self.idle_timer.stop()  # Stop the idle message timer
            logging.info("Header restored and idle timer stopped")
        # If a success message box is still open, close it
        if hasattr(self, '_success_box') and self._success_box is not None:
            self._success_box.close()
            self._success_box = None
            logging.info("Success box closed")
        #logging.info("stop_processing_gif completed")

    def open_resources_folder(self):
        try:
            folder_path = Path.home() / "Downloads" / "Case Law Auto-Routing Resources"
            if folder_path.exists():
                os.startfile(folder_path)
            else:
                ModernMessageBox("Folder Not Found", "The resources folder does not exist yet.", "warning", self).exec_()
        except Exception as e:
            logging.error(f"Failed to open resources folder")
            ModernMessageBox("Error", f"Unable to open folder.\n{e}", "error", self).exec_()    

    def auto_save_config(self):
        try:
            current_mode = self.config.get("mode", "dar" if self.config.get("dar_mode", False) else "smd")
            with open(CONFIG_DIR / "config.json", "w") as f:
                json.dump({
                    "headless": self.config.get("headless", False),
                    "show_console": self.config.get("show_console", False),
                    "dar_mode": current_mode == "dar",
                    "mode": current_mode,
                    "parallel_routers_enabled": self.config.get("parallel_routers_enabled", False),
                    "parallel_lni_limit": 0,
                    "parallel_router_instances": self.config.get("parallel_router_instances", 2),
                    "critical_error_email_enabled": self.config.get("critical_error_email_enabled", True),
                    "run_summary_email_enabled": self.config.get("run_summary_email_enabled", True),
                    "critical_error_developer_email": self.config.get(
                        "critical_error_developer_email",
                        "kevinjohn.libuna@reedelsevier.com"
                    ),
                    "critical_error_user_email": self.config.get("critical_error_user_email", ""),
                }, f, indent=4)
            logging.info(f"Config auto-saved. Headless: {self.config.get('headless', False)}")
        except Exception as e:
            logging.warning(f"Auto-save of config failed: {e}")

    def on_generate(self):
        try:
            self.progress_label.setText("Generating Excel Sheet...")
            QApplication.processEvents()
            base_folder = create_folders()

            self.progress_label.setText("Saving Excel Sheet...")
            QApplication.processEvents()
            excel_path = generate_excel(base_folder)

            self.progress_label.setText("Excel Sheet Saved")
            QApplication.processEvents()

            self.progress_label.setText("Opening Excel Sheet...")
            QApplication.processEvents()
            open_excel_file(excel_path)

            self.progress_label.setText("Excel Sheet Opened")
            QApplication.processEvents()
        except Exception as e:
            logging.error(f"Error")
            ModernMessageBox("Error", str(e), "error", self).exec_()

    def is_excel_file_open(self, file_path):
        try:
            # Try to open the file in exclusive mode
            with open(file_path, 'r+b'):
                return False
        except IOError:
            return True

    def on_run(self):
        self._success_message_shown = False
        try:
            # Show loading resources status immediately
            self.set_progress_status("Loading Resources...")
            # Reset completion/messagebox flags at the start of automation
            self._pending_success_messagebox = None
            self._success_message_shown = False  # Reset at start of automation run
            #logging.info("Reset automation completion flags at start of automation")
            base_folder = str(Path.home() / "Downloads" / "Case Law Auto-Routing Resources")
            latest_excel = get_latest_excel_file(base_folder)
            df = read_mapping_data(latest_excel)

            if self.is_excel_file_open(latest_excel):
                ModernMessageBox(
                    "Excel File Open",
                    "Please close the Excel file before running the automation.\n\n"
                    "The data mapping sheet must be closed to prevent any conflicts during processing.",
                    "warning",
                    self
                ).exec_()
                return

            # Exit minimal mode when starting automation
            if self.minimal_mode:
                self.exit_minimal_mode()

            self.stop_greeting_updates()
            self.is_running = True
            self._update_run_locked_controls()
            # Start the processing GIF and show automation UI
            self.start_processing_gif()
            # Start the Qt worker from the GUI thread; the worker handles heavy automation.
            self._run_automation_with_progress(latest_excel, df)
        except Exception as e:
            logging.error(f"Error checking Excel file: {e}", exc_info=True)
            self.is_running = False
            self._update_run_locked_controls()
            self.start_greeting_updates()
            ModernMessageBox("Error", f"Failed to check Excel file status:\n{e}", "error", self).exec_()

    def _run_automation_with_progress(self, latest_excel, df):
        try:
            if df.empty:
                logging.error("No valid data in Excel.")
                self.error_signal.emit("No valid data in Excel.")
                return
            
            # Auto-detect mode from filenames
            self.auto_detect_mode_from_filenames(df)
            
            # Log the current mode configuration
            current_mode = self.config.get("mode", "dar" if self.config.get("dar_mode", False) else "smd")
            logging.info(f"Mode configuration - dar_mode: {self.config.get('dar_mode', False)}, mode: {current_mode}")
            
            total = len(df)
            # Set status to Initializing Browser before browser is started
            self.status_signal.emit("Initializing Browser...")
            set_status_fn = lambda text: self.status_signal.emit(text)
            def emit_progress(batch, current, total):
                self.progress_signal.emit(batch, current, total)
            self.worker_thread = WorkerThread(
                update_progress=emit_progress,
                set_status=set_status_fn,
                show_success=self.final_success_signal.emit,
                show_error=self.error_signal.emit,
                total_count=total,
                latest_excel=latest_excel,
                df=df,
                dar_mode=current_mode == "dar",
                wc_mode=False,
                mspb_mode=current_mode == "mspb",
                itc_mode=current_mode == "itc",
                irsplr_mode=current_mode == "irsplr",
                ohtax0_mode=current_mode == "ohtax0",
                mnsutb_mode=current_mode == "mnsutb",
            )
            self.worker_thread.start()
        except Exception as e:
            logging.error(f"Error initializing progress tracking: {str(e)}")
            import traceback
            logging.error(f"Traceback: {traceback.format_exc()}")
            self.error_signal.emit(f"Error initializing progress tracking: {e}")

    def on_reset(self):
        # Cancel any pending reset timer
        if hasattr(self, '_reset_timer') and self._reset_timer is not None:
            self._reset_timer.stop()
            self._reset_timer = None

        # Stop the worker thread if it exists
        if hasattr(self, 'worker_thread') and self.worker_thread:
            if self.worker_thread.isRunning():
                current_mode = self.config.get("mode", "dar" if self.config.get("dar_mode", False) else "smd")
                latest_excel = getattr(self.worker_thread, "latest_excel", None)
                worker_df = getattr(self.worker_thread, "df", None)
                logging.critical("User reset automation during an active run. Capturing critical report.")
                if hasattr(self.worker_thread, "request_stop"):
                    self.worker_thread.request_stop()
                self.worker_thread.terminate()
                self.worker_thread.wait()

                rerun_summary = finalize_rerun_ready_statuses(
                    df=worker_df,
                    latest_excel=latest_excel,
                    mode=current_mode,
                    flush=True,
                )
                threading.Thread(
                    target=notify_critical_error,
                    kwargs={
                        "title": "User reset automation during active run",
                        "error": "The user clicked Reset while automation was still running or waiting too long.",
                        "latest_excel": latest_excel,
                        "mode": current_mode,
                        "details": {
                            "Trigger": "Manual Reset",
                            "Reason": "User reset the bot during an active run.",
                            "Rerun Status Summary": rerun_summary,
                        },
                        "run_status_summary": rerun_summary,
                        "config": dict(self.config),
                    },
                    daemon=True,
                ).start()
            else:
                self.worker_thread.wait()
            self.worker_thread = None

        # Reset UI state
        self.is_running = False
        self.reset_bot_ui()

        # Clear any pending success messagebox
        self._pending_success_messagebox = None
        self._success_message_shown = False

        logging.info("Automation reset completed.")


    def build_success_message(self, user_name, counsel_success, main_success, counsel_already, main_already, error_log_entries=None, counsel_timeout=0, main_timeout=0):
        try:
            counsel_success = int(counsel_success) if counsel_success is not None else 0
            main_success = int(main_success) if main_success is not None else 0
            counsel_already = int(counsel_already) if counsel_already is not None else 0
            main_already = int(main_already) if main_already is not None else 0
        except (ValueError, TypeError):
            counsel_success = main_success = counsel_already = main_already = 0
        total_success = counsel_success + main_success
        total_already = counsel_already + main_already
        current_mode = self.config.get("mode", "dar" if self.config.get("dar_mode", False) else "smd")

        if total_success == 0 and total_already == 0 and error_log_entries and len(error_log_entries) > 0:
            message = (
                f"Automation completed, but all documents encountered errors.\n\n"
                f"Please review the error details below and re-run the automation if needed.\n\n"
            )
            message += "🫠 The following LNIs encountered errors:\n"
            for entry in error_log_entries[:10]:
                lni = entry.get('LNI', 'Unknown LNI')
                fname = entry.get('File Name', 'Unknown File')
                err = entry.get('Error Message', 'Unknown Error')
                message += f"• {lni} ({fname}): {err}\n"
            if len(error_log_entries) > 10:
                message += f"...and {len(error_log_entries) - 10} more. See error report for details.\n"
            return message

        if total_success == 0 and total_already == 0:
            return f"No unfinished rows found for this run.\n\nNo new routing needed, {user_name}!"

        if current_mode == "itc":
            if total_success == 0 and total_already > 0:
                return f"All ITC documents were already processed.\n\nNo new routing needed, {user_name}!"
            message = (
                f"Routing completed!\n\n"
                f"Successfully routed {main_success} new ITC document(s).\n\n"
            )
            if main_already > 0:
                message += f"Additionally, {main_already} ITC document(s) were already processed.\n\n"
            message += f"Way to go, {user_name}!"
            return message

        if current_mode == "irsplr":
            if total_success == 0 and total_already > 0:
                return f"All IRSPLR documents were already processed.\n\nNo new routing needed, {user_name}!"
            message = (
                f"Routing completed!\n\n"
                f"Successfully routed {main_success} new IRSPLR document(s).\n\n"
            )
            if main_already > 0:
                message += f"Additionally, {main_already} IRSPLR document(s) were already processed.\n\n"
            message += f"Way to go, {user_name}!"
            return message

        if current_mode == "ohtax0":
            if total_success == 0 and total_already > 0:
                return f"All OHTAX0 documents were already processed.\n\nNo new routing needed, {user_name}!"
            message = (
                f"Routing completed!\n\n"
                f"Successfully routed {main_success} new OHTAX0 document(s).\n\n"
            )
            if main_already > 0:
                message += f"Additionally, {main_already} OHTAX0 document(s) were already processed.\n\n"
            message += f"Way to go, {user_name}!"
            return message

        if current_mode == "mnsutb":
            if total_success == 0 and total_already > 0:
                return f"All MNSUTB documents were already processed.\n\nNo new routing needed, {user_name}!"
            message = (
                f"Routing completed!\n\n"
                f"Successfully routed {main_success} new MNSUTB document(s).\n\n"
            )
            if main_already > 0:
                message += f"Additionally, {main_already} MNSUTB document(s) were already processed.\n\n"
            message += f"Way to go, {user_name}!"
            return message
    
        if total_success == 0 and total_already > 0:
            message = (
                f"All documents were already processed.\n\n"
                f"No new routing needed, {user_name}! 🫡"
            )
        else:
            message = (
                f"Routing completed!\n\n"
                f"Successfully routed {total_success} new document(s):\n"
                f"• Counsel: {counsel_success}\n"
                f"• Main Opinion: {main_success}\n\n"
            )
            if total_already > 0:
                message += (
                    f"Additionally, {total_already} document(s) were already processed:\n"
                    f"• Counsel: {counsel_already}\n"
                    f"• Main Opinion: {main_already}\n\n"
                )
            message += f"Way to go, {user_name}! 🚀"

                # Add error details if present
            if error_log_entries and len(error_log_entries) > 0:
                message += "\n🫠 The following LNIs encountered errors:\n"
                for entry in error_log_entries[:10]:
                    lni = entry.get('LNI', 'Unknown LNI')
                    fname = entry.get('File Name', 'Unknown File')
                    err = entry.get('Error Message', 'Unknown Error')
                    message += f"• {lni} ({fname}): {err}\n"
                if len(error_log_entries) > 10:
                    message += f"...and {len(error_log_entries) - 10} more. See error report for details.\n"

        return message
    def handle_success(self, user_name, counsel_success, main_success, counsel_already, main_already, counsel_timeout=0, main_timeout=0):
        def do_handle():
            self._automation_completed = True
            logging.info("Starting post-automation cleanup...")
            # Always stop and hide processing.gif after automation
            if hasattr(self, 'processing_gif_movie'):
                self.processing_gif_movie.stop()
            if hasattr(self, 'processing_gif'):
                self.processing_gif.hide()
            if hasattr(self, 'idle_label'):
                self.idle_label.hide()
            # Cancel any previous reset timer
            if hasattr(self, '_reset_timer') and self._reset_timer is not None:
                self._reset_timer.stop()
                self._reset_timer = None
            # Always close any existing success messagebox before showing a new one
            if hasattr(self, '_success_box') and self._success_box is not None:
                self._success_box.close()
                self._success_box = None
            # Remove any notification popup
            if hasattr(self, '_notification_popup') and self._notification_popup:
                self._notification_popup.hide()
                self._notification_popup.deleteLater()
                self._notification_popup = None
            # Award progression from one central economy helper.
            try:
                total_success = int(counsel_success or 0) + int(main_success or 0)
                total_already = int(counsel_already or 0) + int(main_already or 0)
                total_timeouts = int(counsel_timeout or 0) + int(main_timeout or 0)
                total_errors = len(global_error_log_entries) if global_error_log_entries else 0
                current_mode = self.config.get("mode", "dar" if self.config.get("dar_mode", False) else "smd")
                parallel_routers = 1
                if self.config.get("parallel_routers_enabled", False):
                    parallel_routers = int(self.config.get("parallel_router_instances", 1) or 1)

                reward_summary = award_run_rewards(
                    load_user_rewards(),
                    fresh_documents=total_success,
                    already_processed=total_already,
                    error_count=total_errors,
                    timeout_count=total_timeouts,
                    mode=current_mode,
                    parallel_routers=parallel_routers,
                )
                self.user_data = load_user_rewards()

                self._last_run_reward_summary = reward_summary
                self.update_level_display()
            except Exception:
                logging.error("Failed to award run rewards", exc_info=True)

            # If in minimal mode, show notification popup and set pending messagebox
            if self.minimal_mode:
                self._pending_success_messagebox = (user_name, counsel_success, main_success, counsel_already, main_already, counsel_timeout, main_timeout)
                self.header_visible = True
                self.is_running = False
                self._update_run_locked_controls()
                self.show_notification_badge()
                return
            # ✅ Defensive cleanup to prevent accidental re-trigger
            if self._pending_success_messagebox is not None:
                logging.info("Clearing pending success messagebox flag to prevent re-show")
                self._pending_success_messagebox = None

            # Default behavior if not in minimal mode
            if hasattr(self, '_success_box') and self._success_box is not None:
                self._success_box.close()
                self._success_box = None
            if hasattr(self, '_notification_popup') and self._notification_popup:
                self._notification_popup.hide()
                self._notification_popup.deleteLater()
                self._notification_popup = None
            reward_summary = getattr(self, '_last_run_reward_summary', None)
            if reward_summary and (int(reward_summary.get("fresh_documents", 0) or 0) > 0 or reward_summary.get("new_achievements")):
                reward_popup = format_reward_summary(reward_summary)
                old_level = int(reward_summary.get("old_level", 0) or 0)
                new_level = int(reward_summary.get("new_level", old_level) or old_level)
                if new_level > old_level:
                    if new_level >= 2 and old_level < 2:
                        self.show_lvl2unlock_gif()
                    else:
                        self.show_lvlup_gif_then_popup(reward_popup, duration=6000)
                else:
                    self.show_notification_popup(reward_popup, duration=4500)
            self._last_run_reward_summary = None
            #logging.info("About to call stop_processing_gif()")
            self.stop_processing_gif()
            #logging.info("stop_processing_gif() completed")
            self.is_running = False
            self._update_run_locked_controls()
            self.apply_visual_settings_to_current_state()
            success_message = self.get_success_message(
                user_name, counsel_success, main_success,
                counsel_already, main_already,
                error_log_entries=global_error_log_entries,
                counsel_timeout=counsel_timeout,
                main_timeout=main_timeout
            )
            logging.info(f"Auto-Routing Summary: {success_message}")
            if global_error_log_entries and len(global_error_log_entries) > 0:
                logging.error(f"Errors encountered in the following LNIs: {[e['LNI'] for e in global_error_log_entries]}")
            
            # Reposition console window if it's visible
            if hasattr(self, 'log_console_window') and self.log_console_window and self.log_console_window.isVisible():
                self.log_console_window.position_window()
            
        if not self.minimal_mode:
            if self._success_message_shown:
                return  # Avoid re-showing

            message = self.build_success_message(user_name, counsel_success, main_success, counsel_already, main_already, error_log_entries=global_error_log_entries)
            
            if (
                not self._success_message_dismissed and
                self._last_success_log_time and
                not self.is_running
            ):
                logging.info("Showing success messagebox after toggling back to default mode.")
                message = self.build_success_message(
                    user_name, counsel_success, main_success,
                    counsel_already, main_already,
                    error_log_entries=global_error_log_entries,
                    counsel_timeout=counsel_timeout,
                    main_timeout=main_timeout
                )
            
            # Decide headline based on results
            total_success = (counsel_success or 0) + (main_success or 0)
            total_already = (counsel_already or 0) + (main_already or 0)
            total_errors = len(global_error_log_entries) if global_error_log_entries else 0

            if total_errors > 0 and (total_success > 0 or total_already > 0):
                headline = "ALMOST THERE!"
            elif total_success > 0 or total_already > 0:
                headline = "SUCCESS!"
            elif total_errors > 0 and total_success == 0 and total_already == 0:
                headline = "OOPS."
            elif total_success == 0 and total_already == 0:
                headline = "NO NEW ROUTING"
            else:
                headline = self.get_success_title()

            # Build message body
            success_title = headline
            success_message = self.get_success_message(
                user_name, counsel_success, main_success,
                counsel_already, main_already,
                error_log_entries=global_error_log_entries,
                counsel_timeout=counsel_timeout,
                main_timeout=main_timeout
            )
            box = ModernMessageBox(success_title, success_message, "success", self)
            self._success_box = box
            self._success_message_shown = True
            self._pending_success_messagebox = None

            def on_box_closed():
                logging.info("Final Summary Message closed")
                self._success_box = None
                self._success_message_shown = False
                self._automation_completed = False
                self._pending_success_messagebox = None
                self.progress_label.setText("Success!")
                self.reset_bot_ui()
                
            box.finished.connect(on_box_closed)
            logging.info("Displaying Final Summary Message.")
            
            # Show toast notification to alert user (mode-sensitive title and concise message)
            current_mode = self.config.get("mode", "dar" if self.config.get("dar_mode", False) else "smd")
            
            if current_mode == "mspb":
                toast_title = "MSPB Auto-Routing Complete"
            elif current_mode == "itc":
                toast_title = "ITC Auto-Routing Complete"
            elif current_mode == "irsplr":
                toast_title = "IRSPLR Auto-Routing Complete"
            elif current_mode == "ohtax0":
                toast_title = "OHTAX0 Auto-Routing Complete"
            elif current_mode == "mnsutb":
                toast_title = "MNSUTB Auto-Routing Complete"
            elif current_mode == "dar":
                toast_title = "DAR Auto-Routing Complete"
            else:
                toast_title = "SMD USAP Courts Auto-Routing Complete"
            toast_msg = f"Awesome job, {user_name}! Click to open app and view summary."
            self.show_toast_notification(toast_title, toast_msg)
            box.exec_()

            self._pending_success_messagebox = None

            #logging.info("Final success QMessageBox shown")
            self.start_greeting_updates()
            self._sync_run_buttons()
            # Check for NO COUNSEL ATTACHED status and show real-time popup
            if hasattr(self, 'current_status') and self.current_status == 'NO COUNSEL ATTACHED':
                box = ModernMessageBox("Counsel Missing", "Oops! Looks like we missed a counsel. Please click reset and run the bot again.", "warning", self)
                box.exec_()
                return
        QTimer.singleShot(0, do_handle)

    def test_intro_animation(self):
        """Test method to manually trigger the intro animation"""
        try:
            if hasattr(self, 'intro_animation') and hasattr(self, 'header_image'):
                # Reset the intro played flag to allow re-triggering
                if hasattr(self, '_intro_played'):
                    delattr(self, '_intro_played')
                
                # Start the intro animation
                self.intro_animation.start_intro_sequence(
                    self.header_image,
                    on_complete=lambda: self._on_intro_animation_complete("Test intro animation completed")
                )
                logging.info("Test intro animation started")
            else:
                logging.error("Intro animation or header image not available")
        except Exception as e:
            logging.error(f"Failed to start test intro animation: {e}")

    def toggle_settings_menu(self):
        if self.settings_menu.isVisible():
            self.settings_menu.hide()
            self.settings_menu_visible = False
            self._settings_menu_timer.stop()
        else:
            button_pos = self.settings_btn.mapToGlobal(self.settings_btn.rect().bottomLeft())
            self.settings_menu.move(button_pos)
            self.apply_frosted_glass_background()  # <- Required before showing
            self.settings_menu.show()
            self.settings_menu_visible = True
            self._settings_menu_timer.start()

    def hide_settings_menu(self):
        self.settings_menu.hide()
        self.settings_menu_visible = False
        self._settings_menu_timer.stop()
        
    def _settings_btn_hover_enter(self, event):
        if not self.settings_menu.isVisible():
            self.toggle_settings_menu()
        event.accept()
        
    def _settings_btn_hover_leave(self, event):
        # Start timer to check if mouse is over menu or button
        self._settings_menu_timer.start()
        event.accept()
        
    def _check_settings_menu_mouse(self):
        # Check if mouse is over settings_btn or settings_menu
        pos = QCursor.pos()
        btn_rect = self.settings_btn.rect()
        menu_rect = self.settings_menu.rect()
        btn_global = self.settings_btn.mapToGlobal(btn_rect.topLeft()), self.settings_btn.mapToGlobal(btn_rect.bottomRight())
        menu_global = self.settings_menu.mapToGlobal(menu_rect.topLeft()), self.settings_menu.mapToGlobal(menu_rect.bottomRight())
        def in_rect(global_rect):
            top_left, bottom_right = global_rect
            return (top_left.x() <= pos.x() <= bottom_right.x() and
                    top_left.y() <= pos.y() <= bottom_right.y())
        if not (in_rect(btn_global) or (self.settings_menu.isVisible() and in_rect(menu_global))):
            self.hide_settings_menu()
            self._settings_menu_timer.stop()

    def eventFilter(self, obj, event):
        if obj == self.settings_btn:
            if event.type() == QEvent.HoverEnter:
                if not getattr(self, 'settings_menu_visible', False):
                    self.toggle_settings_menu()
            elif event.type() == QEvent.Leave:
                self._settings_menu_timer.start()
        return super().eventFilter(obj, event)
    
    def get_next_idle_message(self):
        if not self.idle_message_queue:
            # Shuffle a new cycle
            self.idle_message_queue = self.idle_messages[:]
            random.shuffle(self.idle_message_queue)
        return self.idle_message_queue.pop()

    def update_idle_message(self):
        """Update the idle message to a random one from the list"""
        if self.is_running and self._quiet_run_mode_enabled():
            return
        # Update message during automation (when header is not visible OR when automation is running)
        if not self.header_visible or self.is_running:
            self.current_message_index = random.randint(0, len(self.idle_messages) - 1)
            new_message = self.get_next_idle_message()
            if hasattr(self, 'idle_label') and self.idle_label.isVisible():
                self.idle_label.setText(new_message)
        # Removed unnecessary log for 'Header visible and not running, skipping idle message update'

    def toggle_header_visibility(self, event):
        """Toggle minimal mode on header double-click"""
        self.toggle_minimal_mode()

    def event(self, event):
        """Handle window events"""
        if event.type() == event.NonClientAreaMouseButtonDblClick:
            # Double click on title bar - now just toggles minimal mode
            if self.minimal_mode:
                self.exit_minimal_mode()
                logging.info(f"Toggled Default Mode.")
            else:
                self.enter_minimal_mode()
                logging.info(f"Toggled Minimal Mode.")
            return True
        return super().event(event)

    def update_header_image(self, width=HEADER_AVATAR_DIM, height=HEADER_AVATAR_DIM):
        """Reset the header avatar to avoid distortion after animations."""
        try:
            # Aggressively clear/reset the label
            self.header_image.setGeometry(0, 0, width, height)
            # Remove any lingering animation
            if hasattr(self, '_header_fade_anim'):
                self._header_fade_anim.stop()
                del self._header_fade_anim
            self._apply_header_avatar(QSize(width, height))
            logging.info(f"Header avatar reset with size {width}x{height}")
        except Exception as e:
            logging.error("Error updating header avatar")

    def _restore_default_mode_widgets(self):
        """Restore only the main UI widgets when returning from minimal mode."""
        central_widget = self.centralWidget()
        if central_widget:
            central_widget.show()
            for child in central_widget.findChildren(QWidget, options=Qt.FindDirectChildrenOnly):
                if isinstance(child, QDialog) or child.windowFlags() & (Qt.Popup | Qt.Tool):
                    continue
                child.show()

        log_console_window = getattr(self, 'log_console_window', None)
        if log_console_window:
            if self.config.get("show_console", False):
                log_console_window.show()
            else:
                log_console_window.hide()

        if hasattr(self, 'settings_menu'):
            self.hide_settings_menu()

    def _resume_header_avatar_animations(self):
        """Restart badge/Silcrow animations after compact mode reveals the header."""
        if not hasattr(self, 'header_image') or not self.header_image:
            return

        if hasattr(self, 'header_movie') and self.header_image.movie() is self.header_movie:
            self.header_movie.start()

        effect_layer = getattr(self, '_header_badge_effect_layer', None)
        if effect_layer:
            effect_layer.setGeometry(self.header_image.rect())
            effect_layer.start()
            effect_layer.raise_()

        motion_animator = getattr(self, '_header_badge_motion_animator', None)
        if motion_animator:
            motion_animator.start()

        bob_anim = getattr(self, '_header_badge_bob_anim', None)
        if bob_anim and bob_anim.state() != QAbstractAnimation.Running:
            bob_anim.start()

    def _stop_widget_fade(self, widget, opacity=1.0):
        """Stop a pending fade so hidden compact-mode widgets cannot reappear."""
        if not widget:
            return
        anim = getattr(widget, '_fade_anim', None)
        if anim:
            anim.stop()
            anim.deleteLater()
            widget._fade_anim = None
        widget.setWindowOpacity(opacity)

    def _suspend_run_visuals_for_minimal_mode(self):
        """Hide run-only idle text and processing animation while compact."""
        for attr in ('idle_label', 'processing_gif'):
            widget = getattr(self, attr, None)
            if widget:
                self._stop_widget_fade(widget)
                widget.hide()

        if hasattr(self, 'idle_timer') and self.idle_timer.isActive():
            self.idle_timer.stop()
        if hasattr(self, 'gif_anim') and self.gif_anim.state() == QAbstractAnimation.Running:
            self.gif_anim.stop()
        if hasattr(self, 'processing_gif_movie'):
            self.processing_gif_movie.stop()

        self.header_visible = True

    def _show_minimal_header_only(self):
        """Keep compact mode focused on the badge/Silcrow avatar only."""
        self._suspend_run_visuals_for_minimal_mode()
        self.header_container.show()
        self.header_image.show()
        self.header_container.raise_()
        self.header_image.raise_()
        self._resume_header_avatar_animations()

    def _restore_running_automation_ui(self):
        """Return from compact mode to the in-run layout without waking idle controls."""
        self._update_run_locked_controls()

        if hasattr(self, 'header_image'):
            self.header_image.hide()
        if self._quiet_run_mode_enabled():
            self._apply_quiet_run_mode_visibility()
            return
        if hasattr(self, 'idle_label'):
            self._stop_widget_fade(self.idle_label)
            if not self.idle_label.text():
                self.idle_label.setText(self.get_next_idle_message())
            self.idle_label.show()
            self.idle_label.raise_()
        if hasattr(self, 'idle_timer') and not self.idle_timer.isActive():
            self.idle_timer.start()

        if hasattr(self, 'processing_gif'):
            self._stop_widget_fade(self.processing_gif)
            self.processing_gif.show()
            self.processing_gif.raise_()
        if hasattr(self, 'processing_gif_movie'):
            self.processing_gif_movie.start()
        if hasattr(self, 'gif_anim') and self.gif_anim.state() != QAbstractAnimation.Running:
            self.gif_anim.start()

        self.header_visible = False

    def closeEvent(self, event):
        """Clean up resources when window is closed"""
        try:
            if hasattr(self, '_stop_header_badge_bob'):
                self._stop_header_badge_bob()
            if hasattr(self, 'header_movie'):
                self.header_movie.stop()
            if hasattr(self, 'processing_gif_movie'):
                self.processing_gif_movie.stop()
            if hasattr(self, 'idle_timer'):
                self.idle_timer.stop()
            if hasattr(self, 'greeting_timer'):
                self.greeting_timer.stop()
        except Exception as e:
            logging.error(f"Error during cleanup")
        super().closeEvent(event)

    def hide_gui_on_hover_exit(self):
        """Hide the GUI when mouse leaves the window area"""
        if not self.underMouse():
            self.enter_minimal_mode()
            logging.info(f"Toggled Minimal Mode.")

    def enter_minimal_mode(self):
        # Allow minimal mode during automation - removed restriction
        if not self.minimal_mode:
            self.minimal_mode = True
            self.original_geometry = self.geometry()
            self.original_size = self.size()
            self._saved_pos = self.pos()
            if hasattr(self, 'settings_menu'):
                self.hide_settings_menu()
            for child in self.centralWidget().findChildren(QWidget, options=Qt.FindDirectChildrenOnly):
                if child is not self.header_container:
                    child.hide()
            for child in self.header_container.findChildren(QLabel):
                if child is not self.header_image:
                    child.hide()
            # Hide lvlup.gif overlay if present
            if hasattr(self, '_lvlup_gif_overlay') and self._lvlup_gif_overlay is not None:
                self._lvlup_gif_overlay.hide()
            self._show_minimal_header_only()
            
            # Start intro animation on initial launch.
            if (hasattr(self, 'intro_animation') and 
                not hasattr(self, '_intro_played')):
                self._intro_played = True
                QTimer.singleShot(500, lambda: self.intro_animation.start_intro_sequence(
                    self.header_image, 
                    on_complete=self._on_intro_animation_complete
                ))
            
            self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
            self.setAttribute(Qt.WA_TranslucentBackground, True)
            self.centralWidget().setAttribute(Qt.WA_TranslucentBackground, True)
            
            # Preserve the background image instead of setting transparent
            # Get current background from equipped rewards
            user_data = load_user_rewards()
            equipped = user_data.get('equipped', {})
            header = equipped.get('header')
            
            bg_path = self.get_background_path(header)
            
            # Apply background image for minimal mode
            bg_position = self._background_position_css(header)
            minimal_stylesheet = f"""
                QMainWindow {{
                    background-image: url({bg_path});
                    background-repeat: no-repeat;
                    background-position: {bg_position};
                    background-attachment: fixed;
                }}
            """
            self.setStyleSheet(minimal_stylesheet)
            self.centralWidget().setStyleSheet("background: transparent;")
            
            # Re-set the window icon after changing window flags to ensure it appears in taskbar
            app_icon = QIcon(str(ICONS_DIR / "silcrow.ico"))
            self.setWindowIcon(app_icon)
            header_height = self.header_container.height()
            self.resize(self.header_container.width(), header_height)
            self.move(self._saved_pos)
            self.show()

            # Show emoji marker in minimal mode, or a fallback marker for pending success.
            if self._has_equipped_emoji() or getattr(self, '_pending_success_messagebox', None):
                self.show_notification_badge()
            else:
                self.hide_notification_badge()

    def exit_minimal_mode(self):
        if self.minimal_mode:
            self.minimal_mode = False
            self._saved_pos = self.pos()
            self.setWindowFlags(Qt.Window)
            self.setAttribute(Qt.WA_TranslucentBackground, False)
            self.centralWidget().setAttribute(Qt.WA_TranslucentBackground, False)
            
            # Restore the background image by calling apply_equipped_rewards
            self.apply_equipped_rewards()
            
            # Re-set the window icon after changing window flags to ensure it appears in taskbar
            app_icon = QIcon(str(ICONS_DIR / "silcrow.ico"))
            self.setWindowIcon(app_icon)
            self.resize(self.original_size)
            self._restore_default_mode_widgets()
            # Show lvlup.gif overlay if present
            if hasattr(self, '_lvlup_gif_overlay') and self._lvlup_gif_overlay is not None:
                self._lvlup_gif_overlay.show()
                self._lvlup_gif_overlay.raise_()  # Bring to front
                gif_label = self._lvlup_gif_overlay.findChild(QLabel)
                if gif_label and gif_label.movie():
                    gif_label.movie().start()    
            # Ensure level info panel stays hidden when exiting minimal mode
            if hasattr(self, 'level_info_panel'):
                self.level_info_panel.hide()
                self.level_info_visible = False
            if self.is_running:
                self._restore_running_automation_ui()
                self.setGeometry(self.original_geometry)
                self.move(self._saved_pos)
                self.show()
                self.hide_notification_badge()
                return
            # Ensure processing.gif is properly hidden after automation completion
            if hasattr(self, 'processing_gif') and not self.is_running:
                self.processing_gif.hide()
            if hasattr(self, 'processing_gif_movie') and not self.is_running:
                self.processing_gif_movie.stop()
            if not self.is_running:
                if hasattr(self, 'idle_label') and hasattr(self, 'is_running') and not self.is_running:
                    self.idle_label.hide()
            self.setGeometry(self.original_geometry)
            self.move(self._saved_pos)
            self.show()
            # If a success message box is still open, close it
            if hasattr(self, '_success_box') and self._success_box is not None:
                self._success_box.close()
                self._success_box = None
                self._success_message_shown = False

            # Hide notification popup if present
            if hasattr(self, '_notification_popup') and self._notification_popup:
                self._notification_popup.hide()
                self._notification_popup.deleteLater()
                self._notification_popup = None
            
            # Only show the pending success messagebox if automation is complete, not running, AND it hasn't been shown yet.
            if (getattr(self, '_pending_success_messagebox', None) and
                getattr(self, '_automation_completed', False) and
                not self.is_running and not self._success_message_shown):

                logging.info(f"Showing pending success messagebox. Args: {self._pending_success_messagebox}")
                
                args = self._pending_success_messagebox
                if isinstance(args, tuple) and len(args) == 7:
                    user_name, counsel_success, main_success, counsel_already, main_already, counsel_timeout, main_timeout = args
                    message = self.build_success_message(user_name, counsel_success, main_success, counsel_already, main_already, error_log_entries=global_error_log_entries)

                    box = self.create_styled_message_box(
                        self.get_success_title(),
                        message
                    )
                    self._success_box = box
                    self._success_message_shown = True
                    self._pending_success_messagebox = None
                    self._automation_completed = False  # ✅ prevent it from re-qualifying for display

                    def on_box_closed():
                        logging.info("Final Summary Message closed")
                        self._success_box = None
                        self._success_message_shown = False
                        self._success_message_dismissed = True  # ✅ This ensures no repeat display
                        self._automation_completed = False
                        self._pending_success_messagebox = None
                        self.progress_label.setText("Success!")
                        self.reset_bot_ui()


                    box.finished.connect(on_box_closed)
                    logging.info("Displaying Final Summary Message.")
                    box.show()
                    # Center the box over the main window
                    center_point = self.geometry().center()
                    # Adjust these offsets as needed (positive = right/down, negative = left/up)
                    x_offset = 0   # e.g., +20 to move right, -20 to move left
                    y_offset = -40   # e.g., +20 to move down, -20 to move up

                    box.move(
                        center_point.x() - box.width() // 2 + x_offset,
                        center_point.y() - box.height() // 2 + y_offset
                    )
                    self.start_greeting_updates()
                else:
                    self._pending_success_messagebox = None


            self.hide_notification_badge()
            # Clear taskbar overlay icon if notification is acknowledged

    def fade_and_toggle_mode(self, to_minimal):
        """Fade out, toggle mode, then fade in."""
        self.fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self.fade_anim.setDuration(200)
        self.fade_anim.setStartValue(1.0)
        self.fade_anim.setEndValue(0.0)
        self.fade_anim.finished.connect(lambda: self._toggle_mode_and_fade_in(to_minimal))
        self.fade_anim.start()

    def _toggle_mode_and_fade_in(self, to_minimal):
        if to_minimal:
            self.enter_minimal_mode()
            logging.info(f"Toggled Minimal Mode.")
        else:
            self.exit_minimal_mode()
            logging.info(f"Toggled Default Mode.")
        self.setWindowOpacity(0.0)
        self.fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self.fade_anim.setDuration(200)
        self.fade_anim.setStartValue(0.0)
        self.fade_anim.setEndValue(1.0)
        self.fade_anim.start()

    def toggle_minimal_mode(self, event=None):
        """Toggle between minimal and full mode with fade animation"""
        self.fade_and_toggle_mode(not self.minimal_mode)

    def enterEvent(self, event):
        super().enterEvent(event)

    def leaveEvent(self, event):
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        """Handle mouse press for window dragging and minimal mode"""
        if event.button() == Qt.LeftButton:
            # Check if we're in the title bar area (top 50 pixels)
            if event.y() <= 50:
                self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
                event.accept()
                return
            elif self.minimal_mode:
                self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
                event.accept()
                return
            else:
                # Check if we clicked on an empty area (not on any widget)
                clicked_widget = self.childAt(event.pos())
                
                # Don't allow background dragging if clicking on header area
                if hasattr(self, 'header_container'):
                    header_rect = self.header_container.geometry()
                    if header_rect.contains(event.pos()):
                        super().mousePressEvent(event)
                        return
            

    def mouseMoveEvent(self, event):
        """Handle mouse move for window dragging and minimal mode"""
        if event.buttons() == Qt.LeftButton and self._drag_pos is not None:
            self.move(event.globalPos() - self._drag_pos)
            
            # Update the background position if in minimal mode
            if self.minimal_mode:
                self.update_background_position()
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """Handle mouse release to stop window dragging"""
        if event.button() == Qt.LeftButton:
            self._drag_pos = None
        super().mouseReleaseEvent(event)

    def showEvent(self, event):
        """Ensure frameless window is properly applied when shown"""
        super().showEvent(event)
        # Use a timer to re-apply frameless window flags and rounded mask after the window is shown
        QTimer.singleShot(100, self.ensure_frameless_window)
        QTimer.singleShot(150, self.create_rounded_mask)

    def ensure_frameless_window(self):
        """Ensure the window is properly frameless"""
        if not self.windowFlags() & Qt.FramelessWindowHint:
            self.setWindowFlags(Qt.FramelessWindowHint)
            self.show()

    def create_rounded_mask(self):
        """Create a rounded mask for the window to ensure truly rounded corners"""
        from PyQt5.QtGui import QPainterPath, QRegion
        
        # Create a rounded rectangle path that covers the entire window
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 25, 25)
        
        # Create region from path and apply to the entire window
        region = QRegion(path.toFillPolygon().toPolygon())
        self.setMask(region)
        
        # Also ensure the central widget has proper styling
        if hasattr(self, 'central_widget'):
            self.central_widget.setStyleSheet(f"""
                QWidget#CentralWidget {{
                    background: transparent;
                    border-radius: 25px;
                    border: none;
                }}
            """)
        
        # Force a repaint to ensure the mask is applied
        self.repaint()

    def resizeEvent(self, event):
        """Re-apply rounded mask when window is resized"""
        super().resizeEvent(event)
        QTimer.singleShot(50, self.create_rounded_mask)

    def _get_or_create_background_label(self):
        """Return the dedicated wallpaper label, adopting old unlabeled labels if needed."""
        label = self.centralWidget().findChild(QLabel, BACKGROUND_LABEL_OBJECT_NAME)
        if label:
            label.mouseDoubleClickEvent = self.header_area_double_click
            return label

        old_background_geometries = {
            QRect(0, 0, 400, 470),
            QRect(0, 50, 400, 470),
            QRect(0, 0, 400, 520),
            QRect(0, 50, 400, 520),
        }
        for child in self.centralWidget().findChildren(QLabel):
            if child.geometry() in old_background_geometries:
                child.setObjectName(BACKGROUND_LABEL_OBJECT_NAME)
                child.mouseDoubleClickEvent = self.header_area_double_click
                logging.info("Adopted existing wallpaper label for cosmetic rendering.")
                return child

        label = QLabel(self.centralWidget())
        label.setObjectName(BACKGROUND_LABEL_OBJECT_NAME)
        label.mouseDoubleClickEvent = self.header_area_double_click
        label.lower()
        logging.info("Created wallpaper label for cosmetic rendering.")
        return label

    def _load_wallpaper_pixmap(self, bg_path, header=None):
        """Load the selected wallpaper and fall back cleanly if the image is unreadable."""
        pixmap = QPixmap(bg_path)
        if not pixmap.isNull():
            return pixmap, bg_path

        fallback_path = str(IMAGES_DIR / 'autotestbg.jpg').replace('\\', '/')
        logging.warning(
            "Wallpaper image could not be loaded; falling back to default. header=%s path=%s",
            header,
            bg_path,
        )
        fallback_pixmap = QPixmap(fallback_path)
        if fallback_pixmap.isNull():
            logging.error("Default wallpaper image could not be loaded: %s", fallback_path)
            return None, fallback_path
        return fallback_pixmap, fallback_path

    def _apply_wallpaper_to_background_label(self, bg_path, header):
        """Apply a cover-fit wallpaper to the dedicated background label."""
        label = self._get_or_create_background_label()
        original_pixmap, used_path = self._load_wallpaper_pixmap(bg_path, header)
        if original_pixmap is None:
            return

        original_width = max(1, original_pixmap.width())
        original_height = max(1, original_pixmap.height())
        window_width = max(1, self.width())
        window_height = max(1, self.height())
        scale_factor = max(window_width / original_width, window_height / original_height)

        scaled_width = max(1, int(original_width * scale_factor))
        scaled_height = max(1, int(original_height * scale_factor))
        pixmap = original_pixmap.scaled(
            scaled_width,
            scaled_height,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )

        offset_x, offset_y = self._background_offsets(header, scaled_width, scaled_height)
        label.setPixmap(pixmap)
        label.setGeometry(offset_x, offset_y, scaled_width, scaled_height)
        label.lower()
        self.background_image_width = scaled_width
        self.background_image_height = scaled_height
        logging.info(
            "Wallpaper applied to main UI. header=%s path=%s scaled_size=%sx%s offset=(%s,%s)",
            header or "default",
            used_path,
            scaled_width,
            scaled_height,
            offset_x,
            offset_y,
        )


    def update_background_position(self):
        """Update the background position based on current offset"""
        user_data = load_user_rewards()
        equipped = user_data.get('equipped', {})
        header = equipped.get('header')
        
        
        if header:
            if self.reposition_mode:
                # In reposition mode: update CSS background
                bg_path = self.get_background_path(header)
                bg_position = self._background_position_css(header)
                
                # CSS background doesn't support background-size, so we'll use the background label approach
                # Hide the background label during reposition mode and use CSS for smooth dragging
                stylesheet = f"""
                    QMainWindow {{
                        background-image: url({bg_path});
                        background-repeat: no-repeat;
                        background-position: {bg_position};
                        background-attachment: fixed;
                    }}
                """
                

                self.setStyleSheet(stylesheet)
            else:
                # Normal mode: move the background label
                child = self._get_or_create_background_label()
                scaled_width = getattr(self, 'background_image_width', child.width())
                scaled_height = getattr(self, 'background_image_height', child.height())
                offset_x, offset_y = self._background_offsets(header, scaled_width, scaled_height)
                child.setGeometry(offset_x, offset_y, scaled_width, scaled_height)
                child.lower()
                logging.info(
                    "Wallpaper position updated. header=%s offset=(%s,%s) size=%sx%s",
                    header,
                    offset_x,
                    offset_y,
                    scaled_width,
                    scaled_height,
                )
                return


    def get_background_path(self, header):
        """Get the background path for a given header reward"""
        if header == CUSTOM_WALLPAPER_ID:
            custom_path = get_custom_wallpaper_path(load_user_rewards())
            if custom_path:
                logging.info("Resolved custom wallpaper path: %s", custom_path)
                return str(custom_path).replace('\\', '/')
            logging.warning("Custom wallpaper is equipped but the processed image is missing; using default wallpaper.")
        reward = REWARDS.get(header or '', {})
        image_name = get_reward_image_filename(header, reward) if reward else None
        if image_name:
            image_path = IMAGES_DIR / image_name
            if image_path.exists():
                logging.info("Resolved wallpaper path: header=%s path=%s", header or "default", image_path)
                return str(image_path).replace('\\', '/')
            logging.warning("Configured wallpaper image is missing: header=%s image=%s", header, image_path)
        return str(IMAGES_DIR / 'autotestbg.jpg').replace('\\', '/')

    def _background_position_css(self, header):
        """Return a Qt stylesheet background-position value for the active wallpaper."""
        centered_wallpapers = {
            'aurora_desk_wall',
            'cyberpunk_command_wall',
            'sugar_glass_wall',
            'pop_prism_stage_wall',
            CUSTOM_WALLPAPER_ID,
        }
        if header in centered_wallpapers:
            return "center center"
        return f"{self.background_offset_x}px {self.background_offset_y}px"

    def _background_offsets(self, header, scaled_width, scaled_height):
        """Return label offsets for fitted wallpapers."""
        centered_wallpapers = {
            'aurora_desk_wall',
            'cyberpunk_command_wall',
            'sugar_glass_wall',
            'pop_prism_stage_wall',
            CUSTOM_WALLPAPER_ID,
        }
        if header in centered_wallpapers:
            return (
                int((self.width() - scaled_width) / 2),
                int((self.height() - scaled_height) / 2),
            )
        return self.background_offset_x, self.background_offset_y

    def _reward_image_path(self, reward_id, reward=None):
        """Return an absolute image path for a reward asset, if it exists."""
        reward = reward or REWARDS.get(reward_id or '', {})
        image_name = get_reward_image_filename(reward_id, reward) if reward else None
        if not image_name:
            return None
        image_path = IMAGES_DIR / image_name
        return image_path if image_path.exists() else None

    def _equipped_badge_path(self, equipped=None):
        equipped = equipped or load_user_rewards().get('equipped', {})
        badge_id = equipped.get('badge')
        badge_reward = REWARDS.get(badge_id or '', {})
        if badge_reward.get('type') != 'badge':
            return None, None
        return badge_id, self._reward_image_path(badge_id, badge_reward)

    def _stop_header_badge_bob(self, restore=True):
        """Stop the equipped-badge idle bob and optionally restore its base position."""
        anim = getattr(self, '_header_badge_bob_anim', None)
        if anim:
            anim.stop()
            self._header_badge_bob_anim = None
        if restore and hasattr(self, '_header_badge_base_pos') and hasattr(self, 'header_image'):
            self.header_image.move(self._header_badge_base_pos)

    def _stop_header_badge_effect(self):
        """Remove the runtime personality effect from the equipped badge."""
        effect_layer = getattr(self, '_header_badge_effect_layer', None)
        if effect_layer:
            effect_layer.stop()
            effect_layer.hide()
            effect_layer.deleteLater()
            self._header_badge_effect_layer = None

    def _stop_header_badge_motion(self, restore=True):
        """Stop the full-frame mechanical badge idle and optionally restore the still badge."""
        animator = getattr(self, '_header_badge_motion_animator', None)
        if animator:
            animator.stop(restore=restore)
            animator.deleteLater()
            self._header_badge_motion_animator = None

    def _sync_header_badge_effect_geometry(self):
        """Keep the overlay fitted to the current badge label size."""
        effect_layer = getattr(self, '_header_badge_effect_layer', None)
        if effect_layer and hasattr(self, 'header_image') and self.header_image:
            effect_layer.setGeometry(self.header_image.rect())
            effect_layer.raise_()

    def _start_header_badge_effect(self, badge_id):
        """Start the equipped badge's unique mini animation, if one exists."""
        self._stop_header_badge_effect()
        if not has_badge_effect(badge_id):
            return
        effect_layer = BadgeEffectLayer(self.header_image, reward_id=badge_id)
        effect_layer.setGeometry(self.header_image.rect())
        effect_layer.raise_()
        effect_layer.start()
        self._header_badge_effect_layer = effect_layer

    def _start_header_badge_motion(self, badge_id, base_pixmap):
        """Play rare mechanical idles by swapping the actual badge pixmap frames."""
        self._stop_header_badge_motion(restore=False)
        if not has_badge_motion(badge_id):
            return
        animator = BadgeMechanicalAnimator(self.header_image, badge_id, base_pixmap, parent=self)
        if not animator.has_frames():
            animator.deleteLater()
            return
        animator.start()
        self._header_badge_motion_animator = animator

    def _start_header_badge_bob(self):
        """Give static achievement badges the same gentle idle motion as Silcrow."""
        if not hasattr(self, 'header_image') or not self.header_image:
            return
        pixmap = self.header_image.pixmap()
        if not getattr(self, '_header_avatar_reward_id', None) or not pixmap or pixmap.isNull():
            return

        self._stop_header_badge_bob(restore=False)
        base_pos = self.header_image.pos()
        self._header_badge_base_pos = base_pos

        bob_anim = QPropertyAnimation(self.header_image, b"pos", self)
        bob_anim.setDuration(2100)
        bob_anim.setStartValue(base_pos)
        bob_anim.setKeyValueAt(0.5, QPoint(base_pos.x(), base_pos.y() + 7))
        bob_anim.setEndValue(base_pos)
        bob_anim.setEasingCurve(QEasingCurve.InOutSine)
        bob_anim.setLoopCount(-1)
        bob_anim.start()
        self._header_badge_bob_anim = bob_anim

    def _apply_header_avatar(self, size=None, equipped=None):
        """Use the equipped achievement badge as the main header, else Silcrow."""
        if not hasattr(self, 'header_image') or not self.header_image:
            return

        size = size or QSize(HEADER_AVATAR_DIM, HEADER_AVATAR_DIM)
        badge_id, badge_path = self._equipped_badge_path(equipped)
        self._stop_header_badge_bob(restore=False)
        self._stop_header_badge_motion(restore=False)
        self._stop_header_badge_effect()
        self.header_image.clear()
        self.header_image.setWindowOpacity(1.0)
        self.header_image.setAlignment(Qt.AlignCenter)
        self.header_image.setStyleSheet("background: transparent;")
        self.header_image.setFixedSize(size)

        if badge_path:
            if hasattr(self, 'header_movie') and self.header_movie:
                self.header_movie.stop()
            pixmap = QPixmap(str(badge_path)).scaled(
                size,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            self.header_image.setPixmap(pixmap)
            self._header_avatar_reward_id = badge_id
            self.apply_shadow(self.header_image, color=QColor(0, 224, 255, 190), blur=18, x_offset=0, y_offset=4)
            self._start_header_badge_motion(badge_id, pixmap)
            self._start_header_badge_effect(badge_id)
            QTimer.singleShot(0, self._start_header_badge_bob)
        else:
            gif_path = str(GIFS_DIR / "silcrow.gif")
            if not os.path.exists(gif_path):
                logging.error(f"Header GIF not found at: {gif_path}")
                return
            self.header_movie = QMovie(gif_path)
            self.header_movie.setScaledSize(size)
            self.header_image.setMovie(self.header_movie)
            self.header_movie.start()
            self._header_avatar_reward_id = None
            self.apply_shadow(self.header_image, color=Qt.darkCyan, blur=12, x_offset=2, y_offset=2)

        self.header_image.raise_()
        self.header_image.setVisible(True)

    def _header_visual_size(self):
        """Return the rendered header avatar size for positioning small markers."""
        if not hasattr(self, 'header_image') or not self.header_image:
            return QSize(0, 0)
        movie = self.header_image.movie()
        if movie:
            size = movie.scaledSize()
            if size.width() > 0 and size.height() > 0:
                return size
        pixmap = self.header_image.pixmap()
        if pixmap and not pixmap.isNull():
            return pixmap.size()
        return QSize(self.header_image.width(), self.header_image.height())

    def _has_equipped_emoji(self):
        equipped = load_user_rewards().get('equipped', {})
        emoji_id = equipped.get('emoji')
        return bool(emoji_id and REWARDS.get(emoji_id, {}).get('type') == 'emoji')

    def _visual_settings(self):
        """Return current cosmetic display toggles."""
        return get_visual_settings(load_user_rewards())

    def _focus_mode_enabled(self):
        return bool(self._visual_settings().get("focus_mode"))

    def _quiet_run_mode_enabled(self):
        return bool(self._visual_settings().get("quiet_run_mode"))

    def _apply_focus_mode_visibility(self):
        """Hide the idle center avatar only in full/default mode."""
        if not hasattr(self, 'header_image') or not self.header_image:
            return
        focus_enabled = self._focus_mode_enabled()
        should_hide_avatar = bool(focus_enabled and not self.minimal_mode and not self.is_running)
        if should_hide_avatar:
            self._stop_widget_fade(self.header_image)
            self.header_image.hide()
            self.header_visible = False
            logging.info("Focus Mode applied: center badge/Silcrow hidden in default view.")
        elif not self.is_running or self.minimal_mode:
            self.header_container.show()
            self.header_image.show()
            self._resume_header_avatar_animations()
            if not self.is_running:
                self.header_visible = True
            logging.info("Focus Mode applied: center badge/Silcrow visible.")

    def _apply_quiet_run_mode_visibility(self):
        """Hide decorative run animation/message when Quiet Run Mode is enabled."""
        if not self.is_running or self.minimal_mode:
            return
        if not self._quiet_run_mode_enabled():
            return
        for attr in ('idle_label', 'processing_gif'):
            widget = getattr(self, attr, None)
            if widget:
                self._stop_widget_fade(widget)
                widget.hide()
        if hasattr(self, 'idle_timer') and self.idle_timer.isActive():
            self.idle_timer.stop()
        if hasattr(self, 'gif_anim') and self.gif_anim.state() == QAbstractAnimation.Running:
            self.gif_anim.stop()
        if hasattr(self, 'processing_gif_movie'):
            self.processing_gif_movie.stop()
        if hasattr(self, 'header_image'):
            self.header_image.hide()
        self.header_visible = False
        logging.info("Quiet Run Mode applied: decorative run message and cat animation hidden.")

    def apply_visual_settings_to_current_state(self):
        """Apply cosmetic toggles without changing reward ownership."""
        if self.is_running and not self.minimal_mode:
            if self._quiet_run_mode_enabled():
                self._apply_quiet_run_mode_visibility()
            else:
                self._restore_running_automation_ui()
            return
        self._apply_focus_mode_visibility()

    def _on_intro_animation_complete(self, message="Intro animation completed"):
        logging.info(message)
        self.apply_equipped_rewards()

    def fade_widget(self, widget, fade_in=True, duration=300, on_finished=None):
        if not widget:
            return
        anim = QPropertyAnimation(widget, b"windowOpacity")
        anim.setDuration(duration)
        if fade_in:
            widget.setWindowOpacity(0.0)
            widget.show()
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
        else:
            anim.setStartValue(widget.windowOpacity())
            anim.setEndValue(0.0)
        if on_finished:
            anim.finished.connect(on_finished)
        anim.start()
        widget._fade_anim = anim

    def show_header_gif_only(self, ensure_animation=True):
        # Fade out idle messages and processing.gif, then fade in header GIF (and ensure animation)
        def after_automation_fade():
            if hasattr(self, 'idle_label'):
                self.idle_label.hide()
            if hasattr(self, 'processing_gif'):
                self.processing_gif.hide()
            if hasattr(self, 'header_image'):
                self.header_image.show()
                if ensure_animation and hasattr(self, 'header_movie') and self.header_image.movie() is self.header_movie:
                    self.header_movie.start()  # Ensure animation immediately
                self.fade_widget(self.header_image, fade_in=True)
            self.header_visible = True
            if not self.is_running and not self.minimal_mode:
                self._apply_focus_mode_visibility()

        widgets_to_fade = []
        if hasattr(self, 'idle_label') and self.idle_label.isVisible():
            widgets_to_fade.append(self.idle_label)
        if hasattr(self, 'processing_gif') and self.processing_gif.isVisible():
            widgets_to_fade.append(self.processing_gif)
        if widgets_to_fade:
            count = len(widgets_to_fade)

            def fade_next():
                nonlocal count
                count -= 1
                if count == 0:
                    after_automation_fade()

            for w in widgets_to_fade:
                self.fade_widget(w, fade_in=False, on_finished=fade_next)
        else:
            after_automation_fade()

    def fade_out_header_gif(self, on_finished=None):
        if hasattr(self, 'header_image') and self.header_image.isVisible():
            self.fade_widget(self.header_image, fade_in=False, on_finished=on_finished)
        else:
            if on_finished:
                on_finished()

    def fade_out_processing_and_idle(self, on_finished=None):
        widgets_to_fade = []
        if hasattr(self, 'idle_label') and self.idle_label.isVisible():
            widgets_to_fade.append(self.idle_label)
        if hasattr(self, 'processing_gif') and self.processing_gif.isVisible():
            widgets_to_fade.append(self.processing_gif)
        if widgets_to_fade:
            count = len(widgets_to_fade)

            def fade_next():
                nonlocal count
                count -= 1
                if count == 0 and on_finished:
                    on_finished()

            for w in widgets_to_fade:
                self.fade_widget(w, fade_in=False, on_finished=fade_next)
        else:
            if on_finished:
                on_finished()

    def header_area_double_click(self, event):
        if event.type() == event.MouseButtonDblClick:
            if self.is_running:
                if self._quiet_run_mode_enabled() and not self.minimal_mode:
                    self.enter_minimal_mode()
                    logging.info(f"Toggled Minimal Mode.")
                    return
                if self.minimal_mode:
                    def after_header_fade():
                        self.exit_minimal_mode()
                        logging.info(f"Toggled Default Mode.")

                    self.fade_out_header_gif(on_finished=after_header_fade)
                    return
                if not self.header_visible:  # idle+processing.gif are shown
                    self.show_header_gif_only()
                else:  # header GIF is visible
                    self.toggle_minimal_mode()
            else:
                self.toggle_minimal_mode()

    def center_on_screen(self):
        screen = QApplication.primaryScreen()
        screen_geometry = screen.availableGeometry()
        window_geometry = self.frameGeometry()
        x = screen_geometry.center().x() - window_geometry.width() // 2
        y = screen_geometry.center().y() - window_geometry.height() // 2
        self.move(x, y)

    def force_refresh_taskbar_icon(self):
        """Force refresh the taskbar icon by temporarily hiding and showing the window"""
        if self.isVisible():
            self.hide()
            QTimer.singleShot(50, self.show)
            QTimer.singleShot(100, lambda: self.setWindowIcon(QIcon(str(ICONS_DIR / "silcrow.ico"))))
    def show_notification_badge(self):
        if not hasattr(self, 'header_image') or not self.header_image:
            return
        if self.notification_badge is None:
            self.notification_badge = QLabel(self.header_image)
            self.notification_badge.setAlignment(Qt.AlignCenter)
        self.notification_badge.setFixedSize(52, 52)

        user_data = load_user_rewards()
        equipped = user_data.get('equipped', {})
        marker = equipped.get('emoji')

        if marker is None or marker == '' or marker == 'badge_checkmark':
            self.notification_badge.clear()
            self.notification_badge.setText(chr(10003))
            self.notification_badge.setStyleSheet(
                """
                background: #2ecc40;
                border-radius: 26px;
                color: white;
                font-size: 30px;
                font-weight: bold;
                border: 2px solid #1e7e34;
                """
            )
        else:
            marker_reward = REWARDS.get(marker, {})
            marker_image = get_reward_image_filename(marker, marker_reward)
            badge_path = IMAGES_DIR / marker_image if marker_image else None
            if badge_path and badge_path.exists():
                pixmap = QPixmap(str(badge_path)).scaled(44, 44, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.notification_badge.clear()
                self.notification_badge.setPixmap(pixmap)
                self.notification_badge.setStyleSheet("background: transparent; border: none;")
            else:
                badge_text = get_reward_icon(marker, marker_reward) or "#"
                self.notification_badge.clear()
                self.notification_badge.setText(badge_text)
                self.notification_badge.setStyleSheet(
                    """
                    background: transparent;
                    color: white;
                    font-size: 30px;
                    font-weight: bold;
                    border: none;
                    """
                )

        shadow = QGraphicsDropShadowEffect(self.notification_badge)
        shadow.setBlurRadius(18)
        shadow.setColor(QColor(0, 128, 0, 180))
        shadow.setOffset(0, 4)
        self.notification_badge.setGraphicsEffect(shadow)

        self._position_notification_badge()
        self.notification_badge.raise_()
        self.notification_badge.show()

    def _position_notification_badge(self):
        if not self.notification_badge or not hasattr(self, 'header_image') or not self.header_image:
            return
        badge_w, badge_h = self.notification_badge.width(), self.notification_badge.height()
        visual_size = self._header_visual_size()
        gif_w, gif_h = visual_size.width(), visual_size.height()
        widget_w, widget_h = self.header_image.width(), self.header_image.height()
        offset_x = (widget_w - gif_w) // 2
        offset_y = (widget_h - gif_h) // 2
        badge_x = offset_x + gif_w - badge_w + 8
        badge_y = offset_y + 2
        badge_x = max(0, min(badge_x, widget_w - badge_w))
        badge_y = max(0, min(badge_y, widget_h - badge_h))
        self.notification_badge.move(badge_x, badge_y)

    def hide_notification_badge(self):
        if self.notification_badge:
            self.notification_badge.hide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, '_sync_header_badge_effect_geometry'):
            self._sync_header_badge_effect_geometry()
        # Reposition badge if visible
        if hasattr(self, 'notification_badge') and self.notification_badge and self.notification_badge.isVisible():
            self._position_notification_badge()


    def show_toast_notification(self, title, message):
        """Show a toast notification using native Windows QSystemTrayIcon for standard layout"""
        try:
            import os
            from PyQt5.QtWidgets import QSystemTrayIcon
            from PyQt5.QtGui import QIcon
            from PyQt5.QtCore import QCoreApplication, QTimer
            
            # Create a new tray icon for this notification
            tray_icon = QSystemTrayIcon(self)
            
            # Use silcrow.ico if available, otherwise use window icon
            icon_path = os.path.abspath("silcrow.ico")
            if os.path.exists(icon_path):
                tray_icon.setIcon(QIcon(icon_path))
            else:
                tray_icon.setIcon(self.windowIcon())
            
            tray_icon.setVisible(True)
            tray_icon.setToolTip(self.get_app_title())
            tray_icon.messageClicked.connect(self._on_toast_clicked)
            
            # Set the application name for the notification
            app_title = self.get_app_title()
            logging.info(f"Showing native Windows toast with app name: {app_title}")
            QCoreApplication.setApplicationName(app_title)
            
            # Show the notification with Information icon (this gives the standard Windows layout)
            tray_icon.showMessage(title, message, QSystemTrayIcon.Information, 6000)
            
            # Clean up after 7 seconds
            QTimer.singleShot(7000, lambda: tray_icon.deleteLater())
            
        except Exception as e:
            logging.warning(f"Failed to show toast notification: {e}")

    def _on_toast_clicked(self):
        """Handle toast notification click - bring main window to foreground"""
        try:
            # Bring window to front and activate it
            self.show()
            self.raise_()
            self.activateWindow()
            
            # If in minimal mode, ensure it stays in minimal mode
            if hasattr(self, 'minimal_mode') and self.minimal_mode:
                # Window is already in minimal mode, just bring it to front
                pass
            else:
                # In default mode, ensure full window is visible
                self.showNormal()
            
            #logging.info("Toast notification clicked - window brought to foreground")
        except Exception as e:
            logging.warning(f"Failed to bring window to foreground")

    def open_shop_dialog(self):
        user_data = load_user_rewards()
        user_level = user_data.get('level', 0)
        
        if user_level < 2:
            xp_needed = xp_to_next_level(user_data.get('xp', 0))
            ModernMessageBox(
                "Shop Locked", 
                f"Shop requires Level 2 to access!\n\n"
                f"Current Level: {user_level}\n"
                f"Current XP: {user_data.get('xp', 0)}\n"
                f"XP needed: {xp_needed}\n\n"
                f"Process fresh documents to unlock the shop!",
                "info",
                self
            ).exec_()
            return
        
        try:
            dlg = ShopDialog(self)
            dlg.show()
            dlg.setModal(False)
            dlg.raise_()
            dlg.activateWindow()
        except Exception as e:
            logging.error(f"Error creating ShopDialog: {e}")
            import traceback
            logging.error(f"Traceback: {traceback.format_exc()}")

    def open_inventory_dialog(self, focus_reward_id=None):
        """Open the inventory dialog for managing owned rewards"""
        from utils.rewards import load_user_rewards, save_user_rewards, REWARDS
        user_data = load_user_rewards()
        user_level = user_data.get('level', 0)
        if user_level < 2:
            xp_needed = xp_to_next_level(user_data.get('xp', 0))
            ModernMessageBox(
                "Inventory Locked", 
                f"Inventory requires Level 2 to access!\n\n"
                f"Current Level: {user_level}\n"
                f"Current XP: {user_data.get('xp', 0)}\n"
                f"XP needed: {xp_needed}\n\n"
                f"Process fresh documents to unlock the inventory!",
                "info",
                self
            ).exec_()
            return
        try:
            dialog = InventoryDialog(self, focus_reward_id=focus_reward_id)
            dialog.setModal(False)
            dialog.show()
            dialog.raise_()
            dialog.activateWindow()
            # Refresh UI after inventory interaction
            self.apply_equipped_rewards()
        except Exception as e:
            logging.error(f"Failed to open inventory dialog: {e}")
            ModernMessageBox("Error", f"Failed to open inventory dialog:\n{e}", "error", self).exec_()

    def apply_equipped_rewards(self):
        user_data = load_user_rewards()
        equipped = user_data.get('equipped', {})
        self._apply_equipped_font(equipped.get('font'))
        

        
        # Apply wallpaper background. Saved rewards still use the legacy "header" key.
        header = equipped.get('header')
        bg_path = self.get_background_path(header)
        logging.info("Applying wallpaper reward. header=%s path=%s", header or "default", bg_path)
        
        # Handle background based on current mode
        if self.minimal_mode:
            # In minimal mode, update the CSS stylesheet
            bg_position = self._background_position_css(header)
            minimal_stylesheet = f"""
                QMainWindow {{
                    background-image: url({bg_path});
                    background-repeat: no-repeat;
                    background-position: {bg_position};
                    background-attachment: fixed;
                }}
            """
            self.setStyleSheet(minimal_stylesheet)
            self.centralWidget().setStyleSheet("background: transparent;")
            logging.info("Wallpaper applied to minimal UI. header=%s position=%s", header or "default", bg_position)
        else:
            self._apply_wallpaper_to_background_label(bg_path, header)
            
            # Set transparent background on main window since we're using the label approach
            self.setStyleSheet("QMainWindow { background: transparent; }")
            
            # Force a repaint to ensure the background change is visible
            QApplication.processEvents()  # Process any pending events first
            self.repaint()
            self.centralWidget().repaint()
                    
        # Apply UI theme. Internal type remains "skin" for backward compatibility.
        skin = equipped.get('skin')
        self._apply_ui_theme(skin)
        
        # Apply the main header avatar: earned badge first, otherwise Silcrow.
        self._apply_header_avatar(QSize(HEADER_AVATAR_DIM, HEADER_AVATAR_DIM), equipped=equipped)
        
        # Emojis remain a small cosmetic marker; badges own the main avatar slot.
        if equipped.get('emoji'):
            self.show_notification_badge()
        else:
            self.hide_notification_badge()
        self.apply_visual_settings_to_current_state()

    def create_styled_message_box(self, title, message, icon=QMessageBox.Information):
        """Create a properly styled message box with modern theme"""
        # Map QMessageBox icons to ModernMessageBox msg_type
        msg_type = "info"
        if icon == QMessageBox.Warning:
            msg_type = "warning"
        elif icon == QMessageBox.Critical:
            msg_type = "error"
        
        return ModernMessageBox(title, message, msg_type, self)

    def reset_rewards_and_ui(self):
        reset_user_rewards()
        self.apply_equipped_rewards()
        box = ModernMessageBox("Rewards Reset", "Coins and UI have been reset for testing.", "info", self)
        box.exec_()

    def update_level_display(self):
        """Update the level display with current progression stats."""
        user_data = load_user_rewards()
        level = user_data.get('level', 0)
        total_docs = user_data.get('total_documents_processed', 0)
        xp = user_data.get('xp', 0)
        coins = user_data.get('coins', 0)
        xp_progress = get_level_progress(xp)
        xp_needed = xp_progress.get('xp_to_next', xp_to_next_level(xp))
        
        if hasattr(self, 'level_info_panel'):
            if hasattr(self, 'level_title_label'):
                self.level_title_label.setText(f"Level {level}")
            if hasattr(self, 'level_xp_label'):
                self.level_xp_label.setText(f"XP: {xp:,} | {xp_needed:,} to next")
            if hasattr(self, 'level_xp_bar'):
                level_span = max(1, xp_progress.get('level_span', xp_needed))
                xp_in_level = max(0, min(xp_progress.get('xp_in_level', 0), level_span))
                progress_ratio = xp_in_level / level_span
                self.level_xp_bar.setRange(0, level_span)
                self._apply_level_xp_gradient(progress_ratio)
                self.level_xp_bar.setValue(xp_in_level)
                self.level_xp_bar.setToolTip(
                    f"{xp_in_level:,} / {level_span:,} XP this level ({xp:,} total XP) toward Level {level + 1}"
                )
            if hasattr(self, 'level_coins_label'):
                self.level_coins_label.setText(f"Coins: {coins:,}")
            if hasattr(self, 'level_docs_label'):
                self.level_docs_label.setText(f"Fresh Docs: {total_docs:,}")
            self.level_info_panel.adjustSize()

    def toggle_level_info(self):
        if getattr(self, 'level_info_visible', False):
            self.hide_level_info()
        else:
            logging.info("Viewed Level Info Panel")
            # (Optional) Code to show the panel here
            self.level_info_visible = True
            # Fade out lvlup.gif and show the notification popup after fade-out
            if not getattr(self, "_levelup_notification_shown", False):
                if hasattr(self, 'user_data') and 'last_levelup_coins' in self.user_data:
                    self.fade_out_and_remove_lvlup_gif(
                        on_finished=lambda: self.show_notification_popup(
                            f"<span style='color: white; font-size:15px;'>🏆 You leveled up to "
                            f"<span style='color: gold; font-weight: bold;'>LEVEL {self.user_data['level']}</span>!<br><br>"
                            f"+{self.user_data['last_levelup_coins']} coins awarded.<br><br><b>Keep going!</b></span>"
                        )
                    )
                else:
                    self.fade_out_and_remove_lvlup_gif()  # just fade out gif if no levelup context
            from PyQt5.QtWidgets import QApplication
            self.update_level_display()
            triangle_pos = self.level_triangle_btn.mapToGlobal(self.level_triangle_btn.rect().topRight())
            tooltip_x = triangle_pos.x() + 2   # Position closer to the right of the button
            tooltip_y = triangle_pos.y() + 5   # Position lower on the Y-axis
            self.level_info_panel.move(tooltip_x, tooltip_y)
            self.level_info_panel.show()
            self.level_info_panel.raise_()
            self.level_triangle_btn.setText("▴")
            self._apply_level_button_style(expanded=True)
            self.level_info_panel.installEventFilter(self)
            self.level_info_panel.setFocusPolicy(Qt.StrongFocus)
            self.level_info_panel.setAttribute(Qt.WA_Hover, True)
            self.level_info_panel.setMouseTracking(True)
            self.level_info_panel.setFocus()
            QApplication.instance().installEventFilter(self)

    def hide_level_info(self):
        logging.info("Closed Level Info Panel")
        from PyQt5.QtWidgets import QApplication
        self.level_info_panel.hide()
        self.level_info_visible = False
        self.level_triangle_btn.setText("▾")
        self._apply_level_button_style(expanded=False)
        if hasattr(self, 'remove_glow_from_arrow'):
            self.remove_glow_from_arrow()
        if hasattr(self, 'fade_out_and_remove_lvlup_gif'):
            self.fade_out_and_remove_lvlup_gif()
        self.level_info_panel.removeEventFilter(self)
        QApplication.instance().removeEventFilter(self)

    def fade_out_and_remove_lvlup_gif(self, on_finished=None):
        overlay = getattr(self, '_lvlup_gif_overlay', None)
        if overlay is None or not overlay.isVisible():
            if on_finished:
                on_finished()
            return


        if hasattr(self, '_lvlup_fade_anim') and self._lvlup_fade_anim is not None:
            self._lvlup_fade_anim.stop()

        anim = QPropertyAnimation(overlay, b"windowOpacity")
        anim.setDuration(400)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)

        def cleanup():
            overlay.hide()
            overlay.deleteLater()
            self._lvlup_gif_overlay = None
            self._lvlup_fade_anim = None
            if on_finished:
                on_finished()

        anim.finished.connect(cleanup)
        self._lvlup_fade_anim = anim
        anim.start()    
        
    def _remove_lvlup_overlay(self, overlay):
        print("Fade-out animation finished, removing overlay")
        overlay.hide()
        overlay.deleteLater()
        self._lvlup_gif_overlay = None
        self._lvlup_fade_anim = None

    def eventFilter(self, obj, event):
        if obj == self.level_triangle_btn:
            if event.type() == QEvent.HoverEnter:
                if not getattr(self, 'level_info_visible', False):
                    self.toggle_level_info()
            elif event.type() == QEvent.HoverLeave:
                # Close panel when mouse leaves the button area
                if getattr(self, 'level_info_visible', False):
                    self.hide_level_info()
                return True

        # Auto-close level info tooltip if mouse leaves its area
        if obj == self.level_info_panel and self.level_info_visible:
            if event.type() == QEvent.Leave:
                self.hide_level_info()
                return True
            if event.type() == QEvent.FocusOut:
                self.hide_level_info()
                return True
        # Auto-close if user clicks outside the tooltip
        if obj == QApplication.instance() and self.level_info_visible:
            if event.type() == QEvent.MouseButtonPress:
                # Check if click is outside the tooltip
                if not self.level_info_panel.rect().contains(self.level_info_panel.mapFromGlobal(event.globalPos())):
                    self.hide_level_info()
                    return False  # Let the event continue
        return super().eventFilter(obj, event)

    def changeEvent(self, event):
        """Handle window state changes to hide level info when window loses focus"""
        super().changeEvent(event)
        if event.type() == QEvent.WindowStateChange or event.type() == QEvent.ActivationChange:
            if not self.isActiveWindow() and self.level_info_visible:
                self.hide_level_info()


    def game_over_check_high_score(self):
        if self.score >= 100:
            try:
                rewards = load_user_rewards()
                # Award 1 coin per 20 points (rounded down)
                coins_earned = self.score // 20
                rewards['coins'] = rewards.get('coins', 0) + coins_earned
                save_user_rewards(rewards)
                # Show notification popup for coin reward only at game over
                if hasattr(self, 'show_notification_popup') and self.game_over:
                    self.show_notification_popup(
                        f"<div style='text-align:center;'>"
                        f"<span style='font-size:40px; font-weight:bold; color:#FFD700;'>+{coins_earned} coins! 🪙</span><br>"
                        f"</div>"
                    )
            except Exception as e:
                logging.error(f"Failed to award Tetris coins")

    def show_lvl2unlock_gif(self):
        gif_path = str(GIFS_DIR / "lvl2unlock.gif")
        if hasattr(self, 'header_image') and self.header_image:
            self._stop_header_badge_bob()
            # Hide header_image before animation
            self.header_image.setVisible(False)
            # Save the current movie and visibility
            original_movie = getattr(self, 'header_movie', None)
            original_visible = self.header_image.isVisible()
            # Set lvl2unlock.gif as the movie
            unlock_movie = QMovie(gif_path)
            self.header_image.setMovie(unlock_movie)
            self.header_image.setVisible(True)
            unlock_movie.start()
            # Fade out after 5.5 seconds
            fade = QPropertyAnimation(self.header_image, b"windowOpacity")
            fade.setDuration(700)
            fade.setStartValue(1.0)
            fade.setEndValue(0.0)
            QTimer.singleShot(5500, fade.start)
            # Cleanup and restore header.gif after fade
            def after_gif():
                fade.stop()
                self.header_image.setWindowOpacity(1.0)
                self.header_image.setVisible(False)  # Keep hidden until popup is dismissed
                from core.smducar import get_full_username, clean_display_name
                display_name = clean_display_name(get_full_username())
                logging.info('Showing Level 2 congratulations notification popup (show_notification_popup)')
                self.show_notification_popup(f"""
                            <span style='color: white; font-size:15px;'>
                                🏆 Congratulations, {display_name}!<br><br>
                                You've reached <span style="color: gold; font-weight: bold;">LEVEL 2</span>.<br><br>
                                <span style="color: pink; font-weight: bold;">SHOP</span> and 
                                <span style="color: cyan; font-weight: bold;">INVENTORY</span> are now unlocked.<br><br>
                                You can now spend your coins and manage your rewards!<br><br>
                                <b>Click this message to restart the app.</b>
                            </span>
                        """)
            QTimer.singleShot(6200, after_gif)
        else:
            # Fallback: floating label in center
            gif_label = QLabel(self)
            gif_label.setAlignment(Qt.AlignCenter)
            gif_movie = QMovie(gif_path)
            gif_label.setMovie(gif_movie)
            gif_label.setAttribute(Qt.WA_TranslucentBackground)
            gif_label.setStyleSheet("background: transparent;")
            # Center the GIF
            w, h = 320, 180
            center_x = (self.width() - w) // 2
            center_y = (self.height() - h) // 2
            gif_label.setGeometry(center_x, center_y, w, h)
            gif_label.raise_()
            gif_label.show()
            gif_movie.start()
            # Fade out after 5.5 seconds
            fade = QPropertyAnimation(gif_label, b"windowOpacity")
            fade.setDuration(700)
            fade.setStartValue(1.0)
            fade.setEndValue(0.0)
            QTimer.singleShot(5500, fade.start)
            # Cleanup and show popup after fade
            def after_gif():
                gif_label.deleteLater()
                from core.smducar import get_full_username, clean_display_name
                display_name = clean_display_name(get_full_username())
                logging.info('Showing Level 2 congratulations notification popup (show_notification_popup)')
                self.show_notification_popup(f"""
                            <span style='color: white; font-size:15px;'>
                                🏆 Congratulations, {display_name}!<br><br>
                                You've reached <span style="color: gold; font-weight: bold;">LEVEL 2</span>.<br><br>
                                <span style="color: pink; font-weight: bold;">SHOP</span> and 
                                <span style="color: cyan; font-weight: bold;">INVENTORY</span> are now unlocked.<br><br>
                                You can now spend your coins and manage your rewards!<br><br>
                                <b>Click this message to restart the app.</b>
                            </span>
                        """)
            QTimer.singleShot(6200, after_gif)

    def set_levelup_notification_shown(self, val: bool):
        self._levelup_notification_shown = val
        

    def show_notification_popup(self, text, duration=3000):
        # Remove any existing notification
        if hasattr(self, '_notification_popup') and self._notification_popup:
            self._notification_popup.hide()
            self._notification_popup.deleteLater()
            self._notification_popup = None
        popup = self.NotificationPopup(self, text)
        popup.adjustSize()
        # Set main window as transient parent for stacking (optional, but helps on some platforms)
        popup.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        popup.setAttribute(Qt.WA_TranslucentBackground)
        popup.show()
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

                # ✅ Clear level-up flag after showing notification
                if hasattr(self, 'user_data') and 'last_levelup_coins' in self.user_data:
                    del self.user_data['last_levelup_coins']

                # For congratulations popup, let the popup handle the restart logic
                # For other popups, just repaint
                if 'Congratulations' not in text:
                    self.repaint()



    def apply_pink_glow_to_arrow(self):
        from PyQt5.QtWidgets import QGraphicsDropShadowEffect
        from PyQt5.QtGui import QColor

        if hasattr(self, 'level_triangle_btn'):
            glow = QGraphicsDropShadowEffect(self.level_triangle_btn)
            glow.setBlurRadius(48)
            glow.setColor(QColor(255, 0, 200, 255))  # Strong pink glow
            glow.setOffset(0, 0)
            self.level_triangle_btn.setGraphicsEffect(glow)

            # 💖 Change triangle text color to pink
            self.level_triangle_btn.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: rgb(255, 0, 200);  /* Pink */
                    border: none;
                    font-weight: bold;
                    padding: 0px;
                    margin: 0px;
                }
                QPushButton:hover {
                    color: #FFA500;
                }
            """)

    def remove_glow_from_arrow(self):
        if hasattr(self, 'level_triangle_btn'):
            self.level_triangle_btn.setGraphicsEffect(None)

            # Reset style to white triangle
            self.level_triangle_btn.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: white;
                    border: none;
                    font-weight: bold;
                    padding: 0px;
                    margin: 0px;
                }
                QPushButton:hover {
                    color: #FFA500;
                }
            """)       
    def show_lvlup_gif_then_popup(self, popup_text, duration=3000, x_offset=0, y_offset=0):
        print("=" * 50)
        print(" GENERIC LEVEL UP - SHOWING GIF ONLY")
        print(f"📁 Current file: {__file__}")
        print("=" * 50)
        
        gif_path = str(GIFS_DIR / "lvlup.gif")
        print(f"🎬 GIF path: {gif_path}")
        print(f"✅ GIF exists: {os.path.exists(gif_path)}")
        
        if not os.path.exists(gif_path):
            print(f"❌ ERROR: lvlup.gif not found at path: {gif_path}")
            return

        # Create overlay, set opacity to 0 BEFORE showing
        gif_overlay = QWidget(self)
        gif_overlay.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        gif_overlay.setStyleSheet("background-color: transparent;")
        gif_overlay.setGeometry(self.rect())
        gif_overlay.setWindowOpacity(0.0)  # Set opacity to 0 before show
        gif_overlay.show()
        gif_overlay.raise_()
        self._lvlup_gif_overlay = gif_overlay

        print(f"🎬 Created transparent overlay with geometry: {gif_overlay.geometry()}")
        print(f" Overlay visible: {gif_overlay.isVisible()}")

        self.apply_pink_glow_to_arrow()

        # Create the GIF label
        gif_label = QLabel(gif_overlay)
        gif_movie = QMovie(gif_path)
        gif_movie.setScaledSize(QSize(50, 80))
        gif_label.setFixedSize(50, 80)
        gif_label.setMovie(gif_movie)
        gif_label.setStyleSheet("background: transparent")
        gif_label.setAttribute(Qt.WA_TranslucentBackground, True)

        # Add drop shadow
        from PyQt5.QtWidgets import QGraphicsDropShadowEffect
        from PyQt5.QtGui import QColor
        shadow = QGraphicsDropShadowEffect(gif_label)
        shadow.setBlurRadius(24)
        shadow.setColor(QColor(0, 0, 0, 180))
        shadow.setOffset(0, 8)
        gif_label.setGraphicsEffect(shadow)

        gif_label.move(18, 50)

        gif_label.show()
        gif_label.raise_()

        # Fade in the entire overlay (including gif and shadow)
        from PyQt5.QtCore import QPropertyAnimation
        fade_in = QPropertyAnimation(gif_overlay, b"windowOpacity")
        fade_in.setDuration(2000)  # 0.5 seconds for a quick fade
        fade_in.setStartValue(0.0)
        fade_in.setEndValue(1.0)
        fade_in.start()

        gif_movie.start()

        from PyQt5.QtWidgets import QApplication
        QApplication.processEvents()
        
        print(f" GIF label visible: {gif_label.isVisible()}")
        print(f" GIF movie state: {gif_movie.state()}")
        print(f"🎬 GIF movie frame count: {gif_movie.frameCount()}")
        print("🎬 GIF should now fade in with shadow and pink arrow glow!")
        print("=" * 50)

        if hasattr(self, 'apply_pink_glow_to_arrow'):
            self.apply_pink_glow_to_arrow()


if __name__ == '__main__':

    install_qt_message_filter()
    app = QApplication(sys.argv)
    # Set application icon
    app_icon = QIcon(str(ICONS_DIR / "silcrow.ico"))
    app.setWindowIcon(app_icon)

    # Set the application name BEFORE creating the window
    from PyQt5.QtCore import QCoreApplication
    # We need to determine the mode before creating the window
    # Let's check the config file directly
    try:
        with open('config/config.json', 'r') as f:
            config = json.load(f)
            mode = config.get("mode", "dar" if config.get("dar_mode", False) else "smd")
            
            if mode == "mspb":
                app_name = "MSPB Autorouter"
            elif mode == "itc":
                app_name = "ITC Autorouter"
            elif mode == "irsplr":
                app_name = "IRSPLR Autorouter"
            elif mode == "ohtax0":
                app_name = "OHTAX0 Autorouter"
            elif mode == "mnsutb":
                app_name = "MNSUTB Autorouter"
            elif mode == "dar":
                app_name = "DAR Autoruter"
            else:
                app_name = "SMD Autorouter"
    except:
        app_name = "SMD Autorouter"
    
    # Set the application name for system notifications
    QCoreApplication.setApplicationName(app_name)
    
    # Set Windows-specific application ID for better taskbar integration
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_name)

    window = SMDUSAPGui()
    # Set window icon
    window.setWindowIcon(app_icon)
    window.show()
    window.center_on_screen()
    # Ensure the window icon is set after showing the window
    window.setWindowIcon(app_icon)
    # Force refresh taskbar icon after a short delay
    QTimer.singleShot(200, window.force_refresh_taskbar_icon)
    # Ensure fade-in if not already set
    if window.windowOpacity() < 1.0:
        window.setWindowOpacity(0.0)
        fade_anim = QPropertyAnimation(window, b"windowOpacity")
        fade_anim.setDuration(400)
        fade_anim.setStartValue(0.0)
        fade_anim.setEndValue(1.0)
        fade_anim.start()
    sys.exit(app.exec_())
