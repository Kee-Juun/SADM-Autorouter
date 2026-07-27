"""Application entrypoint for SADM Autorouter."""

import sys
import os
import json
import logging
import traceback
from pathlib import Path
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import QCoreApplication, QTimer, QPropertyAnimation
import ctypes

# Import the main window class
from frontend.smducar_pyqt import SMDUSAPGui

# Import logging setup
from frontend.pyqt_logging import install_qt_message_filter, setup_logging

# Import resource_path for asset handling
from core.smducar_config import resource_path
from core.critical_error_notifier import notify_critical_error


def install_global_exception_hook():
    """Capture unexpected GUI/app exceptions in the critical report system."""
    original_hook = sys.excepthook

    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            original_hook(exc_type, exc_value, exc_traceback)
            return

        tb = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        logging.critical("Unhandled application exception: %s", exc_value)
        logging.critical("Unhandled traceback: %s", tb)
        notify_critical_error(
            "Unhandled application crash",
            exc_value,
            traceback_text=tb,
        )
        original_hook(exc_type, exc_value, exc_traceback)

    sys.excepthook = handle_exception


def main():
    # Set up logging
    setup_logging()
    install_qt_message_filter()
    install_global_exception_hook()
    
    app = QApplication(sys.argv)
    
    # Set application icon (works in dev and PyInstaller)
    try:
        base_path = getattr(sys, '_MEIPASS', os.path.abspath('.'))
        icon_path = Path(base_path) / 'assets' / 'icons' / 'silcrow.ico'
        if not icon_path.exists():
            # Fallback to resource_path
            icon_path = Path(resource_path('assets')) / 'icons' / 'silcrow.ico'
        if icon_path.exists():
            app_icon = QIcon(str(icon_path))
            app.setWindowIcon(app_icon)
        else:
            app_icon = None
    except Exception:
        app_icon = None
    
    # Determine application name based on config
    try:
        config_path = Path(resource_path('config')) / 'config.json'
        with open(config_path, 'r') as f:
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
    except Exception:
        app_name = "SMD Autorouter"
    
    # Set the application name for system notifications
    QCoreApplication.setApplicationName(app_name)
    
    # Set Windows-specific application ID for better taskbar integration
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_name)
    except Exception:
        pass
    
    # Create and show the main window
    window = SMDUSAPGui()
    
    # Set window icon
    if app_icon:
        window.setWindowIcon(app_icon)
    
    window.show()
    window.center_on_screen()
    
    # Ensure the window icon is set after showing the window
    if app_icon:
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


if __name__ == "__main__":
    main()


