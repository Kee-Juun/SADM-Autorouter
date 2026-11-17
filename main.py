"""Application entrypoint for SADM Autorouter."""

import sys
import os
import json
import logging
import traceback
from pathlib import Path
import ctypes

from core.startup_progress import close_startup, fail_startup, report_startup


def install_global_exception_hook():
    """Capture unexpected GUI/app exceptions in the critical report system."""
    from core.critical_error_notifier import notify_critical_error

    original_hook = sys.excepthook

    def handle_exception(exc_type, exc_value, exc_traceback):
        fail_startup(str(exc_value))
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


def _run_application():
    report_startup("Loading Interface Libraries", 5)
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtGui import QIcon
    from PyQt5.QtCore import QCoreApplication, QTimer, QPropertyAnimation

    report_startup("Loading App Components", 12)
    from frontend.smducar_pyqt import SMDUSAPGui
    from frontend.pyqt_logging import install_qt_message_filter, setup_logging
    from core.smducar_config import resource_path
    from core.build_info import build_version_footer

    # Set up logging
    setup_logging()
    logging.info(build_version_footer().replace("\n", " | "))
    install_qt_message_filter()
    install_global_exception_hook()
    
    report_startup("Starting the Interface", 55)
    app = QApplication(sys.argv)
    
    # Set application icon (works in dev and PyInstaller)
    report_startup("Loading App Icons", 59)
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
    report_startup("Reading Your Settings", 63)
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
            elif mode == "mework":
                app_name = "MEWORK Autorouter"
            elif mode == "mosu00":
                app_name = "MOSU Autorouter"
            elif mode == "fcc":
                app_name = "FCC Autorouter"
            elif mode == "ferc":
                app_name = "FERC Autorouter"
            elif mode == "nlrb":
                app_name = "NLRB Autorouter"
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
    report_startup("Building Your Workspace", 66)
    window = SMDUSAPGui()
    
    # Set window icon
    if app_icon:
        window.setWindowIcon(app_icon)
    
    window.show()
    window.center_on_screen()
    report_startup("Opening Your Workspace", 97)
    # Let Qt paint the main window and complete its 400ms fade first.
    QTimer.singleShot(450, close_startup)
    
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
    
    return app.exec_()


def main():
    try:
        return _run_application()
    except BaseException as exc:
        fail_startup(str(exc))
        raise
    finally:
        # Also close on import/initialization failures and early app exits.
        close_startup()


if __name__ == "__main__":
    sys.exit(main())


