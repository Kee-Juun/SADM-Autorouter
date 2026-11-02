"""Metadata extraction and routing classification for FCC (FDFCC000) documents.

The FCC controller uses the release number in the document header as the
primary docket, and the *Released* date as the decision date.  This module
intentionally classifies from the first-page heading only; words such as
"erratum" and "order" in a citation or the body must never alter routing.
"""

from __future__ import annotations

import datetime as _datetime
import io
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .mspb_extractor import extract_text_from_pdf_bytes


FCC_COURT_CODE = "FDFCC000"
NO_NUMBER_IN_ORIGINAL = "NO NUMBER IN ORIGINAL"


@dataclass(frozen=True)
class FCCMetadata:
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
    requires_review: bool = False
    review_status: str = ""


def is_fcc_row(row) -> bool:
    try:
        value = row.get("CourtCode", row.get("Court Code", ""))
    except AttributeError:
        value = ""
    return str(value or "").strip().upper() == FCC_COURT_CODE


def parse_fcc_pdf_bytes(pdf_bytes: bytes, filename_hint: Optional[str] = None, use_ocr_fallback: bool = True) -> Optional[FCCMetadata]:
    # FCC's controlling header and title are on page one.  Reading only that
    # page prevents a cited decision, erratum, or order deeper in the PDF from
    # changing classification.  Fall back to the shared extractor for damaged
    # or image-only PDFs, where its OCR path is needed.
    try:
        from pypdf import PdfReader

        first_page_text = PdfReader(io.BytesIO(pdf_bytes)).pages[0].extract_text() or ""
        if first_page_text.strip():
            return parse_fcc_document_text(first_page_text, filename_hint=filename_hint)
    except Exception:
        pass
    return parse_fcc_document_text(
        extract_text_from_pdf_bytes(pdf_bytes, use_ocr_fallback=use_ocr_fallback),
        filename_hint=filename_hint,
    )


def parse_fcc_document_text(text: str, filename_hint: Optional[str] = None) -> Optional[FCCMetadata]:
    normalized = normalize_fcc_text(text)
    if not normalized.strip():
        return None

    lines = _clean_lines(normalized)
    header = "\n".join(lines[:150])
    # Petition/Court exclusions are determined from the visible header/title,
    # never from a later application description in the document body.
    classification_header = "\n".join(lines[:18])
    title = find_fcc_title_hint(header)
    upper_title = _label(title)
    is_errata = bool(re.search(r"\bERRAT(?:A|UM)\b", upper_title))
    is_attachment = bool(re.search(r"\b(?:ATTACHMENT|EXHIBIT|APPENDIX)\b", upper_title))

    # Errata and its attachments are deliberately stopped before IRT.  This
    # avoids treating specialist Webstar work as an ordinary FCC document.
    if is_errata:
        review_status = "ERRATA FOR REVIEW"
    elif is_attachment:
        review_status = "ATTACHMENT FOR REVIEW"
    else:
        review_status = ""

    exclusion_reason = classify_fcc_exclusion(classification_header, upper_title)
    source_detail = classify_fcc_source_detail(upper_title, exclusion_reason)
    docket = (
        extract_fcc_primary_docket(header)
        or extract_daily_digest_docket(header)
        or extract_fcc_publication_number(header)
        or NO_NUMBER_IN_ORIGINAL
    )
    decision_date = extract_fcc_release_date(header)
    other_numbers = tuple(item for item in extract_fcc_other_numbers(header) if _label(item) != _label(docket))

    if not decision_date:
        # A missing release/publish date cannot safely be invented from a
        # collection filename.  Retain extracted metadata for audit and halt.
        review_status = review_status or "NEEDS REVIEW"

    comment_parts = []
    if exclusion_reason:
        comment_parts.append(f"Exclude - {exclusion_reason}")
    comment_parts.extend(other_numbers)
    return FCCMetadata(
        court=FCC_COURT_CODE,
        docket_number=docket,
        decision_date=decision_date or "",
        source_detail=source_detail,
        other_numbers=other_numbers,
        comments_text="; ".join(dict.fromkeys(comment_parts)),
        title_hint=title,
        has_text_content=True,
        is_excluded=bool(exclusion_reason),
        exclusion_reason=exclusion_reason,
        requires_review=bool(review_status),
        review_status=review_status,
    )


def classify_fcc_source_detail(title: str, exclusion_reason: str = "") -> str:
    if exclusion_reason:
        return "Excluded"
    if _looks_like_letter(title):
        return "Letter"
    # A substantive heading joined with "and Order" is an Opinion under the
    # FCC rule, even where historical rows called it an Order.
    if re.search(r"\b(?:DECISION|OPINION|REPORT|NOTICE|AUTHORIZATION|MEMORANDUM)\b.*\bAND\s+ORDER\b", title):
        return "Opinion"
    if "ORDER" in title:
        return "Order"
    return "Opinion"


def classify_fcc_exclusion(header: str, title: str) -> str:
    header_label = _label(header)
    # "Petition" routinely appears in the body of otherwise ordinary Public
    # Notices.  Only an operative title can make it an excluded petition.
    is_reconsideration_or_rehearing = bool(re.search(r"\b(?:RECONSIDERATION|REHEARING)\b", title))
    if re.search(r"\bPETITION(?:S)?\b", title) and not (
        is_reconsideration_or_rehearing and re.search(r"\b(?:ORDER|DECISION)\b", title)
    ):
        return "Petition"
    # FCC orders have "Federal Communications Commission" in their header;
    # court decisions do not.  Limit this test to the header to avoid quoted
    # cases in an FCC decision's body.
    if re.search(r"\b(?:UNITED STATES )?(?:DISTRICT COURT|COURT OF APPEALS|SUPREME COURT)\b", header_label) and "FEDERAL COMMUNICATIONS COMMISSION" not in header_label:
        return "Court Decision"
    return ""


def find_fcc_title_hint(header: str) -> str:
    lines = _clean_lines(header)
    candidates: list[str] = []
    for line in lines[:100]:
        label = _label(line)
        if not label or len(label) > 170 or _is_non_title_line(label):
            continue
        # Headings are normally all-caps in FCC PDFs. Preserve title-like lines
        # for letter and Daily Digest identification too.
        letters = [char for char in line if char.isalpha()]
        ratio = sum(char.isupper() for char in letters) / len(letters) if letters else 0
        if ratio >= .68 or re.search(r"(?i)^(?:Re:|Dear\s|Daily Digest)", line):
            candidates.append(re.sub(r"\s+", " ", line).strip())

    for candidate in candidates:
        if re.search(r"(?i)\bERRAT(?:A|UM)\b", candidate):
            return candidate
    for candidate in candidates:
        if re.search(r"(?i)\b(?:ATTACHMENT|EXHIBIT|APPENDIX)\b", candidate):
            return candidate
    for candidate in candidates:
        label = _label(candidate)
        if re.search(r"\b(?:DECISION|OPINION|REPORT|NOTICE|AUTHORIZATION|MEMORANDUM)\b.*\bAND\s+ORDER\b", label):
            return candidate
    for candidate in candidates:
        if re.search(r"\b(?:FINAL |PROTECTIVE |FORFEITURE )?ORDER\b", _label(candidate)):
            return candidate
    for candidate in candidates:
        if _looks_like_letter(_label(candidate)) or "DAILY DIGEST" in _label(candidate):
            return candidate
    return candidates[0] if candidates else ""


def extract_fcc_primary_docket(header: str) -> Optional[str]:
    # The release number appears in the upper-right FCC header, in either
    # "DA 26-1039" or "DA-26-1039" form.
    for match in re.finditer(r"\b(FCC|DA)\s*[- ]\s*(\d{2,4}(?:[A-Z]+)?[-–]\d{1,5}[A-Z]?)\b", header, re.I):
        return f"{match.group(1).upper()} {match.group(2).upper().replace('–', '-')}"
    return None


def extract_daily_digest_docket(header: str) -> Optional[str]:
    if "DAILY DIGEST" not in _label(header):
        return None
    match = re.search(r"(?i)\b(?:VOLUME|VOL\.)\s*(\d+)\s*[,;:-]?\s*(?:ISSUE|NO\.)\s*(\d+)", header)
    return f"Volume {match.group(1)}, Issue {match.group(2)}" if match else None


def extract_fcc_publication_number(header: str) -> Optional[str]:
    """Return a labeled Report/Publication number when no release number exists."""
    match = re.search(
        r"(?i)\b(REPORT|PUBLICATION)\s+NO\.?\s*([-A-Z0-9.]+)",
        header,
    )
    if not match:
        # A small set of FCC public notices use the reversed column order,
        # e.g. "20677Report Number:".  It is still a report number.
        reversed_match = re.search(r"(?im)(?:^|\n)\s*(\d{3,})\s*REPORT\s+NUMBER\s*:", header)
        return f"Report No. {reversed_match.group(1)}" if reversed_match else None
    return f"{match.group(1).title()} No. {match.group(2).upper()}"


def extract_fcc_other_numbers(header: str) -> list[str]:
    found: list[str] = []
    patterns = (
        r"\b((?:[A-Z]{2,3})\s+Docket\s+No\.?\s*[-A-Z0-9.]+)",
        r"\b((?:Report|Transmittal|File|Document|Application)\s+No\.?\s*[-A-Z0-9.]+)",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, header, re.I):
            value = re.sub(r"\s+", " ", match.group(1)).strip(" .;,")
            if value and value not in found:
                found.append(value)
    return found


def extract_fcc_release_date(header: str) -> Optional[str]:
    for pattern in (
        r"(?im)^\s*(?:Released|Release Date|Published|Publish Date)\s*:\s*([^\n]+)",
        # Some public-notice PDFs extract the header in visual-column order:
        # "PUBLISH DATE: REPORT NO. ... 10/13/2026".  Accept the date later
        # on that same header line instead of treating the document as missing
        # its decision date.
        r"(?im)\b(?:Released|Release Date|Published|Publish Date)\b[^\n]{0,120}?([A-Za-z]+\s+\d{1,2},\s*\d{4}|\d{1,2}/\d{1,2}/\d{2,4})",
        r"(?im)\b(?:Released|Release Date|Published|Publish Date)\s*[:\-]?\s*([A-Za-z]+\s+\d{1,2},\s*\d{4}|\d{1,2}/\d{1,2}/\d{2,4})",
        r"(?im)\bDate\s+of\s+Report\s*:\s*([A-Za-z]+\s+\d{1,2},\s*\d{4}|\d{1,2}/\d{1,2}/\d{2,4})",
        # Standard public-notice header: "Report No. XYZ Wednesday January 14, 2026".
        r"(?im)\b(?:Report|Publication)\s+No\.?\s*[-A-Z0-9.]+\s+(?:(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+)?([A-Za-z]+\s+\d{1,2},\s*\d{4})",
    ):
        match = re.search(pattern, header)
        if match:
            date = normalize_fcc_date(match.group(1))
            if date:
                return date
    return None


def normalize_fcc_date(value: str) -> Optional[str]:
    value = re.sub(r"\s+", " ", str(value or "").strip(" .;,"))
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y"):
        try:
            return _datetime.datetime.strptime(value, fmt).strftime("%m-%d-%Y")
        except ValueError:
            pass
    return None


def normalize_fcc_text(value: str) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).replace("\u00a0", " ").replace("\u2013", "-").replace("\u2014", "-")


def _clean_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _label(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9]+", " ", normalize_fcc_text(value).upper())).strip()


def _looks_like_letter(label: str) -> bool:
    # FCC public notices commonly use "RE:" for their subject line (for
    # example, Applications Accepted for Filing).  That is not a Letter.
    # Reserve LE for an actual letter salutation or an explicit LETTER title.
    return label.startswith("DEAR ") or "LETTER" in label


def _is_non_title_line(label: str) -> bool:
    return bool(re.search(r"^(?:FEDERAL COMMUNICATIONS COMMISSION|WASHINGTON|FCC|DA)\b", label) or re.search(r"\b(?:ADOPTED|RELEASED|BEFORE THE|DOCKET NO)\b", label))
