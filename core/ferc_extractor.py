"""First-page metadata extraction and routing classification for FERC (FDFERC00).

FERC's operative details live on the first page: its official FERC citation,
the docket/project number(s), a title, and an issued date.  The parser keeps
that boundary deliberately tight so docket references deeper in the decision
cannot become accidental primary metadata.
"""

from __future__ import annotations

import datetime as _datetime
import io
import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

from .mspb_extractor import extract_text_from_pdf_bytes


FERC_COURT_CODE = "FDFERC00"
_FERC_CITATION_RE = re.compile(r"\b\d{3}\s+FERC\s*¶\s*\d{2},\d{3}\b", re.I)
_ALPHA_DOCKET_RE = re.compile(r"\b[A-Z]{1,4}\d{1,4}-\d{1,4}-\d{3}\b")
_PROJECT_NUMBER_RE = re.compile(
    r"\bProject\s+Nos?\.?(?:\s+|\s*:\s*)"
    r"(\d{1,6}-\d{1,4}(?:\s*(?:,|and|&)\s*\d{1,6}-\d{1,4})*)\b",
    re.I,
)
_BARE_PROJECT_NUMBER_RE = re.compile(r"\b\d{1,6}-\d{1,4}\b")
_LETTER_SALUTATION_RE = re.compile(r"^Dear\s+[^\n:]+[:,]\s*$", re.I)


@dataclass(frozen=True)
class FERCMetadata:
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


def is_ferc_row(row) -> bool:
    try:
        value = row.get("CourtCode", row.get("Court Code", ""))
    except AttributeError:
        value = ""
    return str(value or "").strip().upper() == FERC_COURT_CODE


def parse_ferc_pdf_bytes(
    pdf_bytes: bytes, filename_hint: Optional[str] = None, use_ocr_fallback: bool = True
) -> Optional[FERCMetadata]:
    """Read page one first; use the shared OCR-capable extractor only if needed."""
    try:
        from pypdf import PdfReader

        text = PdfReader(io.BytesIO(pdf_bytes)).pages[0].extract_text() or ""
        if text.strip():
            return parse_ferc_document_text(text, filename_hint=filename_hint)
    except Exception:
        pass
    return parse_ferc_document_text(
        extract_text_from_pdf_bytes(pdf_bytes, use_ocr_fallback=use_ocr_fallback),
        filename_hint=filename_hint,
    )


def parse_ferc_docx_bytes(docx_bytes: bytes, filename_hint: Optional[str] = None) -> Optional[FERCMetadata]:
    """Extract a DOCX document's text before applying the ordinary FERC rules.

    DOCX does not expose stable physical page boundaries in its file format.
    ``parse_ferc_document_text`` already limits metadata discovery to the
    opening header lines, which is the DOCX equivalent of the PDF first-page
    boundary used by this router.
    """
    if not docx_bytes:
        return None
    try:
        from docx import Document

        document = Document(io.BytesIO(docx_bytes))
        # FERC DOCX files commonly place their docket in a first-page header
        # or a two-column caption table beside the party names.  Reading all
        # paragraphs and appending all tables afterwards puts that table after
        # the issued-date line, outside the deliberately bounded metadata
        # header.  Preserve the document's block order instead, and put its
        # visual header ahead of the first body block.
        text_parts = _ferc_docx_header_text(document)
        iter_inner_content = getattr(document, "iter_inner_content", None)
        if callable(iter_inner_content):
            for block in iter_inner_content():
                if hasattr(block, "rows"):
                    text_parts.extend(_ferc_docx_table_text(block))
                elif getattr(block, "text", "").strip():
                    text_parts.append(block.text.strip())
        else:
            # Compatibility fallback for older python-docx releases.  The
            # packaged runtime currently supports iter_inner_content(), but
            # retaining this path makes a malformed/older local environment
            # fail safe rather than rejecting every DOCX outright.
            text_parts.extend(paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip())
            for table in document.tables:
                text_parts.extend(_ferc_docx_table_text(table))
        return parse_ferc_document_text("\n".join(text_parts), filename_hint=filename_hint)
    except Exception:
        return None


def _ferc_docx_header_text(document) -> list[str]:
    """Return nonempty DOCX header lines once, preserving section order."""
    header_lines: list[str] = []
    for section in document.sections:
        for paragraph in section.header.paragraphs:
            value = paragraph.text.strip()
            if value and value not in header_lines:
                header_lines.append(value)
    return header_lines


def _ferc_docx_table_text(table) -> list[str]:
    """Flatten a table one visual row at a time, ignoring merged-cell repeats."""
    lines: list[str] = []
    for row in table.rows:
        seen_cells: set[int] = set()
        cells: list[str] = []
        for cell in row.cells:
            cell_id = id(cell._tc)
            if cell_id in seen_cells:
                continue
            seen_cells.add(cell_id)
            value = cell.text.strip()
            if value:
                cells.append(value)
        if cells:
            lines.append(" ".join(cells))
    return lines


def parse_ferc_document_text(text: str, filename_hint: Optional[str] = None) -> Optional[FERCMetadata]:
    normalized = normalize_ferc_text(text)
    if not normalized.strip():
        return None

    lines = [line.strip() for line in normalized.splitlines() if line.strip()]
    header = _metadata_header(lines)
    title = find_ferc_title(lines[:70])
    title_label = _label(title)
    citation_match = _FERC_CITATION_RE.search(header)
    citation = re.sub(r"\s+", " ", citation_match.group(0)).strip() if citation_match else ""
    docket_numbers = extract_ferc_docket_numbers(header)
    docket = docket_numbers[0] if docket_numbers else ""
    other_numbers = tuple(docket_numbers[1:])
    decision_date = extract_ferc_issued_date(header, letter=title_label.startswith("DEAR "))

    if re.search(r"\bERRAT(?:A|UM)\b", title_label):
        review_status = "ERRATA FOR REVIEW"
        source_detail = "Corrections"
    elif not citation or not docket or not decision_date:
        review_status = "NEEDS REVIEW"
        source_detail = classify_ferc_source_detail(title_label)
    else:
        review_status = ""
        source_detail = classify_ferc_source_detail(title_label)

    # FERC citations belong in Comments.  The other docket numbers are kept
    # there too so they remain auditable even on IRT forms without a dedicated
    # secondary-number control.
    comment_parts = [citation, *other_numbers]
    return FERCMetadata(
        court=FERC_COURT_CODE,
        docket_number=docket,
        decision_date=decision_date or "",
        source_detail=source_detail,
        other_numbers=other_numbers,
        comments_text="; ".join(dict.fromkeys(part for part in comment_parts if part)),
        title_hint=title,
        has_text_content=True,
        requires_review=bool(review_status),
        review_status=review_status,
    )


def find_ferc_title(lines: list[str]) -> str:
    """Return the operative all-caps first-page heading, never body prose."""
    salutation = next((i for i, line in enumerate(lines[:35]) if _LETTER_SALUTATION_RE.fullmatch(line)), None)
    # Correspondence has no operative heading. Ignore headings/order references
    # in its body, while preserving formal headings ahead of a salutation.
    header_lines = lines[:salutation] if salutation is not None else lines
    for line in header_lines:
        label = _label(line)
        if re.search(r"\bERRAT(?:A|UM)\b", label):
            return line
    for line in header_lines:
        label = _label(line)
        if _is_ferc_all_caps(line) and re.match(r"^(?:CERTIFICATION|OPINION|MEMORANDUM|ORDER)\b", label):
            return line
    if salutation is not None:
        return lines[salutation]
    # FERC also publishes operative headings such as "NOTICE OF DENIAL ...".
    # Treat a title-shaped all-caps header as the title before looking for an
    # incidental "order" in the body.  The exclusions avoid mistaking the
    # court masthead, a docket/citation line, or the issued date for a title.
    for line in lines:
        if _looks_like_ferc_title(line):
            return line
    for line in lines:
        if re.search(r"\bORDER\b", _label(line)):
            return line
    return ""


def classify_ferc_source_detail(title: str) -> str:
    if re.match(r"^DEAR\s+", title):
        return "Letter"
    # A title headed OPINION, CERTIFICATION, or MEMORANDUM remains OP even if
    # a later phrase includes "ORDER" (for example, Opinion No. 595).
    if re.match(r"^(?:CERTIFICATION|OPINION|MEMORANDUM)\b", title):
        return "Opinion"
    if "ORDER" in title:
        return "Order"
    return "Opinion"


def extract_ferc_docket_numbers(header: str) -> list[str]:
    """Return docket/project numbers in their first-page display order."""
    found: list[str] = []
    for match in _ALPHA_DOCKET_RE.finditer(header):
        value = match.group(0).upper()
        if value not in found:
            found.append(value)
    # Project numbers do not carry an alphabetic prefix, unlike conventional
    # FERC dockets.  Only accept them when explicitly labeled as Project No.
    # or Project Nos. A plural header may carry multiple numbers; retain the
    # display order so IRT receives the first number and the others are saved
    # as auditable secondary numbers in Comments.
    for match in _PROJECT_NUMBER_RE.finditer(header):
        for value in _BARE_PROJECT_NUMBER_RE.findall(match.group(1)):
            value = value.upper()
            if value not in found:
                found.append(value)
    return found


def extract_ferc_issued_date(header: str, letter: bool = False) -> Optional[str]:
    if letter:
        # Choose the standalone date closest to the top citation/masthead,
        # never a historical date embedded in the correspondence body.
        anchor = _FERC_CITATION_RE.search(header) or re.search(
            r"FEDERAL ENERGY REGULATORY COMMISSION", header, re.I
        )
        dates = list(re.finditer(
            r"(?m)^[ \t]*\(?[ \t]*(?:Issued(?: on)?(?:[ \t]*:[ \t]*|[ \t]+))?([A-Za-z]+[ \t]+\d{1,2},[ \t]*\d{4})[ \t]*\)?[ \t]*$",
            header, re.I,
        ))
        anchor_line = header[:anchor.start()].count("\n") if anchor else 0
        dates.sort(key=lambda match: abs(header[:match.start()].count("\n") - anchor_line))
        for match in dates:
            try:
                return _datetime.datetime.strptime(re.sub(r"\s+", " ", match.group(1)), "%B %d, %Y").strftime("%m-%d-%Y")
            except ValueError:
                continue
        return None
    patterns = (
        r"\(\s*([A-Za-z]+\s+\d{1,2},\s*\d{4})\s*\)",
        r"\(\s*Issued(?:\s+on)?\s+([A-Za-z]+\s+\d{1,2},\s*\d{4})\s*\)",
        r"\bIssued(?:\s+on)?\s+([A-Za-z]+\s+\d{1,2},\s*\d{4})",
    )
    for pattern in patterns:
        match = re.search(pattern, header, re.I)
        if match:
            try:
                return _datetime.datetime.strptime(match.group(1), "%B %d, %Y").strftime("%m-%d-%Y")
            except ValueError:
                continue
    return None


def normalize_ferc_text(value: str) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).replace("\u00a0", " ").replace("\u2013", "-").replace("\u2014", "-")


def _label(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9]+", " ", normalize_ferc_text(value).upper())).strip()


def _looks_like_ferc_title(value: str) -> bool:
    """Identify a substantive all-caps heading in the first-page FERC header."""
    line = re.sub(r"\s+", " ", normalize_ferc_text(value)).strip()
    label = _label(line)
    if _ALPHA_DOCKET_RE.fullmatch(line):
        return False
    if len(label.split()) < 3 or not re.search(r"[A-Z]", label):
        return False
    if not _is_ferc_all_caps(line):
        return False
    if re.search(r"\b(?:UNITED STATES OF AMERICA|FEDERAL ENERGY REGULATORY COMMISSION|BEFORE COMMISSIONERS|DOCKET|PROJECT NO|FERC)\b", label):
        return False
    return not re.fullmatch(r"(?:ISSUED\s+)?[A-Z]+\s+\d{1,2}\s+\d{4}", label)


def _is_ferc_all_caps(value: str) -> bool:
    line = re.sub(r"\s+", " ", normalize_ferc_text(value)).strip()
    return bool(re.search(r"[A-Z]", line)) and line.upper() == line


def _metadata_header(lines: list[str]) -> str:
    """Keep extraction inside the visual header, ending at its date line."""
    # A letter's date precedes its docket. Keep both, stopping at the
    # salutation so body citations, dates and dockets cannot leak in.
    if find_ferc_title(lines[:70]).lower().startswith("dear "):
        for index, line in enumerate(lines[:35]):
            if _LETTER_SALUTATION_RE.fullmatch(line):
                return "\n".join(lines[:index])
    date_line = re.compile(
        r"^\(\s*(?:Issued(?:\s+on)?\s+)?[A-Za-z]+\s+\d{1,2},\s*\d{4}\s*\)$",
        re.I,
    )
    for index, line in enumerate(lines[:70]):
        if date_line.match(line):
            return "\n".join(lines[: index + 1])
    return "\n".join(lines[:35])
