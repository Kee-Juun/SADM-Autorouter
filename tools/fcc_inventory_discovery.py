"""Read-only FCC inventory discovery collector.

This tool is deliberately *not* an FCC router.  It is the evidence-gathering
step for adding one safely: it searches IRT inventory, downloads the returned
FDFCC000 PDFs, and checkpoints a report containing the result-table metadata.
It never opens a Modify form and contains no Process, Archive, Ready, or Save
actions.

The IRT search page has changed markup in the past.  Run ``--inspect-ui``
first if automatic field detection cannot confidently identify the Court and
Received Date controls.  A small JSON selector file can then be supplied with
``--selectors``; see ``FCC_DISCOVERY_GUIDE.md``.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from selenium.common.exceptions import JavascriptException, TimeoutException
from selenium.webdriver import Chrome
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.chromedriver_resolver import resolve_chromedriver_path  # noqa: E402


COURT_CODE = "FDFCC000"
DEFAULT_IRT_URL = "https://tcfabprod.lexisnexis.com/shared/InventoryInvoicing/"
REPORT_HEADERS = (
    "LNI",
    "Filename",
    "Docket Number",
    "Decision Date",
    "Date Received",
    "Route",
    "Source Detail",
    "Document Link",
    "Download Status",
)
IRT_SEARCH_SELECTORS = {
    # Verified from the live Search Inventory control inventory captured on
    # 2026-10-14.  Explicit --selectors values may override these if IRT is
    # redesigned later.
    "court": "#courtSearch",
    "received_from": "#receivedDateandTimeSearchFrom",
    "received_to": "#receivedDateandTimeSearchTo",
    "search": "#search",
}


@dataclass(frozen=True)
class FccInventoryRecord:
    """The fields retained from one IRT result row."""

    lni: str
    decision_date: str
    received_date: str
    route: str
    source_detail: str
    filename: str = ""
    docket_number: str = ""
    document_link: str = ""
    download_status: str = "Not downloaded"

    def as_report_row(self) -> list[str]:
        return [
            self.lni,
            self.filename,
            self.docket_number,
            self.decision_date,
            self.received_date,
            self.route,
            self.source_detail,
            self.document_link,
            self.download_status,
        ]


def normalise_text(value: str | None) -> str:
    """Lowercase a visible IRT label while retaining only comparison content."""
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def map_result_columns(headers: Iterable[str]) -> dict[str, int]:
    """Map slightly different result-table headings to the FCC report fields."""
    aliases = {
        "lni": ("lni", "document lni", "lexisnexis identifier"),
        "file_name": ("file name", "filename", "original file name"),
        "docket_number": ("docket no", "docket number", "docket"),
        "decision_date": ("decision date", "decided date", "date decision"),
        "received_date": ("date received", "received date", "received"),
        "route": ("route",),
        "source_detail": ("source detail", "source details"),
    }
    mapped: dict[str, int] = {}
    for index, heading in enumerate(headers):
        clean = normalise_text(heading)
        for field, names in aliases.items():
            if field not in mapped and any(clean == name or name in clean for name in names):
                mapped[field] = index
    return mapped


def required_report_columns_present(headers: Iterable[str]) -> bool:
    mapped = map_result_columns(headers)
    return all(field in mapped for field in ("lni", "decision_date", "received_date", "route", "source_detail"))


def default_output_paths() -> tuple[Path, Path]:
    base = Path.home() / "Downloads" / "Case Law Auto-Routing Resources" / "FCC Discovery"
    downloads = base / "FCC PDF Downloads"
    report = base / "FDFCC000_inventory_discovery.xlsx"
    return downloads, report


def load_selector_config(path: Path | None) -> dict[str, str]:
    if not path:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    required = {"court", "received_from", "received_to", "search"}
    missing = sorted(required - set(payload))
    if missing:
        raise ValueError(f"Selector file is missing: {', '.join(missing)}")
    return {key: str(value) for key, value in payload.items()}


def normalise_irt_date(value: str) -> str:
    """Accept a user-friendly date but send IRT its required mm-dd-yyyy form."""
    for pattern in ("%m-%d-%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(value.strip(), pattern).strftime("%m-%d-%Y")
        except ValueError:
            continue
    raise ValueError(f"Invalid date '{value}'. Use mm-dd-yyyy or mm/dd/yyyy.")


def build_driver(download_dir: Path, *, headless: bool = False) -> Chrome:
    """Create an isolated visible Chrome session with PDFs downloaded locally."""
    download_dir.mkdir(parents=True, exist_ok=True)
    options = Options()
    options.add_experimental_option(
        "prefs",
        {
            "download.default_directory": str(download_dir),
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "plugins.always_open_pdf_externally": True,
        },
    )
    if headless:
        options.add_argument("--headless=new")
        options.add_argument("--window-size=1920,1080")
    else:
        options.add_argument("--start-maximized")
    driver = Chrome(service=ChromeService(resolve_chromedriver_path()), options=options)
    driver.execute_cdp_cmd(
        "Page.setDownloadBehavior",
        {"behavior": "allow", "downloadPath": str(download_dir)},
    )
    return driver


class FccInventoryDiscovery:
    """Read-only IRT inventory search and download workflow for FCC discovery."""

    def __init__(
        self,
        driver: Chrome,
        *,
        output_dir: Path,
        report_path: Path,
        selectors: dict[str, str] | None = None,
        court_code: str = COURT_CODE,
    ) -> None:
        self.driver = driver
        self.output_dir = output_dir
        self.report_path = report_path
        self.selectors = selectors or {}
        self.court_code = str(court_code or COURT_CODE).strip().upper()
        self.records: dict[str, FccInventoryRecord] = self._load_report_records()

    def inspect_ui(self) -> list[dict[str, str]]:
        """Return non-sensitive labels/identifiers to help map IRT search controls."""
        return self.driver.execute_script(
            """
            return [...document.querySelectorAll('input, select, button, textarea')].map((el) => ({
              tag: el.tagName.toLowerCase(), id: el.id || '', name: el.name || '',
              type: el.type || '', placeholder: el.placeholder || '',
              ariaLabel: el.getAttribute('aria-label') || '', text: (el.innerText || '').trim(),
              label: (el.labels && [...el.labels].map((label) => label.innerText).join(' ')) || ''
            }));
            """
        )

    def save_ui_inventory(self) -> Path:
        path = self.report_path.with_name("fcc_search_ui_inventory.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.inspect_ui(), indent=2), encoding="utf-8")
        return path

    def open_search_inventory(self, inventory_url: str) -> None:
        self.driver.get(inventory_url)
        self._wait_for_ready_state(timeout_seconds=90)
        # The existing autorouter uses this menu location.  If IRT already
        # opened Search Inventory, this is a harmless no-op.
        for locator in (
            (By.XPATH, '//*[@id="menu"]/table/thead/tr/td[3]/h3/a'),
            (By.PARTIAL_LINK_TEXT, "Search Inventory"),
        ):
            try:
                element = self.driver.find_element(*locator)
                if element.is_displayed():
                    self.driver.execute_script("arguments[0].click();", element)
                    self._wait_for_ready_state(timeout_seconds=30)
                    break
            except Exception:
                continue

    def discover_search_selectors(self) -> dict[str, str]:
        """Find likely search inputs from labels; explicit JSON remains authoritative."""
        controls = self.inspect_ui()
        candidates: list[tuple[int, str, dict[str, str]]] = []
        for index, control in enumerate(controls):
            selector = self._selector_for_control(control)
            if selector:
                haystack = normalise_text(" ".join(control.values()))
                candidates.append((index, haystack, control | {"selector": selector}))

        def best(*terms: str, button: bool = False) -> str | None:
            matches = [
                item for item in candidates
                if all(term in item[1] for term in terms)
                and (not button or item[2].get("tag") == "button" or item[2].get("type") in {"submit", "button"})
            ]
            return matches[0][2]["selector"] if matches else None

        detected = {
            "court": best("court"),
            "received_from": best("received", "from") or best("date", "from"),
            "received_to": best("received", "to") or best("date", "to"),
            "search": best("search", button=True),
        }
        return {key: value for key, value in detected.items() if value}

    @staticmethod
    def _selector_for_control(control: dict[str, str]) -> str | None:
        if control.get("id"):
            return f"#{control['id']}"
        if control.get("name"):
            tag = control.get("tag", "input")
            return f'{tag}[name="{control["name"]}"]'
        return None

    def submit_search(self, *, date_from: str, date_to: str) -> None:
        # The known IRT IDs are more reliable than generic label matching.
        # A caller-supplied selector file remains the final override.
        selectors = self.discover_search_selectors() | IRT_SEARCH_SELECTORS | self.selectors
        missing = sorted({"court", "received_from", "received_to", "search"} - set(selectors))
        if missing:
            inventory_path = self.save_ui_inventory()
            raise RuntimeError(
                "Could not safely identify IRT search controls: "
                f"{', '.join(missing)}. Review {inventory_path} and provide --selectors."
            )
        self._set_control(selectors["court"], self.court_code)
        self._set_control(selectors["received_from"], normalise_irt_date(date_from))
        self._set_control(selectors["received_to"], normalise_irt_date(date_to))
        self.driver.find_element(By.CSS_SELECTOR, selectors["search"]).click()

    def wait_for_results(self, timeout_seconds: int = 3600, stable_seconds: int = 20) -> dict[str, Any]:
        """Wait until the result table's row count and content stop changing."""
        deadline = time.monotonic() + timeout_seconds
        last_signature = ""
        stable_since: float | None = None
        next_progress_log = time.monotonic()
        while time.monotonic() < deadline:
            table = self._result_table_payload()
            if table and table["rows"] and required_report_columns_present(table["headers"]):
                signature = json.dumps(table["rows"], sort_keys=True)
                if signature == last_signature:
                    stable_since = stable_since or time.monotonic()
                    if time.monotonic() - stable_since >= stable_seconds:
                        return table
                else:
                    last_signature = signature
                    stable_since = None
                if time.monotonic() >= next_progress_log:
                    logging.info(
                        "%s results detected: %s visible rows; waiting %s seconds for the page to settle before collection.",
                        self.court_code,
                        len(table["rows"]),
                        stable_seconds,
                    )
                    next_progress_log = time.monotonic() + 30
            elif time.monotonic() >= next_progress_log:
                if table and table.get("headers"):
                    logging.info(
                        "Waiting for the %s results table. Closest visible table has headers: %s",
                        self.court_code,
                        " | ".join(table["headers"]),
                    )
                else:
                    logging.info("Waiting for the %s search results table to appear after IRT search.", self.court_code)
                next_progress_log = time.monotonic() + 30
            time.sleep(2)
        raise TimeoutException(f"Results did not finish loading within {timeout_seconds} seconds.")

    def collect_pages(
        self,
        *,
        download_pdfs: bool,
        page_limit: int = 0,
        stable_seconds: int = 20,
    ) -> int:
        """Capture the one unpaginated IRT result set and optionally download PDFs.

        IRT's ``#searchTable`` explicitly has DataTables pagination disabled,
        so all matching FCC records are rendered in this one result set.
        ``page_limit`` is retained only for command-line compatibility and is
        deliberately ignored.
        """
        table = self.wait_for_results(stable_seconds=stable_seconds)
        rows = self._records_from_table(table)
        logging.info("%s result set contains %s records.", self.court_code, len(rows))
        for row_number, record in enumerate(rows, start=1):
            existing = self.records.get(record.lni)
            if existing and existing.download_status == "Downloaded":
                continue
            if download_pdfs and record.document_link:
                record = self._download_record(record)
            self.records[record.lni] = record
            # Large courts can have thousands of documents.  Persist progress
            # throughout the read-only collection so an interruption is
            # recoverable and the user can audit downloaded rows immediately.
            if row_number % 25 == 0:
                self._write_report()
                logging.info(
                    "%s discovery checkpoint: %s/%s result rows collected.",
                    self.court_code,
                    row_number,
                    len(rows),
                )
        self._write_report()
        return len(self.records)

    def _records_from_table(self, table: dict[str, Any]) -> list[FccInventoryRecord]:
        mapping = map_result_columns(table["headers"])
        records: list[FccInventoryRecord] = []
        for row in table["rows"]:
            cells = row.get("cells", [])
            if len(cells) <= max(mapping.values()):
                continue
            lni = cells[mapping["lni"]].strip()
            if not lni:
                continue
            # IRT's File name column is the verified document/PDF link.  Do
            # not fall back to a random link elsewhere in the row: those can
            # be LNI/detail actions rather than the source file.
            links_by_cell = row.get("links_by_cell", [])
            file_name_index = mapping.get("file_name")
            link = (
                links_by_cell[file_name_index][0]
                if file_name_index is not None
                and file_name_index < len(links_by_cell)
                and links_by_cell[file_name_index]
                else ""
            )
            records.append(
                FccInventoryRecord(
                    lni=lni,
                    filename=cells[mapping["file_name"]].strip() if "file_name" in mapping else "",
                    docket_number=cells[mapping["docket_number"]].strip() if "docket_number" in mapping else "",
                    decision_date=cells[mapping["decision_date"]].strip(),
                    received_date=cells[mapping["received_date"]].strip(),
                    route=cells[mapping["route"]].strip(),
                    source_detail=cells[mapping["source_detail"]].strip(),
                    document_link=link,
                )
            )
        return records

    def _result_table_payload(self) -> dict[str, Any] | None:
        """Read visible result rows only; no form values are changed here."""
        return self.driver.execute_script(
            """
            const clean = (value) => (value || '').replace(/\\s+/g, ' ').trim();
            const table = document.querySelector('#searchTable');
            if (!table) return null;
            const headerRows = [...table.querySelectorAll('thead tr')].map((tr) =>
              [...tr.querySelectorAll(':scope > th, :scope > td')].map((cell) => clean(cell.innerText)));
            const headers = headerRows.sort((left, right) =>
              right.filter(Boolean).length - left.filter(Boolean).length)[0] || [];
            const rows = [...table.querySelectorAll('tbody > tr.searchRow')].map((tr) => {
              const rowCells = [...tr.querySelectorAll(':scope > td')];
              const cells = rowCells.map((cell) => clean(cell.innerText));
              const linksByCell = rowCells.map((cell) =>
                [...cell.querySelectorAll('a[href]')].map((link) => link.href));
              return {cells, links_by_cell: linksByCell};
            }).filter((row) => row.cells.length);
            return {headers, rows};
            """
        )

    def _download_record(self, record: FccInventoryRecord) -> FccInventoryRecord:
        before = {path.name for path in self.output_dir.glob("*")}
        try:
            self.driver.execute_script("window.open(arguments[0], '_blank');", record.document_link)
            self._wait_for_download(before, timeout_seconds=90)
            if len(self.driver.window_handles) > 1:
                self.driver.switch_to.window(self.driver.window_handles[-1])
                self.driver.close()
                self.driver.switch_to.window(self.driver.window_handles[0])
            return FccInventoryRecord(**(asdict(record) | {"download_status": "Downloaded"}))
        except Exception as exc:
            logging.warning("Download failed for %s: %s", record.lni, exc)
            return FccInventoryRecord(**(asdict(record) | {"download_status": f"Failed: {type(exc).__name__}"}))

    def _wait_for_download(self, before: set[str], timeout_seconds: int) -> None:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            new_files = [path for path in self.output_dir.glob("*") if path.name not in before]
            if new_files and not any(path.suffix == ".crdownload" for path in new_files):
                return
            time.sleep(1)
        raise TimeoutException("PDF download did not complete.")

    def _set_control(self, selector: str, value: str) -> None:
        element = self.driver.find_element(By.CSS_SELECTOR, selector)
        if element.tag_name.lower() == "select":
            select = Select(element)
            try:
                select.select_by_visible_text(value)
            except Exception:
                select.select_by_value(value)
        else:
            element.click()
            element.send_keys(Keys.CONTROL, "a")
            element.send_keys(value)
        self.driver.execute_script(
            "arguments[0].dispatchEvent(new Event('input', {bubbles: true}));"
            "arguments[0].dispatchEvent(new Event('change', {bubbles: true}));",
            element,
        )

    def _load_report_records(self) -> dict[str, FccInventoryRecord]:
        if not self.report_path.exists():
            return {}
        workbook = load_workbook(self.report_path, read_only=True, data_only=True)
        sheet = workbook.active
        headers = [str(cell.value or "") for cell in next(sheet.iter_rows(min_row=1, max_row=1), ())]
        header_indexes = {normalise_text(value): index for index, value in enumerate(headers)}
        required_headers = {"lni", "decision date", "date received", "route", "source detail"}
        if not required_headers <= set(header_indexes):
            raise ValueError(f"Existing report has unexpected headers: {headers}")

        def value_at(row: tuple[Any, ...], heading: str) -> str:
            index = header_indexes.get(heading)
            return str(row[index] or "") if index is not None and index < len(row) else ""

        records: dict[str, FccInventoryRecord] = {}
        for row in sheet.iter_rows(min_row=2, values_only=True):
            lni = value_at(row, "lni")
            if lni:
                records[lni] = FccInventoryRecord(
                    lni=lni,
                    filename=value_at(row, "filename"),
                    docket_number=value_at(row, "docket number"),
                    decision_date=value_at(row, "decision date"),
                    received_date=value_at(row, "date received"),
                    route=value_at(row, "route"),
                    source_detail=value_at(row, "source detail"),
                    document_link=value_at(row, "document link"),
                    download_status=value_at(row, "download status") or "Not downloaded",
                )
        workbook.close()
        return records

    def _write_report(self) -> None:
        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = f"{self.court_code} Results"
        sheet.append(list(REPORT_HEADERS))
        for cell in sheet[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="1F4E78")
        for record in sorted(self.records.values(), key=lambda item: (item.received_date, item.lni)):
            sheet.append(record.as_report_row())
        for column, width in {"A": 28, "B": 42, "C": 28, "D": 18, "E": 22, "F": 20, "G": 32, "H": 70, "I": 22}.items():
            sheet.column_dimensions[column].width = width
        sheet.freeze_panes = "A2"
        workbook.save(self.report_path)
        workbook.close()

    def _wait_for_ready_state(self, timeout_seconds: int) -> None:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            try:
                if self.driver.execute_script("return document.readyState") == "complete":
                    return
            except JavascriptException:
                pass
            time.sleep(0.5)
        raise TimeoutException("Page did not finish loading.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only FCC IRT inventory discovery collector")
    parser.add_argument("--collect", action="store_true", help="Run the search. Without this, only inspect the IRT UI.")
    parser.add_argument("--download-pdfs", action="store_true", help="Download each returned document PDF.")
    parser.add_argument("--date-from", default="01-01-2026")
    parser.add_argument("--date-to", default="10-01-2026")
    parser.add_argument("--irt-url", default=DEFAULT_IRT_URL)
    parser.add_argument("--selectors", type=Path, help="JSON file with court, received_from, received_to, and search CSS selectors")
    parser.add_argument("--page-limit", type=int, default=0, help=argparse.SUPPRESS)
    parser.add_argument("--stable-seconds", type=int, default=20, help="Seconds a result table must remain stable")
    parser.add_argument("--headless", action="store_true", help="Use only after a visible session has been verified")
    parser.add_argument("--inspect-ui", action="store_true", help="Save available search labels/IDs and exit")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    download_dir, report_path = default_output_paths()
    driver = build_driver(download_dir, headless=args.headless)
    try:
        collector = FccInventoryDiscovery(
            driver,
            output_dir=download_dir,
            report_path=report_path,
            selectors=load_selector_config(args.selectors),
        )
        collector.open_search_inventory(args.irt_url)
        if args.inspect_ui or not args.collect:
            output = collector.save_ui_inventory()
            logging.info("Saved IRT search-control inventory to %s", output)
            return 0
        collector.submit_search(date_from=args.date_from, date_to=args.date_to)
        count = collector.collect_pages(
            download_pdfs=args.download_pdfs,
            page_limit=args.page_limit,
            stable_seconds=args.stable_seconds,
        )
        logging.info("FCC discovery complete: %s records checkpointed in %s", count, report_path)
        return 0
    finally:
        driver.quit()


if __name__ == "__main__":
    raise SystemExit(main())
