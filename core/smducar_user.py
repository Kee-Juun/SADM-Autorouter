"""
User and display name utilities for SADM Autorouter.

This module handles:
- Username parsing and formatting
- Windows username retrieval
- Display name cleaning for UI
"""

import re
import getpass
import ctypes


def split_username(username):
    """
    Split username into readable parts using various delimiters.
    
    Args:
        username: Username string to split
    
    Returns:
        str: Formatted name with capitalized parts
    """
    # Try to split on common delimiters
    if "_" in username:
        parts = username.split("_")
    elif "." in username:
        parts = username.split(".")
    else:
        # Try to split camel case or just capitalize first and last
        parts = re.findall(r'[A-Z][a-z]*', username)
        if not parts:
            # Try to split in the middle for two names if all lowercase
            if len(username) > 6:
                mid = len(username) // 2
                parts = [username[:mid], username[mid:]]
            else:
                parts = [username]
    return " ".join([p.capitalize() for p in parts if p])


def get_full_username():
    """
    Get the full Windows username for display purposes.
    Tries Windows API first, falls back to system username.
    
    Returns:
        str: Full username or formatted username, or "User" as fallback
    """
    try:
        GetUserNameEx = ctypes.windll.secur32.GetUserNameExW
        NameDisplay = 3

        size = ctypes.pointer(ctypes.c_ulong(0))
        GetUserNameEx(NameDisplay, None, size)

        name_buffer = ctypes.create_unicode_buffer(size.contents.value)
        result = GetUserNameEx(NameDisplay, name_buffer, size)
        
        if result and name_buffer.value:
            return name_buffer.value
    except Exception:
        pass
    
    # Fallback to username
    try:
        username = getpass.getuser()
        return split_username(username)
    except Exception:
        return "User"


def clean_display_name(full_name):
    """
    Clean and format a full name for display in the UI.
    Removes parentheses content and handles comma-separated names.
    
    Args:
        full_name: Full name string to clean
    
    Returns:
        str: Cleaned and formatted name
    """
    cleaned = re.sub(r"\(.*?\)", "", full_name)
    if "," in cleaned:
        cleaned = cleaned.split(",")[1]
    return cleaned.strip().title()

