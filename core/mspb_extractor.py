"""
MSPB document text extraction and field classification helpers.

MSPBAR reads the linked PDF itself instead of relying on docket/date/source
detail values from the mapping sheet.
"""

from __future__ import annotations

import datetime
import importlib.util
import logging
import os
import re
import shutil
import sys
from dataclasses import dataclass
from io import BytesIO
from typing import Optional


NONPRECEDENTIAL_PHRASES = (
    "NONPRECEDENTIAL",
    "NONPRECEDENTIAL ORDER",
    "THIS ORDER IS NONPRECEDENTIAL",
    "THIS FINAL ORDER IS NONPRECEDENTIAL",
)


_ocr_unavailable_logged = False


@dataclass(frozen=True)
class MSPBMetadata:
    court: str
    docket_number: str
    decision_date: str
    source_detail: str
    other_numbers: tuple[str, ...] = ()
    comments_text: str = ""
    title_hint: str = ""


def extract_text_from_pdf_bytes(pdf_bytes: bytes, use_ocr_fallback: bool = True) -> str:
    """Extract text from PDF bytes, with an optional OCR fallback for image PDFs."""
    text = _extract_text_with_pypdf(pdf_bytes)
    if text.strip():
        return text

    if use_ocr_fallback:
        return _extract_text_with_optional_ocr(pdf_bytes)

    return ""


def parse_mspb_pdf_bytes(
    pdf_bytes: bytes,
    use_ocr_fallback: bool = True,
    filename_hint: Optional[str] = None,
) -> Optional[MSPBMetadata]:
    """Extract text from a PDF and parse MSPB routing metadata."""
    text = extract_text_from_pdf_bytes(pdf_bytes, use_ocr_fallback=use_ocr_fallback)
    if not text.strip():
        logging.warning("MSPB PDF text extraction returned no text.")
        return None
    return parse_mspb_document_text(text, filename_hint=filename_hint)


def parse_mspb_document_text(text: str, filename_hint: Optional[str] = None) -> Optional[MSPBMetadata]:
    """Parse MSPB court, docket, decision date, and source detail from text."""
    if not text or not text.strip():
        return None

    lines = _clean_lines(text)
    header_text = _get_header_text(lines)
    header_normalized = _normalize_text(header_text)

    court = classify_mspb_court(header_normalized, filename_hint=filename_hint)
    docket_numbers = extract_mspb_dockets(lines)
    docket_number = docket_numbers[0] if docket_numbers else None
    other_numbers = tuple(docket for docket in docket_numbers[1:] if docket != docket_number)
    decision_date = extract_mspb_decision_date(text)
    title_hint = _find_title_hint(lines) or _title_hint_from_filename(filename_hint)
    source_detail = classify_mspb_source_detail(court, header_normalized, title_hint=title_hint)

    if not docket_number or not decision_date or not source_detail:
        logging.warning(
            "Incomplete MSPB metadata: court=%s docket=%s decision_date=%s source_detail=%s",
            court,
            docket_number,
            decision_date,
            source_detail,
        )
        return None

    return MSPBMetadata(
        court=court,
        docket_number=docket_number,
        decision_date=decision_date,
        source_detail=source_detail,
        other_numbers=other_numbers,
        comments_text=format_mspb_comments(other_numbers),
        title_hint=title_hint,
    )


def classify_mspb_court(header_normalized: str, filename_hint: Optional[str] = None) -> str:
    """Classify an MSPB document into FDMSPB00, FDMSPB01, or FDMSPB02."""
    if re.search(r"\bNON\s*[- ]?\s*PRECEDENTIAL\b", header_normalized) or any(
        phrase in header_normalized for phrase in NONPRECEDENTIAL_PHRASES
    ):
        return "FDMSPB00"
    if "INITIAL DECISION" in header_normalized:
        return "FDMSPB01"
    if filename_indicates_initial_decision(filename_hint):
        return "FDMSPB01"
    return "FDMSPB02"


def classify_mspb_source_detail(court: str, header_normalized: str, title_hint: str = "") -> str:
    """Return the IRT Source Detail value for an MSPB document."""
    if court == "FDMSPB01":
        return "Opinion"
    if court == "FDMSPB00":
        return "Order"

    title_normalized = _normalize_text(title_hint)
    if re.search(r"\bOPINION\b", title_normalized) or title_normalized.startswith("DECISION"):
        return "Opinion"
    if re.search(r"\bORDER\b", title_normalized):
        return "Order"

    if "OPINION AND ORDER" in header_normalized or re.search(r"\bOPINION\b", header_normalized):
        return "Opinion"
    if re.search(r"\bDECISION\b", header_normalized):
        return "Opinion"
    return "Order" if re.search(r"\bORDER\b", header_normalized) else "Opinion"


def extract_mspb_docket(lines: list[str]) -> Optional[str]:
    """Extract the primary docket number exactly as printed below the DOCKET NUMBER header."""
    dockets = extract_mspb_dockets(lines)
    return dockets[0] if dockets else None


def extract_mspb_dockets(lines: list[str]) -> list[str]:
    """Extract one or more docket numbers printed below the DOCKET NUMBER(S) header."""
    for index, line in enumerate(lines):
        normalized = _normalize_text(line)
        if re.fullmatch(r"DOCKET\s+NUMBERS?\s*:?", normalized):
            dockets = _extract_dockets_after_header(lines, index)
            if dockets:
                return dockets

        if re.search(r"\bDOCKET\s+NUMBERS?\b", normalized):
            after_header = re.split(r"DOCKET\s+NUMBERS?", _normalize_dashes(line), flags=re.IGNORECASE, maxsplit=1)
            if len(after_header) > 1:
                dockets = _extract_dockets_from_line(after_header[1])
                if dockets:
                    return dockets
            dockets = _extract_dockets_after_header(lines, index)
            if dockets:
                return dockets

    for line in lines[:120]:
        normalized = _normalize_text(line)
        if re.search(r"\bDOCKET\s+(?:NOS?\.?|NUMBERS?)\b", normalized):
            dockets = _extract_dockets_from_line(line)
            if dockets:
                return dockets

    return []


def _extract_dockets_after_header(lines: list[str], header_index: int) -> list[str]:
    dockets = []
    for candidate in lines[header_index + 1 : header_index + 8]:
        candidate_dockets = _extract_dockets_from_line(candidate)
        if candidate_dockets:
            for docket in candidate_dockets:
                if docket not in dockets:
                    dockets.append(docket)
            continue
        if dockets:
            break
    return dockets


def format_mspb_comments(other_numbers) -> str:
    numbers = [str(number).strip() for number in other_numbers if str(number).strip()]
    if not numbers:
        return ""
    return "; ".join(numbers)


def extract_mspb_decision_date(text: str) -> Optional[str]:
    """Extract and normalize the MSPB decision date to mm-dd-yyyy."""
    date_value_pattern = r"(?:[A-Za-z]+\s+\d{1,2},\s+\d\s*\d\s*\d\s*\d|\d{1,2}[-/]\d{1,2}[-/]\d{2,4})"
    match = re.search(
        rf"\b(?:DATE|DECIDED|ISSUED)\s*:?\s*({date_value_pattern})",
        text,
        re.IGNORECASE,
    )
    if match:
        return _normalize_date(match.group(1))

    for line in _clean_lines(text)[:120]:
        line_match = re.fullmatch(date_value_pattern, line, re.IGNORECASE)
        if line_match:
            return _normalize_date(line_match.group(0))

    return None


def _extract_text_with_pypdf(pdf_bytes: bytes) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(pdf_bytes))
        page_texts = []
        for page in reader.pages:
            page_texts.append(page.extract_text() or "")
        return "\n".join(page_texts)
    except Exception as exc:
        logging.warning("pypdf MSPB extraction failed: %s", exc)
        return ""


def _extract_text_with_optional_ocr(pdf_bytes: bytes, max_pages: int = 3) -> str:
    global _ocr_unavailable_logged

    if importlib.util.find_spec("pytesseract") is None:
        if not _ocr_unavailable_logged:
            logging.warning(
                "Optional PDF OCR fallback unavailable: missing Python package: pytesseract"
            )
            _ocr_unavailable_logged = True
        return ""

    try:
        import pytesseract
        _configure_tesseract_cmd(pytesseract)
        if importlib.util.find_spec("fitz") is not None:
            return _extract_text_with_pymupdf_ocr(pdf_bytes, pytesseract, max_pages=max_pages)
        if importlib.util.find_spec("pdf2image") is not None:
            return _extract_text_with_pdf2image_ocr(pdf_bytes, pytesseract, max_pages=max_pages)
        if not _ocr_unavailable_logged:
            logging.warning("Optional PDF OCR fallback unavailable: missing PDF renderer package PyMuPDF or pdf2image")
            _ocr_unavailable_logged = True
        return ""
    except Exception as exc:
        if not _ocr_unavailable_logged:
            logging.warning("Optional PDF OCR fallback unavailable or failed: %s", exc)
            _ocr_unavailable_logged = True
        return ""


def _configure_tesseract_cmd(pytesseract_module) -> None:
    bundled_root = getattr(sys, "_MEIPASS", None)
    for candidate in _tesseract_candidates(bundled_root):
        if os.path.exists(candidate):
            pytesseract_module.pytesseract.tesseract_cmd = candidate
            _configure_tessdata_prefix(os.path.dirname(candidate))
            return

    path_candidate = shutil.which("tesseract")
    if path_candidate:
        pytesseract_module.pytesseract.tesseract_cmd = path_candidate
        _configure_tessdata_prefix(os.path.dirname(path_candidate))
        return

    for candidate in (
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ):
        if os.path.exists(candidate):
            pytesseract_module.pytesseract.tesseract_cmd = candidate
            _configure_tessdata_prefix(os.path.dirname(candidate))
            return


def _tesseract_candidates(root: Optional[str]) -> tuple[str, ...]:
    if not root:
        return ()
    return (
        os.path.join(root, "tesseract", "tesseract.exe"),
        os.path.join(root, "Tesseract-OCR", "tesseract.exe"),
    )


def _configure_tessdata_prefix(tesseract_dir: str) -> None:
    tessdata_dir = os.path.join(tesseract_dir, "tessdata")
    if os.path.isdir(tessdata_dir):
        os.environ["TESSDATA_PREFIX"] = tessdata_dir


def _extract_text_with_pymupdf_ocr(pdf_bytes: bytes, pytesseract_module, max_pages: int = 3) -> str:
    import fitz
    from PIL import Image

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page_texts = []
    for page_index in range(min(max_pages, doc.page_count)):
        page = doc.load_page(page_index)
        pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        image = Image.open(BytesIO(pixmap.tobytes("png")))
        page_texts.append(pytesseract_module.image_to_string(image))
    return "\n".join(page_texts)


def _extract_text_with_pdf2image_ocr(pdf_bytes: bytes, pytesseract_module, max_pages: int = 3) -> str:
    from pdf2image import convert_from_bytes

    images = convert_from_bytes(pdf_bytes, first_page=1, last_page=max_pages)
    return "\n".join(pytesseract_module.image_to_string(image) for image in images)


def _clean_lines(text: str) -> list[str]:
    return [line.strip() for line in _normalize_dashes(text).splitlines() if line.strip()]


def _get_header_text(lines: list[str]) -> str:
    header = []

    for line in lines[:100]:
        header.append(line)
        normalized = _normalize_text(line)
        if _line_is_mspb_title(normalized) and len(header) > 5:
            break

    return "\n".join(header or lines[:60])


def _find_title_hint(lines: list[str]) -> str:
    for line in lines[:100]:
        normalized = _normalize_text(line)
        if _line_is_mspb_title(normalized):
            return normalized
    return ""


def _line_is_mspb_title(normalized_line: str) -> bool:
    return bool(
        normalized_line in {"INITIAL DECISION", "ORDER", "FINAL ORDER", "OPINION AND ORDER", "DECISION"}
        or re.match(r"^(?:INITIAL DECISION|OPINION AND ORDER|FINAL ORDER|ORDER|DECISION)\b", normalized_line)
    )


def filename_indicates_initial_decision(filename_hint: Optional[str]) -> bool:
    if not filename_hint:
        return False
    normalized = _normalize_filename_hint(filename_hint)
    compact = re.sub(r"[^A-Z0-9]+", "", str(filename_hint).upper())
    return "INITIAL DECISION" in normalized or "INITIALDECISION" in compact


def _title_hint_from_filename(filename_hint: Optional[str]) -> str:
    if filename_indicates_initial_decision(filename_hint):
        return "INITIAL DECISION"
    return ""


def _normalize_filename_hint(filename_hint: str) -> str:
    return re.sub(r"[^A-Z0-9]+", " ", str(filename_hint).upper()).strip()


def _extract_docket_from_line(line: str) -> Optional[str]:
    dockets = _extract_dockets_from_line(line)
    return dockets[0] if dockets else None


def _extract_dockets_from_line(line: str) -> list[str]:
    line = _normalize_dashes(line).strip()
    dockets = []
    for match in re.finditer(
        r"\b([A-Z]{1,6}\s*-\s*[A-Z0-9][A-Z0-9\s-]*\s*-\s*[A-Z0-9])\b",
        line,
        re.IGNORECASE,
    ):
        docket = re.sub(r"\s+", "", match.group(1)).upper()
        if docket not in dockets:
            dockets.append(docket)
    return dockets


def _normalize_date(raw_date: str) -> Optional[str]:
    cleaned = re.sub(r"\s+", " ", _normalize_dashes(raw_date).strip().rstrip(".,"))
    cleaned = re.sub(
        r"(,\s*)([\d\s]{4,})$",
        lambda match: match.group(1) + re.sub(r"\s+", "", match.group(2)),
        cleaned,
    )
    formats = (
        "%B %d, %Y",
        "%b %d, %Y",
        "%m-%d-%Y",
        "%m/%d/%Y",
        "%m-%d-%y",
        "%m/%d/%y",
    )

    for fmt in formats:
        try:
            return datetime.datetime.strptime(cleaned, fmt).strftime("%m-%d-%Y")
        except ValueError:
            continue

    logging.warning("Could not normalize MSPB date: %s", raw_date)
    return None


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", _normalize_dashes(text).upper()).strip()


def _normalize_dashes(text) -> str:
    return (
        str(text or "")
        .replace("\u2010", "-")
        .replace("\u2011", "-")
        .replace("\u2012", "-")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u2212", "-")
        .replace("?", "-")
    )
