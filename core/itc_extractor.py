"""
International Trade Commission metadata extraction helpers.

ITC rows do not use the SADM counsel/main tandem. They are routed from the
document metadata itself: court, investigation number, decision date, source
detail, and optional other numbers.
"""

from __future__ import annotations

import datetime
import hashlib
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .mspb_extractor import extract_text_from_pdf_bytes


ITC_COURT_CODES = {"FDITC000", "FDITCALJ"}
ITC_SOURCE_DETAIL_BY_COURT = {
    "FDITC000": "Opinion",
    "FDITCALJ": "Order",
}
ITC_TA_PREFIXES = {"337", "701", "731"}


@dataclass(frozen=True)
class ITCMetadata:
    court: str
    docket_number: str
    decision_date: str
    source_detail: str
    other_numbers: tuple[str, ...] = ()
    comments_text: str = ""
    title_hint: str = ""
    content_fingerprint: str = ""
    has_text_content: bool = False
    is_true_duplicate: bool = False
    duplicate_of: str = ""
    duplicate_of_lni: str = ""
    is_excluded: bool = False
    exclusion_reason: str = ""
    used_filename_docket_fallback: bool = False


def is_itc_court_code(court_code) -> bool:
    return str(court_code or "").strip().upper() in ITC_COURT_CODES


def is_itc_filename(file_name) -> bool:
    name = Path(str(file_name or "")).name.lower()
    return name.startswith("itc000_") or name.startswith("itcalj_")


def is_itc_row(row) -> bool:
    court_code = ""
    file_name = ""
    try:
        court_code = row.get("CourtCode", row.get("Court Code", ""))
        file_name = row.get("FileName", row.get("File Name", ""))
    except AttributeError:
        pass
    return is_itc_court_code(court_code) or is_itc_filename(file_name)


def get_itc_court(file_name=None, court_code=None) -> Optional[str]:
    court = str(court_code or "").strip().upper()
    if court in ITC_COURT_CODES:
        return court

    name = Path(str(file_name or "")).name.lower()
    if name.startswith("itc000_"):
        return "FDITC000"
    if name.startswith("itcalj_"):
        return "FDITCALJ"
    return None


def get_itc_source_detail(court: str) -> Optional[str]:
    return ITC_SOURCE_DETAIL_BY_COURT.get(str(court or "").strip().upper())


def normalize_itc_docket(raw_docket) -> Optional[str]:
    if not raw_docket:
        return None

    docket = normalize_itc_text(raw_docket)
    docket = re.sub(r"\s+", "", str(docket).strip().upper())
    docket = re.sub(r"-+", "-", docket)
    match = re.fullmatch(r"(\d{3})-(?:TA-)?(\d+)", docket)
    if not match:
        return None

    prefix, number = match.groups()
    if prefix in ITC_TA_PREFIXES:
        return f"{prefix}-TA-{number}"
    return f"{prefix}-{number}"


def extract_itc_docket_from_filename(file_name) -> Optional[str]:
    name = Path(str(file_name or "")).name
    match = re.search(
        r"^(?:itc000|itcalj)_(\d{3}-\d+)_\d{8}(?:_\d+)?\.pdf$",
        name,
        re.IGNORECASE,
    )
    if not match:
        return None
    return normalize_itc_docket(match.group(1))


def extract_itc_date_from_filename(file_name) -> Optional[str]:
    name = Path(str(file_name or "")).name
    match = re.search(r"[_-](\d{8})(?=[_-]|\.|$)", name)
    if not match:
        return None

    digits = match.group(1)
    for fmt in ("%Y%m%d", "%m%d%Y"):
        try:
            return datetime.datetime.strptime(digits, fmt).strftime("%m-%d-%Y")
        except ValueError:
            continue
    return None


def parse_itc_pdf_bytes(
    pdf_bytes: bytes,
    filename_hint: Optional[str] = None,
    court_code_hint: Optional[str] = None,
    use_ocr_fallback: bool = True,
) -> Optional[ITCMetadata]:
    text = extract_text_from_pdf_bytes(pdf_bytes, use_ocr_fallback=use_ocr_fallback)
    if not text.strip():
        logging.warning("ITC PDF text extraction returned no text.")
    return parse_itc_document_text(
        text,
        filename_hint=filename_hint,
        court_code_hint=court_code_hint,
    )


def parse_itc_document_text(
    text: str,
    filename_hint: Optional[str] = None,
    court_code_hint: Optional[str] = None,
) -> Optional[ITCMetadata]:
    court = get_itc_court(filename_hint, court_code_hint)
    content_fingerprint = compute_itc_content_fingerprint(text)
    has_text_content = bool(content_fingerprint)
    content_docket = extract_primary_itc_docket(text)
    docket_number, used_filename_docket_fallback = resolve_itc_docket_number(
        text,
        filename_hint,
        has_text_content,
        content_docket,
        court,
    )
    decision_date = extract_itc_decision_date_from_text(text, court) or extract_itc_date_from_filename(filename_hint)
    exclusion_reason = classify_itc_exclusion(text, court)
    source_detail = "Excluded" if exclusion_reason else get_itc_source_detail(court)

    if not court or not source_detail or not docket_number or not decision_date:
        logging.warning(
            "Incomplete ITC metadata: court=%s docket=%s decision_date=%s source_detail=%s",
            court,
            docket_number,
            decision_date,
            source_detail,
        )
        return None

    other_numbers = extract_itc_other_numbers(text, docket_number, court) if has_text_content else []
    return ITCMetadata(
        court=court,
        docket_number=docket_number,
        decision_date=decision_date,
        source_detail=source_detail,
        other_numbers=tuple(other_numbers),
        comments_text=format_itc_comments(other_numbers, exclusion_reason=exclusion_reason),
        title_hint=find_itc_title_hint(text),
        content_fingerprint=content_fingerprint,
        has_text_content=has_text_content,
        is_excluded=bool(exclusion_reason),
        exclusion_reason=exclusion_reason,
        used_filename_docket_fallback=used_filename_docket_fallback,
    )


def resolve_itc_docket_number(
    text: str,
    filename_hint: Optional[str],
    has_text_content: bool,
    content_docket: Optional[str],
    court: Optional[str],
) -> tuple[Optional[str], bool]:
    if content_docket:
        return content_docket, False

    filename_docket = extract_itc_docket_from_filename(filename_hint)
    if not filename_docket:
        return None, False

    if not has_text_content:
        return filename_docket, True

    if should_use_itc_filename_docket_fallback(text, filename_docket, court):
        logging.warning(
            "ITC PDF text was readable, but no primary docket was found in the document; "
            "using filename docket fallback: %s",
            filename_docket,
        )
        return filename_docket, True

    return None, False


def should_use_itc_filename_docket_fallback(text: str, filename_docket: str, court: Optional[str]) -> bool:
    if not looks_like_itc_document_text(text, court):
        logging.warning(
            "Readable text did not look like an ITC document; not using ITC filename docket fallback."
        )
        return False

    loose_dockets = extract_loose_itc_docket_candidates(text)
    conflicting_dockets = [docket for docket in loose_dockets if docket != filename_docket]
    if conflicting_dockets:
        logging.warning(
            "Readable ITC text contains possible docket(s) %s that conflict with filename docket %s; "
            "not using filename docket fallback.",
            ", ".join(conflicting_dockets),
            filename_docket,
        )
        return False

    if loose_dockets:
        logging.info(
            "Readable ITC text only exposed loose docket candidate(s) matching the filename; "
            "using filename docket fallback."
        )
    return True


def extract_primary_itc_docket(text: str) -> Optional[str]:
    numbers = extract_itc_docket_numbers(text)
    return numbers[0] if numbers else None


def extract_loose_itc_docket_candidates(text: str) -> list[str]:
    if not text:
        return []

    normalized_text = normalize_itc_text(text)
    candidates = []

    patterns = (
        r"\b(337|701|731)\s*(?:-| )?\s*TA\s*(?:-| )?\s*(\d{2,5}(?:\s*-\s*\d{2,5})*)\b",
        r"\b(?:INV(?:ESTIGATION)?\.?\s+NO(?:S)?\.?\s*[:#]?\s*)(337|701|731)\s*-\s*(\d{2,5})\b",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, normalized_text, re.IGNORECASE):
            prefix = match.group(1)
            tail = match.group(2)
            for docket in expand_itc_ta_docket_range(prefix, tail):
                if docket not in candidates:
                    candidates.append(docket)

    return candidates


def extract_itc_docket_numbers(text: str) -> list[str]:
    if not text:
        return []

    text = normalize_itc_text(text)
    numbers = []

    ta_pattern = r"\b(337|701|731)\s*-\s*TA\s*-\s*(\d{2,5}(?:\s*-\s*\d{2,5})*)\b"
    for match in re.finditer(ta_pattern, text, re.IGNORECASE):
        prefix = match.group(1)
        tail = match.group(2)
        for docket in expand_itc_ta_docket_range(prefix, tail):
            if docket not in numbers:
                numbers.append(docket)

        for docket in extract_itc_shorthand_companion_dockets(text, match):
            if docket not in numbers:
                numbers.append(docket)

    for match in re.finditer(r"\b(332\s*-\s*\d{2,5})\b", text, re.IGNORECASE):
        docket = normalize_itc_docket(match.group(1))
        if docket and docket not in numbers:
            numbers.append(docket)
    return numbers


def extract_itc_shorthand_companion_dockets(text: str, full_docket_match: re.Match) -> list[str]:
    """Expand caption shorthand like 731-TA-1014 and 1016 into companion dockets."""
    prefix = full_docket_match.group(1)
    first_tail = full_docket_match.group(2)
    first_parts = re.findall(r"\d+", first_tail)
    if not prefix or not first_parts:
        return []

    first_width = len(first_parts[-1])
    tail = text[full_docket_match.end():full_docket_match.end() + 160]
    tail = re.split(
        r"\(|\n|\.|\bAGENCY\b|\bACTION\b|\bSUMMARY\b|\bSUPPLEMENTARY\s+INFORMATION\b",
        tail,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]

    companions = []
    pattern = r"^\s*(?:,|;|\band\b|&)\s*(?:\band\b\s*)?(\d{2,5})(?!\s*-\s*TA)\b"
    while tail:
        match = re.match(pattern, tail, re.IGNORECASE)
        if not match:
            break

        number = match.group(1)
        if abs(len(number) - first_width) <= 1:
            companions.append(f"{prefix}-TA-{number}")
        tail = tail[match.end():]

    return companions


def expand_itc_ta_docket_range(prefix: str, number_tail: str) -> list[str]:
    """Expand ITC caption ranges like 731-TA-1543-1545 into full docket values."""
    prefix = str(prefix or "").strip()
    parts = [int(part) for part in re.findall(r"\d+", str(number_tail or ""))]
    if not prefix or not parts:
        return []

    expanded = []
    if len(parts) == 1:
        expanded = parts
    elif len(parts) == 2 and parts[1] >= parts[0] and parts[1] - parts[0] <= 50:
        expanded = list(range(parts[0], parts[1] + 1))
    else:
        expanded = parts

    return [f"{prefix}-TA-{number}" for number in expanded]


def extract_itc_order_numbers(text: str) -> list[str]:
    if not text:
        return []

    search_text = text[:2500]
    match = re.search(r"\bORDER\s+NO\.?\s*[:#]?\s*([A-Z0-9][A-Z0-9.\-]*)", search_text, re.IGNORECASE)
    if not match:
        return []
    number = match.group(1).strip().strip(".,;:)")
    return [number] if number else []


def extract_itcalj_title_order_numbers(text: str) -> list[str]:
    title_hint = find_itc_title_hint(text)
    for candidate in [title_hint, *_clean_lines(text)[:100]]:
        normalized = re.sub(r"\s+", " ", normalize_itc_text(candidate)).strip()
        if not re.match(r"(?i)^ORDER\s+NO\.?\s+", normalized):
            continue
        match = re.match(r"(?i)^ORDER\s+NO\.?\s*[:#]?\s*([A-Z0-9][A-Z0-9.\-]*)", normalized)
        if match:
            number = match.group(1).strip().strip(".,;:)")
            return [number] if number else []
    return extract_itc_order_numbers(text)


def extract_itc_other_numbers(text: str, primary_docket: str, court: Optional[str] = None) -> list[str]:
    other_numbers = []
    primary_normalized = normalize_itc_docket(primary_docket) or str(primary_docket or "").strip()

    if str(court or "").strip().upper() == "FDITCALJ":
        return extract_itcalj_title_order_numbers(text)

    for docket in extract_itc_docket_numbers(get_itc_header_text(text)):
        if docket != primary_normalized and docket not in other_numbers:
            other_numbers.append(docket)

    return other_numbers


def get_itc_header_text(text: str) -> str:
    if not text:
        return ""

    header = normalize_itc_text(text)[:3000]
    for marker in ("\nAGENCY:", "\nACTION:", "\nSUMMARY:", "\nSUPPLEMENTARY INFORMATION:"):
        index = header.upper().find(marker)
        if index > 0:
            return header[:index]
    return header


def get_itc_action_text(text: str) -> str:
    if not text:
        return ""

    search_text = normalize_itc_text(text)[:5000]
    match = re.search(
        r"(?ims)^\s*ACTION\s*:\s*(.+?)(?=^\s*(?:AGENCY|SUMMARY|DATES|ADDRESSES|SUPPLEMENTARY\s+INFORMATION)\s*:|\n\s*\n|$)",
        search_text,
    )
    if not match:
        return ""
    return re.sub(r"\s+", " ", match.group(1)).strip(" .;:")


def classify_itc_exclusion(text: str, court: Optional[str] = None) -> str:
    if not text:
        return ""

    court_upper = str(court or "").strip().upper()
    header = _normalize_for_rule_matching(get_itc_header_text(text))
    action = _normalize_for_rule_matching(get_itc_action_text(text))

    if court_upper == "FDITC000":
        if "SCHEDULING OF HEARING" in header or "SCHEDULING HEARING" in header:
            return "Scheduling of Hearing"
        if re.search(r"\bNOTICE TO (?:THE )?PARTIES\b", header) or re.search(r"\bNOTICE TO (?:THE )?PARTIES\b", action):
            return "Notice to the Parties"
        if re.search(r"\bMEMORANDUM\b", header):
            return "Memorandum"
        return ""

    if court_upper == "FDITCALJ":
        if re.search(r"\bNOTICE TO (?:THE )?PARTIES\b", header) or re.search(r"\bNOTICE TO (?:THE )?PARTIES\b", action):
            return "Notice to the Parties"
        if "SETTING THE PROCEDURAL SCHEDULE" in header or "SETTING PROCEDURAL SCHEDULE" in header:
            return "Setting the Procedural Schedule"
        if "PREHEARING" in header and ("SCHEDULING" in header or "RESCHEDULING" in header):
            return "Scheduling/rescheduling a prehearing"
        if "TARGET DATE" in header and ("SETTING" in header or re.search(r"\bSET\b", header)):
            return "Setting a Target Date"
        if (
            ("RESETTING DATES" in header or "RESETTING" in header)
            and "PREHEARING CONFERENCE" in header
            and "HEARING" in header
        ):
            return "Resetting dates of prehearing conference and hearing"
        return ""

    return ""


def format_itc_comments(other_numbers, exclusion_reason: str = "") -> str:
    numbers = [str(number).strip() for number in other_numbers if str(number).strip()]
    parts = []
    if exclusion_reason:
        parts.append(f"Exclude - {exclusion_reason}")
    parts.extend(numbers)
    return "; ".join(parts)


def extract_itc_decision_date_from_text(text: str, court: Optional[str] = None) -> Optional[str]:
    if not text:
        return None

    date_pattern = (
        r"(?:[A-Za-z]+\s+\d{1,2},\s+\d{4}|"
        r"\d{1,2}[-/]\d{1,2}[-/]\d{2,4})"
    )

    for pattern in (
        rf"\bIssued\s*:?\s*({date_pattern})",
        rf"\bDated\s*:?\s*({date_pattern})",
        rf"\bDate\s+Issued\s*:?\s*({date_pattern})",
    ):
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            normalized = normalize_itc_date(match.group(1))
            if normalized:
                return normalized

    if str(court or "").strip().upper() == "FDITCALJ":
        for match in re.finditer(rf"\(({date_pattern})\)", text[:4000], re.IGNORECASE):
            normalized = normalize_itc_date(match.group(1))
            if normalized:
                return normalized

    return None


def normalize_itc_date(raw_date: str) -> Optional[str]:
    cleaned = re.sub(r"\s+", " ", str(raw_date or "").strip().rstrip(".,"))
    for fmt in (
        "%B %d, %Y",
        "%b %d, %Y",
        "%m-%d-%Y",
        "%m/%d/%Y",
        "%m-%d-%y",
        "%m/%d/%y",
    ):
        try:
            return datetime.datetime.strptime(cleaned, fmt).strftime("%m-%d-%Y")
        except ValueError:
            continue
    return None


def find_itc_title_hint(text: str) -> str:
    for line in _clean_lines(text)[:80]:
        normalized = re.sub(r"\s+", " ", line.upper()).strip()
        if normalized.startswith("ORDER NO."):
            return normalized[:160]
        if normalized.startswith("NOTICE "):
            return normalized[:160]
        if normalized.startswith("INSTITUTION OF INVESTIGATION"):
            return normalized[:160]
    return ""


def compute_itc_content_fingerprint(text: str) -> str:
    normalized = normalize_itc_text(text).lower()
    normalized = re.sub(r"\s+", " ", normalized).strip()
    normalized = re.sub(r"[^a-z0-9]+", "", normalized)
    if len(normalized) < 200:
        return ""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def looks_like_itc_document_text(text: str, court: Optional[str] = None) -> bool:
    if not text:
        return False

    text_upper = normalize_itc_text(text).upper()
    if (
        "INTERNATIONAL TRADE COMMISSION" in text_upper
        or "INV. NO." in text_upper
        or "INVESTIGATION NO." in text_upper
        or "ORDER NO." in text_upper
    ):
        return True

    if str(court or "").strip().upper() == "FDITCALJ":
        return "ADMINISTRATIVE LAW JUDGE" in text_upper
    return False


def normalize_itc_text(text) -> str:
    value = str(text or "")
    return (
        value.replace("\u00a0", " ")
        .replace("\u2010", "-")
        .replace("\u2011", "-")
        .replace("\u2012", "-")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u2212", "-")
    )


def _normalize_for_rule_matching(text: str) -> str:
    return re.sub(r"\s+", " ", normalize_itc_text(text).upper()).strip()


def _clean_lines(text: str) -> list[str]:
    return [line.strip() for line in normalize_itc_text(text).splitlines() if line.strip()]
