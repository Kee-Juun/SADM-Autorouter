"""Analyze FCC discovery PDFs against the saved IRT Search Inventory HTML.

This intentionally operates offline on a user-saved IRT result page.  It does
not open IRT or modify any inventory record.  It is used to study the evidence
needed before implementing FCC routing logic.
"""

from __future__ import annotations

import json
import re
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable

from pypdf import PdfReader


def normalise_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def normalise_compact(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


@dataclass(frozen=True)
class IrtResultRow:
    lni: str
    filename: str
    docket_number: str
    decision_date: str
    received_date: str
    route: str
    source_detail: str


@dataclass(frozen=True)
class PdfAudit:
    lni: str
    filename: str
    docket_number: str
    decision_date: str
    source_detail: str
    route: str
    filename_pattern: str
    local_pdf_status: str
    pdf_page_count: int
    content_title: str
    docket_match: str
    decision_date_match: str
    source_detail_evidence: str
    read_error: str = ""


class SearchTableParser(HTMLParser):
    """Parse the static IRT ``#searchTable`` without third-party HTML tools."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_table = False
        self.table_depth = 0
        self.in_thead = False
        self.in_tbody = False
        self.header_rows: list[list[str]] = []
        self.rows: list[list[str]] = []
        self.current_row: list[str] | None = None
        self.current_header = False
        self.current_cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "table" and attributes.get("id") == "searchTable":
            self.in_table = True
            self.table_depth = 1
            return
        if not self.in_table:
            return
        if tag == "table":
            self.table_depth += 1
        elif tag == "thead":
            self.in_thead = True
        elif tag == "tbody":
            self.in_tbody = True
        elif tag == "tr":
            self.current_row = []
            self.current_header = self.in_thead
        elif tag in {"th", "td"} and self.current_row is not None:
            self.current_cell = []

    def handle_endtag(self, tag: str) -> None:
        if not self.in_table:
            return
        if tag in {"th", "td"} and self.current_cell is not None and self.current_row is not None:
            self.current_row.append(" ".join("".join(self.current_cell).split()))
            self.current_cell = None
        elif tag == "tr" and self.current_row is not None:
            if self.current_header:
                self.header_rows.append(self.current_row)
            elif self.in_tbody and self.current_row:
                self.rows.append(self.current_row)
            self.current_row = None
        elif tag == "thead":
            self.in_thead = False
        elif tag == "tbody":
            self.in_tbody = False
        elif tag == "table":
            self.table_depth -= 1
            if self.table_depth == 0:
                self.in_table = False

    def handle_data(self, data: str) -> None:
        if self.current_cell is not None:
            self.current_cell.append(data)


def parse_irt_results(html_path: Path) -> dict[str, IrtResultRow]:
    parser = SearchTableParser()
    parser.feed(html_path.read_text(encoding="cp1252", errors="replace"))
    headers = max(parser.header_rows, key=lambda row: sum(bool(value) for value in row), default=[])
    indexes = {normalise_header(value): index for index, value in enumerate(headers)}

    def index_for(*names: str) -> int:
        for name in names:
            if name in indexes:
                return indexes[name]
        raise ValueError(f"IRT heading missing. Expected one of {names}; found {headers}")

    fields = {
        "lni": index_for("lni"),
        "filename": index_for("file name", "filename"),
        "docket_number": index_for("docket no", "docket number"),
        "decision_date": index_for("decided date", "decision date"),
        "received_date": index_for("received date", "date received"),
        "route": index_for("route"),
        "source_detail": index_for("source detail", "source details"),
    }
    parsed: dict[str, IrtResultRow] = {}
    for row in parser.rows:
        if len(row) <= max(fields.values()):
            continue
        lni = row[fields["lni"]].strip()
        if lni:
            parsed[lni] = IrtResultRow(**{name: row[index].strip() for name, index in fields.items()})
    return parsed


def filename_pattern(filename: str) -> str:
    lower = filename.lower()
    if lower.startswith("mc"):
        return "mc missing-case filename"
    if lower.startswith("ldc_smd_") and lower.endswith("_e2e.pdf"):
        return "standard LDC_SMD E2E"
    return "other filename pattern"


def parse_irt_date(value: str) -> datetime | None:
    match = re.search(r"(\d{4})-(\d{2})-(\d{2})", value)
    return datetime.strptime(match.group(0), "%Y-%m-%d") if match else None


def content_title(text: str) -> str:
    for line in text.splitlines():
        candidate = " ".join(line.split())
        if len(candidate) >= 4 and re.search(r"\b(ORDER|OPINION|NOTICE|MEMORANDUM|REPORT|RELEASE)\b", candidate, re.I):
            return candidate[:180]
    return ""


def date_matches_content(decision_date: str, text: str) -> str:
    expected = parse_irt_date(decision_date)
    if not expected:
        return "IRT date unavailable"
    numeric_forms = {
        expected.strftime("%m/%d/%Y"),
        expected.strftime("%m-%d-%Y"),
        expected.strftime("%Y-%m-%d"),
        f"{expected.month}/{expected.day}/{expected.year}",
    }
    textual_forms = {
        f"{expected.strftime('%B')} {expected.day}, {expected.year}".lower(),
        expected.strftime("%B %d, %Y").lower(),
    }
    compact = normalise_compact(text)
    if any(normalise_compact(item) in compact for item in numeric_forms | textual_forms):
        return "Matched in sampled text"
    return "Not found in sampled text"


def docket_matches_content(docket_number: str, text: str) -> str:
    if not docket_number or normalise_header(docket_number) in {"no number in original", "n a", "na"}:
        return "Not applicable: no docket in IRT"
    expected = normalise_compact(docket_number)
    return "Matched in sampled text" if expected and expected in normalise_compact(text) else "Not found in sampled text"


def source_detail_evidence(source_detail: str, title: str) -> str:
    source = source_detail.strip().upper()
    title_upper = title.upper()
    if source == "OP":
        return "Opinion title found" if "OPINION" in title_upper else "No Opinion title found"
    if source == "OR":
        return "Order title found" if "ORDER" in title_upper else "No Order title found"
    if source == "E":
        return "Excluded: content classification not evaluated"
    return "No rule yet for this Source Detail"


def sampled_pdf_text(pdf_path: Path) -> tuple[str, int]:
    reader = PdfReader(pdf_path)
    page_count = len(reader.pages)
    indexes = list(dict.fromkeys([0, 1, page_count - 1]))
    text = "\n".join(reader.pages[index].extract_text() or "" for index in indexes if 0 <= index < page_count)
    return text, page_count


def audit_pdf(row: IrtResultRow, downloads_dir: Path) -> PdfAudit:
    local_path = downloads_dir / row.filename
    pattern = filename_pattern(row.filename)
    audit_fields = {
        "lni": row.lni,
        "filename": row.filename,
        "docket_number": row.docket_number,
        "decision_date": row.decision_date,
        "source_detail": row.source_detail,
        "route": row.route,
    }
    if not local_path.exists():
        return PdfAudit(
            **audit_fields, filename_pattern=pattern, local_pdf_status="File not found", pdf_page_count=0,
            content_title="", docket_match="Not assessed", decision_date_match="Not assessed",
            source_detail_evidence="Not assessed",
        )
    try:
        text, page_count = sampled_pdf_text(local_path)
        title = content_title(text)
        return PdfAudit(
            **audit_fields, filename_pattern=pattern, local_pdf_status="Read", pdf_page_count=page_count,
            content_title=title, docket_match=docket_matches_content(row.docket_number, text),
            decision_date_match=date_matches_content(row.decision_date, text),
            source_detail_evidence=source_detail_evidence(row.source_detail, title),
        )
    except Exception as exc:
        return PdfAudit(
            **audit_fields, filename_pattern=pattern, local_pdf_status="Unreadable", pdf_page_count=0,
            content_title="", docket_match="Not assessed", decision_date_match="Not assessed",
            source_detail_evidence="Not assessed", read_error=f"{type(exc).__name__}: {exc}",
        )


def write_audit_json(rows: Iterable[PdfAudit], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps([asdict(row) for row in rows], indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline FCC PDF audit using a saved IRT Search Inventory HTML page")
    parser.add_argument("--html", type=Path, required=True)
    parser.add_argument("--pdf-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()

    irt_rows = list(parse_irt_results(args.html).values())
    audits: list[PdfAudit] = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = [executor.submit(audit_pdf, row, args.pdf_dir) for row in irt_rows]
        for completed, future in enumerate(as_completed(futures), start=1):
            audits.append(future.result())
            if completed % 100 == 0 or completed == len(irt_rows):
                print(f"Audited {completed}/{len(irt_rows)} PDFs...", flush=True)
    audits.sort(key=lambda row: row.lni)
    write_audit_json(audits, args.output)
    print(f"Audited {len(audits)} IRT rows. Output: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
