# Standard library imports
import os
import sys
import datetime
import logging
from pathlib import Path
import subprocess
import platform
import pandas as pd
import re
import time
import threading
import json


# User/display utilities moved to smducar_user.py module
from .smducar_user import (
    split_username,
    get_full_username,
    clean_display_name,
)


# Config and logging utilities moved to smducar_config.py module
from .smducar_config import (
    resource_path,
    CONFIG_DIR,
    load_config,
    setup_logging,
    create_folders,
    status_updates_buffer,
    error_log_entries,
)


from .smducar_excel import (
    generate_excel,
    open_excel_file,
    get_latest_excel_file,
    read_mapping_data,
    flush_status_updates,
    get_source_detail_mapping,
)
from .smducar_utils import (
    normalize_docket_number,
    extract_docket_number,
    detect_mode,
)
# File type detection functions moved to smducar_filetypes.py module
from .smducar_filetypes import (
    is_counsel,
    get_related_counsel_lnis,
    COUNSEL_PATTERN,
)

# Selenium/WebDriver utilities moved to smducar_selenium.py module
from .smducar_selenium import (
    launch_chrome_driver,
    retry_click,
    select_dropdown_by_text,
)


# ========== Main Routing Class ==========
# CaseLawRouter class moved to smducar_router.py module
from .smducar_router import CaseLawRouter

# Data processing utilities moved to smducar_data.py module
from .smducar_data import (
    filter_mapping_data,
    resolve_source_detail,
)

# Workflow orchestration moved to smducar_workflow.py module
# Import directly from smducar_workflow when needed
