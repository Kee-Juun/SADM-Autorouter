"""
Configuration and logging utilities for SADM Autorouter.

This module handles:
- Resource path resolution (PyInstaller-compatible)
- Configuration loading from JSON
- Logging setup with color formatting
- Folder creation for downloads/logs
"""

import os
import sys
import datetime
import json
import logging
from pathlib import Path


def resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller"""
    try:
        base_path = sys._MEIPASS  # type: ignore[attr-defined]
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


CONFIG_DIR = Path(resource_path("config"))

DEFAULT_CONFIG = {
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
}


def load_config():
    """Load configuration from config.json file"""
    try:
        config_path = CONFIG_DIR / "config.json"
        if config_path.exists():
            with open(config_path, "r") as f:
                config = json.load(f)
                merged = DEFAULT_CONFIG.copy()
                merged.update(config)
                return merged
        return DEFAULT_CONFIG.copy()
    except Exception as e:
        logging.error(f"Error loading config")
        return DEFAULT_CONFIG.copy()


# ========== Global Error Log ==========
# These are shared state variables used across the application
status_updates_buffer = {}
mspb_metadata_buffer = {}
itc_content_fingerprint_buffer = {}
error_log_entries = []


def setup_logging():
    """Setup logging with color formatters for console and plain formatter for file"""
    import sys
    from colorama import Fore, Style, init
    init(autoreset=True)

    class ColorFormatter(logging.Formatter):
        COLORS = {
            'INFO': Fore.GREEN,
            'WARNING': Fore.YELLOW,
            'ERROR': Fore.RED,
        }

        def format(self, record):
            color = self.COLORS.get(record.levelname, "")
            time_str = datetime.datetime.now().strftime("%I:%M:%S %p")
            message = f"{time_str} - {record.levelname} - {record.getMessage()}"
            return color + message + Style.RESET_ALL

    class PlainFormatter(logging.Formatter):
        def format(self, record):
            time_str = datetime.datetime.now().strftime("%I:%M:%S %p")
            return f"{time_str} - {record.levelname} - {record.getMessage()}"

    logs_path = Path.home() / "Downloads" / "Case Law Auto-Routing Resources" / "Logs"
    logs_path.mkdir(parents=True, exist_ok=True)

    now = datetime.datetime.now().strftime("%I-%M-%S_%p").lstrip("0")
    log_file = logs_path / f"log_{now}.txt"

    # Create console and file handlers separately
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setFormatter(PlainFormatter())

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(ColorFormatter())

    logging.basicConfig(
        level=logging.INFO,
        handlers=[file_handler, console_handler]
    )

    logging.info("Logging initialized.")


def create_folders():
    """Create folder structure for downloads and logs"""
    downloads_path = str(Path.home() / "Downloads")
    base_folder = os.path.join(downloads_path, "Case Law Auto-Routing Resources")
    logs_folder = os.path.join(base_folder, "Logs")
    os.makedirs(logs_folder, exist_ok=True)
    for folder_name in ("MSPB PDF Downloads", "ITC PDF Downloads", "IRSPLR PDF Downloads", "OHTAX0 PDF Downloads", "MNSUTB PDF Downloads"):
        os.makedirs(os.path.join(base_folder, folder_name), exist_ok=True)
    logging.info("Created folders at Downloads.")
    return base_folder

