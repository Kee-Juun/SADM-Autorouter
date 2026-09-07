"""MOSU00 document detection and metadata helpers.

MOSU00 has two workflows:
- normal SMD-style main opinion/counsel routing for SC docket PDFs
- table-case routing driven by the docket list in a minutes HTML file
"""

from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable


MOSU00_COURT_CODE = "MOSU00"
MOSU00_COURT_CODES = {"MOSU00", "STMOSU00"}
MOSU00_TABLE_SOURCE_DETAIL = "Table-(5-day spec source)"


@dataclass(frozen=True)
class MOSU00Metadata:
    docket_number: str
    decision_date: str
    child_dockets: tuple[str, ...]
    court: str = MOSU00_COURT_CODE
    source_detail: str = MOSU00_TABLE_SOURCE_DETAIL
    comments_text: str = ""
    title_hint: str = ""
    is_table_case: bool = True
    has_text_content: bool = True


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data and data.strip():
            self._parts.append(data.strip())

    def get_text(self) -> str:
        return "\n".join(self._parts)


def normalize_mosu00_text(text: str | None) -> str:
    """Normalize whitespace and dashes before extraction."""
    if not text:
        return ""
    normalized = html.unescape(str(text))
    normalized = normalized.replace("\u2010", "-").replace("\u2011", "-")
    normalized = normalized.replace("\u2012", "-").replace("\u2013", "-").replace("\u2014", "-")
    normalized = normalized.replace("\xa0", " ")
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def html_to_text(raw_html: str | bytes) -> str:
    if isinstance(raw_html, bytes):
        raw_html = _decode_html_bytes(raw_html)
    parser = _HTMLTextExtractor()
    try:
        parser.feed(raw_html)
        parser.close()
    except Exception as exc:
        logging.warning("MOSU00 HTML parser fallback used: %s", exc)
        raw_html = re.sub(r"<(script|style)\b.*?</\1>", " ", raw_html, flags=re.IGNORECASE | re.DOTALL)
        raw_html = re.sub(r"<[^>]+>", " ", raw_html)
        return normalize_mosu00_text(raw_html)
    return normalize_mosu00_text(parser.get_text())


def normalize_mosu00_docket(value: str | None) -> str | None:
    if not value:
        return None
    text = normalize_mosu00_text(value).upper()
    match = re.search(r"\bSC\s*[- ]?\s*(\d{4,8})\b", text, flags=re.IGNORECASE)
    if match:
        return f"SC{match.group(1)}"
    return None


def extract_mosu00_dockets_from_text(text: str | None) -> list[str]:
    normalized = normalize_mosu00_text(text)
    dockets: list[str] = []
    seen: set[str] = set()
    for match in re.finditer(r"\bSC\s*[- ]?\s*\d{4,8}\b", normalized, flags=re.IGNORECASE):
        docket = normalize_mosu00_docket(match.group(0))
        if docket and docket not in seen:
            seen.add(docket)
            dockets.append(docket)
    return dockets


def extract_mosu00_docket_from_filename(file_name: str | None) -> str | None:
    if not file_name:
        return None
    name = Path(str(file_name)).name
    match = re.search(r"\bLDC_SMD_(SC\s*[- ]?\s*\d{4,8})(?:counsel)?(?:[_\-.]|$)", name, flags=re.IGNORECASE)
    if not match:
        return None
    return normalize_mosu00_docket(match.group(1))


def is_mosu00_table_filename(file_name: str | None) -> bool:
    if not file_name:
        return False
    name = Path(str(file_name)).name.lower()
    return name.endswith((".htm", ".html")) and "minutesof" in name and name.startswith("ldc_smd_")


def is_mosu00_pdf_filename(file_name: str | None) -> bool:
    if not file_name:
        return False
    name = Path(str(file_name)).name
    return bool(re.search(r"\bLDC_SMD_SC\s*[- ]?\s*\d{4,8}.*\.pdf$", name, flags=re.IGNORECASE))


def is_mosu00_filename(file_name: str | None) -> bool:
    return is_mosu00_table_filename(file_name) or is_mosu00_pdf_filename(file_name)


def is_mosu00_row(row) -> bool:
    file_name = _row_value(row, "FileName") or _row_value(row, "File Name")
    court_code = str(_row_value(row, "CourtCode") or _row_value(row, "Court Code") or "").upper().strip()
    return court_code in MOSU00_COURT_CODES or is_mosu00_filename(file_name)


def is_mosu00_table_row(row) -> bool:
    return is_mosu00_table_filename(_row_value(row, "FileName") or _row_value(row, "File Name"))


def parse_mosu00_html_text(raw_html_or_text: str | bytes, filename_hint: str | None = None) -> MOSU00Metadata | None:
    """Extract table-case metadata from a MOSU00 minutes HTML document."""
    text = html_to_text(raw_html_or_text)
    if not text:
        return None

    dockets = extract_mosu00_dockets_from_text(text)
    decision_date = extract_mosu00_decision_date(text, filename_hint=filename_hint)
    if not dockets or not decision_date:
        logging.debug(
            "Incomplete MOSU00 table metadata: dockets=%s decision_date=%s",
            dockets,
            decision_date,
        )
        return None

    return MOSU00Metadata(
        docket_number=dockets[0],
        decision_date=decision_date,
        child_dockets=tuple(dockets),
        title_hint=extract_mosu00_title_hint(text, filename_hint=filename_hint),
    )


def parse_mosu00_html_file(file_path: str | Path) -> MOSU00Metadata | None:
    path = Path(file_path)
    raw = path.read_bytes()
    return parse_mosu00_html_text(raw, filename_hint=path.name)


def extract_mosu00_decision_date(text: str | None, filename_hint: str | None = None) -> str | None:
    normalized = normalize_mosu00_text(text)
    month_date = (
        r"(January|February|March|April|May|June|July|August|September|October|November|December)"
        r"\s+\d{1,2},\s+\d{4}"
    )
    patterns = [
        rf"\bMinutes\s+of\s+({month_date})\b",
        rf"\bOpinion\s+issued\s+({month_date})\b",
        rf"\bDate\s*:\s*({month_date})\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if match:
            parsed = _format_mosu00_date(match.group(1))
            if parsed:
                return parsed

    if filename_hint:
        from_file = _extract_date_from_mosu00_filename(filename_hint)
        if from_file:
            return from_file

    return None


def extract_mosu00_title_hint(text: str | None, filename_hint: str | None = None) -> str:
    normalized = normalize_mosu00_text(text)
    match = re.search(r"\b(Minutes\s+of\s+[A-Za-z]+\s+\d{1,2},\s+\d{4})\b", normalized, flags=re.IGNORECASE)
    if match:
        return match.group(1)
    return Path(filename_hint).stem if filename_hint else ""


def find_mosu00_source_file(file_name: str | None, reference_path: str | Path | None = None) -> Path | None:
    """Find a local MOSU00 HTML/PDF sample by filename for metadata extraction fallback."""
    if not file_name:
        return None

    raw_path = Path(str(file_name))
    if raw_path.is_absolute() and raw_path.exists():
        return raw_path

    name = raw_path.name
    roots = _candidate_source_roots(reference_path)
    for root in roots:
        if not root.exists() or not root.is_dir():
            continue
        direct = root / name
        if direct.exists():
            return direct
        try:
            matches = list(root.rglob(name))
        except OSError as exc:
            logging.debug("Skipped MOSU00 source search root %s: %s", root, exc)
            continue
        if matches:
            return max(matches, key=lambda p: p.stat().st_mtime)
    return None


def _candidate_source_roots(reference_path: str | Path | None = None) -> list[Path]:
    roots: list[Path] = []
    if reference_path:
        ref = Path(reference_path)
        if ref.is_file():
            roots.append(ref.parent)
        else:
            roots.append(ref)

    home = Path.home()
    roots.extend(
        [
            home / "Downloads" / "Case Law Auto-Routing Resources",
            home / "Downloads",
            home
            / "OneDrive - Reed Elsevier Group ICO Reed Elsevier Inc"
            / "Documents"
            / "SADM"
            / "SMD"
            / "Collections"
            / "mosu00",
            home / "Documents" / "SADM" / "SMD" / "Collections" / "mosu00",
        ]
    )
    return _dedupe_paths(roots)


def _extract_date_from_mosu00_filename(filename: str) -> str | None:
    name = Path(filename).stem
    match = re.search(r"Minutesof([A-Za-z]+)(\d{1,2})[_-](\d{4})", name, flags=re.IGNORECASE)
    if not match:
        return None
    return _format_mosu00_date(f"{match.group(1)} {match.group(2)}, {match.group(3)}")


def _format_mosu00_date(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = normalize_mosu00_text(value)
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%m/%d/%Y", "%m-%d-%Y"):
        try:
            return datetime.strptime(cleaned, fmt).strftime("%m-%d-%Y")
        except ValueError:
            continue
    return None


def _decode_html_bytes(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace")


def _row_value(row, key: str):
    if row is None:
        return None
    if hasattr(row, "get"):
        try:
            return row.get(key)
        except Exception:
            return None
    try:
        return row[key]
    except Exception:
        return None


def _dedupe_paths(paths: Iterable[Path]) -> list[Path]:
    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        key = str(path).lower()
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique
