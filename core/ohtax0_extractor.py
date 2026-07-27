"""
Ohio Board of Tax Appeals metadata extraction helpers.

OHTAX0 rows are routed from the linked PDF itself. The controller instruction
uses the first-page CASE NO(S). value for docket and the Entered date for the
decision date.
"""

from __future__ import annotations

import datetime
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .mspb_extractor import extract_text_from_pdf_bytes


OHTAX0_COURT_CODE = "STOHTAX0"


@dataclass(frozen=True)
class OHTAX0Metadata:
    court: str
    docket_number: str
    decision_date: str
    source_detail: str
    other_numbers: tuple[str, ...] = ()
    comments_text: str = ""
    title_hint: str = ""
    has_text_content: bool = False
    is_excluded: bool = False


def is_ohtax0_court_code(court_code) -> bool:
    return str(court_code or "").strip().upper() == OHTAX0_COURT_CODE


def is_ohtax0_filename(file_name) -> bool:
    name = Path(str(file_name or "")).name.lower()
    return bool(re.match(r"^saq\d+_\d{4}_\d+.*\.pdf$", name))


def is_ohtax0_row(row) -> bool:
    court_code = ""
    file_name = ""
    try:
        court_code = row.get("CourtCode", row.get("Court Code", ""))
        file_name = row.get("FileName", row.get("File Name", ""))
    except AttributeError:
        pass
    return is_ohtax0_court_code(court_code) or is_ohtax0_filename(file_name)


def parse_ohtax0_pdf_bytes(
    pdf_bytes: bytes,
    filename_hint: Optional[str] = None,
    use_ocr_fallback: bool = True,
) -> Optional[OHTAX0Metadata]:
    text = extract_text_from_pdf_bytes(pdf_bytes, use_ocr_fallback=use_ocr_fallback)
    if not text.strip():
        logging.warning("OHTAX0 PDF text extraction returned no text.")
        return None
    return parse_ohtax0_document_text(text, filename_hint=filename_hint)


def parse_ohtax0_document_text(text: str, filename_hint: Optional[str] = None) -> Optional[OHTAX0Metadata]:
    if not text or not text.strip():
        return None

    normalized_text = normalize_ohtax0_text(text)
    has_text_content = bool(_content_fingerprint_ready(normalized_text))
    docket_numbers = extract_ohtax0_case_numbers(normalized_text)
    docket_number = docket_numbers[0] if docket_numbers else extract_ohtax0_case_number_from_filename(filename_hint)
    other_numbers = tuple(number for number in docket_numbers[1:] if number != docket_number)
    decision_date = extract_ohtax0_entered_date(normalized_text)
    title_hint = find_ohtax0_title_hint(normalized_text)
    source_detail = classify_ohtax0_source_detail(title_hint)

    if not docket_number or not decision_date or not source_detail:
        logging.warning(
            "Incomplete OHTAX0 metadata: court=%s docket=%s decision_date=%s source_detail=%s",
            OHTAX0_COURT_CODE,
            docket_number,
            decision_date,
            source_detail,
        )
        return None

    return OHTAX0Metadata(
        court=OHTAX0_COURT_CODE,
        docket_number=docket_number,
        decision_date=decision_date,
        source_detail=source_detail,
        other_numbers=other_numbers,
        comments_text=format_ohtax0_comments(other_numbers),
        title_hint=title_hint,
        has_text_content=has_text_content,
    )


def extract_ohtax0_case_numbers(text: str) -> list[str]:
    lines = _clean_lines(text)
    candidates: list[str] = []

    for index, line in enumerate(lines[:80]):
        if not re.search(r"(?i)\bCASE\s+NO(?:\(?S\)?)?\.?", line):
            continue

        search_text = line
        for following_line in lines[index + 1 : index + 35]:
            if re.search(r"(?i)\b(?:ORDER|DECISION|APPEARANCES|ENTERED)\b", following_line):
                break
            search_text += " " + following_line

        for docket in _extract_case_numbers_from_text(search_text):
            if docket not in candidates:
                candidates.append(docket)

        if candidates:
            return candidates

    return candidates


def extract_ohtax0_case_number_from_filename(file_name) -> Optional[str]:
    name = Path(str(file_name or "")).name
    match = re.search(r"_(\d{4})_(\d+)", name)
    if not match:
        return None
    return f"{match.group(1)}-{match.group(2)}"


def extract_ohtax0_entered_date(text: str) -> Optional[str]:
    match = re.search(
        r"(?i)\bEntered\s+(?:[A-Za-z]+,?\s+)?([A-Za-z]+\s+\d{1,2},\s+\d{4})",
        text,
    )
    if match:
        return normalize_ohtax0_date(match.group(1))
    return None


def classify_ohtax0_source_detail(title_hint: str) -> str:
    normalized = _normalize_label(title_hint)
    if normalized == "ORDER":
        return "Order"
    return "Opinion"


def find_ohtax0_title_hint(text: str) -> str:
    lines = _clean_lines(text)
    for index, line in enumerate(lines[:80]):
        if not re.search(r"(?i)\bCASE\s+NO(?:\(?S\)?)?\.?", line):
            continue

        title_lines = []
        for candidate in lines[index : index + 35]:
            if re.search(r"(?i)\b(?:APPEARANCES|ENTERED)\b", candidate):
                break
            cleaned = _strip_leading_case_number_block(candidate)
            if not cleaned:
                continue
            normalized = _normalize_label(cleaned)
            if not normalized or _looks_like_case_number_continuation(normalized):
                continue
            if normalized in {"ORDER", "DECISION AND ORDER", "DECISION"}:
                title_lines.append(normalized)
                break
            match = re.search(r"\b(DECISION\s+AND\s+ORDER|ORDER|DECISION)\b", normalized)
            if match:
                title_lines.append(match.group(1))
                break

        if title_lines:
            return title_lines[0]

    return ""


def format_ohtax0_comments(other_numbers) -> str:
    numbers = [str(number).strip() for number in other_numbers if str(number).strip()]
    return "; ".join(dict.fromkeys(numbers))


def normalize_ohtax0_date(raw_date: str) -> Optional[str]:
    cleaned = re.sub(r"\s+", " ", normalize_ohtax0_text(raw_date).strip().rstrip(".,;"))
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
    logging.warning("Could not normalize OHTAX0 date: %s", raw_date)
    return None


def normalize_ohtax0_text(text) -> str:
    return (
        str(text or "")
        .replace("\u00a0", " ")
        .replace("\u2010", "-")
        .replace("\u2011", "-")
        .replace("\u2012", "-")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u2212", "-")
    )


def _extract_case_numbers_from_text(text: str) -> list[str]:
    numbers = []
    for match in re.finditer(r"\b(\d{4}\s*-\s*\d{1,6})\b", normalize_ohtax0_text(text)):
        number = re.sub(r"\s+", "", match.group(1))
        if number not in numbers:
            numbers.append(number)
    return numbers


def _strip_leading_case_number_block(line: str) -> str:
    cleaned = re.sub(r"(?i)^.*?\bCASE\s+NO(?:\(?S\)?)?\.?\s*", "", line)
    cleaned = re.sub(r"^(?:\d{4}\s*-\s*\d{1,6}[\s,;/]*)+", "", cleaned)
    cleaned = re.sub(r"^\([^)]*\)\s*", "", cleaned)
    return cleaned.strip()


def _normalize_label(text: str) -> str:
    return re.sub(r"\s+", " ", normalize_ohtax0_text(text).upper()).strip(" .:-")


def _clean_lines(text: str) -> list[str]:
    return [line.strip() for line in normalize_ohtax0_text(text).splitlines() if line.strip()]


def _looks_like_case_number_continuation(text: str) -> bool:
    cleaned = re.sub(r"\([^)]*\)", "", normalize_ohtax0_text(text).upper())
    cleaned = re.sub(r"[\d\s,;/.-]", "", cleaned)
    return not cleaned


def _content_fingerprint_ready(text: str) -> bool:
    compact = re.sub(r"[^A-Za-z0-9]+", "", text or "")
    return len(compact) >= 100
