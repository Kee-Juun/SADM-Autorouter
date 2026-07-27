"""
PyQt Logging Module

Contains logging formatters, handlers, and setup for the SADM Auto-Router application.
"""

import sys
import logging
from pathlib import Path
from datetime import datetime

_qt_message_filter_installed = False

# Set up colored logging with colorama (optional)
try:
    from colorama import Fore, Style, init
    init(autoreset=True)
    COLORAMA_AVAILABLE = True
except ImportError:
    # If colorama is not available, use empty strings for colors
    class Fore:
        CYAN = ""
        GREEN = ""
        YELLOW = ""
        RED = ""
    class Style:
        RESET_ALL = ""
    COLORAMA_AVAILABLE = False


class ColorFormatter(logging.Formatter):
    """Logging formatter that adds color to console output using colorama."""
    COLORS = {
        'DEBUG': Fore.CYAN,
        'INFO': Fore.GREEN,
        'WARNING': Fore.YELLOW,
        'ERROR': Fore.RED,
    }

    def format(self, record):
        color = self.COLORS.get(record.levelname, "")
        time_str = datetime.now().strftime("%I:%M:%S %p")
        message = f"{time_str} - {record.levelname} - {record.getMessage()}"
        return color + message + Style.RESET_ALL


class PlainFormatter(logging.Formatter):
    """Logging formatter without colors for file output."""
    def format(self, record):
        time_str = datetime.now().strftime("%I:%M:%S %p")
        return f"{time_str} - {record.levelname} - {record.getMessage()}"


def setup_logging():
    """
    Set up logging configuration with console and file handlers.
    Returns the log file path.
    """
    # Create logs directory
    logs_path = Path.home() / "Downloads" / "Case Law Auto-Routing Resources" / "Logs"
    logs_path.mkdir(parents=True, exist_ok=True)

    now = datetime.now().strftime("%I-%M-%S_%p").lstrip("0")
    log_file = logs_path / f"log_{now}.txt"

    # Create console and file handlers separately
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setFormatter(PlainFormatter())

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(ColorFormatter())

    logging.basicConfig(
        level=logging.DEBUG,
        handlers=[file_handler, console_handler]
    )

    # Suppress debug logs from noisy libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("selenium").setLevel(logging.WARNING)
    logging.getLogger("webdriver_manager").setLevel(logging.WARNING)
    logging.getLogger("WDM").setLevel(logging.WARNING)

    logging.info("Logging initialized.")
    
    return log_file


def install_qt_message_filter():
    """Suppress known harmless Qt console noise while preserving other Qt messages."""
    global _qt_message_filter_installed
    if _qt_message_filter_installed:
        return

    try:
        from PyQt5.QtCore import QtDebugMsg, QtInfoMsg, QtWarningMsg, QtCriticalMsg, qInstallMessageHandler
    except Exception:
        return

    message_labels = {
        QtDebugMsg: "QtDebugMsg",
        QtInfoMsg: "QtInfoMsg",
        QtWarningMsg: "QtWarningMsg",
        QtCriticalMsg: "QtCriticalMsg",
    }

    def message_handler(mode, context, message):
        message_text = str(message or "")
        if (
            "QWindowsWindow::setMouseGrabEnabled" in message_text
            and "QComboBoxPrivateContainerClassWindow" in message_text
        ):
            return

        if mode == QtWarningMsg:
            prefix = ""
        else:
            prefix = f"{message_labels.get(mode, 'QtMessage')}: "
        print(f"{prefix}{message_text}", file=sys.stderr)

    qInstallMessageHandler(message_handler)
    _qt_message_filter_installed = True


class QtLogHandler(logging.Handler):
    """
    Custom logging handler that emits log messages to a PyQt signal.
    
    This handler is used to display log messages in the GUI console window.
    It requires a GUI object with a log_signal attribute (pyqtSignal).
    """
    
    def __init__(self, gui):
        """
        Initialize the QtLogHandler.
        
        Args:
            gui: The GUI object that has a log_signal attribute (pyqtSignal)
        """
        super().__init__()
        self.gui = gui
    
    def emit(self, record):
        """
        Emit a log record by sending it to the GUI's log signal.
        
        Args:
            record: The log record to emit
        """
        msg = self.format(record)
        self.gui.log_signal.emit(msg)

