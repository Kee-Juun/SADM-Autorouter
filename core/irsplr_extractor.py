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
from io import BytesIO
from pathlib import Path
from typing import Optional

from .mspb_extractor import extract_text_from_pdf_bytes


IRSPLR_QUEUE_CODE = "FDIRSPLR"
IRSPLR_OUTPUT_COURTS = {"FDPLR000", "FDCCA001"}
IRSPLR_ALL_COURTS = {IRSPLR_QUEUE_CODE, *IRSPLR_OUTPUT_COURTS}
IRSPLR_EXCLUDED_DOCKET = "NO NUMBER IN ORIGINAL"


class IRSPLRDocumentReviewRequired(ValueError):
    """The source document cannot safely authorize normal content routing."""


class IRSPLRCorruptDocument(IRSPLRDocumentReviewRequired):
    """A verified invalid file or failed PDF viewer authorizes corrupt exclusion."""


def validate_irsplr_pdf_bytes(pdf_bytes: bytes) -> None:
    """Separate verified invalid formats from uncertain PDF/OCR failures.

    OCR can read a bitmap named .pdf even when Chrome cannot open it. Metadata
    recovered from that bitmap does not make the source a usable PDF.
    """
    if not pdf_bytes:
        raise IRSPLRDocumentReviewRequired("UNAVAILABLE - the download is empty; a corrupt file has not been verified")
    if not pdf_bytes.lstrip(b" \t\r\n").startswith(b"%PDF-"):
        if pdf_bytes.lstrip().startswith(b"<"):
            raise IRSPLRDocumentReviewRequired("UNAVAILABLE - the server returned an HTML/error page instead of a PDF; corruption is not verified")
        # These are file-format signatures, not an OCR/readability test. An
        # unknown response can be a login/service error or unusual PDF header.
        replacement_signatures = (
            b"BM", b"\x89PNG\r\n", b"\xff\xd8\xff", b"GIF87a", b"GIF89a",
            b"II*\x00", b"MM\x00*", b"PK\x03\x04", b"{\\rtf",
        )
        if pdf_bytes.startswith(replacement_signatures):
            raise IRSPLRCorruptDocument("CORRUPT OR INVALID FILE - the downloaded content is not a PDF (another file format was identified)")
        raise IRSPLRDocumentReviewRequired("UNRECOGNIZED DOWNLOAD - no PDF header or known replacement file format; corruption is not verified")
    needs_render_validation = False
    if not re.search(rb"%%EOF[\x00\t\n\f\r ]*\Z", pdf_bytes):
        # Some replacement PLRs have a complete original EOF followed only
        # by an empty incremental xref/trailer whose final F became NUL.
        # Recognize that narrow case, not arbitrary bytes after an old EOF
        # that might hide incomplete new pages/content.
        end = pdf_bytes.rfind(b"%%EOF")
        tail = pdf_bytes[end + 5:] if end >= 0 else b""
        needs_render_validation = bool(
            end >= 0 and len(tail) <= 4096
            and re.match(rb"\s*xref\s+0\s+0\s+trailer\b", tail)
            and re.search(rb"startxref\s+\d+\s+%%EO\x00[\x00\t\n\f\r ]*\Z", tail)
            and not re.search(rb"\b(?:obj|endobj|stream|endstream)\b", tail)
        )
        # A viewer may recover a missing trailer. Never exclude solely for a
        # strict-parser requirement, unsupported encoding, or repairable defect.
        if not needs_render_validation:
            raise IRSPLRDocumentReviewRequired("POSSIBLY TRUNCATED OR NONSTANDARD PDF - the final PDF end marker is missing or followed by unexpected data; corruption is not verified")
    try:
        from pypdf import PdfReader
        from pypdf.errors import DependencyError
    except ImportError as exc:
        raise IRSPLRDocumentReviewRequired("VALIDATION UNAVAILABLE - PDF validation dependencies could not be loaded") from exc

    try:
        reader = PdfReader(BytesIO(pdf_bytes), strict=True)
        if reader.is_encrypted and not reader.decrypt(""):
            raise IRSPLRDocumentReviewRequired("PASSWORD PROTECTED - supply an unlocked PDF; corruption is not verified")
        if len(reader.pages) == 0:
            raise IRSPLRCorruptDocument("CORRUPT PDF - the file has no pages")
        for page in reader.pages:
            # Force page/content references to resolve, rather than treating
            # a surviving header or recoverable first-page text as proof.
            contents = page.get_contents()
            if contents is not None:
                contents.get_data()
        if needs_render_validation:
            _validate_irsplr_nonstandard_trailer_rendering(pdf_bytes, len(reader.pages))
    except IRSPLRDocumentReviewRequired:
        raise
    except DependencyError as exc:
        raise IRSPLRDocumentReviewRequired("VALIDATION UNAVAILABLE - required PDF decryption support is missing") from exc
    except Exception as exc:
        raise IRSPLRDocumentReviewRequired("PDF VALIDATION INCONCLUSIVE - structural validation failed; supply a working PDF or review it manually; corruption is not verified") from exc


def _validate_irsplr_nonstandard_trailer_rendering(pdf_bytes: bytes, expected_pages: int) -> None:
    """Require independent, complete page rendering for the known trailer quirk."""
    try:
        import fitz

        with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
            if document.needs_pass or document.page_count != expected_pages:
                raise ValueError("PDF readers disagree about accessible pages")
            for page in document:
                pixels = page.get_pixmap(matrix=fitz.Matrix(0.5, 0.5), alpha=False)
                if pixels.width <= 0 or pixels.height <= 0:
                    raise ValueError("a page could not be rendered")
    except Exception as exc:
        raise IRSPLRDocumentReviewRequired(
            "PDF VALIDATION INCONCLUSIVE - the nonstandard trailer could not be independently checked on every page; corruption is not verified"
        ) from exc
    logging.info("IRSPLR nonstandard PDF trailer accepted after structural validation and independent rendering of all %d pages.", expected_pages)


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
    is_verified_corrupt: bool = False


def build_irsplr_corrupt_exclusion_metadata(court_code_hint=None, reason="") -> IRSPLRMetadata:
    """Authorize exclusion only, without inventing unreadable docket/date values."""
    court_hint = str(court_code_hint or "").strip().upper()
    return IRSPLRMetadata(
        court=court_hint if court_hint in IRSPLR_OUTPUT_COURTS else "",
        docket_number="",
        decision_date="",
        source_detail="Excluded",
        comments_text="Exclude - Corrupt File",
        title_hint="Verified corrupt file",
        is_excluded=True,
        exclusion_reason=reason or "Corrupt File",
        is_verified_corrupt=True,
    )


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
    validate_irsplr_pdf_bytes(pdf_bytes)
    text = extract_text_from_pdf_bytes(pdf_bytes, use_ocr_fallback=False)
    metadata = parse_irsplr_document_text(
        text,
        filename_hint=filename_hint,
        court_code_hint=court_code_hint,
    )
    if metadata is not None or not use_ocr_fallback:
        return metadata

    # A partial text layer (e.g. a watermark) must not suppress OCR of the
    # actual scan. OCR trouble never changes the file-validation outcome.
    logging.info("IRSPLR native text has incomplete metadata; trying Tesseract OCR on the validated PDF.")
    ocr_text = extract_text_from_pdf_bytes(pdf_bytes, force_ocr=True)
    if not ocr_text.strip():
        logging.warning("IRSPLR PDF passed validation but OCR returned no text; manual review is required, not corrupt exclusion.")
        return None
    return parse_irsplr_document_text(
        ocr_text,
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
