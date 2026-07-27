"""
IRS Private Letter Rulings metadata extraction helpers.

IRSPLR rows enter the queue under the umbrella FDIRSPLR court code, but the
IRT form should be routed under either FDPLR000 or FDCCA001 based on the PDF
content.
"""

from __future__ import annotations

import datetime
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .mspb_extractor import extract_text_from_pdf_bytes


IRSPLR_QUEUE_CODE = "FDIRSPLR"
IRSPLR_OUTPUT_COURTS = {"FDPLR000", "FDCCA001"}
IRSPLR_ALL_COURTS = {IRSPLR_QUEUE_CODE, *IRSPLR_OUTPUT_COURTS}
IRSPLR_EXCLUDED_DOCKET = "NO NUMBER IN ORIGINAL"


@dataclass(frozen=True)
class IRSPLRMetadata:
    court: str
    docket_number: str
    decision_date: str
    source_detail: str
    other_numbers: tuple[str, ...] = ()
    comments_text: str = ""
    title_hint: str = ""
    has_text_content: bool = False
    is_excluded: bool = False
    exclusion_reason: str = ""
    is_text_fallback: bool = False


def is_irsplr_court_code(court_code) -> bool:
    return str(court_code or "").strip().upper() in IRSPLR_ALL_COURTS


def is_irsplr_filename(file_name) -> bool:
    name = Path(str(file_name or "")).name.lower()
    return bool(re.match(r"^(?:ldc_bc_)?(?:\d{2}[-_]\d+|\d{4,9}).*\.pdf$", name))


def is_irsplr_row(row) -> bool:
    court_code = ""
    file_name = ""
    try:
        court_code = row.get("CourtCode", row.get("Court Code", ""))
        file_name = row.get("FileName", row.get("File Name", ""))
    except AttributeError:
        pass
    return is_irsplr_court_code(court_code) or is_irsplr_filename(file_name)


def build_irsplr_unreadable_fallback_metadata(
    filename_hint: Optional[str] = None,
    court_code_hint: Optional[str] = None,
) -> IRSPLRMetadata:
    """Build minimal metadata only to let the router inspect an existing IRT form."""
    is_excluded, exclusion_reason = classify_irsplr_exclusion(filename_hint)
    court_hint = str(court_code_hint or "").strip().upper()
    court = court_hint if court_hint in IRSPLR_OUTPUT_COURTS else "FDPLR000"
    return IRSPLRMetadata(
        court=court,
        docket_number=IRSPLR_EXCLUDED_DOCKET if is_excluded else "",
        decision_date="",
        source_detail="Excluded" if is_excluded else "Letter",
        comments_text=format_irsplr_comments(exclusion_reason),
        title_hint="Unreadable PDF fallback",
        has_text_content=False,
        is_excluded=is_excluded,
        exclusion_reason=exclusion_reason,
        is_text_fallback=True,
    )


def parse_irsplr_pdf_bytes(
    pdf_bytes: bytes,
    filename_hint: Optional[str] = None,
    court_code_hint: Optional[str] = None,
    use_ocr_fallback: bool = True,
) -> Optional[IRSPLRMetadata]:
    text = extract_text_from_pdf_bytes(pdf_bytes, use_ocr_fallback=use_ocr_fallback)
    if not text.strip():
        logging.warning("IRSPLR PDF text extraction returned no text.")
    return parse_irsplr_document_text(
        text,
        filename_hint=filename_hint,
        court_code_hint=court_code_hint,
    )


def parse_irsplr_document_text(
    text: str,
    filename_hint: Optional[str] = None,
    court_code_hint: Optional[str] = None,
) -> Optional[IRSPLRMetadata]:
    if not text or not text.strip():
        return None

    normalized_text = normalize_irsplr_text(text)
    has_text_content = bool(_content_fingerprint_ready(normalized_text))
    if not has_text_content:
        logging.warning("IRSPLR text is too short to classify safely.")
        return None

    is_excluded, exclusion_reason = classify_irsplr_exclusion(filename_hint)
    court = classify_irsplr_court(normalized_text, court_code_hint=court_code_hint)
    source_detail = "Excluded" if is_excluded else "Letter"
    docket_number = IRSPLR_EXCLUDED_DOCKET if is_excluded else extract_irsplr_number(normalized_text)
    decision_date = (
        extract_irsplr_issue_date(normalized_text)
        if is_excluded
        else extract_irsplr_decision_date(normalized_text)
    )

    if not court or not docket_number or not decision_date or not source_detail:
        logging.warning(
            "Incomplete IRSPLR metadata: court=%s docket=%s decision_date=%s source_detail=%s",
            court,
            docket_number,
            decision_date,
            source_detail,
        )
        return None

    return IRSPLRMetadata(
        court=court,
        docket_number=docket_number,
        decision_date=decision_date,
        source_detail=source_detail,
        comments_text=format_irsplr_comments(exclusion_reason),
        title_hint=find_irsplr_title_hint(normalized_text),
        has_text_content=has_text_content,
        is_excluded=is_excluded,
        exclusion_reason=exclusion_reason,
    )


def classify_irsplr_exclusion(filename_hint: Optional[str]) -> tuple[bool, str]:
    name = Path(str(filename_hint or "")).name
    name_lower = name.lower()
    if "idx" in name_lower:
        return True, "Filename contains idx"
    if "-" in name:
        return True, "Filename contains hyphen"
    return False, ""


def classify_irsplr_court(text: str, court_code_hint: Optional[str] = None) -> str:
    header_lines = _clean_lines(text)[:80]
    header = "\n".join(header_lines)
    normalized_header = re.sub(r"\s+", " ", header.upper())
    normalized_lines = [re.sub(r"\s+", " ", line.upper()).strip(" .:;-") for line in header_lines]

    if re.search(r"\bID\s*:\s*CCA[_\-\s]*\d{8,}\b", normalized_header):
        return "FDCCA001"
    if re.search(r"\bCCA[_\-\s]*\d{8,}\b", normalized_header):
        return "FDCCA001"
    if re.search(r"\bOFFICE\s+OF\s+CHIEF\s+COUNSEL\b", normalized_header):
        return "FDCCA001"
    if any(line in {"CHIEF COUNSEL ADVICE", "OFFICE OF CHIEF COUNSEL"} for line in normalized_lines):
        return "FDCCA001"
    return "FDPLR000"


def extract_irsplr_number(text: str) -> Optional[str]:
    for pattern in (
        r"(?im)^\s*(?:Release\s+Number|Number)\s*:\s*(\d{9})\b",
        r"(?im)^\s*ID\s*:\s*(?:PLR|TAM|CCA)[_\-\s]*(\d{9})\b",
    ):
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return None


def extract_irsplr_decision_date(text: str) -> Optional[str]:
    lines = _clean_lines(text)
    saw_blank_date_label = False
    for index, line in enumerate(lines[:160]):
        normalized = re.sub(r"\s+", " ", line).strip()
        if re.search(r"(?i)\bRelease\s+Date\s*:", normalized):
            continue
        if re.match(r"(?i)^Date\s*:\s*$", normalized):
            saw_blank_date_label = True
            for candidate in lines[index + 1 : index + 4]:
                date_value = _extract_date_value(candidate)
                if date_value:
                    return date_value
        match = re.match(r"(?i)^Date\s*:\s*(.+)$", normalized)
        if match:
            date_value = _extract_date_value(match.group(1))
            if date_value:
                return date_value
            saw_blank_date_label = True
        match = re.search(r"(?i)\bDate\s*:\s*(.*)$", normalized)
        if match:
            date_value = _extract_date_value(match.group(1))
            if date_value:
                return date_value
            saw_blank_date_label = True
            for candidate in lines[index + 1 : index + 4]:
                if re.search(r"(?i)\bRelease\s+Date\s*:", candidate):
                    continue
                date_value = _extract_date_value(candidate)
                if date_value:
                    return date_value

    header_date = extract_irsplr_standalone_header_date(text)
    if header_date:
        return header_date

    sent_date = extract_irsplr_sent_date(text)
    if sent_date:
        return sent_date

    if saw_blank_date_label:
        release_date = extract_irsplr_release_date(text)
        if release_date:
            logging.warning(
                "IRSPLR Date field appears blank/redacted; using Release Date as a last-resort decision date fallback."
            )
            return release_date

    return None


def extract_irsplr_standalone_header_date(text: str) -> Optional[str]:
    """Find IRSPLR dates printed as a standalone header line away from the Date label."""
    lines = _clean_lines(text)
    for index, line in enumerate(lines[:80]):
        normalized = re.sub(r"\s+", " ", line).strip()
        if not _extract_date_value(normalized):
            continue
        if re.search(r"(?i)\b(?:Release\s+Date|Date\s+of\s+Communication|Tax\s+periods?\s+ended)\b", normalized):
            continue

        nearby = " ".join(lines[max(0, index - 4) : min(len(lines), index + 8)])
        if re.search(
            r"(?i)\b(?:Third\s+Party\s+Communication|Person\s+To\s+Contact|Refer\s+Reply\s+To|PLR[-\s]|\bDate\s*:|Dear\b)",
            nearby,
        ):
            return _extract_date_value(normalized)

    return None


def extract_irsplr_release_date(text: str) -> Optional[str]:
    match = re.search(r"(?im)^\s*Release\s+Date\s*:\s*([^\n]+)$", text)
    if match:
        return _extract_date_value(match.group(1))
    return None


def extract_irsplr_sent_date(text: str) -> Optional[str]:
    match = re.search(
        r"(?im)^\s*Sent\s*:\s*(?:[A-Za-z]+,\s*)?([A-Za-z]+\s+\d{1,2},\s+\d{4})",
        text,
    )
    if match:
        return normalize_irsplr_date(match.group(1))
    return None


def extract_irsplr_issue_date(text: str) -> Optional[str]:
    for pattern in (
        r"(?im)^\s*Issue\s*:\s*([^\n]+)$",
        r"(?im)^\s*Date\s*:\s*([^\n]+)$",
    ):
        match = re.search(pattern, text)
        if match:
            date_value = _extract_date_value(match.group(1))
            if date_value:
                return date_value
    return extract_irsplr_decision_date(text)


def format_irsplr_comments(exclusion_reason: str = "") -> str:
    if not exclusion_reason:
        return ""
    return f"Exclude - {exclusion_reason}"


def find_irsplr_title_hint(text: str) -> str:
    lines = _clean_lines(text)
    header = "\n".join(lines[:20])
    if re.search(r"\bCCA[_\-\s]*\d{8,}\b", header, re.IGNORECASE):
        return "CCA"
    if re.search(r"\bPublication\s+1078\b|\bSection\s+6110\s+Index\b", header, re.IGNORECASE):
        return "IRSPLR Index"
    if re.search(r"\bPrivate\s+Letter\s+Ruling\b|\bPLR-", header, re.IGNORECASE):
        return "Private Letter Ruling"
    return lines[0][:160] if lines else ""


def normalize_irsplr_date(raw_date: str) -> Optional[str]:
    cleaned = re.sub(r"\s+", " ", str(raw_date or "").strip().rstrip(".,;"))
    for fmt in (
        "%B %d, %Y",
        "%b %d, %Y",
        "%m/%d/%Y",
        "%m/%d/%y",
        "%m-%d-%Y",
        "%m-%d-%y",
    ):
        try:
            return datetime.datetime.strptime(cleaned, fmt).strftime("%m-%d-%Y")
        except ValueError:
            continue
    return None


def normalize_irsplr_text(text) -> str:
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


def _extract_date_value(value: str) -> Optional[str]:
    date_pattern = (
        r"(?:[A-Za-z]+\s+\d{1,2},\s+\d{4}|"
        r"\d{1,2}[-/]\d{1,2}[-/]\d{2,4})"
    )
    match = re.search(date_pattern, str(value or ""), re.IGNORECASE)
    return normalize_irsplr_date(match.group(0)) if match else None


def _clean_lines(text: str) -> list[str]:
    return [line.strip() for line in normalize_irsplr_text(text).splitlines() if line.strip()]


def _content_fingerprint_ready(text: str) -> bool:
    compact = re.sub(r"[^A-Za-z0-9]+", "", text or "")
    return len(compact) >= 100
