"""Maine Workers' Compensation Board metadata extraction helpers."""

from __future__ import annotations

import datetime
import hashlib
import logging
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .mspb_extractor import extract_text_from_pdf_bytes


MEWORK_COURT_CODE = "STMEWORK"
MEWORK_FINDINGS_SOURCE_DETAIL = "Reports and Recommendations/Finding of Facts/Conclusion of Law"


@dataclass(frozen=True)
class MEWORKMetadata:
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
    used_filename_date_fallback: bool = False


def is_mework_court_code(court_code) -> bool:
    return str(court_code or "").strip().upper() == MEWORK_COURT_CODE


def is_mework_filename(file_name) -> bool:
    name = Path(str(file_name or "")).name
    return bool(
        re.match(
            r"^[A-Za-z][A-Za-z' -]*_[A-Za-z][A-Za-z' _-]*\d{8}(?:dec(?:am\d*)?|fof|con(?:am)?|rem)\.pdf$",
            name,
            re.IGNORECASE,
        )
    )


def is_mework_row(row) -> bool:
    court_code = ""
    file_name = ""
    try:
        court_code = row.get("CourtCode", row.get("Court Code", ""))
        file_name = row.get("FileName", row.get("File Name", ""))
    except AttributeError:
        pass
    # The surname/date filename convention overlaps other courts. Court code is
    # the only safe row-level discriminator for this mode.
    return is_mework_court_code(court_code)


def parse_mework_pdf_bytes(
    pdf_bytes: bytes,
    filename_hint: Optional[str] = None,
    use_ocr_fallback: bool = True,
) -> Optional[MEWORKMetadata]:
    text = extract_text_from_pdf_bytes(pdf_bytes, use_ocr_fallback=use_ocr_fallback)
    if not text.strip():
        logging.warning("MEWORK PDF text extraction returned no text.")
    return parse_mework_document_text(text, filename_hint=filename_hint)


def parse_mework_document_text(text: str, filename_hint: Optional[str] = None) -> Optional[MEWORKMetadata]:
    normalized_text = normalize_mework_text(text)
    case_numbers, wcb_numbers = extract_mework_header_numbers(normalized_text)
    all_numbers = _unique(case_numbers + wcb_numbers)
    docket_number = case_numbers[0] if case_numbers else (wcb_numbers[0] if wcb_numbers else None)
    other_numbers = tuple(number for number in all_numbers if number != docket_number)

    decision_date = extract_mework_decision_date(normalized_text)
    used_filename_date_fallback = False
    if not decision_date:
        decision_date = extract_mework_date_from_filename(filename_hint)
        used_filename_date_fallback = bool(decision_date)

    title_hint = find_mework_title_hint(normalized_text)
    exclusion_reason = classify_mework_exclusion(title_hint)
    source_detail = classify_mework_source_detail(title_hint, exclusion_reason)
    content_fingerprint = compute_mework_content_fingerprint(normalized_text)

    if not docket_number or not decision_date or not source_detail:
        logging.warning(
            "Incomplete MEWORK metadata: court=%s docket=%s decision_date=%s source_detail=%s",
            MEWORK_COURT_CODE,
            docket_number,
            decision_date,
            source_detail,
        )
        return None

    return MEWORKMetadata(
        court=MEWORK_COURT_CODE,
        docket_number=docket_number,
        decision_date=decision_date,
        source_detail=source_detail,
        other_numbers=other_numbers,
        comments_text=format_mework_comments(other_numbers, exclusion_reason),
        title_hint=title_hint,
        content_fingerprint=content_fingerprint,
        has_text_content=bool(normalized_text.strip()),
        is_excluded=bool(exclusion_reason),
        exclusion_reason=exclusion_reason,
        used_filename_date_fallback=used_filename_date_fallback,
    )


def extract_mework_header_numbers(text: str) -> tuple[list[str], list[str]]:
    """Return Case# values and WCB values from the first-page header only."""
    lines = _clean_lines(text)[:120]
    case_numbers: list[str] = []
    wcb_numbers: list[str] = []

    for index, line in enumerate(lines):
        if _header_has_ended(line):
            break
        if re.search(r"(?i)\bCASE\s*(?:#|NO\.?|NUMBER)\s*:?", line):
            block = _labeled_number_block(lines, index, "case")
            case_numbers.extend(_extract_docket_candidates(block))
        if re.search(r"(?i)\bWCB\s*(?:FILE\s+)?(?:#|N\.?|NO\.?)?\s*:?\s*#?", line):
            block = _labeled_number_block(lines, index, "wcb")
            wcb_numbers.extend(_extract_docket_candidates(_remove_injury_dates(block)))

    return _unique(case_numbers), _unique(wcb_numbers)


def extract_mework_decision_date(text: str) -> Optional[str]:
    if not text:
        return None
    date_pattern = _date_pattern()
    patterns = (
        rf"(?im)^\s*Dated\s*:\s*({date_pattern})",
        rf"(?im)^\s*(?:Issuance\s+Date|Date\s+Issued)\s*:\s*({date_pattern})",
        rf"(?im)^\s*(?:Mail\s+Date|Date\s+Mailed)\s*:\s*({date_pattern})",
    )
    for pattern in patterns:
        matches = list(re.finditer(pattern, text))
        for match in reversed(matches):
            normalized = normalize_mework_date(match.group(1))
            if normalized:
                return normalized
    return None


def extract_mework_date_from_filename(file_name) -> Optional[str]:
    name = Path(str(file_name or "")).name
    matches = re.findall(r"(?<!\d)(\d{8})(?!\d)", name)
    for digits in reversed(matches):
        try:
            return datetime.datetime.strptime(digits, "%m%d%Y").strftime("%m-%d-%Y")
        except ValueError:
            continue
    return None


def find_mework_title_hint(text: str) -> str:
    """Find an operative title without treating incidental body text as a document type."""
    heading_candidates = []
    for line in _clean_lines(text)[:180]:
        label = _normalize_label(line)
        if not label or len(label) > 120:
            continue
        if _looks_like_heading(line):
            heading_candidates.append(label)

    # Specific operative headings outrank a generic DECISION or ORDER label
    # that may appear earlier on the first page.
    for label in heading_candidates:
        if label == "AMENDED CONSENT DECREE":
            return "Amended Consent Decree"
        if label == "CONSENT DECREE":
            return "Consent Decree"
        if "CORRECTION FOR CLERICAL ERROR" in label or "CORRECT CLERICAL ERROR" in label:
            return "Correction for Clerical Error"
        if label == "DECREE":
            return "Decree"
    for label in heading_candidates:
        if re.fullmatch(r"FURTHER\s+FINDINGS\s+OF\s+FACT(?:S)?\s+AND\s+CONCLUSIONS\s+OF\s+LAW", label):
            return "Further Findings of Fact and Conclusions of Law"
        if re.fullmatch(r"FINDINGS\s+OF\s+FACT(?:S)?\s+AND\s+CONCLUSIONS\s+OF\s+LAW", label):
            return "Findings of Fact and Conclusions of Law"
    for label in heading_candidates:
        if label in {"ORDER", "DECISION", "OPINION", "DECISION AND ORDER"}:
            return label.title()
    return "Decision"


def classify_mework_exclusion(title_hint: str) -> str:
    label = _normalize_label(title_hint)
    if label == "AMENDED CONSENT DECREE":
        return "Amended Consent Decree"
    if label == "CONSENT DECREE":
        return "Consent Decree"
    if "CORRECTION FOR CLERICAL ERROR" in label or "CORRECT CLERICAL ERROR" in label:
        return "Correction for Clerical Error"
    if label == "DECREE":
        return "Decree"
    return ""


def classify_mework_source_detail(title_hint: str, exclusion_reason: str = "") -> str:
    if exclusion_reason:
        return "Excluded"
    label = _normalize_label(title_hint)
    if "FURTHER FINDINGS OF FACT" in label:
        return MEWORK_FINDINGS_SOURCE_DETAIL
    if label in {"ORDER", "DECISION AND ORDER"}:
        return "Order"
    return "Opinion"


def format_mework_comments(other_numbers, exclusion_reason: str = "") -> str:
    parts = []
    if exclusion_reason:
        parts.append(f"Exclude - {exclusion_reason}")
    parts.extend(str(number).strip() for number in other_numbers if str(number).strip())
    return "; ".join(_unique(parts))


def compute_mework_content_fingerprint(text: str) -> str:
    normalized = re.sub(r"[^A-Z0-9]+", "", normalize_mework_text(text).upper())
    if len(normalized) < 500:
        return ""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def normalize_mework_date(raw_date: str) -> Optional[str]:
    cleaned = re.sub(r"\s+", " ", normalize_mework_text(raw_date).strip().rstrip(".,;"))
    for fmt in (
        "%B %d, %Y", "%b %d, %Y", "%m/%d/%Y", "%m/%d/%y",
        "%m-%d-%Y", "%m-%d-%y",
    ):
        try:
            return datetime.datetime.strptime(cleaned, fmt).strftime("%m-%d-%Y")
        except ValueError:
            continue
    return None


def normalize_mework_text(text) -> str:
    value = unicodedata.normalize("NFKC", str(text or ""))
    return (
        value.replace("\u00a0", " ")
        .replace("\u200b", "")
        .replace("\ufeff", "")
        .replace("\u2010", "-")
        .replace("\u2011", "-")
        .replace("\u2012", "-")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u2212", "-")
        .replace("�", "'")
    )


def _labeled_number_block(lines: list[str], index: int, label_type: str) -> str:
    block = [lines[index]]
    for following in lines[index + 1 : index + 5]:
        if re.search(r"(?i)\b(?:CASE|WCB|RE|ISSUANCE|DATE\s+ISSUED|MAIL\s+DATE|DATE\s+MAILED)\b\s*(?:#|:)", following):
            break
        if _header_has_ended(following):
            break
        if label_type == "case" and not re.match(r"^\s*[#A-Z0-9]", following):
            break
        block.append(following)
    return " ".join(block)


def _extract_docket_candidates(text: str) -> list[str]:
    cleaned = normalize_mework_text(text).upper()
    cleaned = re.sub(
        r"(?i)\b(?:CASE|WCB)\s*(?:FILE\s+)?(?:#|N\.?|NO\.?|NUMBER)?\s*:?\s*#?",
        " ",
        cleaned,
    )
    candidates = []
    pattern = r"(?<![A-Z0-9])#?((?:\d{1,2}-){1,3}\d{2,8}[A-Z]?|\d{7,8}[A-Z]?)(?![A-Z0-9/])"
    for match in re.finditer(pattern, cleaned):
        value = match.group(1).strip("- ")
        if _looks_like_calendar_date(value):
            continue
        candidates.append(value)
    return _unique(candidates)


def _remove_injury_dates(text: str) -> str:
    return re.sub(
        r"(?i)(?:DOI|DOE|DATE\s+OF\s+INJURY)\s*:?\s*\d{1,2}[/-]\d{1,2}[/-]\d{2,4}",
        " ",
        text,
    )


def _looks_like_calendar_date(value: str) -> bool:
    if not re.fullmatch(r"\d{1,2}-\d{1,2}-\d{2,4}", value):
        return False
    month, day, _year = (int(part) for part in value.split("-"))
    return 1 <= month <= 12 and 1 <= day <= 31


def _header_has_ended(line: str) -> bool:
    label = _normalize_label(line)
    return bool(
        label.startswith("WITHIN 25 DAYS")
        or label.startswith("WITHIN 20 DAYS")
        or label.startswith("PENDING BEFORE")
    )


def _looks_like_heading(line: str) -> bool:
    letters = [character for character in line if character.isalpha()]
    if not letters:
        return False
    uppercase_ratio = sum(character.isupper() for character in letters) / len(letters)
    return uppercase_ratio >= 0.72 or len(line.split()) <= 4


def _normalize_label(text: str) -> str:
    label = re.sub(r"[^A-Z0-9]+", " ", normalize_mework_text(text).upper())
    return re.sub(r"\s+", " ", label).strip()


def _date_pattern() -> str:
    return r"(?:[A-Za-z]+\s+\d{1,2},\s+\d{4}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})"


def _clean_lines(text: str) -> list[str]:
    return [line.strip() for line in normalize_mework_text(text).splitlines() if line.strip()]


def _unique(values) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
