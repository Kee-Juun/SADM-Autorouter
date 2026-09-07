import logging
import re

from .mosu00_extractor import (
    extract_mosu00_docket_from_filename,
    is_mosu00_filename,
)


ITC_TA_PREFIXES = {"337", "701", "731"}


def normalize_docket_number(docket):
    """Remove leading zeroes from case number for consistent matching across all modes."""
    if docket and "-" in docket:
        year, case = docket.split("-")
        if case.isdigit() and case.startswith("0") and len(case) > 1:
            case_normalized = str(int(case))
            return f"{year}-{case_normalized}"
        return docket
    return docket


def normalize_itc_docket_number(docket):
    """Normalize ITC docket numbers such as 337-1447 to 337-TA-1447."""
    if not docket:
        return None

    docket = re.sub(r"\s+", "", str(docket).strip().upper())
    match = re.fullmatch(r"(\d{3})-(?:TA-)?(\d+)", docket)
    if not match:
        return None

    prefix, number = match.groups()
    if prefix in ITC_TA_PREFIXES:
        return f"{prefix}-TA-{number}"
    return f"{prefix}-{number}"


def extract_itc_docket_number(file_name):
    file_name = str(file_name).replace("\\", "/").split("/")[-1]
    match = re.search(
        r"^(?:itc000|itcalj)_(\d{3}-\d+)_\d{8}(?:_\d+)?\.pdf$",
        file_name,
        re.IGNORECASE,
    )
    if not match:
        return None
    return normalize_itc_docket_number(match.group(1))


def extract_docket_number(file_name, dar_mode=False, wc_mode=False):
    """
    Extract base docket number from filename, supporting SMD and DAR patterns.
    
    Note: wc_mode parameter kept for backward compatibility but WC mode is no longer supported.

    This is a direct extraction of the logic previously implemented in smducar.py,
    kept byte-for-byte equivalent for behavior.
    """
    itc_docket = extract_itc_docket_number(file_name)
    if itc_docket:
        logging.info(f"ITC mode: Extracted docket: {itc_docket}")
        return itc_docket

    mosu00_docket = extract_mosu00_docket_from_filename(file_name)
    if mosu00_docket:
        logging.info(f"MOSU00 mode: Extracted docket: {mosu00_docket}")
        return mosu00_docket

    if dar_mode:
        dar_match = re.search(
            r"dar_[\w\-]*(\d{2})[-_]?(cv|md|cd|mc|cr|mj)(\d+)(?:[-_]|(?=[a-zA-Z]))",
            str(file_name),
            re.IGNORECASE,
        )
        if dar_match:
            before_court_raw = dar_match.group(1)
            after_court = dar_match.group(3)

            if len(before_court_raw) >= 2:
                year = before_court_raw[-2:]
                original_docket = f"{year}-{after_court}"
                normalized_docket = normalize_docket_number(original_docket)
                if original_docket != normalized_docket:
                    logging.info(
                        f"DAR mode: Normalized docket: {original_docket} -> {normalized_docket}"
                    )
                else:
                    logging.info(
                        f"DAR mode: Extracted docket: {original_docket} (no normalization needed)"
                    )
                return normalized_docket

        simple_dar = re.search(
            r"dar_(\d{2})-(\d+)(?:[_\-]|$)", str(file_name), re.IGNORECASE
        )
        if simple_dar:
            year = simple_dar.group(1)
            case_number = simple_dar.group(2)
            original_docket = f"{year}-{case_number}"
            normalized_docket = normalize_docket_number(original_docket)
            if original_docket != normalized_docket:
                logging.info(
                    f"DAR mode (simple): Normalized docket: {original_docket} -> {normalized_docket}"
                )
            else:
                logging.info(
                    f"DAR mode (simple): Extracted docket: {normalized_docket} (no normalization needed)"
                )
            return normalized_docket

        ldc_match = re.search(
            r"ldc_(pc|rr)_[\w\-]*(\d{2})[-_]?(cv|md|cd|mc|cr|mj)(\d+)",
            str(file_name),
            re.IGNORECASE,
        )
        if ldc_match:
            before_court_raw = ldc_match.group(2)
            after_court = ldc_match.group(4)
            year = before_court_raw[-2:] if len(before_court_raw) >= 2 else before_court_raw
            original_docket = f"{year}-{after_court}"
            normalized_docket = normalize_docket_number(original_docket)
            logging.info(
                f"DAR mode (LDC_PC/RR): Extracted docket: {original_docket} -> {normalized_docket}"
            )
            return normalized_docket

    file_name = re.sub(r"counsel-\d+", "counsel", str(file_name))
    smd_match = re.search(r"LDC_SMD_([\d\-]+)[a-z]?", file_name)
    if smd_match:
        original_docket = smd_match.group(1)
        normalized_docket = normalize_docket_number(original_docket)
        if original_docket != normalized_docket:
            logging.info(
                f"SMD mode: Normalized docket: {original_docket} -> {normalized_docket}"
            )
        else:
            logging.info(
                f"SMD mode: Extracted docket: {original_docket} (no normalization needed)"
            )
        return normalized_docket

    smd_match = re.search(
        r"smd_([\d\-]+)(?:[a-z]|[_\-])", str(file_name), re.IGNORECASE
    )
    if smd_match:
        original_docket = smd_match.group(1)
        normalized_docket = normalize_docket_number(original_docket)
        if original_docket != normalized_docket:
            logging.info(
                f"SMD mode (new pattern): Normalized docket: {original_docket} -> {normalized_docket}"
            )
        else:
            logging.info(
                f"SMD mode (new pattern): Extracted docket: {original_docket} (no normalization needed)"
            )
        return normalized_docket

    if dar_mode:
        smd_match = re.search(r"LDC_SMD_([\d\-]+)[a-z]?", file_name)
        if smd_match:
            original_docket = smd_match.group(1)
            normalized_docket = normalize_docket_number(original_docket)
            if original_docket != normalized_docket:
                logging.info(
                    f"DAR fallback to SMD: Normalized docket: {original_docket} -> {normalized_docket}"
                )
            else:
                logging.info(
                    f"DAR fallback to SMD: Extracted docket: {original_docket} (no normalization needed)"
                )
            return normalized_docket

    return None


def detect_mode(filename):
    """
    Auto-detect the mode (SMD, DAR, MSPB, ITC, IRSPLR, OHTAX0, MNSUTB, MOSU00, WC) from filename patterns.

    Returns:
        str: 'smd', 'dar', 'mspb', 'wc', 'itc', 'irsplr', 'ohtax0', 'mnsutb', 'mosu00', or 'unknown'
    """
    filename_str = (
        str(filename)
        .lower()
        .replace("\u200b", "")
        .replace("\u200c", "")
        .replace("\u200d", "")
        .replace("\ufeff", "")
    )

    if filename_str.startswith("fdmspb") or "mspb" in filename_str:
        return "mspb"
    if filename_str.startswith("itc000_") or filename_str.startswith("itcalj_"):
        return "itc"
    if re.match(r"^saq\d+_\d{4}_\d+.*\.pdf$", filename_str):
        return "ohtax0"
    if re.match(r"^ldc_smd_a\d{2}-\d{4,6}.*\.pdf$", filename_str):
        return "mnsutb"
    if is_mosu00_filename(filename_str):
        return "mosu00"
    if re.match(r"^(?:ldc_bc_)?(?:\d{2}[-_]\d+|\d{4,9}).*\.pdf$", filename_str):
        return "irsplr"
    if filename_str.startswith("wc_cl_"):
        return "wc"
    elif filename_str.startswith("dar_"):
        return "dar"
    elif filename_str.startswith("ldc_pc_") or filename_str.startswith("ldc_rr_"):
        return "dar"
    elif "ldc_smd_" in filename_str or filename_str.startswith("smd_"):
        return "smd"
    else:
        return "unknown"


