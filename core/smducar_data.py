"""
Data processing utilities for SADM Autorouter.

This module handles:
- Filtering mapping data into counsel/main DataFrames
- Resolving source detail abbreviations to full names
"""

import logging
from .smducar_filetypes import is_counsel
from .smducar_excel import get_source_detail_mapping


def filter_mapping_data(df, dar_mode=False, wc_mode=False, mspb_mode=False):
    """
    Filter mapping data DataFrame into counsel and main opinion DataFrames.
    
    Args:
        df: DataFrame containing file mapping data
        dar_mode: Whether DAR mode is enabled
        wc_mode: Whether WC mode is enabled
        mspb_mode: Whether MSPB mode is enabled
    
    Returns:
        tuple: (counsel_df, main_df) - Two DataFrames separated by file type
    """
    df = df.copy()
    if mspb_mode:
        df["FileType"] = "Main"
        logging.info(f"MSPB Count: {len(df)}")
        return df.iloc[0:0].copy(), df.copy()

    df["FileType"] = df["FileName"].apply(lambda x: "Counsel" if is_counsel(x, dar_mode, wc_mode) else "Main")

    counsel_df = df[df["FileType"] == "Counsel"].copy()
    main_df = df[df["FileType"] == "Main"].copy()

    logging.info(f"Counsel Count: {len(counsel_df)}, Main Opinion Count: {len(main_df)}")
    return counsel_df, main_df


def resolve_source_detail(source_detail_input):
    """
    Resolve source detail input to full name, supporting both abbreviations and full names.
    
    Args:
        source_detail_input: Source detail string (abbreviation or full name)
    
    Returns:
        str: Full source detail name, or None if input is invalid
    """
    if not source_detail_input or str(source_detail_input).lower() == "nan":
        return None

    source_detail_input = str(source_detail_input).strip()
    mapping = get_source_detail_mapping()

    # Check if input is an abbreviation (case-insensitive)
    if source_detail_input.lower() in mapping:
        return mapping[source_detail_input.lower()]

    # If not found in abbreviations, return the original input (assumes it's a full name)
    return source_detail_input

