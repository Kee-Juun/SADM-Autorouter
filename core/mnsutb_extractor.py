"""
Minnesota Supreme Court metadata extraction helpers for MNSUTB.

MNSUTB documents in the current samples are Minnesota Supreme Court orders.
The IRT court is already provided by inventory; STMNSUTB is retained here for
documentation and metadata reporting.
"""

from __future__ import annotations

import datetime
import logging
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .mspb_extractor import extract_text_from_pdf_bytes


MNSUTB_COURT_CODE = "STMNSUTB"
MNSUTB_SOURCE_DETAIL = "Table-(5-day spec source)"


@dataclass(frozen=True)
class MNSUTBMetadata:
    court: str
    docket_number: str
    decision_date: str
    source_detail: str
    other_numbers: tuple[str, ...] = ()
    comments_text: str = ""
    title_hint: str = ""
    has_text_content: bool = False


def is_mnsutb_court_code(court_code) -> bool:
    return str(court_code or "").strip().upper() == MNSUTB_COURT_CODE


def is_mnsutb_filename(file_name) -> bool:
    name = normalize_mnsutb_text(Path(str(file_name or "")).name).lower()
    return bool(re.match(r"^ldc_smd_a\d{2}-\d{4,6}.*\.pdf$", name))


def is_mnsutb_row(row) -> bool:
    court_code = ""
    file_name = ""
    try:
        court_code = row.get("CourtCode", row.get("Court Code", ""))
        file_name = row.get("FileName", row.get("File Name", ""))
    except AttributeError:
        pass
    return is_mnsutb_court_code(court_code) or is_mnsutb_filename(file_name)


def parse_mnsutb_pdf_bytes(
    pdf_bytes: bytes,
    filename_hint: Optional[str] = None,
    use_ocr_fallback: bool = True,
) -> Optional[MNSUTBMetadata]:
    text = extract_text_from_pdf_bytes(pdf_bytes, use_ocr_fallback=use_ocr_fallback)
    if not text.strip():
        logging.warning("MNSUTB PDF text extraction returned no text.")
        return None
    return parse_mnsutb_document_text(text, filename_hint=filename_hint)


def parse_mnsutb_document_text(text: str, filename_hint: Optional[str] = None) -> Optional[MNSUTBMetadata]:
    if not text or not text.strip():
        return None

    normalized_text = normalize_mnsutb_text(text)
    has_text_content = bool(_content_fingerprint_ready(normalized_text))
    docket_numbers = extract_mnsutb_header_dockets(normalized_text)
    docket_number = docket_numbers[0] if docket_numbers else extract_mnsutb_docket_from_filename(filename_hint)
    other_numbers = tuple(number for number in docket_numbers[1:] if number != docket_number)
    decision_date = extract_mnsutb_decision_date(normalized_text)
    title_hint = find_mnsutb_title_hint(normalized_text)
    source_detail = classify_mnsutb_source_detail(title_hint)

    if not docket_number or not decision_date or not source_detail:
        logging.warning(
            "Incomplete MNSUTB metadata: court=%s docket=%s decision_date=%s source_detail=%s",
            MNSUTB_COURT_CODE,
            docket_number,
            decision_date,
            source_detail,
        )
        return None

    return MNSUTBMetadata(
        court=MNSUTB_COURT_CODE,
        docket_number=docket_number,
        decision_date=decision_date,
        source_detail=source_detail,
        other_numbers=other_numbers,
        comments_text=format_mnsutb_comments(other_numbers),
        title_hint=title_hint,
        has_text_content=has_text_content,
    )


def extract_mnsutb_header_dockets(text: str) -> list[str]:
    lines = _clean_lines(text)
    dockets: list[str] = []

    for line in lines[:25]:
        line_dockets = _extract_header_line_dockets(line)
        if line_dockets:
            dockets.extend(line_dockets)
            continue
        if dockets:
            break

    return list(dict.fromkeys(dockets))


def extract_mnsutb_docket_from_filename(file_name) -> Optional[str]:
    name = normalize_mnsutb_text(Path(str(file_name or "")).name)
    match = re.search(r"\b(A\d{2}-\d{4,6})\b", name, re.IGNORECASE)
    return _normalize_mnsutb_docket(match.group(1)) if match else None


def extract_mnsutb_decision_date(text: str) -> Optional[str]:
    match = re.search(r"(?im)^\s*Dated\s*:\s*([^\n]+)$", text)
    if match:
        return _extract_date_value(match.group(1))
    return None


def find_mnsutb_title_hint(text: str) -> str:
    for line in _clean_lines(text)[:80]:
        normalized = re.sub(r"\s+", "", line).upper().strip(" .:-")
        if normalized == "ORDER":
            return "Order"
    return ""


def classify_mnsutb_source_detail(title_hint: str) -> Optional[str]:
    if re.sub(r"\s+", " ", str(title_hint or "")).strip().upper() == "ORDER":
        return MNSUTB_SOURCE_DETAIL
    return None


def format_mnsutb_comments(other_numbers) -> str:
    numbers = [str(number).strip() for number in other_numbers if str(number).strip()]
    return "; ".join(dict.fromkeys(numbers))


def normalize_mnsutb_date(raw_date: str) -> Optional[str]:
    cleaned = re.sub(r"\s+", " ", normalize_mnsutb_text(raw_date).strip().rstrip(".,;"))
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
    logging.warning("Could not normalize MNSUTB date: %s", raw_date)
    return None


def _extract_date_value(value: str) -> Optional[str]:
    match = re.search(
        r"(?:[A-Za-z]+\s+\d{1,2},\s+\d{4}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
        normalize_mnsutb_text(value),
        re.IGNORECASE,
    )
    return normalize_mnsutb_date(match.group(0)) if match else None


def normalize_mnsutb_text(text) -> str:
    value = unicodedata.normalize("NFKC", str(text or ""))
    return (
        value.replace("\u00a0", " ")
        .replace("\u200b", "")
        .replace("\u200c", "")
        .replace("\u200d", "")
        .replace("\ufeff", "")
        .replace("\u2010", "-")
        .replace("\u2011", "-")
        .replace("\u2012", "-")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u2212", "-")
    )


def _normalize_mnsutb_docket(value: str) -> Optional[str]:
    normalized = normalize_mnsutb_text(value).upper()
    normalized = re.sub(r"\s+", "", normalized)
    match = re.fullmatch(r"A(\d{2})-(\d{4,6})", normalized)
    if not match:
        return None
    return f"A{match.group(1)}-{match.group(2)}"


def _extract_header_line_dockets(line: str) -> list[str]:
    normalized = normalize_mnsutb_text(line).upper()
    matches = re.findall(r"A\s*(\d{2})\s*-\s*(\d{4,6})", normalized)
    if not matches:
        return []

    remainder = re.sub(r"A\s*\d{2}\s*-\s*\d{4,6}", " ", normalized)
    remainder = re.sub(r"\b(?:CASE|NO|NOS|NUMBER|NUMBERS|FILE|DOCKET)\b", " ", remainder)
    remainder = re.sub(r"[\s,;/&()#.:_-]+", "", remainder)
    if remainder:
        return []

    return [f"A{year}-{number}" for year, number in matches]


def _clean_lines(text: str) -> list[str]:
    return [line.strip() for line in normalize_mnsutb_text(text).splitlines() if line.strip()]


def _content_fingerprint_ready(text: str) -> bool:
    compact = re.sub(r"[^A-Za-z0-9]+", "", text or "")
    return len(compact) >= 100
