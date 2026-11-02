"""Read-only NLRB (FDNLRB00) inventory discovery collector.

This is the evidence-gathering stage for a future NLRB Autorouter. It searches
IRT, saves the result-table metadata, and downloads the document linked in the
File Name column. It never opens Modify or performs any IRT processing action.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

try:  # Supports both ``python tools/...`` and test/package imports.
    from .fcc_inventory_discovery import (
        DEFAULT_IRT_URL,
        FccInventoryDiscovery,
        build_driver,
        load_selector_config,
    )
except ImportError:  # pragma: no cover - direct script execution path
    from fcc_inventory_discovery import (
        DEFAULT_IRT_URL,
        FccInventoryDiscovery,
        build_driver,
        load_selector_config,
    )


COURT_CODE = "FDNLRB00"
DEFAULT_DATE_FROM = "01-01-2026"
DEFAULT_DATE_TO = "10-15-2026"


def default_output_paths() -> tuple[Path, Path]:
    base = Path.home() / "Downloads" / "Case Law Auto-Routing Resources" / "NLRB Discovery"
    return base / "NLRB PDF Downloads", base / "FDNLRB00_inventory_discovery.xlsx"


class NlrbInventoryDiscovery(FccInventoryDiscovery):
    """NLRB-configured version of the proven read-only discovery collector."""

    def __init__(self, *args, **kwargs) -> None:
        kwargs["court_code"] = COURT_CODE
        super().__init__(*args, **kwargs)

    def save_ui_inventory(self) -> Path:
        path = self.report_path.with_name("nlrb_search_ui_inventory.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.inspect_ui(), indent=2), encoding="utf-8")
        return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only NLRB IRT inventory discovery collector")
    parser.add_argument("--collect", action="store_true", help="Run the search; otherwise only inspect IRT controls.")
    parser.add_argument("--download-pdfs", action="store_true", help="Download each File Name document from the results.")
    parser.add_argument("--date-from", default=DEFAULT_DATE_FROM)
    parser.add_argument("--date-to", default=DEFAULT_DATE_TO)
    parser.add_argument("--irt-url", default=DEFAULT_IRT_URL)
    parser.add_argument("--selectors", type=Path, help="JSON override for court, received_from, received_to, and search selectors")
    parser.add_argument("--stable-seconds", type=int, default=20, help="Seconds the unpaginated result set must remain stable")
    parser.add_argument("--headless", action="store_true", help="Use only after a visible run has verified the IRT controls")
    parser.add_argument("--inspect-ui", action="store_true", help="Save available search labels/IDs and exit")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    download_dir, report_path = default_output_paths()
    driver = build_driver(download_dir, headless=args.headless)
    try:
        collector = NlrbInventoryDiscovery(
            driver,
            output_dir=download_dir,
            report_path=report_path,
            selectors=load_selector_config(args.selectors),
        )
        collector.open_search_inventory(args.irt_url)
        if args.inspect_ui or not args.collect:
            output = collector.save_ui_inventory()
            logging.info("Saved NLRB IRT search-control inventory to %s", output)
            return 0
        collector.submit_search(date_from=args.date_from, date_to=args.date_to)
        count = collector.collect_pages(
            download_pdfs=args.download_pdfs,
            stable_seconds=args.stable_seconds,
        )
        logging.info("NLRB discovery complete: %s records checkpointed in %s", count, report_path)
        return 0
    finally:
        driver.quit()


if __name__ == "__main__":
    raise SystemExit(main())
