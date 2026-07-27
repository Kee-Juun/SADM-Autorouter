"""
File type detection utilities for SADM Autorouter.

This module handles:
- Detecting counsel files vs main opinion files
- Finding related counsel LNIs for main opinions
"""

import re
from .smducar_utils import extract_docket_number


# Pattern for matching counsel files (legacy, kept for compatibility)
COUNSEL_PATTERN = re.compile(r"counsel.*\.htm$", re.IGNORECASE)


def is_counsel(file_name, dar_mode=False, wc_mode=False):
    """
    Determine if a file is a counsel file based on filename patterns.
    
    Args:
        file_name: Filename to check
        dar_mode: Whether DAR mode is enabled
        wc_mode: Whether WC mode is enabled (kept for backward compatibility, no longer used)
    
    Returns:
        bool: True if file is a counsel file, False otherwise
    """
    file_name_str = str(file_name).lower()
    
    # Check for counsel in the filename (case-insensitive)
    if 'counsel' in file_name_str:
        return True
    
    # Check for ARC documents - treat as counsel even if PDF (case-insensitive)
    if 'arc' in file_name_str:
        return True
    
    # If DAR mode is on, also check for DAR-specific counsel patterns
    if dar_mode:
        # Check for DAR pattern with counsel
        if re.search(r'dar.*counsel', file_name_str, re.IGNORECASE):
            return True
    
    return False


def get_related_counsel_lnis(main_docket, full_df, recycled_lni=None, dar_mode=False, wc_mode=False):
    """
    Get all related counsel LNIs for a given main docket number.
    
    Args:
        main_docket: The docket number of the main opinion
        full_df: DataFrame containing all file information
        recycled_lni: Optional recycled counsel LNI(s) to include
        dar_mode: Whether DAR mode is enabled
        wc_mode: Whether WC mode is enabled (kept for backward compatibility, no longer used)
    
    Returns:
        list: List of related counsel LNI strings
    """
    related_lnis = []

    # First, get all counsel LNIs with matching docket numbers (including ARC documents)
    for _, row in full_df.iterrows():
        file_name = str(row["FileName"]).strip()
        if is_counsel(file_name, dar_mode, wc_mode):
            docket = extract_docket_number(file_name, dar_mode, wc_mode)
            # Both docket and main_docket are already normalized by extract_docket_number
            if docket == main_docket:
                lni = str(row["LNI"]).strip()
                if lni.lower() != "nan":
                    related_lnis.append(lni)

    # Then handle recycled LNIs if present
    if recycled_lni and str(recycled_lni).strip().lower() != "nan":
        # Split by semicolon and handle each LNI
        recycled_lnis = [lni.strip() for lni in str(recycled_lni).split(';') if lni.strip()]
        for lni in recycled_lnis:
            if lni.lower() != "nan" and lni not in related_lnis:
                related_lnis.append(lni)

    return related_lnis

