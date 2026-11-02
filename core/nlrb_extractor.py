"""Metadata extraction and conservative routing rules for NLRB (FDNLRB00).

NLRB filenames are not authoritative: a document may be collected under a
related case number while its caption identifies another primary case.  The
parser therefore reads the caption first, uses its first case number as the
primary docket, and preserves subsequent caption dockets in Comments.
"""

from __future__ import annotations

import datetime as _datetime
import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

from .mspb_extractor import extract_text_from_pdf_bytes


NLRB_COURT_CODE = "FDNLRB00"
_DOCKET_RE = re.compile(r"\b\d{1,2}\s*[-–]\s*[A-Z]{1,3}\s*[-–]\s*\d{3,6}\b", re.I)
_MONTH_DATE_RE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+\d{1,2},\s*\d{4}\b",
    re.I,
)


@dataclass(frozen=True)
class NLRBMetadata:
    court: str
    docket_number: str
    decision_date: str
    source_detail: str
    other_numbers: tuple[str, ...] = ()
    comments_text: str = ""
    title_hint: str = ""
    has_text_content: bool = False
    requires_review: bool = False
    review_status: str = ""


def is_nlrb_row(row) -> bool:
    try:
        value = row.get("CourtCode", row.get("Court Code", ""))
    except AttributeError:
        value = ""
    return str(value or "").strip().upper() == NLRB_COURT_CODE


def parse_nlrb_pdf_bytes(pdf_bytes: bytes, filename_hint: Optional[str] = None, use_ocr_fallback: bool = True) -> NLRBMetadata:
    """Read an NLRB PDF and always return a review-safe metadata result."""
    text = extract_text_from_pdf_bytes(pdf_bytes, use_ocr_fallback=use_ocr_fallback)
    return parse_nlrb_document_text(text, filename_hint=filename_hint)


def parse_nlrb_document_text(text: str, filename_hint: Optional[str] = None) -> NLRBMetadata:
    normalized = normalize_nlrb_text(text)
    lines = [line.strip() for line in normalized.splitlines() if line.strip()]
    if not lines:
        return _review_metadata("MANUAL REVIEW REQUIRED — DOCUMENT CONTENT UNREADABLE")

    header_lines = lines[:120]
    title = find_nlrb_title(header_lines)
    title_label = _heading_label(title)
    caption_text = _caption_text(header_lines)
    dockets = extract_nlrb_dockets(caption_text)
    # A transfer order can put its caption after the short order and signature
    # block.  Only when the ordinary pre-title caption has no docket do we
    # broaden the scan to the remaining first-page/header text.
    if not dockets:
        dockets = extract_nlrb_dockets("\n".join(header_lines))
    docket = dockets[0] if dockets else ""
    other_numbers = tuple(dockets[1:])
    decision_date = extract_nlrb_decision_date(normalized, header_lines)

    if _is_exhibit_or_attachment(header_lines, title_label):
        return NLRBMetadata(
            court=NLRB_COURT_CODE,
            docket_number=docket,
            decision_date=decision_date or "",
            source_detail="",
            other_numbers=other_numbers,
            comments_text="; ".join(other_numbers),
            title_hint=title,
            has_text_content=True,
            requires_review=True,
            review_status="MANUAL REVIEW REQUIRED — EXHIBIT / ATTACHMENT",
        )

    missing = []
    if not docket:
        missing.append("DOCKET NUMBER")
    if not decision_date:
        missing.append("DECISION DATE")
    if not title:
        missing.append("DOCUMENT TITLE / SOURCE DETAIL")
    review_status = (
        "MANUAL REVIEW REQUIRED — MISSING " + " AND ".join(missing)
        if missing
        else ""
    )
    source_detail = "OR" if title_label.startswith("ORDER") else "OP"
    return NLRBMetadata(
        court=NLRB_COURT_CODE,
        docket_number=docket,
        decision_date=decision_date or "",
        source_detail=source_detail,
        other_numbers=other_numbers,
        comments_text="; ".join(other_numbers),
        title_hint=title,
        has_text_content=True,
        requires_review=bool(review_status),
        review_status=review_status,
    )


def find_nlrb_title(lines: list[str]) -> str:
    """Return the operative first-page heading, not words in the body text."""
    for line in lines:
        label = _heading_label(line)
        if re.match(r"^(?:ORDER|DECISION|SUPPLEMENTAL DECISION|EXHIBIT|ATTACHMENT)\b", label):
            return line
    # An ALJ decision can display a bare ``Decision`` line after its caption.
    # A non-Order heading defaults to OP under the agreed NLRB rules, but it
    # must still be visibly title-like rather than party/caption prose.
    for line in lines:
        label = _label(line)
        if label in {"NOTICE", "CERTIFICATION", "REPORT", "RECOMMENDATION", "JUDGMENT"}:
            return line
    return ""


def extract_nlrb_dockets(caption_text: str) -> list[str]:
    found: list[str] = []
    for match in _DOCKET_RE.finditer(caption_text):
        docket = re.sub(r"\s*[-–]\s*", "-", match.group(0).upper())
        if docket not in found:
            found.append(docket)
    return found


def extract_nlrb_decision_date(text: str, header_lines: list[str]) -> Optional[str]:
    # Published Board decisions put their decision date in the caption, before
    # ``DECISION AND ORDER``.  Prefer that location over a later ``Dated``
    # reference from an attached ALJ decision or notice.
    title_index = next(
        (
            index
            for index, line in enumerate(header_lines)
            if re.match(r"^(?:ORDER|DECISION|SUPPLEMENTAL DECISION)\b", _heading_label(line))
        ),
        None,
    )
    if title_index is not None:
        for line in reversed(header_lines[:title_index]):
            # A caption date stands alone. A historical date in a sentence
            # above a later heading is not the document's decision date.
            match = _MONTH_DATE_RE.fullmatch(line.strip().rstrip("."))
            if match:
                normalized = _normalize_date(match.group(0))
                if normalized:
                    return normalized

    # Prefer an explicit signature date wherever it appears; ALJ decisions
    # commonly put it immediately above the signature near the end.
    # ALJ PDFs print line numbers in the margin. Extraction can concatenate
    # one to the signature year ("October 30, 202610"). Strip only a known
    # margin number at the end of an explicit Dated line, never arbitrary
    # digits from prose, docket numbers, or an invalid date.
    signature_text = re.sub(
        r"(^[ \t]*Dated\b[^\n]{0,100}?\b(?:19|20)\d{2})"
        r"(?:5|10|15|20|25|30|35|40|45|50)[ \t]*(?=\n|$)",
        r"\1", text, flags=re.I | re.M,
    )
    dated_matches = list(re.finditer(r"^[ \t]*Dated\s*,?[^\n]{0,100}?" + _MONTH_DATE_RE.pattern, signature_text, re.I | re.M))
    # The primary decision precedes any appended decision or employee notice.
    for match in dated_matches:
        value = _MONTH_DATE_RE.search(match.group(0))
        normalized = _normalize_date(value.group(0)) if value else None
        if normalized:
            return normalized

    # Without a caption or signature date, require review. Dates in the
    # hearing history, cited cases, or a filing are not safe substitutes.
    return None


def normalize_nlrb_text(value: str) -> str:
    normalized = (
        unicodedata.normalize("NFKC", str(value or ""))
        .replace("\u00a0", " ")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
    )
    # Some NLRB PDFs encode a display-spaced month (for example,
    # ``S eptember``). Normalize it before date recognition without changing
    # regular body text.
    for month in (
        "January", "February", "March", "April", "May", "June", "July",
        "August", "September", "October", "November", "December",
    ):
        spaced = r"\b" + r"\s*".join(re.escape(letter) for letter in month) + r"\b"
        normalized = re.sub(spaced, month, normalized, flags=re.I)
    return normalized


def _caption_text(lines: list[str]) -> str:
    """Limit docket extraction to the caption, before the operative heading."""
    collected: list[str] = []
    for line in lines:
        label = _heading_label(line)
        if re.match(r"^(?:ORDER|DECISION|SUPPLEMENTAL DECISION)\b", label):
            break
        collected.append(line)
    return "\n".join(collected) or "\n".join(lines[:45])


def _is_exhibit_or_attachment(lines: list[str], title_label: str) -> bool:
    if re.match(r"^(?:EXHIBIT|ATTACHMENT)\b", title_label):
        return True
    return any(re.match(r"^(?:EXHIBIT|ATTACHMENT)\b", _label(line)) for line in lines[:45])


def _normalize_date(value: str) -> Optional[str]:
    try:
        return _datetime.datetime.strptime(re.sub(r"\s+", " ", value.strip()), "%B %d, %Y").strftime("%m-%d-%Y")
    except ValueError:
        return None


def _label(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9]+", " ", str(value or "").upper())).strip()


def _heading_label(value: str) -> str:
    # Superscript footnotes become ordinary digits after NFKC normalization.
    # Recognize ORDER1 / DECISION2 as headings without changing case numbers.
    return _label(re.sub(r"(?<=[A-Za-z])\d{1,2}\s*$", "", value))


def _review_metadata(status: str) -> NLRBMetadata:
    return NLRBMetadata(
        court=NLRB_COURT_CODE,
        docket_number="",
        decision_date="",
        source_detail="",
        has_text_content=False,
        requires_review=True,
        review_status=status,
    )
