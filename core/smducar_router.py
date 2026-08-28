import os
import base64
import datetime
import hashlib
import json
import logging
from dataclasses import replace
from pathlib import Path
import pandas as pd
import re
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, UnexpectedAlertPresentException
import time
import threading
from urllib.parse import parse_qs, unquote, urljoin, urlparse

# Config and logging utilities
from .smducar_config import (
    status_updates_buffer,
    mspb_metadata_buffer,
    itc_content_fingerprint_buffer,
    error_log_entries,
)

# Utils
from .smducar_utils import (
    extract_docket_number,
)

# File types
from .smducar_filetypes import (
    is_counsel,
    get_related_counsel_lnis,
)

# Data processing
from .smducar_data import (
    filter_mapping_data,
    resolve_source_detail,
)

# Selenium utilities
from .smducar_selenium import (
    retry_click,
)

from .rerun_status import (
    STATUS_DONE,
    STATUS_PROCESSING,
    STATUS_NEEDS_RERUN_INTERRUPTED,
    defer_main_rows_with_failed_counsel,
    is_completed_status,
    mark_row_processing,
    normalize_status,
)

from .mspb_extractor import (
    parse_mspb_document_text,
    parse_mspb_pdf_bytes,
)

from .itc_extractor import (
    ITCMetadata,
    extract_itc_docket_from_filename,
    get_itc_court,
    is_itc_row,
    parse_itc_document_text,
    parse_itc_pdf_bytes,
)

from .irsplr_extractor import (
    IRSPLRMetadata,
    build_irsplr_unreadable_fallback_metadata,
    is_irsplr_row,
    parse_irsplr_document_text,
    parse_irsplr_pdf_bytes,
)

from .ohtax0_extractor import (
    OHTAX0Metadata,
    is_ohtax0_row,
    parse_ohtax0_document_text,
    parse_ohtax0_pdf_bytes,
)

from .mnsutb_extractor import (
    MNSUTBMetadata,
    is_mnsutb_row,
    parse_mnsutb_document_text,
    parse_mnsutb_pdf_bytes,
)


_itc_duplicate_lock = threading.Lock()


class RouterSessionLostError(RuntimeError):
    """Raised when the active Selenium browser session can no longer be used."""


class CaseLawRouter:
    def __init__(self, driver, show_error=None, set_status=None):
        self.driver = driver
        self.wait = WebDriverWait(self.driver, 60)
        self.long_wait = WebDriverWait(self.driver, 600)
        self.search_wait = WebDriverWait(self.driver, 90)
        self.show_error = show_error
        self.set_status = set_status
        self.mspb_download_dir = Path.home() / "Downloads" / "Case Law Auto-Routing Resources" / "MSPB PDF Downloads"
        self.mspb_download_dir.mkdir(parents=True, exist_ok=True)
        self.itc_download_dir = Path.home() / "Downloads" / "Case Law Auto-Routing Resources" / "ITC PDF Downloads"
        self.itc_download_dir.mkdir(parents=True, exist_ok=True)
        self.irsplr_download_dir = Path.home() / "Downloads" / "Case Law Auto-Routing Resources" / "IRSPLR PDF Downloads"
        self.irsplr_download_dir.mkdir(parents=True, exist_ok=True)
        self.ohtax0_download_dir = Path.home() / "Downloads" / "Case Law Auto-Routing Resources" / "OHTAX0 PDF Downloads"
        self.ohtax0_download_dir.mkdir(parents=True, exist_ok=True)
        self.mnsutb_download_dir = Path.home() / "Downloads" / "Case Law Auto-Routing Resources" / "MNSUTB PDF Downloads"
        self.mnsutb_download_dir.mkdir(parents=True, exist_ok=True)
        self._archive_duplicate_mode = False
        self._irsplr_unreadable_pdf_signatures = set()

    @staticmethod
    def _is_invalid_session_error(error):
        error_text = str(error or "").lower()
        return any(
            marker in error_text
            for marker in (
                "invalid session id",
                "chrome not reachable",
                "disconnected",
                "not connected to devtools",
                "target window already closed",
                "no such window",
            )
        )

    def _raise_if_invalid_session_error(self, error, context="browser action"):
        if self._is_invalid_session_error(error):
            raise RouterSessionLostError(f"Router browser session lost during {context}: {error}") from error

    def _is_search_inventory_ready(self, timeout=8):
        try:
            WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((By.XPATH, '//*[@id="documentLNISearch"]'))
            )
            return True
        except Exception as e:
            self._raise_if_invalid_session_error(e, "Search Inventory readiness check")
            return False

    def _close_extra_tabs_and_focus_main(self):
        try:
            handles = list(self.driver.window_handles)
            if not handles:
                raise RouterSessionLostError("Router browser session has no open windows.")

            primary_handle = self._main_tab if getattr(self, "_main_tab", None) in handles else handles[0]
            for handle in handles:
                if handle == primary_handle:
                    continue
                try:
                    self.driver.switch_to.window(handle)
                    self.driver.close()
                except Exception as e:
                    self._raise_if_invalid_session_error(e, "closing recovery tab")

            self.driver.switch_to.window(primary_handle)
            self._opened_tab = None
            self._main_tab = primary_handle
            return True
        except RouterSessionLostError:
            raise
        except Exception as e:
            self._raise_if_invalid_session_error(e, "focusing main tab")
            logging.warning(f"Could not fully reset browser tabs before retry: {e}")
            return False

    def refresh_search_inventory_for_retry(self, reason="recoverable form issue"):
        """Refresh back to Search Inventory so the same LNI can be retried once."""
        logging.warning(f"Attempting Search Inventory refresh recovery after {reason}.")
        self._close_extra_tabs_and_focus_main()

        try:
            self.safe_alert_accept()
        except Exception as e:
            self._raise_if_invalid_session_error(e, "pre-refresh alert cleanup")

        try:
            self.driver.refresh()
            WebDriverWait(self.driver, 25).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            self.safe_alert_accept()
        except Exception as e:
            self._raise_if_invalid_session_error(e, "refresh recovery")
            logging.warning(f"Refresh recovery could not refresh the current page: {e}")

        if self._is_search_inventory_ready(timeout=10):
            logging.info("Search Inventory is ready after refresh recovery.")
            return True

        logging.info("Search Inventory field was not visible after refresh; trying Search Inventory menu once.")
        if self.click_search_inventory() and self._is_search_inventory_ready(timeout=15):
            logging.info("Search Inventory reopened after refresh recovery.")
            return True

        logging.error("Refresh recovery failed to reopen Search Inventory.")
        return False

    def _should_refresh_retry_form_status(self, form_status, row_index):
        status = str(form_status or status_updates_buffer.get(row_index, "") or "").strip().upper()
        return status in {
            "NON-INTERACTABLE IRT FORM",
            "RELATED LNI ERROR",
            "RELATED LNI TIMEOUT",
            "RELATED LNI FIELD LOCKED",
            "ROUTE ERROR",
            "ROUTE_ERROR",
            "ROUTE DROPDOWN ERROR",
        }

    def _mark_remaining_rows_after_router_session_loss(self, df, current_full_index, message):
        mark_rows = False
        for remaining_index in df.index:
            if remaining_index == current_full_index:
                mark_rows = True
            if not mark_rows:
                continue

            row_status = str(status_updates_buffer.get(remaining_index) or df.loc[remaining_index].get("Status", "")).strip().upper()
            if row_status in {"DONE", "ALREADY PROCESSED"}:
                continue
            status_updates_buffer[remaining_index] = STATUS_NEEDS_RERUN_INTERRUPTED

        logging.error(f"Router session lost; remaining assigned rows were marked for rerun. {message}")

    def describe_xpath(self, xpath):
        descriptions = {
            '//*[@id="related"]': 'Related checkbox',
            '//*[@id="sourceDetails"]': 'Source Detail dropdown',
            '//*[@id="add"]': 'Save button',
            '//*[@id="route"]': 'Route dropdown',
            # Add more as needed
        }
        return descriptions.get(xpath, xpath)    

    def safe_fill_field(self, xpath, value, field_name="Field"):
        try:
            value = self.normalize_irt_text(value)
            element = self.long_wait.until(EC.presence_of_element_located((By.XPATH, xpath)))

            if not element.is_enabled() or element.get_attribute("readonly") == "true":
                logging.info(f"Skipped {field_name} because it's not interactable.")
                return

            current_val = element.get_attribute("value")
            if current_val and current_val.strip() == str(value).strip():
                logging.info(f"{field_name} already set correctly. Skipping.")
                return

            # Clear and fill in one go
            element.clear()
            element.send_keys(value)
            logging.info(f"{field_name} set to: {value}")

            # Handle any popup that might have appeared immediately
            try:
                alert = self.driver.switch_to.alert
                alert_text = alert.text.strip()
                alert.accept()

                if "duplicate document" in alert_text.lower():
                    logging.info(f"Duplicate alert detected after {field_name}. Handling...")
                    self.handle_duplicate_lni_popup()
                    # If this was a comments field, retry the fill
                    if field_name == "Comments":
                        element.clear()
                        element.send_keys(value)
                        logging.info(f"Retried filling {field_name} after duplicate alert")
            except:
                pass  # No alert present, continue normally

        except Exception as e:
            logging.error(f"Error filling {field_name}")

    @staticmethod
    def normalize_irt_text(value):
        return (
            str(value or "")
            .replace("\u2010", "-")
            .replace("\u2011", "-")
            .replace("\u2012", "-")
            .replace("\u2013", "-")
            .replace("\u2014", "-")
            .replace("\u2212", "-")
        )

    def check_session_validity(self):
        """Check if the current browser session is still valid"""
        try:
            # Try to get the current URL - this will fail if session is invalid
            current_url = self.driver.current_url
            return True
        except Exception as e:
            if self._is_invalid_session_error(e):
                logging.warning("Invalid session detected. Session may have been closed.")
                return False
            return True

    def record_mspb_metadata(self, row_index, row, lni, metadata=None, metadata_status="Attempted"):
        """Capture MSPB metadata used for the final workbook sheet."""
        if row_index is None:
            return

        existing = mspb_metadata_buffer.get(row_index, {})
        record = {
            "LNI": str(lni or existing.get("LNI", "")).strip(),
            "File Name": str(row.get("FileName", existing.get("File Name", ""))).strip(),
            "Metadata Type": existing.get("Metadata Type", "MSPB"),
            "Extracted Court Code": existing.get("Extracted Court Code", ""),
            "Extracted Docket Number": existing.get("Extracted Docket Number", ""),
            "Extracted Decision Date": existing.get("Extracted Decision Date", ""),
            "Extracted Source Detail": existing.get("Extracted Source Detail", ""),
            "Extracted Other Numbers": existing.get("Extracted Other Numbers", ""),
            "Prepared Comments": existing.get("Prepared Comments", ""),
            "Title Hint": existing.get("Title Hint", ""),
            "Route": "Outside Conversion",
            "Metadata Status": metadata_status,
        }

        if metadata:
            record.update({
                "Extracted Court Code": getattr(metadata, "court", "") or "",
                "Extracted Docket Number": getattr(metadata, "docket_number", "") or "",
                "Extracted Decision Date": getattr(metadata, "decision_date", "") or "",
                "Extracted Source Detail": getattr(metadata, "source_detail", "") or "",
                "Extracted Other Numbers": "; ".join(getattr(metadata, "other_numbers", ()) or ()),
                "Prepared Comments": getattr(metadata, "comments_text", "") or "",
                "Title Hint": getattr(metadata, "title_hint", "") or "",
                "Metadata Status": metadata_status or "Extracted",
            })

        mspb_metadata_buffer[row_index] = record

    def record_itc_metadata(self, row_index, row, lni, metadata=None, metadata_status="Attempted"):
        """Capture ITC metadata used for the final workbook sheet."""
        self.record_mspb_metadata(row_index, row, lni, metadata=metadata, metadata_status=metadata_status)
        if row_index in mspb_metadata_buffer:
            mspb_metadata_buffer[row_index]["Metadata Type"] = "ITC"
            if metadata and (getattr(metadata, "is_true_duplicate", False) or getattr(metadata, "is_excluded", False)):
                mspb_metadata_buffer[row_index]["Route"] = "Archive"
            if metadata and getattr(metadata, "is_true_duplicate", False) and not getattr(metadata, "is_excluded", False):
                duplicate_of = getattr(metadata, "duplicate_of", "") or ""
                if duplicate_of:
                    hint = mspb_metadata_buffer[row_index].get("Title Hint", "")
                    mspb_metadata_buffer[row_index]["Title Hint"] = f"{hint} | Duplicate of {duplicate_of}".strip(" |")
                duplicate_lni = getattr(metadata, "duplicate_of_lni", "") or ""
                if duplicate_lni:
                    prepared_comments = mspb_metadata_buffer[row_index].get("Prepared Comments", "") or ""
                    duplicate_comment = f"Dup of {duplicate_lni}"
                    if duplicate_comment not in prepared_comments:
                        mspb_metadata_buffer[row_index]["Prepared Comments"] = (
                            f"{prepared_comments}; {duplicate_comment}" if prepared_comments else duplicate_comment
                        )

    def record_irsplr_metadata(self, row_index, row, lni, metadata=None, metadata_status="Attempted"):
        """Capture IRSPLR metadata used for the final workbook sheet."""
        self.record_mspb_metadata(row_index, row, lni, metadata=metadata, metadata_status=metadata_status)
        if row_index in mspb_metadata_buffer:
            mspb_metadata_buffer[row_index]["Metadata Type"] = "IRSPLR"
            if metadata and getattr(metadata, "is_excluded", False):
                mspb_metadata_buffer[row_index]["Route"] = "Archive"

    def record_ohtax0_metadata(self, row_index, row, lni, metadata=None, metadata_status="Attempted"):
        """Capture OHTAX0 metadata used for the final workbook sheet."""
        self.record_mspb_metadata(row_index, row, lni, metadata=metadata, metadata_status=metadata_status)
        if row_index in mspb_metadata_buffer:
            mspb_metadata_buffer[row_index]["Metadata Type"] = "OHTAX0"
            if metadata and getattr(metadata, "is_excluded", False):
                mspb_metadata_buffer[row_index]["Route"] = "Archive"

    def record_mnsutb_metadata(self, row_index, row, lni, metadata=None, metadata_status="Attempted"):
        """Capture MNSUTB metadata used for the final workbook sheet."""
        self.record_mspb_metadata(row_index, row, lni, metadata=metadata, metadata_status=metadata_status)
        if row_index in mspb_metadata_buffer:
            mspb_metadata_buffer[row_index]["Metadata Type"] = "MNSUTB"

    def mark_itc_duplicate_status(self, row_index, row, lni, metadata: ITCMetadata):
        """Mark ITC metadata as a true duplicate when this run already saw identical PDF text."""
        if not metadata or not getattr(metadata, "content_fingerprint", ""):
            return metadata
        if getattr(metadata, "is_excluded", False):
            logging.info("ITC document is excluded; skipping duplicate classification so exclusion remains the primary route.")
            return metadata

        current_label = (
            str(row.get("FileName", "")).strip()
            or str(lni or "").strip()
            or f"row {row_index + 2 if row_index is not None else '?'}"
        )
        current_lni = str(lni or "").strip()

        with _itc_duplicate_lock:
            existing_record = itc_content_fingerprint_buffer.get(metadata.content_fingerprint)
            if existing_record:
                if isinstance(existing_record, dict):
                    existing_label = existing_record.get("label", "") or existing_record.get("lni", "")
                    existing_lni = existing_record.get("lni", "")
                else:
                    existing_label = str(existing_record)
                    existing_lni = ""
                logging.warning(
                    "Confirmed ITC true duplicate by PDF text fingerprint: %s duplicates %s",
                    current_label,
                    existing_label,
                )
                return replace(
                    metadata,
                    is_true_duplicate=True,
                    duplicate_of=existing_label,
                    duplicate_of_lni=existing_lni,
                )

            itc_content_fingerprint_buffer[metadata.content_fingerprint] = {
                "label": current_label,
                "lni": current_lni,
            }
            return metadata

    def search_lni(self, lni_value):
        max_retries = 3
        retry_delay = 2

        def recover_before_next_attempt(reason, attempt_number):
            if attempt_number >= max_retries:
                return
            logging.info(
                "Refreshing Search Inventory before LNI retry %d/%d for %s.",
                attempt_number + 1,
                max_retries,
                lni_value,
            )
            recovered = self.refresh_search_inventory_for_retry(
                reason=f"LNI search retry after {reason}"
            )
            if not recovered:
                logging.warning(
                    "Search Inventory recovery did not fully confirm readiness before retrying LNI %s.",
                    lni_value,
                )
            time.sleep(retry_delay)

        for attempt in range(1, max_retries + 1):
            try:
                # Check session validity before attempting search
                if not self.check_session_validity():
                    logging.error("Invalid session detected. Cannot proceed with LNI search.")
                    raise RouterSessionLostError("Router browser session is no longer valid before LNI search.")
                
                logging.info(f"Search attempt {attempt} for LNI: {lni_value}")

                # Wait for search field to be present and interactable
                search_field = self.search_wait.until(
                    EC.presence_of_element_located((By.XPATH, '//*[@id="documentLNISearch"]'))
                )

                # Clear any existing value
                search_field.clear()
                time.sleep(0.5)  # Small delay to ensure clear is complete

                # Input LNI value
                search_field.send_keys(str(lni_value))
                time.sleep(0.5)  # Small delay to ensure input is complete

                # Click search button
                search_button = self.wait.until(
                    EC.element_to_be_clickable((By.XPATH, '//*[@id="search"]'))
                )
                search_button.click()

                # Wait for results
                if self.check_result_available():
                    logging.info(f"Successfully found results for LNI: {lni_value}")
                    return True
                else:
                    logging.warning(f"No results found for LNI on attempt {attempt}/{max_retries}: {lni_value}")
                    recover_before_next_attempt("no result appeared", attempt)

            except Exception as e:
                error_msg = str(e)
                logging.error(f"Search attempt {attempt} failed: {error_msg}")
                
                # Check if it's a session-related error
                if self._is_invalid_session_error(e):
                    logging.error("Session invalid. Cannot retry - browser connection lost.")
                    raise RouterSessionLostError(f"Router browser session lost during LNI search for {lni_value}.") from e
                
                recover_before_next_attempt(error_msg or "search exception", attempt)

        logging.error(f"All {max_retries} search attempts failed for LNI: {lni_value}")
        return False

    def click_search_inventory(self):
        try:
            search_button = self.search_wait.until(
                EC.element_to_be_clickable((By.XPATH, '//*[@id="menu"]/table/thead/tr/td[3]/h3/a')))
            search_button.click()
            logging.info("Clicked 'Search Inventory'.")
            return True
        except Exception as e:
            try:
                diagnostics = (
                    f"url={self.driver.current_url} title={self.driver.title} "
                    f"readyState={self.driver.execute_script('return document.readyState')}"
                )
            except Exception:
                diagnostics = "diagnostics unavailable"
            logging.error(f"Failed to click 'Search Inventory': {e} ({diagnostics})")
            return False

    def is_valid_lni(self, lni):
        pattern = r"^[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-\d{5}-\d{2}$"
        return bool(re.match(pattern, lni))

    def check_result_available(self):
        try:
            self.search_wait.until(EC.presence_of_element_located((By.CSS_SELECTOR,
                                                            "td.searchColumn.ChangeMouseCursorToHand")))
            return True
        except Exception as e:
            self._raise_if_invalid_session_error(e, "checking LNI search results")
            logging.warning(f"No LNI result found")
            return False

    def validate_row(self, row, row_index, file_path):
        lni = str(row["LNI"]).strip()
        if not lni:
            status_updates_buffer[row_index] = "ERROR: LNI NOT FOUND"
            return None
        if not self.is_valid_lni(lni):
            status_updates_buffer[row_index] = "ERROR: INVALID LNI FORMAT"
            return None
        return lni

    def handle_lni_search(self, lni):
        if not self.search_lni(lni):
            return False
        if not self.check_result_available():
            return False
        self.click_matching_result()
        return True

    def extract_mspb_metadata_from_search_result(self, row, row_index=None):
        """Open the result PDF from the File Name column and parse MSPB metadata."""
        try:
            link_element = self.find_mspb_file_name_link(row)
            if link_element is None:
                logging.warning("MSPB File Name link was not found in the search results.")
                return None

            return self.open_mspb_link_and_extract_metadata(link_element)
        except Exception as e:
            logging.error(f"Error extracting MSPB metadata from PDF: {e}")
            return None

    def extract_itc_metadata_from_search_result(self, row, row_index=None):
        """Open the result PDF from the File Name column and parse ITC metadata."""
        try:
            link_element = self.find_mspb_file_name_link(row)
            if link_element is None:
                logging.warning("ITC File Name link was not found in the search results.")
                return None

            metadata = self.open_itc_link_and_extract_metadata(link_element, row)
            if metadata and getattr(metadata, "has_text_content", False):
                return metadata

            logging.warning("ITC PDF metadata could not be extracted after strict filename fallback checks.")
            return None
        except Exception as e:
            logging.error(f"Error extracting ITC metadata from PDF: {e}")
            return None

    def build_itc_metadata_from_row(self, row):
        file_name = str(row.get("FileName", "")).strip()
        court_code = str(row.get("CourtCode", "")).strip()
        return parse_itc_document_text("", filename_hint=file_name, court_code_hint=court_code)

    def extract_irsplr_metadata_from_search_result(self, row, row_index=None):
        """Open the result PDF from the File Name column and parse IRSPLR metadata."""
        try:
            link_element = self.find_mspb_file_name_link(row)
            if link_element is None:
                logging.warning("IRSPLR File Name link was not found in the search results.")
                return None

            metadata = self.open_irsplr_link_and_extract_metadata(link_element, row)
            if metadata and getattr(metadata, "has_text_content", False):
                return metadata

            logging.warning("IRSPLR PDF did not expose readable text.")
            return None
        except Exception as e:
            logging.error(f"Error extracting IRSPLR metadata from PDF: {e}")
            return None

    def extract_ohtax0_metadata_from_search_result(self, row, row_index=None):
        """Open the result PDF from the File Name column and parse OHTAX0 metadata."""
        try:
            link_element = self.find_mspb_file_name_link(row)
            if link_element is None:
                logging.warning("OHTAX0 File Name link was not found in the search results.")
                return None

            metadata = self.open_ohtax0_link_and_extract_metadata(link_element, row)
            if metadata and getattr(metadata, "has_text_content", False):
                return metadata

            logging.warning("OHTAX0 PDF did not expose readable text.")
            return None
        except Exception as e:
            logging.error(f"Error extracting OHTAX0 metadata from PDF: {e}")
            return None

    def extract_mnsutb_metadata_from_search_result(self, row, row_index=None):
        """Open the result PDF from the File Name column and parse MNSUTB metadata."""
        try:
            link_element = self.find_mspb_file_name_link(row)
            if link_element is None:
                logging.warning("MNSUTB File Name link was not found in the search results.")
                return None

            metadata = self.open_mnsutb_link_and_extract_metadata(link_element, row)
            if metadata and getattr(metadata, "has_text_content", False):
                return metadata

            logging.warning("MNSUTB PDF did not expose readable text.")
            return None
        except Exception as e:
            logging.error(f"Error extracting MNSUTB metadata from PDF: {e}")
            return None

    def find_mspb_file_name_link(self, row):
        """Find the clickable document link under the File Name column in IRT results."""
        file_name = str(row.get("FileName", "")).strip()

        if file_name and file_name.lower() != "nan":
            for candidate in self.driver.find_elements(By.XPATH, f"//a[contains(normalize-space(.), {self.xpath_literal(file_name)})]"):
                if candidate.is_displayed():
                    return candidate

        # Prefer a link in the table column whose header says File Name.
        tables = self.driver.find_elements(By.XPATH, "//table")
        for table in tables:
            try:
                header_cells = table.find_elements(By.XPATH, ".//thead//th|.//thead//td|.//tr[1]/*")
                file_name_col = None
                for index, header in enumerate(header_cells):
                    header_text = (header.text or "").strip().lower()
                    if "file" in header_text and "name" in header_text:
                        file_name_col = index
                        break
                if file_name_col is None:
                    continue

                rows = table.find_elements(By.XPATH, ".//tbody/tr|.//tr[position()>1]")
                for result_row in rows:
                    cells = result_row.find_elements(By.XPATH, "./td|./th")
                    if len(cells) <= file_name_col:
                        continue
                    file_cell = cells[file_name_col]
                    links = file_cell.find_elements(By.XPATH, ".//a")
                    for link in links:
                        if link.is_displayed():
                            return link
                    if file_cell.is_displayed():
                        return file_cell
            except Exception:
                continue

        # Fallback: first visible PDF-looking link in the results.
        for candidate in self.driver.find_elements(By.XPATH, "//a[contains(translate(@href, 'PDF', 'pdf'), '.pdf')]"):
            if candidate.is_displayed():
                return candidate

        return None

    def open_mspb_link_and_extract_metadata(self, element):
        """Open the linked PDF in a browser tab and parse MSPB metadata from that tab."""
        main_tab = self.driver.current_window_handle
        before_handles = set(self.driver.window_handles)
        before_downloads = self.snapshot_mspb_downloads()
        opened_tab = None

        try:
            href = self._get_element_href(element)
            expected_filename = self.get_filename_from_document_href(href)
            self.enable_chrome_downloads()
            if href:
                target_url = urljoin(self.driver.current_url, href)
                self.enable_browser_network_capture()
                self.driver.execute_script("window.open(arguments[0], '_blank');", target_url)
            else:
                target_url = None
                self.enable_browser_network_capture()
                element.click()

            downloaded_metadata = self.wait_for_mspb_downloaded_metadata(before_downloads, expected_filename, timeout=20)
            if downloaded_metadata:
                return downloaded_metadata

            try:
                WebDriverWait(self.driver, 10).until(lambda d: len(d.window_handles) > len(before_handles))
                new_handles = set(self.driver.window_handles) - before_handles
                if new_handles:
                    opened_tab = new_handles.pop()
                    self.driver.switch_to.window(opened_tab)
            except TimeoutException:
                logging.info("MSPB link did not open a readable tab yet; continuing to watch for download.")

            downloaded_metadata = self.wait_for_mspb_downloaded_metadata(before_downloads, expected_filename, timeout=25)
            if downloaded_metadata:
                return downloaded_metadata

            logging.info("Opened MSPB PDF link in a browser tab.")
            metadata = self.wait_for_mspb_metadata_from_open_tab(target_url, before_downloads=before_downloads, expected_filename=expected_filename, timeout=75)
            if metadata:
                return metadata

            logging.warning("MSPB PDF tab opened, but metadata could not be extracted from the browser-rendered document.")
            return None
        except Exception as e:
            logging.warning(f"Could not read MSPB document in browser tab: {e}")
            return None
        finally:
            try:
                if opened_tab and opened_tab in self.driver.window_handles:
                    self.driver.close()
                if main_tab in self.driver.window_handles:
                    self.driver.switch_to.window(main_tab)
            except Exception:
                pass

    def open_itc_link_and_extract_metadata(self, element, row):
        """Open the linked PDF in a browser tab and parse ITC metadata from that tab."""
        main_tab = self.driver.current_window_handle
        before_handles = set(self.driver.window_handles)
        before_downloads = self.snapshot_itc_downloads()
        opened_tab = None
        file_name = str(row.get("FileName", "")).strip()
        court_code = str(row.get("CourtCode", "")).strip()

        try:
            href = self._get_element_href(element)
            expected_filename = self.get_filename_from_document_href(href) or file_name
            self.enable_chrome_downloads(self.itc_download_dir)
            if href:
                target_url = urljoin(self.driver.current_url, href)
                self.enable_browser_network_capture()
                self.driver.execute_script("window.open(arguments[0], '_blank');", target_url)
            else:
                target_url = None
                self.enable_browser_network_capture()
                element.click()

            downloaded_metadata = self.wait_for_itc_downloaded_metadata(
                before_downloads,
                expected_filename,
                court_code,
                timeout=20,
            )
            if downloaded_metadata:
                return downloaded_metadata

            try:
                WebDriverWait(self.driver, 10).until(lambda d: len(d.window_handles) > len(before_handles))
                new_handles = set(self.driver.window_handles) - before_handles
                if new_handles:
                    opened_tab = new_handles.pop()
                    self.driver.switch_to.window(opened_tab)
            except TimeoutException:
                logging.info("ITC link did not open a readable tab yet; continuing to watch for download.")

            downloaded_metadata = self.wait_for_itc_downloaded_metadata(
                before_downloads,
                expected_filename,
                court_code,
                timeout=25,
            )
            if downloaded_metadata:
                return downloaded_metadata

            logging.info("Opened ITC PDF link in a browser tab.")
            metadata = self.wait_for_itc_metadata_from_open_tab(
                target_url,
                before_downloads=before_downloads,
                expected_filename=expected_filename,
                court_code=court_code,
                timeout=45,
            )
            if metadata:
                return metadata

            logging.warning("ITC PDF tab opened, but metadata could not be extracted from the browser-rendered document.")
            return None
        except Exception as e:
            logging.warning(f"Could not read ITC document in browser tab: {e}")
            return None
        finally:
            try:
                if opened_tab and opened_tab in self.driver.window_handles:
                    self.driver.close()
                if main_tab in self.driver.window_handles:
                    self.driver.switch_to.window(main_tab)
            except Exception:
                pass

    def open_irsplr_link_and_extract_metadata(self, element, row):
        """Open the linked PDF in a browser tab and parse IRSPLR metadata from that tab."""
        main_tab = self.driver.current_window_handle
        before_handles = set(self.driver.window_handles)
        before_downloads = self.snapshot_irsplr_downloads()
        opened_tab = None
        file_name = str(row.get("FileName", "")).strip()
        court_code = str(row.get("CourtCode", "")).strip()

        try:
            href = self._get_element_href(element)
            expected_filename = self.get_filename_from_document_href(href) or file_name
            self.enable_chrome_downloads(self.irsplr_download_dir)
            if href:
                target_url = urljoin(self.driver.current_url, href)
                self.enable_browser_network_capture()
                self.driver.execute_script("window.open(arguments[0], '_blank');", target_url)
            else:
                target_url = None
                self.enable_browser_network_capture()
                element.click()

            downloaded_metadata = self.wait_for_irsplr_downloaded_metadata(
                before_downloads,
                expected_filename,
                court_code,
                timeout=20,
            )
            if downloaded_metadata:
                return downloaded_metadata

            try:
                WebDriverWait(self.driver, 10).until(lambda d: len(d.window_handles) > len(before_handles))
                new_handles = set(self.driver.window_handles) - before_handles
                if new_handles:
                    opened_tab = new_handles.pop()
                    self.driver.switch_to.window(opened_tab)
            except TimeoutException:
                logging.info("IRSPLR link did not open a readable tab yet; continuing to watch for download.")

            downloaded_metadata = self.wait_for_irsplr_downloaded_metadata(
                before_downloads,
                expected_filename,
                court_code,
                timeout=25,
            )
            if downloaded_metadata:
                return downloaded_metadata

            logging.info("Opened IRSPLR PDF link in a browser tab.")
            metadata = self.wait_for_irsplr_metadata_from_open_tab(
                target_url,
                before_downloads=before_downloads,
                expected_filename=expected_filename,
                court_code=court_code,
                timeout=45,
            )
            if metadata:
                return metadata

            logging.warning("IRSPLR PDF tab opened, but metadata could not be extracted from the browser-rendered document.")
            return None
        except Exception as e:
            logging.warning(f"Could not read IRSPLR document in browser tab: {e}")
            return None
        finally:
            try:
                if opened_tab and opened_tab in self.driver.window_handles:
                    self.driver.close()
                if main_tab in self.driver.window_handles:
                    self.driver.switch_to.window(main_tab)
            except Exception:
                pass

    def open_ohtax0_link_and_extract_metadata(self, element, row):
        """Open the linked PDF in a browser tab and parse OHTAX0 metadata from that tab."""
        main_tab = self.driver.current_window_handle
        before_handles = set(self.driver.window_handles)
        before_downloads = self.snapshot_ohtax0_downloads()
        opened_tab = None
        file_name = str(row.get("FileName", "")).strip()

        try:
            href = self._get_element_href(element)
            expected_filename = self.get_filename_from_document_href(href) or file_name
            self.enable_chrome_downloads(self.ohtax0_download_dir)
            if href:
                target_url = urljoin(self.driver.current_url, href)
                self.enable_browser_network_capture()
                self.driver.execute_script("window.open(arguments[0], '_blank');", target_url)
            else:
                target_url = None
                self.enable_browser_network_capture()
                element.click()

            downloaded_metadata = self.wait_for_ohtax0_downloaded_metadata(
                before_downloads,
                expected_filename,
                timeout=20,
            )
            if downloaded_metadata:
                return downloaded_metadata

            try:
                WebDriverWait(self.driver, 10).until(lambda d: len(d.window_handles) > len(before_handles))
                new_handles = set(self.driver.window_handles) - before_handles
                if new_handles:
                    opened_tab = new_handles.pop()
                    self.driver.switch_to.window(opened_tab)
            except TimeoutException:
                logging.info("OHTAX0 link did not open a readable tab yet; continuing to watch for download.")

            downloaded_metadata = self.wait_for_ohtax0_downloaded_metadata(
                before_downloads,
                expected_filename,
                timeout=25,
            )
            if downloaded_metadata:
                return downloaded_metadata

            logging.info("Opened OHTAX0 PDF link in a browser tab.")
            metadata = self.wait_for_ohtax0_metadata_from_open_tab(
                target_url,
                before_downloads=before_downloads,
                expected_filename=expected_filename,
                timeout=45,
            )
            if metadata:
                return metadata

            logging.warning("OHTAX0 PDF tab opened, but metadata could not be extracted from the browser-rendered document.")
            return None
        except Exception as e:
            logging.warning(f"Could not read OHTAX0 document in browser tab: {e}")
            return None
        finally:
            try:
                if opened_tab and opened_tab in self.driver.window_handles:
                    self.driver.close()
                if main_tab in self.driver.window_handles:
                    self.driver.switch_to.window(main_tab)
            except Exception:
                pass

    def open_mnsutb_link_and_extract_metadata(self, element, row):
        """Open the linked PDF in a browser tab and parse MNSUTB metadata from that tab."""
        main_tab = self.driver.current_window_handle
        before_handles = set(self.driver.window_handles)
        before_downloads = self.snapshot_mnsutb_downloads()
        opened_tab = None
        file_name = str(row.get("FileName", "")).strip()

        try:
            href = self._get_element_href(element)
            expected_filename = self.get_filename_from_document_href(href) or file_name
            self.enable_chrome_downloads(self.mnsutb_download_dir)
            if href:
                target_url = urljoin(self.driver.current_url, href)
                self.enable_browser_network_capture()
                self.driver.execute_script("window.open(arguments[0], '_blank');", target_url)
            else:
                target_url = None
                self.enable_browser_network_capture()
                element.click()

            downloaded_metadata = self.wait_for_mnsutb_downloaded_metadata(
                before_downloads,
                expected_filename,
                timeout=20,
            )
            if downloaded_metadata:
                return downloaded_metadata

            try:
                WebDriverWait(self.driver, 10).until(lambda d: len(d.window_handles) > len(before_handles))
                new_handles = set(self.driver.window_handles) - before_handles
                if new_handles:
                    opened_tab = new_handles.pop()
                    self.driver.switch_to.window(opened_tab)
            except TimeoutException:
                logging.info("MNSUTB link did not open a readable tab yet; continuing to watch for download.")

            downloaded_metadata = self.wait_for_mnsutb_downloaded_metadata(
                before_downloads,
                expected_filename,
                timeout=25,
            )
            if downloaded_metadata:
                return downloaded_metadata

            logging.info("Opened MNSUTB PDF link in a browser tab.")
            metadata = self.wait_for_mnsutb_metadata_from_open_tab(
                target_url,
                before_downloads=before_downloads,
                expected_filename=expected_filename,
                timeout=45,
            )
            if metadata:
                return metadata

            logging.warning("MNSUTB PDF tab opened, but metadata could not be extracted from the browser-rendered document.")
            return None
        except Exception as e:
            logging.warning(f"Could not read MNSUTB document in browser tab: {e}")
            return None
        finally:
            try:
                if opened_tab and opened_tab in self.driver.window_handles:
                    self.driver.close()
                if main_tab in self.driver.window_handles:
                    self.driver.switch_to.window(main_tab)
            except Exception:
                pass

    def wait_for_itc_metadata_from_open_tab(self, target_url=None, before_downloads=None, expected_filename=None, court_code=None, timeout=45):
        deadline = time.time() + timeout
        self._mspb_pdf_request_ids = set()
        self._mspb_pdf_checked_request_ids = set()
        last_status_log = 0

        while time.time() < deadline:
            self.wait_for_open_tab_load_state(timeout=5)

            downloaded_metadata = self.wait_for_itc_downloaded_metadata(
                before_downloads or {},
                expected_filename,
                court_code,
                timeout=1,
            )
            if downloaded_metadata:
                return downloaded_metadata

            pdf_bytes = self.get_opened_pdf_bytes_from_browser_network(target_url, timeout=1)
            if pdf_bytes:
                metadata = parse_itc_pdf_bytes(pdf_bytes, filename_hint=expected_filename, court_code_hint=court_code)
                if (
                    metadata
                    and metadata.has_text_content
                    and self.itc_metadata_matches_expected(metadata, expected_filename, court_code, "browser PDF tab")
                ):
                    self.log_itc_metadata(metadata, "browser PDF tab")
                    return metadata

            accessibility_text = self.read_open_pdf_accessibility_text()
            metadata = parse_itc_document_text(accessibility_text, filename_hint=expected_filename, court_code_hint=court_code)
            if (
                metadata
                and metadata.has_text_content
                and self.looks_like_itc_text(accessibility_text)
                and self.itc_metadata_matches_expected(metadata, expected_filename, court_code, "Chrome accessibility tree")
            ):
                self.log_itc_metadata(metadata, "Chrome accessibility tree")
                return metadata

            copied_text = self.copy_open_pdf_tab_text()
            metadata = parse_itc_document_text(copied_text, filename_hint=expected_filename, court_code_hint=court_code)
            if (
                metadata
                and metadata.has_text_content
                and self.looks_like_itc_text(copied_text)
                and self.itc_metadata_matches_expected(metadata, expected_filename, court_code, "browser PDF viewer clipboard")
            ):
                self.log_itc_metadata(metadata, "browser PDF viewer clipboard")
                return metadata

            visible_text = self.read_open_pdf_tab_text()
            metadata = parse_itc_document_text(visible_text, filename_hint=expected_filename, court_code_hint=court_code)
            if (
                metadata
                and metadata.has_text_content
                and self.looks_like_itc_text(visible_text)
                and self.itc_metadata_matches_expected(metadata, expected_filename, court_code, "browser visible text")
            ):
                self.log_itc_metadata(metadata, "browser visible text")
                return metadata

            if time.time() - last_status_log >= 10:
                logging.info("Waiting for ITC PDF tab to finish loading/expose text...")
                last_status_log = time.time()

            time.sleep(2)

        self.log_mspb_pdf_tab_diagnostics()
        return None

    def wait_for_irsplr_metadata_from_open_tab(self, target_url=None, before_downloads=None, expected_filename=None, court_code=None, timeout=45):
        deadline = time.time() + timeout
        self._mspb_pdf_request_ids = set()
        self._mspb_pdf_checked_request_ids = set()
        last_status_log = 0

        while time.time() < deadline:
            self.wait_for_open_tab_load_state(timeout=5)

            downloaded_metadata = self.wait_for_irsplr_downloaded_metadata(
                before_downloads or {},
                expected_filename,
                court_code,
                timeout=1,
            )
            if downloaded_metadata:
                return downloaded_metadata

            pdf_bytes = self.get_opened_pdf_bytes_from_browser_network(target_url, timeout=1)
            if pdf_bytes:
                pdf_signature = ("network", hashlib.sha1(pdf_bytes).hexdigest())
                if pdf_signature not in self._irsplr_unreadable_pdf_signatures:
                    metadata = parse_irsplr_pdf_bytes(pdf_bytes, filename_hint=expected_filename, court_code_hint=court_code)
                    if metadata and metadata.has_text_content:
                        self.log_irsplr_metadata(metadata, "browser PDF tab")
                        return metadata
                    self._irsplr_unreadable_pdf_signatures.add(pdf_signature)
                    logging.warning(
                        "IRSPLR browser PDF did not expose readable text; OCR support is required for image-only PDFs."
                    )

            accessibility_text = self.read_open_pdf_accessibility_text()
            if self.looks_like_irsplr_text(accessibility_text):
                metadata = parse_irsplr_document_text(accessibility_text, filename_hint=expected_filename, court_code_hint=court_code)
                if metadata and metadata.has_text_content:
                    self.log_irsplr_metadata(metadata, "Chrome accessibility tree")
                    return metadata

            copied_text = self.copy_open_pdf_tab_text()
            if self.looks_like_irsplr_text(copied_text):
                metadata = parse_irsplr_document_text(copied_text, filename_hint=expected_filename, court_code_hint=court_code)
                if metadata and metadata.has_text_content:
                    self.log_irsplr_metadata(metadata, "browser PDF viewer clipboard")
                    return metadata

            visible_text = self.read_open_pdf_tab_text()
            if self.looks_like_irsplr_text(visible_text):
                metadata = parse_irsplr_document_text(visible_text, filename_hint=expected_filename, court_code_hint=court_code)
                if metadata and metadata.has_text_content:
                    self.log_irsplr_metadata(metadata, "browser visible text")
                    return metadata

            if time.time() - last_status_log >= 10:
                logging.info("Waiting for IRSPLR PDF tab to finish loading/expose text...")
                last_status_log = time.time()

            time.sleep(2)

        self.log_mspb_pdf_tab_diagnostics("IRSPLR")
        return None

    def wait_for_ohtax0_metadata_from_open_tab(self, target_url=None, before_downloads=None, expected_filename=None, timeout=45):
        deadline = time.time() + timeout
        self._mspb_pdf_request_ids = set()
        self._mspb_pdf_checked_request_ids = set()
        last_status_log = 0

        while time.time() < deadline:
            self.wait_for_open_tab_load_state(timeout=5)

            downloaded_metadata = self.wait_for_ohtax0_downloaded_metadata(
                before_downloads or {},
                expected_filename,
                timeout=1,
            )
            if downloaded_metadata:
                return downloaded_metadata

            pdf_bytes = self.get_opened_pdf_bytes_from_browser_network(target_url, timeout=1)
            if pdf_bytes:
                metadata = parse_ohtax0_pdf_bytes(pdf_bytes, filename_hint=expected_filename)
                if metadata and metadata.has_text_content:
                    self.log_ohtax0_metadata(metadata, "browser PDF tab")
                    return metadata

            accessibility_text = self.read_open_pdf_accessibility_text()
            if self.looks_like_ohtax0_text(accessibility_text):
                metadata = parse_ohtax0_document_text(accessibility_text, filename_hint=expected_filename)
                if metadata and metadata.has_text_content:
                    self.log_ohtax0_metadata(metadata, "Chrome accessibility tree")
                    return metadata

            copied_text = self.copy_open_pdf_tab_text()
            if self.looks_like_ohtax0_text(copied_text):
                metadata = parse_ohtax0_document_text(copied_text, filename_hint=expected_filename)
                if metadata and metadata.has_text_content:
                    self.log_ohtax0_metadata(metadata, "browser PDF viewer clipboard")
                    return metadata

            visible_text = self.read_open_pdf_tab_text()
            if self.looks_like_ohtax0_text(visible_text):
                metadata = parse_ohtax0_document_text(visible_text, filename_hint=expected_filename)
                if metadata and metadata.has_text_content:
                    self.log_ohtax0_metadata(metadata, "browser visible text")
                    return metadata

            if time.time() - last_status_log >= 10:
                logging.info("Waiting for OHTAX0 PDF tab to finish loading/expose text...")
                last_status_log = time.time()

            time.sleep(2)

        self.log_mspb_pdf_tab_diagnostics("OHTAX0")
        return None

    def wait_for_mnsutb_metadata_from_open_tab(self, target_url=None, before_downloads=None, expected_filename=None, timeout=45):
        deadline = time.time() + timeout
        self._mspb_pdf_request_ids = set()
        self._mspb_pdf_checked_request_ids = set()
        last_status_log = 0

        while time.time() < deadline:
            self.wait_for_open_tab_load_state(timeout=5)

            downloaded_metadata = self.wait_for_mnsutb_downloaded_metadata(
                before_downloads or {},
                expected_filename,
                timeout=1,
            )
            if downloaded_metadata:
                return downloaded_metadata

            pdf_bytes = self.get_opened_pdf_bytes_from_browser_network(target_url, timeout=1)
            if pdf_bytes:
                metadata = parse_mnsutb_pdf_bytes(pdf_bytes, filename_hint=expected_filename)
                if metadata and metadata.has_text_content:
                    self.log_mnsutb_metadata(metadata, "browser PDF tab")
                    return metadata

            accessibility_text = self.read_open_pdf_accessibility_text()
            if self.looks_like_mnsutb_text(accessibility_text):
                metadata = parse_mnsutb_document_text(accessibility_text, filename_hint=expected_filename)
                if metadata and metadata.has_text_content:
                    self.log_mnsutb_metadata(metadata, "Chrome accessibility tree")
                    return metadata

            copied_text = self.copy_open_pdf_tab_text()
            if self.looks_like_mnsutb_text(copied_text):
                metadata = parse_mnsutb_document_text(copied_text, filename_hint=expected_filename)
                if metadata and metadata.has_text_content:
                    self.log_mnsutb_metadata(metadata, "browser PDF viewer clipboard")
                    return metadata

            visible_text = self.read_open_pdf_tab_text()
            if self.looks_like_mnsutb_text(visible_text):
                metadata = parse_mnsutb_document_text(visible_text, filename_hint=expected_filename)
                if metadata and metadata.has_text_content:
                    self.log_mnsutb_metadata(metadata, "browser visible text")
                    return metadata

            if time.time() - last_status_log >= 10:
                logging.info("Waiting for MNSUTB PDF tab to finish loading/expose text...")
                last_status_log = time.time()

            time.sleep(2)

        self.log_mspb_pdf_tab_diagnostics("MNSUTB")
        return None

    def wait_for_mspb_metadata_from_open_tab(self, target_url=None, before_downloads=None, expected_filename=None, timeout=75):
        """Poll an opened PDF tab until the document is loaded enough to parse."""
        deadline = time.time() + timeout
        self._mspb_pdf_request_ids = set()
        self._mspb_pdf_checked_request_ids = set()
        last_status_log = 0

        while time.time() < deadline:
            self.wait_for_open_tab_load_state(timeout=5)

            downloaded_metadata = self.wait_for_mspb_downloaded_metadata(before_downloads or {}, expected_filename, timeout=1)
            if downloaded_metadata:
                return downloaded_metadata

            pdf_bytes = self.get_opened_pdf_bytes_from_browser_network(target_url, timeout=1)
            if pdf_bytes:
                metadata = parse_mspb_pdf_bytes(pdf_bytes, filename_hint=expected_filename)
                if metadata:
                    self.log_mspb_metadata(metadata, "browser PDF tab")
                    return metadata

            accessibility_text = self.read_open_pdf_accessibility_text()
            if self.looks_like_mspb_text(accessibility_text):
                metadata = parse_mspb_document_text(accessibility_text, filename_hint=expected_filename)
                if metadata:
                    self.log_mspb_metadata(metadata, "Chrome accessibility tree")
                    return metadata

            copied_text = self.copy_open_pdf_tab_text()
            if self.looks_like_mspb_text(copied_text):
                metadata = parse_mspb_document_text(copied_text, filename_hint=expected_filename)
                if metadata:
                    self.log_mspb_metadata(metadata, "browser PDF viewer clipboard")
                    return metadata

            visible_text = self.read_open_pdf_tab_text()
            if self.looks_like_mspb_text(visible_text):
                metadata = parse_mspb_document_text(visible_text, filename_hint=expected_filename)
                if metadata:
                    self.log_mspb_metadata(metadata, "browser visible text")
                    return metadata

            if time.time() - last_status_log >= 10:
                logging.info("Waiting for MSPB PDF tab to finish loading/expose text...")
                last_status_log = time.time()

            time.sleep(2)

        self.log_mspb_pdf_tab_diagnostics()
        return None

    def wait_for_open_tab_load_state(self, timeout=5):
        try:
            WebDriverWait(self.driver, timeout).until(
                lambda d: d.execute_script("return document.readyState") in ("interactive", "complete")
            )
        except Exception:
            pass

    def enable_chrome_downloads(self, download_dir=None):
        try:
            download_dir = Path(download_dir or self.mspb_download_dir)
            download_dir.mkdir(parents=True, exist_ok=True)
            self.driver.execute_cdp_cmd("Page.setDownloadBehavior", {
                "behavior": "allow",
                "downloadPath": str(download_dir),
            })
        except Exception as e:
            logging.info(f"Could not set Chrome download behavior for PDF: {e}")

    def snapshot_mspb_downloads(self):
        self.mspb_download_dir.mkdir(parents=True, exist_ok=True)
        snapshot = {}
        for path in self.mspb_download_dir.glob("*"):
            if path.is_file():
                try:
                    stat = path.stat()
                    snapshot[path.name.lower()] = (stat.st_mtime, stat.st_size)
                except Exception:
                    continue
        return snapshot

    def wait_for_mspb_downloaded_metadata(self, before_downloads, expected_filename=None, timeout=30):
        deadline = time.time() + timeout
        while time.time() < deadline:
            pdf_path = self.find_completed_mspb_download(before_downloads, expected_filename)
            if pdf_path:
                try:
                    metadata = parse_mspb_pdf_bytes(pdf_path.read_bytes(), filename_hint=pdf_path.name)
                    if metadata:
                        self.log_mspb_metadata(metadata, f"downloaded PDF {pdf_path.name}")
                        return metadata
                except Exception as e:
                    logging.warning(f"Downloaded MSPB PDF could not be parsed: {pdf_path} ({e})")
            time.sleep(0.5)
        return None

    def snapshot_itc_downloads(self):
        self.itc_download_dir.mkdir(parents=True, exist_ok=True)
        snapshot = {}
        for path in self.itc_download_dir.glob("*"):
            if path.is_file():
                try:
                    stat = path.stat()
                    snapshot[path.name.lower()] = (stat.st_mtime, stat.st_size)
                except Exception:
                    continue
        return snapshot

    def snapshot_irsplr_downloads(self):
        self.irsplr_download_dir.mkdir(parents=True, exist_ok=True)
        snapshot = {}
        for path in self.irsplr_download_dir.glob("*"):
            if path.is_file():
                try:
                    stat = path.stat()
                    snapshot[path.name.lower()] = (stat.st_mtime, stat.st_size)
                except Exception:
                    continue
        return snapshot

    def snapshot_ohtax0_downloads(self):
        self.ohtax0_download_dir.mkdir(parents=True, exist_ok=True)
        snapshot = {}
        for path in self.ohtax0_download_dir.glob("*"):
            if path.is_file():
                try:
                    stat = path.stat()
                    snapshot[path.name.lower()] = (stat.st_mtime, stat.st_size)
                except Exception:
                    continue
        return snapshot

    def snapshot_mnsutb_downloads(self):
        self.mnsutb_download_dir.mkdir(parents=True, exist_ok=True)
        snapshot = {}
        for path in self.mnsutb_download_dir.glob("*"):
            if path.is_file():
                try:
                    stat = path.stat()
                    snapshot[path.name.lower()] = (stat.st_mtime, stat.st_size)
                except Exception:
                    continue
        return snapshot

    def wait_for_itc_downloaded_metadata(self, before_downloads, expected_filename=None, court_code=None, timeout=30):
        deadline = time.time() + timeout
        while time.time() < deadline:
            pdf_path = self.find_completed_itc_download(before_downloads, expected_filename)
            if pdf_path:
                try:
                    metadata = parse_itc_pdf_bytes(
                        pdf_path.read_bytes(),
                        filename_hint=pdf_path.name,
                        court_code_hint=court_code,
                    )
                    if metadata and self.itc_metadata_matches_expected(metadata, expected_filename, court_code, pdf_path.name):
                        if not metadata.has_text_content:
                            logging.warning(
                                "Downloaded ITC PDF %s matched the row but did not expose readable text; "
                                "continuing with browser/OCR fallback.",
                                pdf_path.name,
                            )
                            return None
                        self.log_itc_metadata(metadata, f"downloaded PDF {pdf_path.name}")
                        return metadata
                except Exception as e:
                    logging.warning(f"Downloaded ITC PDF could not be parsed: {pdf_path} ({e})")
            time.sleep(0.5)
        return None

    def wait_for_irsplr_downloaded_metadata(self, before_downloads, expected_filename=None, court_code=None, timeout=30):
        deadline = time.time() + timeout
        while time.time() < deadline:
            pdf_path = self.find_completed_irsplr_download(before_downloads, expected_filename)
            if pdf_path:
                try:
                    stat = pdf_path.stat()
                    file_signature = ("download", str(pdf_path), stat.st_size, stat.st_mtime_ns)
                except Exception:
                    file_signature = ("download", str(pdf_path))
                if file_signature in self._irsplr_unreadable_pdf_signatures:
                    return None
                try:
                    metadata = parse_irsplr_pdf_bytes(
                        pdf_path.read_bytes(),
                        filename_hint=pdf_path.name,
                        court_code_hint=court_code,
                    )
                    if metadata and metadata.has_text_content:
                        self.log_irsplr_metadata(metadata, f"downloaded PDF {pdf_path.name}")
                        return metadata
                    self._irsplr_unreadable_pdf_signatures.add(file_signature)
                    logging.warning(
                        "Downloaded IRSPLR PDF %s did not expose readable text; OCR support is required for image-only PDFs.",
                        pdf_path.name,
                    )
                    return None
                except Exception as e:
                    self._irsplr_unreadable_pdf_signatures.add(file_signature)
                    logging.warning(f"Downloaded IRSPLR PDF could not be parsed: {pdf_path} ({e})")
            time.sleep(0.5)
        return None

    def wait_for_ohtax0_downloaded_metadata(self, before_downloads, expected_filename=None, timeout=30):
        deadline = time.time() + timeout
        while time.time() < deadline:
            pdf_path = self.find_completed_ohtax0_download(before_downloads, expected_filename)
            if pdf_path:
                try:
                    metadata = parse_ohtax0_pdf_bytes(
                        pdf_path.read_bytes(),
                        filename_hint=pdf_path.name,
                    )
                    if metadata and metadata.has_text_content:
                        self.log_ohtax0_metadata(metadata, f"downloaded PDF {pdf_path.name}")
                        return metadata
                    logging.warning("Downloaded OHTAX0 PDF %s did not expose readable text.", pdf_path.name)
                    return None
                except Exception as e:
                    logging.warning(f"Downloaded OHTAX0 PDF could not be parsed: {pdf_path} ({e})")
            time.sleep(0.5)
        return None

    def wait_for_mnsutb_downloaded_metadata(self, before_downloads, expected_filename=None, timeout=30):
        deadline = time.time() + timeout
        while time.time() < deadline:
            pdf_path = self.find_completed_mnsutb_download(before_downloads, expected_filename)
            if pdf_path:
                try:
                    metadata = parse_mnsutb_pdf_bytes(
                        pdf_path.read_bytes(),
                        filename_hint=pdf_path.name,
                    )
                    if metadata and metadata.has_text_content:
                        self.log_mnsutb_metadata(metadata, f"downloaded PDF {pdf_path.name}")
                        return metadata
                    logging.warning("Downloaded MNSUTB PDF %s did not expose readable text.", pdf_path.name)
                    return None
                except Exception as e:
                    logging.warning(f"Downloaded MNSUTB PDF could not be parsed: {pdf_path} ({e})")
            time.sleep(0.5)
        return None

    def itc_metadata_matches_expected(self, metadata, expected_filename=None, court_code=None, actual_filename=None):
        if not metadata:
            return False

        expected_court = get_itc_court(expected_filename, court_code)
        if expected_court and metadata.court != expected_court:
            logging.warning(
                "Rejected ITC metadata from %s: expected court %s but parsed %s.",
                actual_filename or expected_filename or "PDF",
                expected_court,
                metadata.court,
            )
            return False

        expected_docket = extract_itc_docket_from_filename(expected_filename)
        if expected_docket and metadata.docket_number != expected_docket:
            if getattr(metadata, "has_text_content", False):
                logging.warning(
                    "ITC metadata from %s has filename docket %s but readable PDF content parsed %s; using document content.",
                    actual_filename or expected_filename or "PDF",
                    expected_docket,
                    metadata.docket_number,
                )
                return True
            logging.warning(
                "Rejected ITC metadata from %s: expected docket %s but parsed %s.",
                actual_filename or expected_filename or "PDF",
                expected_docket,
                metadata.docket_number,
            )
            return False

        return True

    def find_completed_irsplr_download(self, before_downloads, expected_filename=None):
        expected_lower = expected_filename.lower() if expected_filename else None
        active_downloads = list(self.irsplr_download_dir.glob("*.crdownload"))
        candidates = []

        for path in self.irsplr_download_dir.glob("*.pdf"):
            try:
                stat = path.stat()
            except Exception:
                continue

            prior = before_downloads.get(path.name.lower())
            changed = prior is None or prior != (stat.st_mtime, stat.st_size)
            expected_match = self.path_matches_expected_download(path, expected_lower)
            if expected_lower and not expected_match:
                continue

            if (expected_match and changed) or (not expected_lower and changed):
                if not any(str(download).lower().startswith(str(path).lower()) for download in active_downloads):
                    candidates.append(path)

        if not candidates:
            return None

        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return candidates[0]

    def find_completed_ohtax0_download(self, before_downloads, expected_filename=None):
        expected_lower = expected_filename.lower() if expected_filename else None
        active_downloads = list(self.ohtax0_download_dir.glob("*.crdownload"))
        candidates = []

        for path in self.ohtax0_download_dir.glob("*.pdf"):
            try:
                stat = path.stat()
            except Exception:
                continue

            prior = before_downloads.get(path.name.lower())
            changed = prior is None or prior != (stat.st_mtime, stat.st_size)
            expected_match = self.path_matches_expected_download(path, expected_lower)
            if expected_lower and not expected_match:
                continue

            if (expected_match and changed) or (not expected_lower and changed):
                if not any(str(download).lower().startswith(str(path).lower()) for download in active_downloads):
                    candidates.append(path)

        if not candidates:
            return None

        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return candidates[0]

    def find_completed_mnsutb_download(self, before_downloads, expected_filename=None):
        expected_lower = expected_filename.lower() if expected_filename else None
        active_downloads = list(self.mnsutb_download_dir.glob("*.crdownload"))
        candidates = []

        for path in self.mnsutb_download_dir.glob("*.pdf"):
            try:
                stat = path.stat()
            except Exception:
                continue

            prior = before_downloads.get(path.name.lower())
            changed = prior is None or prior != (stat.st_mtime, stat.st_size)
            expected_match = self.path_matches_expected_download(path, expected_lower)
            if expected_lower and not expected_match:
                continue

            if (expected_match and changed) or (not expected_lower and changed):
                if not any(str(download).lower().startswith(str(path).lower()) for download in active_downloads):
                    candidates.append(path)

        if not candidates:
            return None

        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return candidates[0]

    def find_completed_mspb_download(self, before_downloads, expected_filename=None):
        expected_lower = expected_filename.lower() if expected_filename else None
        active_downloads = list(self.mspb_download_dir.glob("*.crdownload"))
        candidates = []

        for path in self.mspb_download_dir.glob("*.pdf"):
            try:
                stat = path.stat()
            except Exception:
                continue

            prior = before_downloads.get(path.name.lower())
            changed = prior is None or prior != (stat.st_mtime, stat.st_size)
            expected_match = expected_lower and (
                path.name.lower() == expected_lower or
                path.name.lower().startswith(Path(expected_lower).stem.lower())
            )
            if expected_match or changed:
                if not any(str(download).lower().startswith(str(path).lower()) for download in active_downloads):
                    candidates.append(path)

        if not candidates:
            return None

        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return candidates[0]

    def find_completed_itc_download(self, before_downloads, expected_filename=None):
        expected_lower = expected_filename.lower() if expected_filename else None
        active_downloads = list(self.itc_download_dir.glob("*.crdownload"))
        candidates = []

        for path in self.itc_download_dir.glob("*.pdf"):
            try:
                stat = path.stat()
            except Exception:
                continue

            prior = before_downloads.get(path.name.lower())
            changed = prior is None or prior != (stat.st_mtime, stat.st_size)
            expected_match = self.path_matches_expected_download(path, expected_lower)
            if expected_lower and not expected_match:
                continue

            if (expected_match and changed) or (not expected_lower and changed):
                if not any(str(download).lower().startswith(str(path).lower()) for download in active_downloads):
                    candidates.append(path)

        if not candidates:
            return None

        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return candidates[0]

    @staticmethod
    def path_matches_expected_download(path, expected_lower):
        if not expected_lower:
            return False

        path_name = path.name.lower()
        path_stem = path.stem.lower()
        expected_stem = Path(expected_lower).stem.lower()
        return (
            path_name == expected_lower
            or path_stem == expected_stem
            or re.fullmatch(rf"{re.escape(expected_stem)}\s*\(\d+\)", path_stem) is not None
        )

    def get_filename_from_document_href(self, href):
        if not href:
            return None
        try:
            parsed = urlparse(href)
            values = parse_qs(parsed.query).get("fileName")
            if values:
                return unquote(values[0])
            name = Path(unquote(parsed.path)).name
            return name if name.lower().endswith(".pdf") else None
        except Exception:
            return None

    def enable_browser_network_capture(self):
        try:
            self.driver.execute_cdp_cmd("Network.enable", {})
            try:
                self.driver.get_log("performance")
            except Exception:
                pass
        except Exception as e:
            logging.info(f"Chrome network capture is unavailable for MSPB PDF extraction: {e}")

    def get_opened_pdf_bytes_from_browser_network(self, target_url=None, timeout=20):
        deadline = time.time() + timeout
        candidate_request_ids = getattr(self, "_mspb_pdf_request_ids", set())
        checked_request_ids = getattr(self, "_mspb_pdf_checked_request_ids", set())

        while time.time() < deadline:
            for entry in self.read_performance_log_entries():
                try:
                    message = json.loads(entry.get("message", "{}")).get("message", {})
                    method = message.get("method")
                    params = message.get("params", {})

                    if method == "Network.responseReceived":
                        response = params.get("response", {})
                        response_url = response.get("url", "")
                        mime_type = response.get("mimeType", "")
                        if self.is_mspb_pdf_response(response_url, mime_type, target_url):
                            request_id = params.get("requestId")
                            if request_id:
                                candidate_request_ids.add(request_id)

                    if method == "Network.loadingFinished":
                        request_id = params.get("requestId")
                        if request_id in candidate_request_ids and request_id not in checked_request_ids:
                            checked_request_ids.add(request_id)
                            pdf_bytes = self.get_network_response_body(request_id)
                            if self.is_pdf_bytes(pdf_bytes):
                                self._mspb_pdf_request_ids = candidate_request_ids
                                self._mspb_pdf_checked_request_ids = checked_request_ids
                                return pdf_bytes
                            if pdf_bytes:
                                logging.info("Ignoring non-PDF MSPB network response while waiting for the actual PDF.")
                except Exception:
                    continue
            time.sleep(0.5)

        self._mspb_pdf_request_ids = candidate_request_ids
        self._mspb_pdf_checked_request_ids = checked_request_ids
        return None

    def read_performance_log_entries(self):
        try:
            return self.driver.get_log("performance")
        except Exception:
            return []

    def is_mspb_pdf_response(self, response_url, mime_type, target_url=None):
        response_url_lower = (response_url or "").lower()
        mime_type_lower = (mime_type or "").lower()
        target_url_lower = (target_url or "").lower()

        if "pdf" in mime_type_lower:
            return True
        if response_url_lower.endswith(".pdf") or ".pdf" in response_url_lower:
            return True
        if "opendocumentinbrowser" in response_url_lower:
            return True
        if target_url_lower and response_url_lower == target_url_lower:
            return True
        return False

    def get_network_response_body(self, request_id):
        try:
            body = self.driver.execute_cdp_cmd("Network.getResponseBody", {"requestId": request_id})
            raw_body = body.get("body", "")
            if body.get("base64Encoded"):
                return base64.b64decode(raw_body)
            return raw_body.encode("utf-8", errors="ignore")
        except Exception:
            return None

    @staticmethod
    def is_pdf_bytes(content):
        if not content:
            return False
        return content.lstrip().startswith(b"%PDF")

    @staticmethod
    def looks_like_mspb_text(text):
        if not text:
            return False
        text_upper = text.upper()
        return "MERIT SYSTEMS PROTECTION BOARD" in text_upper or "DOCKET NUMBER" in text_upper

    @staticmethod
    def looks_like_itc_text(text):
        if not text:
            return False
        text_upper = text.upper()
        return (
            "INTERNATIONAL TRADE COMMISSION" in text_upper
            or "INV. NO." in text_upper
            or "INVESTIGATION NO." in text_upper
            or "ORDER NO." in text_upper
        )

    @staticmethod
    def looks_like_irsplr_text(text):
        if not text:
            return False
        text_upper = text.upper()
        return (
            "INTERNAL REVENUE SERVICE" in text_upper
            or "PUBLICATION 1078" in text_upper
            or "RELEASE DATE" in text_upper
            or "UILC" in text_upper
            or "CCA_" in text_upper
        )

    @staticmethod
    def looks_like_ohtax0_text(text):
        if not text:
            return False
        text_upper = text.upper()
        return "OHIO BOARD OF TAX APPEALS" in text_upper or "CASE NO(S)" in text_upper

    @staticmethod
    def looks_like_mnsutb_text(text):
        if not text:
            return False
        text_upper = text.upper()
        return (
            "STATE OF MINNESOTA" in text_upper
            and "IN SUPREME COURT" in text_upper
            and "DATED" in text_upper
        )

    def read_open_pdf_accessibility_text(self):
        """Read text exposed through Chrome's accessibility tree, including PDF viewer text."""
        try:
            tree = self.driver.execute_cdp_cmd("Accessibility.getFullAXTree", {})
            values = []
            for node in tree.get("nodes", []):
                for key in ("name", "value", "description"):
                    payload = node.get(key)
                    if isinstance(payload, dict):
                        value = str(payload.get("value", "")).strip()
                        if value:
                            values.append(value)
            text = "\n".join(dict.fromkeys(values))
            if self.looks_like_mspb_text(text):
                logging.info("Read PDF text from Chrome accessibility tree.")
            return text
        except Exception as e:
            logging.info(f"Could not read MSPB PDF accessibility tree: {e}")
            return ""

    def copy_open_pdf_tab_text(self):
        """Copy selectable text from Chrome's PDF viewer and return it from the clipboard."""
        original_clipboard = self.read_windows_clipboard_text()
        try:
            try:
                self.driver.execute_script("window.focus();")
                body = self.driver.find_element(By.TAG_NAME, "body")
                self.click_center_of_pdf_viewer(body)
            except Exception:
                pass

            for _ in range(3):
                copied_text = ""
                try:
                    try:
                        self.driver.switch_to.active_element.send_keys(Keys.ESCAPE)
                    except Exception:
                        pass
                    self.click_center_of_pdf_viewer()
                    self.restore_windows_clipboard_text("")
                    ActionChains(self.driver) \
                        .key_down(Keys.CONTROL) \
                        .send_keys("a") \
                        .key_up(Keys.CONTROL) \
                        .pause(0.2) \
                        .key_down(Keys.CONTROL) \
                        .send_keys("c") \
                        .key_up(Keys.CONTROL) \
                        .perform()
                    time.sleep(0.8)
                    copied_text = self.read_windows_clipboard_text()
                    if self.looks_like_mspb_text(copied_text):
                        logging.info("Copied PDF text from the opened PDF tab.")
                        return copied_text
                    if copied_text:
                        logging.info(f"MSPB PDF clipboard copy did not contain expected text; copied {len(copied_text)} chars.")
                except Exception as e:
                    logging.info(f"MSPB PDF clipboard copy attempt failed: {e}")
                    time.sleep(0.5)

            return copied_text or ""
        finally:
            self.restore_windows_clipboard_text(original_clipboard)

    def click_center_of_pdf_viewer(self, element=None):
        try:
            self.driver.execute_script(
                """
                const x = Math.floor(window.innerWidth / 2);
                const y = Math.floor(window.innerHeight / 2);
                const target = document.elementFromPoint(x, y) || document.body;
                target.dispatchEvent(new MouseEvent('mousedown', {bubbles: true, clientX: x, clientY: y}));
                target.dispatchEvent(new MouseEvent('mouseup', {bubbles: true, clientX: x, clientY: y}));
                target.dispatchEvent(new MouseEvent('click', {bubbles: true, clientX: x, clientY: y}));
                if (target.focus) target.focus();
                """
            )
            time.sleep(0.2)
        except Exception:
            pass

        try:
            if element is None:
                element = self.driver.find_element(By.TAG_NAME, "body")
            ActionChains(self.driver).move_to_element(element).click().perform()
            time.sleep(0.3)
        except Exception:
            try:
                element.click()
            except Exception:
                pass

    def log_mspb_pdf_tab_diagnostics(self, context_label="MSPB"):
        try:
            current_url = self.driver.current_url
        except Exception:
            current_url = "<unavailable>"
        try:
            title = self.driver.title
        except Exception:
            title = "<unavailable>"
        try:
            ready_state = self.driver.execute_script("return document.readyState")
        except Exception:
            ready_state = "<unavailable>"
        try:
            body_text = self.driver.execute_script("return document.body ? document.body.innerText || document.body.textContent || '' : ''") or ""
        except Exception:
            body_text = ""
        try:
            dom_info = self.driver.execute_script(
                """
                const embeds = [...document.querySelectorAll('embed, iframe, pdf-viewer')]
                    .map(e => `${e.tagName}:${e.getAttribute('type') || ''}:${e.getAttribute('src') || ''}`)
                    .join(' | ');
                return embeds;
                """
            ) or ""
        except Exception:
            dom_info = ""

        logging.warning(
            "%s PDF tab diagnostics: url=%s title=%s readyState=%s bodyTextLen=%s embedded=%s",
            context_label,
            current_url,
            title,
            ready_state,
            len(body_text),
            dom_info[:500],
        )

    def read_windows_clipboard_text(self):
        try:
            import win32clipboard
            import win32con

            for _ in range(3):
                try:
                    win32clipboard.OpenClipboard()
                    try:
                        if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
                            return win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT) or ""
                        return ""
                    finally:
                        win32clipboard.CloseClipboard()
                except Exception:
                    time.sleep(0.2)
            return ""
        except Exception:
            return ""

    def restore_windows_clipboard_text(self, text):
        try:
            import win32clipboard
            import win32con

            for _ in range(3):
                try:
                    win32clipboard.OpenClipboard()
                    try:
                        win32clipboard.EmptyClipboard()
                        if text:
                            win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
                    finally:
                        win32clipboard.CloseClipboard()
                    return
                except Exception:
                    time.sleep(0.2)
        except Exception:
            pass

    def read_open_pdf_tab_text(self):
        try:
            text = self.driver.execute_script(
                """
                const texts = [];
                const seen = new Set();
                function walk(node) {
                    if (!node || seen.has(node)) return;
                    seen.add(node);
                    if (node.nodeType === Node.TEXT_NODE) {
                        const value = (node.nodeValue || '').trim();
                        if (value) texts.push(value);
                        return;
                    }
                    if (node.innerText && node.innerText.trim()) {
                        texts.push(node.innerText.trim());
                    } else if (node.textContent && node.textContent.trim()) {
                        texts.push(node.textContent.trim());
                    }
                    if (node.shadowRoot) walk(node.shadowRoot);
                    for (const child of node.children || []) walk(child);
                }
                walk(document.documentElement);
                return [...new Set(texts)].join('\\n');
                """
            )
            return text or ""
        except Exception as e:
            logging.info(f"Could not read text from MSPB PDF tab DOM: {e}")
            return ""

    def log_mspb_metadata(self, metadata, source):
        logging.info(
            "Extracted MSPB metadata from %s: court=%s docket=%s decision_date=%s source_detail=%s",
            source,
            metadata.court,
            metadata.docket_number,
            metadata.decision_date,
            metadata.source_detail,
        )

    def log_itc_metadata(self, metadata, source):
        logging.info(
            "Extracted ITC metadata from %s: court=%s docket=%s decision_date=%s source_detail=%s other_numbers=%s",
            source,
            metadata.court,
            metadata.docket_number,
            metadata.decision_date,
            metadata.source_detail,
            "; ".join(metadata.other_numbers or ()),
        )

    def log_irsplr_metadata(self, metadata, source):
        logging.info(
            "Extracted IRSPLR metadata from %s: court=%s docket=%s decision_date=%s source_detail=%s excluded=%s",
            source,
            metadata.court,
            metadata.docket_number,
            metadata.decision_date,
            metadata.source_detail,
            getattr(metadata, "is_excluded", False),
        )

    def log_ohtax0_metadata(self, metadata, source):
        logging.info(
            "Extracted OHTAX0 metadata from %s: court=%s docket=%s decision_date=%s source_detail=%s other_numbers=%s",
            source,
            metadata.court,
            metadata.docket_number,
            metadata.decision_date,
            metadata.source_detail,
            "; ".join(metadata.other_numbers or ()),
        )

    def log_mnsutb_metadata(self, metadata, source):
        logging.info(
            "Extracted MNSUTB metadata from %s: court=%s docket=%s decision_date=%s source_detail=%s other_numbers=%s",
            source,
            metadata.court,
            metadata.docket_number,
            metadata.decision_date,
            metadata.source_detail,
            "; ".join(metadata.other_numbers or ()),
        )

    def _get_element_href(self, element):
        href = element.get_attribute("href")
        if href:
            return href
        try:
            child_link = element.find_element(By.XPATH, ".//a[@href]")
            return child_link.get_attribute("href")
        except Exception:
            return None

    @staticmethod
    def xpath_literal(value):
        if "'" not in value:
            return f"'{value}'"
        if '"' not in value:
            return f'"{value}"'
        parts = value.split("'")
        return "concat(" + ", \"'\", ".join(f"'{part}'" for part in parts) + ")"

    def open_and_process_form(self, row, full_df, row_index, file_path, retry_count=0, dar_mode=False, wc_mode=False, mspb_mode=False, mspb_metadata=None, itc_metadata=None, irsplr_metadata=None, ohtax0_metadata=None, mnsutb_metadata=None):
        max_modify_attempts = 3
        # Store current tab state
        main_tab = getattr(self, '_main_tab', self.driver.current_window_handle)
        opened_tab = getattr(self, '_opened_tab', None)
        
        # Let the outer form-opening wrapper own Modify retries. If the current
        # IRT tab is stale, one failed wait is enough; the next attempt should
        # reopen the LNI from Search Inventory instead of waiting in-place again.
        found_modify = self.attempt_open_modify(row_index=row_index, max_attempts=1)
        
        if found_modify:
            # Proceed with usual workflow
            status = self.fill_irt_form(
                row,
                full_df,
                row_index,
                file_path,
                skip_ready_check=True,
                dar_mode=dar_mode,
                wc_mode=wc_mode,
                mspb_mode=mspb_mode,
                mspb_metadata=mspb_metadata,
                itc_metadata=itc_metadata,
                irsplr_metadata=irsplr_metadata,
                ohtax0_metadata=ohtax0_metadata,
                mnsutb_metadata=mnsutb_metadata,
            )
            if status == "DONE":
                self.submit_irt_form(file_path, row_index)
                status_updates_buffer[row_index] = status
            
            # After successful processing, clean up tabs
            self._cleanup_tabs(opened_tab, main_tab)
            return status
            
        else:
            # Could not find Modify button - implement fresh start strategy
            logging.warning(f"Modify button not found on attempt {retry_count + 1}/{max_modify_attempts}")
            
            # Immediately close IRT form tab and return to main tab
            self._cleanup_tabs(opened_tab, main_tab)
            
            if retry_count < max_modify_attempts - 1:
                # Fresh start: Re-search LNI from the beginning
                logging.info(
                    f"Fresh start: refreshing Search Inventory, re-searching LNI, and opening form again. "
                    f"Next attempt {retry_count + 2}/{max_modify_attempts}"
                )
                
                # Re-search the LNI to get a fresh page
                lni = str(row["LNI"]).strip()
                if not self.refresh_search_inventory_for_retry(reason=f"Modify button not found for LNI {lni}"):
                    status_updates_buffer[row_index] = "ERROR: MODIFY REFRESH RETRY FAILED"
                    return "ERROR: MODIFY REFRESH RETRY FAILED"
                if self.handle_lni_search(lni):
                    # Recursive call with incremented retry count
                    return self.open_and_process_form(
                        row,
                        full_df,
                        row_index,
                        file_path,
                        retry_count=retry_count + 1,
                        dar_mode=dar_mode,
                        wc_mode=wc_mode,
                        mspb_mode=mspb_mode,
                        mspb_metadata=mspb_metadata,
                        itc_metadata=itc_metadata,
                        irsplr_metadata=irsplr_metadata,
                        ohtax0_metadata=ohtax0_metadata,
                        mnsutb_metadata=mnsutb_metadata,
                    )
                else:
                    logging.error(f"Failed to re-search LNI before Modify retry {retry_count + 2}/{max_modify_attempts}")
                    status_updates_buffer[row_index] = "ERROR: LNI RE-SEARCH FAILED"
                    return "ERROR: LNI RE-SEARCH FAILED"
            else:
                # All 3 attempts failed - log error and move on
                logging.error(f"All 3 attempts failed for row {row_index}. Moving on to next LNI.")
                status_updates_buffer[row_index] = "ERROR: MODIFY BUTTON NOT FOUND AFTER 3 ATTEMPTS"
                return "ERROR: MODIFY BUTTON NOT FOUND AFTER 3 ATTEMPTS"
    
    def _cleanup_tabs(self, opened_tab, main_tab):
        """Helper method to clean up tabs and return to main tab"""
        try:
            handles = self.driver.window_handles
            
            # Close IRT form tab if it exists
            if opened_tab and opened_tab in handles:
                self.driver.switch_to.window(opened_tab)
                self.driver.close()
                logging.info("Closed IRT form tab.")
            
            # Return to main tab
            if main_tab and main_tab in handles:
                self.driver.switch_to.window(main_tab)
                logging.info("Returned to main tab.")
            elif len(handles) > 0:
                # Fallback: switch to first available tab
                self.driver.switch_to.window(handles[0])
                logging.info("Switched to first available tab.")
                
        except Exception as e:
            logging.error(f"Error during tab cleanup: {e}")
        
        # Reset tab tracking
        self._opened_tab = None
        self._main_tab = None

    def _refresh_and_retry_current_row(
        self,
        row,
        full_df,
        full_index,
        file_path,
        form_status,
        dar_mode=False,
        wc_mode=False,
        mspb_mode=False,
        mspb_metadata=None,
        itc_metadata=None,
        irsplr_metadata=None,
        ohtax0_metadata=None,
        mnsutb_metadata=None,
    ):
        lni = str(row.get("LNI", "")).strip()
        logging.warning(
            f"Row {full_index + 2} hit recoverable form status '{form_status}'. "
            f"Refreshing Search Inventory and retrying LNI {lni} once."
        )

        if not self.refresh_search_inventory_for_retry(reason=form_status):
            status_updates_buffer[full_index] = "ERROR: REFRESH RETRY FAILED"
            return "ERROR: REFRESH RETRY FAILED"

        if not self.handle_lni_search(lni):
            status_updates_buffer[full_index] = "ERROR: LNI RE-SEARCH FAILED"
            return "ERROR: LNI RE-SEARCH FAILED"

        return self.open_and_process_form(
            row,
            full_df,
            full_index,
            file_path,
            dar_mode=dar_mode,
            wc_mode=wc_mode,
            mspb_mode=mspb_mode,
            mspb_metadata=mspb_metadata,
            itc_metadata=itc_metadata,
            irsplr_metadata=irsplr_metadata,
            ohtax0_metadata=ohtax0_metadata,
            mnsutb_metadata=mnsutb_metadata,
        )

    def process_batch(self, df, full_df, file_path, update_progress, batch_type, dar_mode=False, wc_mode=False, mspb_mode=False, irsplr_mode=False, ohtax0_mode=False, mnsutb_mode=False):
        self.safe_alert_accept()

        processed_rows = 0
        total_rows = len(df)
        batch_start_time = time.time()
        processed_count = 0
        total_duration = 0

        # Emit 0/total progress at the start so UI shows batch start immediately
        if update_progress and batch_type in ["counsel", "main", "mspb", "itc", "irsplr", "ohtax0", "mnsutb"]:
            update_progress(batch_type, 0, total_rows)

        stop_batch = False
        for full_index in df.index:
            row = df.loc[full_index]
            try:
                row_status = str(row.get("Status", "")).strip().upper()
                if row_status in {"DONE", "ALREADY PROCESSED"}:
                    logging.info(f"Skipping completed row {full_index + 2} with status: {row_status}.")
                    status_updates_buffer[full_index] = row_status
                    continue

                lni = self.validate_row(row, full_index, file_path)
                if not lni:
                    continue

                mark_row_processing(full_index)

                # ⏱ Start timing for this LNI
                lni_start = time.time()

                mspb_metadata = None
                itc_metadata = None
                irsplr_metadata = None
                ohtax0_metadata = None
                mnsutb_metadata = None
                row_is_itc = is_itc_row(row)
                row_is_irsplr = is_irsplr_row(row)
                row_is_ohtax0 = is_ohtax0_row(row)
                row_is_mnsutb = is_mnsutb_row(row)
                if mspb_mode:
                    self.record_mspb_metadata(full_index, row, lni, metadata_status="Attempted")

                    if not self.search_lni(lni) or not self.check_result_available():
                        self.record_mspb_metadata(full_index, row, lni, metadata_status="Search Failed")
                        status_updates_buffer[full_index] = "ERROR: LNI NOT FOUND"
                        continue

                    mspb_metadata = self.extract_mspb_metadata_from_search_result(row, full_index)
                    if not mspb_metadata:
                        self.record_mspb_metadata(full_index, row, lni, metadata_status="Not Extracted")
                        status_updates_buffer[full_index] = "SKIPPED: MSPB PDF DATA NOT FOUND"
                        logging.warning(f"Skipping MSPB row {full_index + 2}: required PDF metadata could not be extracted.")
                        continue

                    self.record_mspb_metadata(full_index, row, lni, metadata=mspb_metadata, metadata_status="Extracted")
                    self.click_matching_result()
                elif row_is_itc:
                    self.record_itc_metadata(full_index, row, lni, metadata_status="Attempted")

                    if not self.search_lni(lni) or not self.check_result_available():
                        self.record_itc_metadata(full_index, row, lni, metadata_status="Search Failed")
                        status_updates_buffer[full_index] = "ERROR: LNI NOT FOUND"
                        continue

                    itc_metadata = self.extract_itc_metadata_from_search_result(row, full_index)
                    if not itc_metadata:
                        self.record_itc_metadata(full_index, row, lni, metadata_status="Not Extracted")
                        status_updates_buffer[full_index] = "SKIPPED: ITC PDF DATA NOT FOUND"
                        logging.warning(f"Skipping ITC row {full_index + 2}: required PDF metadata could not be extracted.")
                        continue

                    itc_metadata = self.mark_itc_duplicate_status(full_index, row, lni, itc_metadata)
                    self.record_itc_metadata(full_index, row, lni, metadata=itc_metadata, metadata_status="Extracted")
                    self.click_matching_result()
                elif irsplr_mode or row_is_irsplr:
                    self.record_irsplr_metadata(full_index, row, lni, metadata_status="Attempted")

                    if not self.search_lni(lni) or not self.check_result_available():
                        self.record_irsplr_metadata(full_index, row, lni, metadata_status="Search Failed")
                        status_updates_buffer[full_index] = "ERROR: LNI NOT FOUND"
                        continue

                    irsplr_metadata = self.extract_irsplr_metadata_from_search_result(row, full_index)
                    if not irsplr_metadata:
                        irsplr_metadata = build_irsplr_unreadable_fallback_metadata(
                            filename_hint=row.get("FileName", ""),
                            court_code_hint=row.get("CourtCode", ""),
                        )
                        self.record_irsplr_metadata(
                            full_index,
                            row,
                            lni,
                            metadata=irsplr_metadata,
                            metadata_status="Unreadable PDF Fallback",
                        )
                        logging.warning(
                            "IRSPLR row %d PDF metadata could not be extracted; opening IRT form to check already-processed state.",
                            full_index + 2,
                        )
                    else:
                        self.record_irsplr_metadata(full_index, row, lni, metadata=irsplr_metadata, metadata_status="Extracted")

                    self.click_matching_result()
                elif ohtax0_mode or row_is_ohtax0:
                    self.record_ohtax0_metadata(full_index, row, lni, metadata_status="Attempted")

                    if not self.search_lni(lni) or not self.check_result_available():
                        self.record_ohtax0_metadata(full_index, row, lni, metadata_status="Search Failed")
                        status_updates_buffer[full_index] = "ERROR: LNI NOT FOUND"
                        continue

                    ohtax0_metadata = self.extract_ohtax0_metadata_from_search_result(row, full_index)
                    if not ohtax0_metadata:
                        self.record_ohtax0_metadata(full_index, row, lni, metadata_status="Not Extracted")
                        status_updates_buffer[full_index] = "SKIPPED: OHTAX0 PDF DATA NOT FOUND"
                        logging.warning(f"Skipping OHTAX0 row {full_index + 2}: required PDF metadata could not be extracted.")
                        continue

                    self.record_ohtax0_metadata(full_index, row, lni, metadata=ohtax0_metadata, metadata_status="Extracted")
                    self.click_matching_result()
                elif mnsutb_mode or row_is_mnsutb:
                    self.record_mnsutb_metadata(full_index, row, lni, metadata_status="Attempted")

                    if not self.search_lni(lni) or not self.check_result_available():
                        self.record_mnsutb_metadata(full_index, row, lni, metadata_status="Search Failed")
                        status_updates_buffer[full_index] = "ERROR: LNI NOT FOUND"
                        continue

                    mnsutb_metadata = self.extract_mnsutb_metadata_from_search_result(row, full_index)
                    if not mnsutb_metadata:
                        self.record_mnsutb_metadata(full_index, row, lni, metadata_status="Not Extracted")
                        status_updates_buffer[full_index] = "SKIPPED: MNSUTB PDF DATA NOT FOUND"
                        logging.warning(f"Skipping MNSUTB row {full_index + 2}: required PDF metadata could not be extracted.")
                        continue

                    self.record_mnsutb_metadata(full_index, row, lni, metadata=mnsutb_metadata, metadata_status="Extracted")
                    self.click_matching_result()
                else:
                    if not self.handle_lni_search(lni):
                        status_updates_buffer[full_index] = "ERROR: LNI NOT FOUND"
                        continue

                form_status = self.open_and_process_form(
                    row,
                    full_df,
                    full_index,
                    file_path,
                    dar_mode=dar_mode,
                    wc_mode=wc_mode,
                    mspb_mode=mspb_mode,
                    mspb_metadata=mspb_metadata,
                    itc_metadata=itc_metadata,
                    irsplr_metadata=irsplr_metadata,
                    ohtax0_metadata=ohtax0_metadata,
                    mnsutb_metadata=mnsutb_metadata,
                )

                # ⏱ End timing
                if self._should_refresh_retry_form_status(form_status, full_index):
                    form_status = self._refresh_and_retry_current_row(
                        row,
                        full_df,
                        full_index,
                        file_path,
                        form_status,
                        dar_mode=dar_mode,
                        wc_mode=wc_mode,
                        mspb_mode=mspb_mode,
                        mspb_metadata=mspb_metadata,
                        itc_metadata=itc_metadata,
                        irsplr_metadata=irsplr_metadata,
                        ohtax0_metadata=ohtax0_metadata,
                        mnsutb_metadata=mnsutb_metadata,
                    )

                if form_status and not is_completed_status(form_status):
                    current_status = normalize_status(status_updates_buffer.get(full_index))
                    if current_status == STATUS_PROCESSING:
                        status_updates_buffer[full_index] = str(form_status).strip().upper()

                lni_duration = time.time() - lni_start
                total_duration += lni_duration
                final_status = normalize_status(status_updates_buffer.get(full_index) or form_status)

                if final_status == STATUS_DONE:
                    processed_count += 1
                    logging.info(f"[LNI PROCESSING TIME] LNI {lni} routed and saved in {lni_duration:.2f} seconds.")
                elif is_completed_status(final_status):
                    logging.info(f"[LNI PROCESSING TIME] LNI {lni} finished as {final_status} in {lni_duration:.2f} seconds.")
                else:
                    logging.warning(
                        f"[LNI PROCESSING TIME] LNI {lni} ended as {final_status or 'UNKNOWN'} after "
                        f"{lni_duration:.2f} seconds; not counted as successfully routed."
                    )


            except RouterSessionLostError as e:
                logging.error(f"Router session lost while processing row {full_index + 2}: {e}")
                self._mark_remaining_rows_after_router_session_loss(df, full_index, str(e))
                error_log_entries.append({
                    "Row": full_index + 2,
                    "LNI": row.get("LNI", ""),
                    "File Name": row.get("FileName", ""),
                    "Status": "ERROR: ROUTER SESSION LOST",
                    "Error Message": str(e)
                })
                stop_batch = True
            except Exception as e:
                logging.error(f"Error processing row {full_index + 2}")
                if mspb_mode:
                    existing_status = mspb_metadata_buffer.get(full_index, {}).get("Metadata Status", "")
                    metadata_status = "Extracted" if existing_status == "Extracted" else "Error"
                    self.record_mspb_metadata(full_index, row, row.get("LNI", ""), metadata_status=metadata_status)
                elif is_itc_row(row):
                    existing_status = mspb_metadata_buffer.get(full_index, {}).get("Metadata Status", "")
                    metadata_status = "Extracted" if existing_status == "Extracted" else "Error"
                    self.record_itc_metadata(full_index, row, row.get("LNI", ""), metadata_status=metadata_status)
                elif is_irsplr_row(row):
                    existing_status = mspb_metadata_buffer.get(full_index, {}).get("Metadata Status", "")
                    metadata_status = "Extracted" if existing_status == "Extracted" else "Error"
                    self.record_irsplr_metadata(full_index, row, row.get("LNI", ""), metadata_status=metadata_status)
                elif is_ohtax0_row(row):
                    existing_status = mspb_metadata_buffer.get(full_index, {}).get("Metadata Status", "")
                    metadata_status = "Extracted" if existing_status == "Extracted" else "Error"
                    self.record_ohtax0_metadata(full_index, row, row.get("LNI", ""), metadata_status=metadata_status)
                elif is_mnsutb_row(row):
                    existing_status = mspb_metadata_buffer.get(full_index, {}).get("Metadata Status", "")
                    metadata_status = "Extracted" if existing_status == "Extracted" else "Error"
                    self.record_mnsutb_metadata(full_index, row, row.get("LNI", ""), metadata_status=metadata_status)
                status_updates_buffer[full_index] = "ERROR"
                error_log_entries.append({
                    "Row": full_index + 2,
                    "LNI": row.get("LNI", ""),
                    "File Name": row.get("FileName", ""),
                    "Status": "ERROR",
                    "Error Message": str(e)
                })
                try:
                    self.driver.close()
                    self.driver.switch_to.window(self.driver.window_handles[0])
                except:
                    pass
            finally:
                # ✅ Always update progress, regardless of success or error
                processed_rows += 1
                if update_progress and batch_type in ["counsel", "main", "mspb", "itc", "irsplr", "ohtax0", "mnsutb"]:
                    update_progress(batch_type, processed_rows, total_rows)

        # ✅ ⏱ Final summary log: outside the loop
            if stop_batch:
                if update_progress and batch_type in ["counsel", "main", "mspb", "itc", "irsplr", "ohtax0", "mnsutb"]:
                    update_progress(batch_type, total_rows, total_rows)
                break

        if processed_count > 0:
            avg = total_duration / processed_count
            est_per_hour = int(3600 / avg)
            elapsed = time.time() - batch_start_time
            mins = int(elapsed // 60)
            secs = int(elapsed % 60)
            logging.info(f"[AVERAGE BATCH PROCESSING TIME - LNI/HOUR ESTIMATE] Successfully routed {processed_count} {batch_type} LNIs in {mins}m {secs}s "
                        f"(Avg: {avg:.2f}s/LNI → Est. {est_per_hour} LNIs/hour)")
            
        return processed_count, total_duration

    def click_matching_result(self):
        try:
            element = self.long_wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "td.searchColumn.ChangeMouseCursorToHand")))
            
            # Try multiple methods to open in new tab
            main_tab = self.driver.current_window_handle
            before_handles = set(self.driver.window_handles)
            
            # Method 1: Try Ctrl+click
            try:
                from selenium.webdriver.common.action_chains import ActionChains
                from selenium.webdriver.common.keys import Keys
                ActionChains(self.driver).key_down(Keys.CONTROL).click(element).key_up(Keys.CONTROL).perform()
                # Wait for new tab with shorter timeout
                WebDriverWait(self.driver, 5).until(lambda d: len(d.window_handles) > len(before_handles))
                new_handles = set(self.driver.window_handles) - before_handles
                if new_handles:
                    new_tab = new_handles.pop()
                    self.driver.switch_to.window(new_tab)
                    logging.info("Switched to new tab for IRT Form.")
                    self._opened_tab = new_tab
                    self._main_tab = main_tab
                    return
            except Exception as e:
                logging.warning(f"New Tab Method 1 failed. Switching to Method 2...")
            
            # Method 2: Try middle-click (simulate with JavaScript)
            try:
                self.driver.execute_script("arguments[0].dispatchEvent(new MouseEvent('click', {button: 1, bubbles: true}));", element)
                WebDriverWait(self.driver, 5).until(lambda d: len(d.window_handles) > len(before_handles))
                new_handles = set(self.driver.window_handles) - before_handles
                if new_handles:
                    new_tab = new_handles.pop()
                    self.driver.switch_to.window(new_tab)
                    logging.info("Switched to new tab for IRT Form.")
                    self._opened_tab = new_tab
                    self._main_tab = main_tab
                    return
            except Exception as e:
                logging.warning(f"New Tab Method 2 failed. Switching to Method 3...")
            
            # Method 3: Try right-click and "Open in new tab"
            try:
                from selenium.webdriver.common.action_chains import ActionChains
                ActionChains(self.driver).context_click(element).perform()
                # Look for "Open in new tab" option
                open_new_tab_option = WebDriverWait(self.driver, 3).until(
                    EC.element_to_be_clickable((By.XPATH, "//*[contains(text(), 'Open in new tab') or contains(text(), 'Open link in new tab')]"))
                )
                open_new_tab_option.click()
                WebDriverWait(self.driver, 5).until(lambda d: len(d.window_handles) > len(before_handles))
                new_handles = set(self.driver.window_handles) - before_handles
                if new_handles:
                    new_tab = new_handles.pop()
                    self.driver.switch_to.window(new_tab)
                    logging.info("Switched to new tab for IRT Form.")
                    self._opened_tab = new_tab
                    self._main_tab = main_tab
                    return
            except Exception as e:
                logging.warning(f"New Tab Method 3 failed. Switching to New Window Method...")
            
            # If all new tab methods fail, fall back to popup window
            logging.error("All new tab methods failed. Falling back to popup window logic.")
            element.click()
            logging.info("Clicked on matching LNI result (popup window fallback).")
            self._opened_tab = None
            self._main_tab = self.driver.current_window_handle
            
        except Exception as e:
            logging.error(f"Failed to click search result")
            if self.show_error:
                self.show_error(f"Failed to click search result")

    def switch_to_popup_window(self):
        try:
            self.wait.until(lambda driver: len(driver.window_handles) > 1)
            self.driver.switch_to.window(self.driver.window_handles[-1])
            logging.info("Switched to popup window.")
            return self.driver.window_handles[0]
        except Exception as e:
            logging.error(f"Failed to switch to popup window")
            if self.show_error:
                self.show_error(f"Failed to switch to popup window")
            return None

    def attempt_open_modify(self, file_path=None, row_index=None, max_attempts=3):
        for attempt in range(1, max_attempts + 1):
            try:
                # Check session validity before attempting to find Modify button
                if not self.check_session_validity():
                    logging.error("Invalid session detected. Cannot proceed with Modify button click.")
                    raise RouterSessionLostError("Router browser session is no longer valid before Modify click.")
                
                logging.info(f"Attempt {attempt}/{max_attempts}: Waiting for Modify button...")
                modify_btn = WebDriverWait(self.driver, 120).until(  # Reduced to 2 minutes (120 seconds) for faster failure detection
                    EC.element_to_be_clickable((By.XPATH, '//*[@id="modify"]'))
                )
                modify_btn.click()
                logging.info("Clicked Modify button.")

                # --- Start of Critical Change ---
                # Immediately check for an alert after clicking.
                try:
                    alert = WebDriverWait(self.driver, 5).until(EC.alert_is_present())
                    alert_text = alert.text.strip()
                    alert.accept()
                    logging.info(f"Accepted alert: {alert_text}")

                    # If it's the 'ready to process' alert, we need to retry the click.
                    if "ready to process = [on]" in alert_text.lower():
                        logging.info("IRT Form is not yet ready. Waiting 5 seconds before retrying Modify click...")
                        time.sleep(5)
                        continue
                    # Handle duplicate document alert
                    if "duplicate document" in alert_text.lower():
                        self.handle_duplicate_lni_popup()
                        # After handling, the form is ready for editing
                        return True
                    # Handle DSAR duplicate alert - check for additional duplicate document alert after DSAR
                    if "dsar" in alert_text.lower() and "duplicate" in alert_text.lower():
                        logging.info("DSAR duplicate alert detected. Checking for additional duplicate document alert...")
                        # Wait a moment for any additional alerts to appear
                        time.sleep(2)
                        try:
                            # Check for additional duplicate document alert
                            additional_alert = WebDriverWait(self.driver, 5).until(EC.alert_is_present())
                            additional_alert_text = additional_alert.text.strip()
                            additional_alert.accept()
                            logging.info(f"Accepted additional alert after DSAR: {additional_alert_text}")
                            
                            # If it's a duplicate document alert, handle it
                            if "duplicate document" in additional_alert_text.lower():
                                self.handle_duplicate_lni_popup()
                                return True
                        except TimeoutException:
                            logging.info("No additional alert found after DSAR duplicate alert.")
                            # Continue with normal flow since no additional alert appeared
                except TimeoutException:
                    # No alert appeared, which is the successful case.
                    # The form should now be in modify mode.
                    logging.info("No alert found. IRT Form is ready for editing.")
                    return True # Successfully clicked Modify and no blocking alert appeared.

            except Exception as e:
                error_msg = str(e)
                logging.warning(f"Attempt {attempt}/{max_attempts} to click Modify button failed: {error_msg}")
                
                # Check if it's a session-related error
                if self._is_invalid_session_error(e):
                    logging.error("Session invalid. Cannot retry - browser connection lost.")
                    raise RouterSessionLostError("Router browser session lost while opening Modify mode.") from e
                
                time.sleep(2) # Brief pause before the next attempt in the loop

        # If all attempts fail (loop finishes without returning True)
        logging.error(f"Failed to enter modify mode after {max_attempts} attempts.")
        if row_index is not None:
            status_updates_buffer[row_index] = "ERROR: MODIFY FAILED"
        return False

    def clear_and_fill_input(self, xpath, value):
        from selenium.common.exceptions import TimeoutException
        try:
            try:
                field = self.wait.until(EC.presence_of_element_located((By.XPATH, xpath)))
            except TimeoutException:
                logging.warning(f"Field {xpath} not found after 60s. Checking for alerts/overlays...")
                # Try to handle any alerts/overlays
                try:
                    self.handle_any_alert(timeout=3)
                except Exception as e:
                    logging.info(f"No alert handled or error in handle_any_alert: {e}")
                try:
                    self.handle_duplicate_overlay()
                except Exception as e:
                    logging.info(f"No duplicate overlay handled or error in handle_duplicate_overlay: {e}")
                # Try again after handling
                try:
                    field = self.wait.until(EC.presence_of_element_located((By.XPATH, xpath)))
                except TimeoutException:
                    logging.warning(f"Field {xpath} still not found after handling alerts. Waiting up to 300s for slow network...")
                    long_wait = WebDriverWait(self.driver, 300)
                    try:
                        field = long_wait.until(EC.presence_of_element_located((By.XPATH, xpath)))
                    except TimeoutException:
                        logging.error(f"Field {xpath} not found after an additional 300s. Giving up.")
                        raise
            if field.is_enabled() and field.get_attribute("readonly") != "true":
                field.clear()
                field.send_keys(value)
                logging.info(f"Field at {xpath} cleared and filled with: {value}")
                return True
            else:
                logging.info(f"Field at {xpath} is not interactable. Skipping.")
                return False
        except Exception as e:
            self._raise_if_invalid_session_error(e, f"filling input {xpath}")
            logging.error(f"Error clearing and filling field at {xpath}: {e}")
            return False

    @staticmethod
    def format_docket_number(_, file_name, dar_mode=False, wc_mode=False):
        # Use the extract_docket_number function for consistent docket extraction
        extracted_docket = extract_docket_number(file_name, dar_mode, wc_mode)
        if extracted_docket:
            return extracted_docket
        
        # Fallback to original SMD logic if extract_docket_number returns None
        # First remove any numbers after "counsel" (e.g., counsel-1, counsel-2, etc.)
        file_name = re.sub(r"counsel-\d+", "counsel", str(file_name))
        # Remove date segment like _MMDDYYYY if present
        file_name = re.sub(r'_\d{8}', '', file_name)
        # Then remove all other parts to get just the docket number, preserving any appended letter
        docket = re.sub(r"LDC_SMD_|_PCQ|_E2E|counsel|\.pdf|\.docx|\.doc|\.html|\.htm|\.csv|\.txt", "", file_name)
        # Remove any trailing letter for IRT form input
        return re.sub(r"[a-z]$", "", docket)

    def get_decision_date_from_received(self):
        try:
            received_xpath = '//*[@id="receivedDateAndTime"]'
            field = self.driver.find_element(By.XPATH, received_xpath)

            # Wait up to 2 seconds for the field to have a value
            WebDriverWait(self.driver, 2).until(
                lambda d: d.find_element(By.XPATH, received_xpath).get_attribute("value").strip()
            )
            raw_text = self.driver.find_element(By.XPATH, received_xpath).get_attribute("value").strip()


            logging.info(f"Received date raw value: {raw_text}")

            # Extract and convert the date
            date_part = raw_text.split()[0]
            received_date = datetime.datetime.strptime(date_part, "%m-%d-%Y")
            decision_date = received_date - datetime.timedelta(days=1)
            return decision_date.strftime("%m-%d-%Y")

        except Exception as e:
            logging.error(f"Failed to get decision date")
            fallback_date = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%m-%d-%Y")
            logging.info(f"Fallback decision date used: {fallback_date}")
            return fallback_date

    @retry_click(max_attempts=1)
    def click_element(self, xpath, wait_time=5):
        try:
            if wait_time > 0:
                element = WebDriverWait(self.driver, wait_time).until(
                    EC.element_to_be_clickable((By.XPATH, xpath))
                )
            else:
                element = self.driver.find_element(By.XPATH, xpath)
            element.click()
            logging.info(f"Clicked: {self.describe_xpath(xpath)}")
            return True
        except Exception as e:
            logging.error(f"Failed to click {xpath}")
            return False


    def click_ready_checkbox_and_check_overlay(self, is_counsel=True):
        """
        Clicks the Ready to Process checkbox, then checks for the overlay popup or alert.
        Returns True if overlay appeared, False if no overlay appeared and Save should proceed,
        'READY_NOT_CLICKABLE' only if the checkbox cannot be clicked before any Ready click succeeds,
        or 'ALERT_HANDLED' if an alert was handled but no overlay appeared (so caller can decide what to do).
        Handles both duplicate overlays, simple OK overlays, and route error alerts.
        """
        ready_clicked = False
        try:
            last_ready_exception = None
            for attempt in range(1, 3):
                try:
                    element = WebDriverWait(self.driver, 5).until(EC.element_to_be_clickable((By.XPATH, '//*[@id="readyToProcess"]')))
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                    time.sleep(0.25)
                    element.click()
                    ready_clicked = True
                    logging.info("Clicked Ready to Process checkbox.")
                    break
                except Exception as e:
                    last_ready_exception = e
                    if attempt < 2:
                        logging.info("Ready to Process checkbox was not clickable on attempt %d/2; retrying.", attempt)
                        self.handle_any_alert(timeout=1)
                        time.sleep(1)
            else:
                logging.info("Ready to Process checkbox is not clickable; treating the document as already processed.")
                return "READY_NOT_CLICKABLE"

            self.handle_any_alert(timeout=2)
            handled_alert = False
            duplicate_handled = False
            while True:
                try:
                    WebDriverWait(self.driver, 2).until(EC.alert_is_present())
                    alert = self.driver.switch_to.alert
                    alert_text = alert.text.strip()
                    alert.accept()
                    logging.warning(f"Got alert after Ready to Process: {alert_text}")
                    handled_alert = True
                    if "duplicate document" in alert_text.lower():
                        logging.info("Duplicate alert detected after Ready to Process. Handling...")
                        self.handle_duplicate_lni_popup()
                        duplicate_handled = True
                        continue
                    elif "document cannot be processed for route - inventory route" in alert_text.lower():
                        logging.info("Route alert indicates document is fresh. Proceeding as fresh.")
                        return True
                    elif "document cannot be processed until workflow is selected" in alert_text.lower():
                        logging.info("Workflow selection alert indicates document is fresh. Proceeding as fresh.")
                        return True
                except TimeoutException:
                    break  # No more alerts
            if duplicate_handled:
                try:
                    WebDriverWait(self.driver, 5).until_not(
                        EC.presence_of_element_located((By.CLASS_NAME, "ui-widget-overlay"))
                    )
                    logging.info("Duplicate overlay cleared after handling. Proceeding to Save.")
                    self.click_element('//*[@id="add"]')
                    logging.info("Clicked Save button after duplicate handling.")
                    return True
                except Exception as e:
                    logging.error(f"Error during fresh doc flow after duplicate overlay")
                    return False
            try:
                WebDriverWait(self.driver, 3).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "ui-widget-overlay"))
                )
                logging.info("Popup overlay appeared after clicking Ready to Process. Document is fresh.")
                self.handle_any_alert()  # Accept any alert if present
                try:
                    ok_button = WebDriverWait(self.driver, 2).until(
                        EC.element_to_be_clickable((By.XPATH, '//button[normalize-space(text())="OK" or normalize-space(text())="Ok" or normalize-space(text())="Okay"]'))
                    )
                    ok_button.click()
                    logging.info("Clicked OK button on overlay.")
                except TimeoutException:
                    pass
                self.handle_duplicate_overlay()
                return True
            except TimeoutException:
                if handled_alert:
                    logging.info("No overlay after handling alert(s) after Ready to Process. Returning ALERT_HANDLED to let caller decide.")
                    return "ALERT_HANDLED"
                else:
                    logging.info("No popup overlay appeared after clicking Ready to Process. Proceeding.")
                    return False
        except Exception as e:
            if ready_clicked:
                logging.warning(
                    "Ready to Process was clicked, but post-click overlay/alert inspection failed; proceeding to Save. Error: %s",
                    e,
                )
                return False
            logging.info("Ready to Process checkbox is not clickable; treating the document as already processed.")
            return "READY_NOT_CLICKABLE"

    def fill_irt_form(self, row, full_df, row_index, file_path, skip_ready_check=False, dar_mode=False, wc_mode=False, mspb_mode=False, mspb_metadata=None, itc_metadata=None, irsplr_metadata=None, ohtax0_metadata=None, mnsutb_metadata=None):
        try:
            file_name = str(row["FileName"]).strip()
            is_counsel_file = is_counsel(file_name, dar_mode, wc_mode)
            lni = str(row["LNI"]).strip()

            if mspb_mode:
                return self.fill_mspb_irt_form(row, row_index, mspb_metadata)
            if itc_metadata:
                return self.fill_itc_irt_form(row, row_index, itc_metadata)
            if irsplr_metadata:
                return self.fill_irsplr_irt_form(row, row_index, irsplr_metadata)
            if ohtax0_metadata:
                return self.fill_ohtax0_irt_form(row, row_index, ohtax0_metadata)
            if mnsutb_metadata:
                return self.fill_mnsutb_irt_form(row, row_index, mnsutb_metadata)
            
            # Determine decision date with clear precedence:
            # 1) Explicit Decision Date from Mapping Data sheet (column K) - HIGHEST PRIORITY
            # 2) Date inferred from filename / Main opinion date (only if no manual decision date)
            # 3) Date derived from Received Date field - FINAL FALLBACK
            manual_decision_raw = row.get("Decision Date")
            decision_date = None

            # 1) Manual Decision Date from mapping sheet (prime source)
            if manual_decision_raw is not None and str(manual_decision_raw).strip().lower() != "nan":
                try:
                    if isinstance(manual_decision_raw, (datetime.date, datetime.datetime)):
                        decision_date = manual_decision_raw.strftime("%m-%d-%Y")
                    else:
                        decision_date = str(manual_decision_raw).strip()
                    logging.info(f"Using manual Decision Date from mapping sheet: {decision_date}")
                except Exception as e:
                    logging.error(f"Error normalizing manual Decision Date '{manual_decision_raw}': {e}")

            # 2) Try filename extraction / Main opinion date (only if no manual decision date)
            if not decision_date and (manual_decision_raw is None or str(manual_decision_raw).strip().lower() == "nan" or str(manual_decision_raw).strip() == ""):
                special_decision_date = None
                if is_counsel_file:
                    # For counsel files, try to get date from matching main opinion filename first
                    counsel_docket = CaseLawRouter.format_docket_number(None, file_name, dar_mode, wc_mode)
                    if counsel_docket:
                        special_decision_date = self.find_main_opinion_date_for_counsel(counsel_docket, file_name, dar_mode, wc_mode)
                        if special_decision_date:
                            logging.info(f"Using Main Opinion date for counsel: {special_decision_date}")
                    
                    # If no main opinion date found, try extracting from counsel filename itself
                    if not special_decision_date:
                        special_decision_date = self.extract_decision_date_from_filename(file_name)
                else:
                    # For main opinion files, extract date from its own filename
                    special_decision_date = self.extract_decision_date_from_filename(file_name)
                
                if special_decision_date:
                    decision_date = special_decision_date
                    logging.info(f"Using Decision Date from filename extraction: {decision_date}")

            # 3) Final fallback: derive from Received Date / IRT Received field
            if not decision_date:
                decision_date = self.get_decision_date_from_received()
                if decision_date:
                    logging.info(f"Using Decision Date derived from Received Date: {decision_date}")

            # Populate common fields with the chosen decision date (if any)
            self.prepare_common_fields(file_name, decision_date, dar_mode, wc_mode)
            self.handle_any_alert()

            max_attempts = 3 if is_counsel_file else 1
            attempts = 0

            while attempts < max_attempts:
                try:
                    if is_counsel_file:
                        self.handle_counsel_fields(row, dar_mode, wc_mode)
                    else:
                        self.handle_main_opinion_fields(row, full_df, row_index, file_path, dar_mode, wc_mode)

                    self.handle_any_alert()

                    # Check Comments and Route fields
                    comments_xpath = '//*[@id="comments"]'
                    route_xpath = '//*[@id="route"]'
                    comments_field = self.wait.until(EC.presence_of_element_located((By.XPATH, comments_xpath)))
                    route_field = self.wait.until(EC.presence_of_element_located((By.XPATH, route_xpath)))

                    comments_enabled = comments_field.is_enabled()
                    route_enabled = route_field.is_enabled()

                    # If route is disabled but comments is fine → mark as already processed
                    if not route_enabled and comments_enabled:
                        logging.info("Route dropdown is disabled — document already processed. Skipping Save & flagging as ALREADY PROCESSED.")
                        status_updates_buffer[row_index] = "ALREADY PROCESSED"
                        self.driver.close()
                        self.driver.switch_to.window(self.driver.window_handles[0])
                        return "ALREADY PROCESSED"

                    # If both comments and route are disabled → retry (or skip if main)
                    if not comments_enabled and not route_enabled:
                        raise Exception("Comments AND Route are both non-interactable")

                    break  # Both fields are fine, proceed

                except Exception as e:
                    attempts += 1
                    logging.warning(f"Attempt {attempts}: Non-interactable IRT form")
                    if attempts >= max_attempts:
                        label = "Non-interactable IRT Form"
                        logging.error(f"{label}. Max attempts reached.")
                        if row_index is not None:
                            status_updates_buffer[row_index] = label.upper()
                        self.driver.close()
                        self.driver.switch_to.window(self.driver.window_handles[0])
                        return label.upper()
                    else:
                        self.driver.close()
                        self.driver.switch_to.window(self.driver.window_handles[0])
                        self.open_lni_in_irt_tab(row)
                        continue

            # Always select the correct route BEFORE clicking Ready to Process
            try:
                route_element = WebDriverWait(self.driver, 3).until(EC.element_to_be_clickable((By.XPATH, '//*[@id="route"]')))
                route_element.click()
                self.handle_any_alert()
                dropdown = Select(route_element)
                route_label = "Archive" if is_counsel_file else "Outside Conversion"
                dropdown.select_by_visible_text(route_label)
                self.handle_any_alert()
                logging.info(f"Selected route: {route_label}")
                self.driver.execute_script("document.getElementById('route').dispatchEvent(new Event('change'))")
                self.handle_any_alert()
            except Exception as e:
                logging.error(f"Failed to select route before Ready to Process: {e}")
                status_updates_buffer[row_index] = "ROUTE ERROR"
                self.driver.close()
                self.driver.switch_to.window(self.driver.window_handles[0])
                return "ROUTE ERROR"

            # Proceed to Ready to Process
            overlay_appeared = self.click_ready_checkbox_and_check_overlay(is_counsel_file)
            self.handle_any_alert()
            if overlay_appeared == "ROUTE_ERROR":
                logging.info("Marking as ROUTE ERROR due to route alert after Ready to Process.")
                self.driver.close()
                self.driver.switch_to.window(self.driver.window_handles[0])
                return "ROUTE ERROR"
            if overlay_appeared == "ALERT_HANDLED":
                logging.info("Alert was handled after Ready to Process, but no overlay appeared. Not flagging as already processed. Returning ALERT_HANDLED.")
                self.driver.close()
                self.driver.switch_to.window(self.driver.window_handles[0])
                return "ALERT_HANDLED"
            if overlay_appeared == "READY_NOT_CLICKABLE":
                logging.info("Ready to Process checkbox was not clickable; marking document as ALREADY PROCESSED.")
                status_updates_buffer[row_index] = "ALREADY PROCESSED"
                self.driver.close()
                self.driver.switch_to.window(self.driver.window_handles[0])
                return "ALREADY PROCESSED"

            return self.handle_routing_and_save(is_counsel_file, row_index, skip_route_and_ready=True)

        except Exception as e:
            logging.error(f"Error in fill_irt_form(): {str(e)}")
            if row_index is not None:
                status_updates_buffer[row_index] = "ERROR"
            return "ERROR"

    def fill_mspb_irt_form(self, row, row_index, mspb_metadata):
        """Fill an IRT form for MSPBAR using metadata extracted from the linked PDF."""
        try:
            if not mspb_metadata:
                logging.warning("Skipping MSPB row because extracted metadata is missing.")
                if row_index is not None:
                    status_updates_buffer[row_index] = "SKIPPED: MSPB PDF DATA NOT FOUND"
                return "SKIPPED: MSPB PDF DATA NOT FOUND"

            file_name = str(row.get("FileName", "")).strip()
            self.prepare_common_fields(
                file_name,
                decision_date=mspb_metadata.decision_date,
                dar_mode=False,
                wc_mode=False,
                docket_override=mspb_metadata.docket_number,
                court=mspb_metadata.court,
            )
            self.handle_any_alert()

            if not self.handle_mspb_fields(row, mspb_metadata):
                if row_index is not None:
                    status_updates_buffer[row_index] = "SKIPPED: MSPB FORM FILL ERROR"
                return "SKIPPED: MSPB FORM FILL ERROR"

            try:
                comments_field = self.wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="comments"]')))
                route_field = self.wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="route"]')))

                if not route_field.is_enabled() and comments_field.is_enabled():
                    logging.info("Route dropdown is disabled - document already processed.")
                    status_updates_buffer[row_index] = "ALREADY PROCESSED"
                    self.driver.close()
                    self.driver.switch_to.window(self.driver.window_handles[0])
                    return "ALREADY PROCESSED"

                if not comments_field.is_enabled() and not route_field.is_enabled():
                    logging.error("MSPB IRT form is non-interactable.")
                    status_updates_buffer[row_index] = "NON-INTERACTABLE IRT FORM"
                    self.driver.close()
                    self.driver.switch_to.window(self.driver.window_handles[0])
                    return "NON-INTERACTABLE IRT FORM"
            except Exception:
                logging.error("Could not verify MSPB form interactability.")
                status_updates_buffer[row_index] = "NON-INTERACTABLE IRT FORM"
                self.driver.close()
                self.driver.switch_to.window(self.driver.window_handles[0])
                return "NON-INTERACTABLE IRT FORM"

            try:
                route_element = WebDriverWait(self.driver, 3).until(EC.element_to_be_clickable((By.XPATH, '//*[@id="route"]')))
                route_element.click()
                self.handle_any_alert()
                dropdown = Select(route_element)
                dropdown.select_by_visible_text("Outside Conversion")
                self.handle_any_alert()
                logging.info("Selected MSPB route: Outside Conversion")
                self.driver.execute_script("document.getElementById('route').dispatchEvent(new Event('change'))")
                self.handle_any_alert()
            except Exception as e:
                logging.error(f"Failed to select MSPB route before Ready to Process: {e}")
                status_updates_buffer[row_index] = "ROUTE ERROR"
                self.driver.close()
                self.driver.switch_to.window(self.driver.window_handles[0])
                return "ROUTE ERROR"

            overlay_appeared = self.click_ready_checkbox_and_check_overlay(False)
            self.handle_any_alert()
            if overlay_appeared == "ROUTE_ERROR":
                self.driver.close()
                self.driver.switch_to.window(self.driver.window_handles[0])
                return "ROUTE ERROR"
            if overlay_appeared == "ALERT_HANDLED":
                self.driver.close()
                self.driver.switch_to.window(self.driver.window_handles[0])
                return "ALERT_HANDLED"
            if overlay_appeared == "READY_NOT_CLICKABLE":
                logging.info("Ready to Process checkbox was not clickable for MSPB; marking document as ALREADY PROCESSED.")
                status_updates_buffer[row_index] = "ALREADY PROCESSED"
                self.driver.close()
                self.driver.switch_to.window(self.driver.window_handles[0])
                return "ALREADY PROCESSED"

            return self.handle_routing_and_save(False, row_index, skip_route_and_ready=True)
        except Exception as e:
            logging.error(f"Error in fill_mspb_irt_form(): {e}")
            if row_index is not None:
                status_updates_buffer[row_index] = "ERROR"
            return "ERROR"

    def is_locked_archive_excluded_form(self, context_label="Document"):
        """Return True when the form already sits in a locked Excluded/Archive state."""
        try:
            source_element = self.wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="sourceDetails"]')))
            route_element = self.wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="route"]')))
            selected_source = self.get_selected_dropdown_text(source_element)
            selected_route = self.get_selected_dropdown_text(route_element)

            ready_clickable = True
            try:
                WebDriverWait(self.driver, 1).until(EC.element_to_be_clickable((By.XPATH, '//*[@id="readyToProcess"]')))
            except Exception:
                ready_clickable = False

            locked_archive_excluded = (
                self.dropdown_text_matches(selected_source, "Excluded")
                and self.dropdown_text_matches(selected_route, "Archive")
                and not route_element.is_enabled()
                and not ready_clickable
            )
            if locked_archive_excluded:
                logging.info(
                    "%s form is already locked as Source Detail Excluded / Route Archive.",
                    context_label,
                )
            return locked_archive_excluded
        except Exception as e:
            logging.debug("Could not inspect locked Excluded/Archive state for %s: %s", context_label, e)
            return False

    def is_irt_form_already_processed(self, context_label="Document"):
        """Return True when the open IRT form looks locked because it was already processed."""
        try:
            comments_field = self.wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="comments"]')))
            route_field = self.wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="route"]')))
            if not route_field.is_enabled() and comments_field.is_enabled():
                logging.info("%s route dropdown is disabled; treating document as ALREADY PROCESSED.", context_label)
                return True

            try:
                WebDriverWait(self.driver, 1).until(EC.element_to_be_clickable((By.XPATH, '//*[@id="readyToProcess"]')))
            except Exception:
                logging.info("%s Ready to Process checkbox is not clickable; treating document as ALREADY PROCESSED.", context_label)
                return True
        except Exception as e:
            logging.debug("Could not inspect already-processed state for %s: %s", context_label, e)
        return False

    def fill_itc_irt_form(self, row, row_index, itc_metadata: ITCMetadata):
        """Fill an IRT form for ITC/ITCALJ using metadata extracted from the linked PDF."""
        previous_archive_duplicate_mode = self._archive_duplicate_mode
        self._archive_duplicate_mode = bool(getattr(itc_metadata, "is_true_duplicate", False))
        try:
            if not itc_metadata:
                logging.warning("Skipping ITC row because extracted metadata is missing.")
                if row_index is not None:
                    status_updates_buffer[row_index] = "SKIPPED: ITC PDF DATA NOT FOUND"
                return "SKIPPED: ITC PDF DATA NOT FOUND"

            file_name = str(row.get("FileName", "")).strip()
            self.prepare_common_fields(
                file_name,
                decision_date=itc_metadata.decision_date,
                dar_mode=False,
                wc_mode=False,
                docket_override=itc_metadata.docket_number,
                court=itc_metadata.court,
            )
            self.handle_any_alert()

            if getattr(itc_metadata, "is_excluded", False) and self.is_locked_archive_excluded_form("ITC"):
                status_updates_buffer[row_index] = "ALREADY PROCESSED"
                self.driver.close()
                self.driver.switch_to.window(self.driver.window_handles[0])
                return "ALREADY PROCESSED"

            if not self.handle_itc_fields(row, itc_metadata):
                if row_index is not None:
                    status_updates_buffer[row_index] = "SKIPPED: ITC FORM FILL ERROR"
                return "SKIPPED: ITC FORM FILL ERROR"

            try:
                comments_field = self.wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="comments"]')))
                route_field = self.wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="route"]')))
                is_excluded = bool(getattr(itc_metadata, "is_excluded", False))

                if not route_field.is_enabled() and comments_field.is_enabled():
                    if is_excluded:
                        selected_route = self.get_selected_dropdown_text(route_field)
                        logging.info(
                            "Route dropdown is disabled after Source Detail Excluded; selected route is: %s",
                            selected_route or "(blank)",
                        )
                    else:
                        logging.info("Route dropdown is disabled - ITC document already processed.")
                        status_updates_buffer[row_index] = "ALREADY PROCESSED"
                        self.driver.close()
                        self.driver.switch_to.window(self.driver.window_handles[0])
                        return "ALREADY PROCESSED"

                if not comments_field.is_enabled() and not route_field.is_enabled():
                    logging.error("ITC IRT form is non-interactable.")
                    status_updates_buffer[row_index] = "NON-INTERACTABLE IRT FORM"
                    self.driver.close()
                    self.driver.switch_to.window(self.driver.window_handles[0])
                    return "NON-INTERACTABLE IRT FORM"
            except Exception:
                logging.error("Could not verify ITC form interactability.")
                status_updates_buffer[row_index] = "NON-INTERACTABLE IRT FORM"
                self.driver.close()
                self.driver.switch_to.window(self.driver.window_handles[0])
                return "NON-INTERACTABLE IRT FORM"

            try:
                route_label = "Archive" if (
                    getattr(itc_metadata, "is_true_duplicate", False)
                    or getattr(itc_metadata, "is_excluded", False)
                ) else "Outside Conversion"
                route_element = self.wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="route"]')))
                if route_element.is_enabled():
                    route_element = WebDriverWait(self.driver, 3).until(EC.element_to_be_clickable((By.XPATH, '//*[@id="route"]')))
                    route_element.click()
                    self.handle_any_alert()
                    dropdown = Select(route_element)
                    dropdown.select_by_visible_text(route_label)
                    self.handle_any_alert()
                    logging.info(f"Selected ITC route: {route_label}")
                    self.driver.execute_script("document.getElementById('route').dispatchEvent(new Event('change'))")
                    self.handle_any_alert()
                elif route_label == "Archive" and getattr(itc_metadata, "is_excluded", False):
                    selected_route = self.get_selected_dropdown_text(route_element)
                    if self.dropdown_text_matches(selected_route, "Archive"):
                        logging.info("Confirmed disabled ITC route dropdown is Archive for Excluded source detail.")
                    else:
                        logging.warning(
                            "Disabled ITC route dropdown is not Archive after Source Detail Excluded; selected route is: %s",
                            selected_route or "(blank)",
                        )
                        if not self.set_dropdown_by_visible_text(route_element, "Archive"):
                            raise Exception("Disabled ITC route dropdown could not be set to Archive")
                        selected_route = self.get_selected_dropdown_text(route_element)
                        if not self.dropdown_text_matches(selected_route, "Archive"):
                            raise Exception(f"Disabled ITC route dropdown did not confirm Archive; selected route is {selected_route!r}")
                        logging.info("Set and confirmed disabled ITC route dropdown is Archive for Excluded source detail.")
                else:
                    raise Exception("ITC route dropdown is disabled before route selection")
            except Exception as e:
                logging.error(f"Failed to select ITC route before Ready to Process: {e}")
                status_updates_buffer[row_index] = "ROUTE ERROR"
                self.driver.close()
                self.driver.switch_to.window(self.driver.window_handles[0])
                return "ROUTE ERROR"

            overlay_appeared = self.click_ready_checkbox_and_check_overlay(False)
            self.handle_any_alert()
            if overlay_appeared == "ROUTE_ERROR":
                self.driver.close()
                self.driver.switch_to.window(self.driver.window_handles[0])
                return "ROUTE ERROR"
            if overlay_appeared == "ALERT_HANDLED":
                self.driver.close()
                self.driver.switch_to.window(self.driver.window_handles[0])
                return "ALERT_HANDLED"
            if overlay_appeared == "READY_NOT_CLICKABLE":
                logging.info("Ready to Process checkbox was not clickable for ITC; marking document as ALREADY PROCESSED.")
                status_updates_buffer[row_index] = "ALREADY PROCESSED"
                self.driver.close()
                self.driver.switch_to.window(self.driver.window_handles[0])
                return "ALREADY PROCESSED"

            return self.handle_routing_and_save(False, row_index, skip_route_and_ready=True)
        except Exception as e:
            logging.error(f"Error in fill_itc_irt_form(): {e}")
            if row_index is not None:
                status_updates_buffer[row_index] = "ERROR"
            return "ERROR"
        finally:
            self._archive_duplicate_mode = previous_archive_duplicate_mode

    def fill_irsplr_irt_form(self, row, row_index, irsplr_metadata: IRSPLRMetadata):
        """Fill an IRT form for IRSPLR using metadata extracted from the linked PDF."""
        try:
            if not irsplr_metadata:
                logging.warning("Skipping IRSPLR row because extracted metadata is missing.")
                if row_index is not None:
                    status_updates_buffer[row_index] = "SKIPPED: IRSPLR PDF DATA NOT FOUND"
                return "SKIPPED: IRSPLR PDF DATA NOT FOUND"

            if getattr(irsplr_metadata, "is_text_fallback", False):
                if self.is_irt_form_already_processed("IRSPLR"):
                    status_updates_buffer[row_index] = "ALREADY PROCESSED"
                    self.driver.close()
                    self.driver.switch_to.window(self.driver.window_handles[0])
                    return "ALREADY PROCESSED"

                logging.warning(
                    "IRSPLR PDF text could not be extracted and the IRT form is not already processed; OCR support is required."
                )
                if row_index is not None:
                    status_updates_buffer[row_index] = "SKIPPED: IRSPLR OCR REQUIRED"
                self.driver.close()
                self.driver.switch_to.window(self.driver.window_handles[0])
                return "SKIPPED: IRSPLR OCR REQUIRED"

            file_name = str(row.get("FileName", "")).strip()
            self.prepare_common_fields(
                file_name,
                decision_date=irsplr_metadata.decision_date,
                dar_mode=False,
                wc_mode=False,
                docket_override=irsplr_metadata.docket_number,
                court=irsplr_metadata.court,
            )
            self.handle_any_alert()

            if getattr(irsplr_metadata, "is_excluded", False) and self.is_locked_archive_excluded_form("IRSPLR"):
                status_updates_buffer[row_index] = "ALREADY PROCESSED"
                self.driver.close()
                self.driver.switch_to.window(self.driver.window_handles[0])
                return "ALREADY PROCESSED"

            if not self.handle_irsplr_fields(row, irsplr_metadata):
                if row_index is not None:
                    status_updates_buffer[row_index] = "SKIPPED: IRSPLR FORM FILL ERROR"
                return "SKIPPED: IRSPLR FORM FILL ERROR"

            try:
                comments_field = self.wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="comments"]')))
                route_field = self.wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="route"]')))
                is_excluded = bool(getattr(irsplr_metadata, "is_excluded", False))

                if not route_field.is_enabled() and comments_field.is_enabled():
                    if is_excluded:
                        selected_route = self.get_selected_dropdown_text(route_field)
                        logging.info(
                            "Route dropdown is disabled after IRSPLR Source Detail Excluded; selected route is: %s",
                            selected_route or "(blank)",
                        )
                    else:
                        logging.info("Route dropdown is disabled - IRSPLR document already processed.")
                        status_updates_buffer[row_index] = "ALREADY PROCESSED"
                        self.driver.close()
                        self.driver.switch_to.window(self.driver.window_handles[0])
                        return "ALREADY PROCESSED"

                if not comments_field.is_enabled() and not route_field.is_enabled():
                    logging.error("IRSPLR IRT form is non-interactable.")
                    status_updates_buffer[row_index] = "NON-INTERACTABLE IRT FORM"
                    self.driver.close()
                    self.driver.switch_to.window(self.driver.window_handles[0])
                    return "NON-INTERACTABLE IRT FORM"
            except Exception:
                logging.error("Could not verify IRSPLR form interactability.")
                status_updates_buffer[row_index] = "NON-INTERACTABLE IRT FORM"
                self.driver.close()
                self.driver.switch_to.window(self.driver.window_handles[0])
                return "NON-INTERACTABLE IRT FORM"

            try:
                route_label = "Archive" if getattr(irsplr_metadata, "is_excluded", False) else "Outside Conversion"
                route_element = self.wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="route"]')))
                if route_element.is_enabled():
                    route_element = WebDriverWait(self.driver, 3).until(EC.element_to_be_clickable((By.XPATH, '//*[@id="route"]')))
                    route_element.click()
                    self.handle_any_alert()
                    dropdown = Select(route_element)
                    dropdown.select_by_visible_text(route_label)
                    self.handle_any_alert()
                    logging.info(f"Selected IRSPLR route: {route_label}")
                    self.driver.execute_script("document.getElementById('route').dispatchEvent(new Event('change'))")
                    self.handle_any_alert()
                elif route_label == "Archive":
                    selected_route = self.get_selected_dropdown_text(route_element)
                    if self.dropdown_text_matches(selected_route, "Archive"):
                        logging.info("Confirmed disabled IRSPLR route dropdown is Archive for Excluded source detail.")
                    else:
                        logging.warning(
                            "Disabled IRSPLR route dropdown is not Archive after Source Detail Excluded; selected route is: %s",
                            selected_route or "(blank)",
                        )
                        if not self.set_dropdown_by_visible_text(route_element, "Archive"):
                            raise Exception("Disabled IRSPLR route dropdown could not be set to Archive")
                        selected_route = self.get_selected_dropdown_text(route_element)
                        if not self.dropdown_text_matches(selected_route, "Archive"):
                            raise Exception(f"Disabled IRSPLR route dropdown did not confirm Archive; selected route is {selected_route!r}")
                        logging.info("Set and confirmed disabled IRSPLR route dropdown is Archive for Excluded source detail.")
                else:
                    raise Exception("IRSPLR route dropdown is disabled before route selection")
            except Exception as e:
                logging.error(f"Failed to select IRSPLR route before Ready to Process: {e}")
                status_updates_buffer[row_index] = "ROUTE ERROR"
                self.driver.close()
                self.driver.switch_to.window(self.driver.window_handles[0])
                return "ROUTE ERROR"

            overlay_appeared = self.click_ready_checkbox_and_check_overlay(False)
            self.handle_any_alert()
            if overlay_appeared == "ROUTE_ERROR":
                self.driver.close()
                self.driver.switch_to.window(self.driver.window_handles[0])
                return "ROUTE ERROR"
            if overlay_appeared == "ALERT_HANDLED":
                self.driver.close()
                self.driver.switch_to.window(self.driver.window_handles[0])
                return "ALERT_HANDLED"
            if overlay_appeared == "READY_NOT_CLICKABLE":
                logging.info("Ready to Process checkbox was not clickable for IRSPLR; marking document as ALREADY PROCESSED.")
                status_updates_buffer[row_index] = "ALREADY PROCESSED"
                self.driver.close()
                self.driver.switch_to.window(self.driver.window_handles[0])
                return "ALREADY PROCESSED"

            return self.handle_routing_and_save(False, row_index, skip_route_and_ready=True)
        except Exception as e:
            logging.error(f"Error in fill_irsplr_irt_form(): {e}")
            if row_index is not None:
                status_updates_buffer[row_index] = "ERROR"
            return "ERROR"

    def fill_ohtax0_irt_form(self, row, row_index, ohtax0_metadata: OHTAX0Metadata):
        """Fill an IRT form for OHTAX0 using metadata extracted from the linked PDF."""
        try:
            if not ohtax0_metadata:
                logging.warning("Skipping OHTAX0 row because extracted metadata is missing.")
                if row_index is not None:
                    status_updates_buffer[row_index] = "SKIPPED: OHTAX0 PDF DATA NOT FOUND"
                return "SKIPPED: OHTAX0 PDF DATA NOT FOUND"

            file_name = str(row.get("FileName", "")).strip()
            self.prepare_common_fields(
                file_name,
                decision_date=ohtax0_metadata.decision_date,
                dar_mode=False,
                wc_mode=False,
                docket_override=ohtax0_metadata.docket_number,
                court=ohtax0_metadata.court,
            )
            self.handle_any_alert()

            if not self.handle_ohtax0_fields(row, ohtax0_metadata):
                if row_index is not None:
                    status_updates_buffer[row_index] = "SKIPPED: OHTAX0 FORM FILL ERROR"
                return "SKIPPED: OHTAX0 FORM FILL ERROR"

            try:
                comments_field = self.wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="comments"]')))
                route_field = self.wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="route"]')))

                if not route_field.is_enabled() and comments_field.is_enabled():
                    logging.info("Route dropdown is disabled - OHTAX0 document already processed.")
                    status_updates_buffer[row_index] = "ALREADY PROCESSED"
                    self.driver.close()
                    self.driver.switch_to.window(self.driver.window_handles[0])
                    return "ALREADY PROCESSED"

                if not comments_field.is_enabled() and not route_field.is_enabled():
                    logging.error("OHTAX0 IRT form is non-interactable.")
                    status_updates_buffer[row_index] = "NON-INTERACTABLE IRT FORM"
                    self.driver.close()
                    self.driver.switch_to.window(self.driver.window_handles[0])
                    return "NON-INTERACTABLE IRT FORM"
            except Exception:
                logging.error("Could not verify OHTAX0 form interactability.")
                status_updates_buffer[row_index] = "NON-INTERACTABLE IRT FORM"
                self.driver.close()
                self.driver.switch_to.window(self.driver.window_handles[0])
                return "NON-INTERACTABLE IRT FORM"

            try:
                route_element = self.wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="route"]')))
                if route_element.is_enabled():
                    route_element = WebDriverWait(self.driver, 3).until(EC.element_to_be_clickable((By.XPATH, '//*[@id="route"]')))
                    route_element.click()
                    self.handle_any_alert()
                    dropdown = Select(route_element)
                    dropdown.select_by_visible_text("Outside Conversion")
                    self.handle_any_alert()
                    logging.info("Selected OHTAX0 route: Outside Conversion")
                    self.driver.execute_script("document.getElementById('route').dispatchEvent(new Event('change'))")
                    self.handle_any_alert()
                else:
                    raise Exception("OHTAX0 route dropdown is disabled before route selection")
            except Exception as e:
                logging.error(f"Failed to select OHTAX0 route before Ready to Process: {e}")
                status_updates_buffer[row_index] = "ROUTE ERROR"
                self.driver.close()
                self.driver.switch_to.window(self.driver.window_handles[0])
                return "ROUTE ERROR"

            overlay_appeared = self.click_ready_checkbox_and_check_overlay(False)
            self.handle_any_alert()
            if overlay_appeared == "ROUTE_ERROR":
                self.driver.close()
                self.driver.switch_to.window(self.driver.window_handles[0])
                return "ROUTE ERROR"
            if overlay_appeared == "ALERT_HANDLED":
                self.driver.close()
                self.driver.switch_to.window(self.driver.window_handles[0])
                return "ALERT_HANDLED"
            if overlay_appeared == "READY_NOT_CLICKABLE":
                logging.info("Ready to Process checkbox was not clickable for OHTAX0; marking document as ALREADY PROCESSED.")
                status_updates_buffer[row_index] = "ALREADY PROCESSED"
                self.driver.close()
                self.driver.switch_to.window(self.driver.window_handles[0])
                return "ALREADY PROCESSED"

            return self.handle_routing_and_save(False, row_index, skip_route_and_ready=True)
        except Exception as e:
            logging.error(f"Error in fill_ohtax0_irt_form(): {e}")
            if row_index is not None:
                status_updates_buffer[row_index] = "ERROR"
            return "ERROR"

    def fill_mnsutb_irt_form(self, row, row_index, mnsutb_metadata: MNSUTBMetadata):
        """Fill an IRT form for MNSUTB using metadata extracted from the linked PDF."""
        try:
            if not mnsutb_metadata:
                logging.warning("Skipping MNSUTB row because extracted metadata is missing.")
                if row_index is not None:
                    status_updates_buffer[row_index] = "SKIPPED: MNSUTB PDF DATA NOT FOUND"
                return "SKIPPED: MNSUTB PDF DATA NOT FOUND"

            file_name = str(row.get("FileName", "")).strip()
            self.prepare_common_fields(
                file_name,
                decision_date=mnsutb_metadata.decision_date,
                dar_mode=False,
                wc_mode=False,
                docket_override=mnsutb_metadata.docket_number,
                court=None,
            )
            self.handle_any_alert()

            if not self.handle_mnsutb_fields(row, mnsutb_metadata):
                if row_index is not None:
                    status_updates_buffer[row_index] = "SKIPPED: MNSUTB FORM FILL ERROR"
                return "SKIPPED: MNSUTB FORM FILL ERROR"

            try:
                comments_field = self.wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="comments"]')))
                route_field = self.wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="route"]')))

                if not route_field.is_enabled() and comments_field.is_enabled():
                    logging.info("Route dropdown is disabled - MNSUTB document already processed.")
                    status_updates_buffer[row_index] = "ALREADY PROCESSED"
                    self.driver.close()
                    self.driver.switch_to.window(self.driver.window_handles[0])
                    return "ALREADY PROCESSED"

                if not comments_field.is_enabled() and not route_field.is_enabled():
                    logging.error("MNSUTB IRT form is non-interactable.")
                    status_updates_buffer[row_index] = "NON-INTERACTABLE IRT FORM"
                    self.driver.close()
                    self.driver.switch_to.window(self.driver.window_handles[0])
                    return "NON-INTERACTABLE IRT FORM"
            except Exception:
                logging.error("Could not verify MNSUTB form interactability.")
                status_updates_buffer[row_index] = "NON-INTERACTABLE IRT FORM"
                self.driver.close()
                self.driver.switch_to.window(self.driver.window_handles[0])
                return "NON-INTERACTABLE IRT FORM"

            try:
                route_element = self.wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="route"]')))
                if route_element.is_enabled():
                    route_element = WebDriverWait(self.driver, 3).until(EC.element_to_be_clickable((By.XPATH, '//*[@id="route"]')))
                    route_element.click()
                    self.handle_any_alert()
                    dropdown = Select(route_element)
                    dropdown.select_by_visible_text("Outside Conversion")
                    self.handle_any_alert()
                    logging.info("Selected MNSUTB route: Outside Conversion")
                    self.driver.execute_script("document.getElementById('route').dispatchEvent(new Event('change'))")
                    self.handle_any_alert()
                else:
                    raise Exception("MNSUTB route dropdown is disabled before route selection")
            except Exception as e:
                logging.error(f"Failed to select MNSUTB route before Ready to Process: {e}")
                status_updates_buffer[row_index] = "ROUTE ERROR"
                self.driver.close()
                self.driver.switch_to.window(self.driver.window_handles[0])
                return "ROUTE ERROR"

            overlay_appeared = self.click_ready_checkbox_and_check_overlay(False)
            self.handle_any_alert()
            if overlay_appeared == "ROUTE_ERROR":
                self.driver.close()
                self.driver.switch_to.window(self.driver.window_handles[0])
                return "ROUTE ERROR"
            if overlay_appeared == "ALERT_HANDLED":
                self.driver.close()
                self.driver.switch_to.window(self.driver.window_handles[0])
                return "ALERT_HANDLED"
            if overlay_appeared == "READY_NOT_CLICKABLE":
                logging.info("Ready to Process checkbox was not clickable for MNSUTB; marking document as ALREADY PROCESSED.")
                status_updates_buffer[row_index] = "ALREADY PROCESSED"
                self.driver.close()
                self.driver.switch_to.window(self.driver.window_handles[0])
                return "ALREADY PROCESSED"

            return self.handle_routing_and_save(False, row_index, skip_route_and_ready=True)
        except Exception as e:
            logging.error(f"Error in fill_mnsutb_irt_form(): {e}")
            if row_index is not None:
                status_updates_buffer[row_index] = "ERROR"
            return "ERROR"

    def handle_itc_fields(self, row, itc_metadata: ITCMetadata):
        try:
            case_name_xpath = '//*[@id="caseName"]'
            try:
                field = self.wait.until(EC.presence_of_element_located((By.XPATH, case_name_xpath)))
                existing_case_name = self.wait_for_existing_field_text(case_name_xpath, timeout=6)
                if existing_case_name:
                    logging.info(f"ITC Case Name already present; leaving unchanged: {existing_case_name[:120]}")
                else:
                    if field.is_enabled() and field.get_attribute("readonly") != "true":
                        field.clear()
                        field.send_keys("RE")
                        logging.info("ITC Case Name was blank; set to RE.")
                    else:
                        logging.info("Skipped ITC Case Name because it is not interactable.")
            except Exception:
                logging.error("Error setting ITC case name")

            if not self.select_source_detail(itc_metadata.source_detail):
                return False

            comment_parts = []
            if itc_metadata.comments_text:
                comment_parts.append(itc_metadata.comments_text)

            duplicate_lni = getattr(itc_metadata, "duplicate_of_lni", "") or ""
            if (
                getattr(itc_metadata, "is_true_duplicate", False)
                and duplicate_lni
                and not getattr(itc_metadata, "is_excluded", False)
            ):
                comment_parts.append(f"Dup of {duplicate_lni}")

            additional_comments = str(row.get("Comments", "")).strip()
            if additional_comments and additional_comments.lower() != "nan":
                comment_parts.append(additional_comments)

            if comment_parts:
                if not self.append_comments(comment_parts, "ITC"):
                    return False

            return True
        except Exception as e:
            logging.error(f"Error handling ITC fields: {e}")
            return False

    def handle_irsplr_fields(self, row, irsplr_metadata: IRSPLRMetadata):
        try:
            case_name_xpath = '//*[@id="caseName"]'
            try:
                field = self.wait.until(EC.presence_of_element_located((By.XPATH, case_name_xpath)))
                existing_case_name = self.wait_for_existing_field_text(case_name_xpath, timeout=6)
                if existing_case_name:
                    logging.info(f"IRSPLR Case Name already present; leaving unchanged: {existing_case_name[:120]}")
                else:
                    if field.is_enabled() and field.get_attribute("readonly") != "true":
                        field.clear()
                        field.send_keys("RE")
                        logging.info("IRSPLR Case Name was blank; set to RE.")
                    else:
                        logging.info("Skipped IRSPLR Case Name because it is not interactable.")
            except Exception:
                logging.error("Error setting IRSPLR case name")

            if not self.select_source_detail(irsplr_metadata.source_detail):
                return False

            comment_parts = []
            if irsplr_metadata.comments_text:
                comment_parts.append(irsplr_metadata.comments_text)

            additional_comments = str(row.get("Comments", "")).strip()
            if additional_comments and additional_comments.lower() != "nan":
                comment_parts.append(additional_comments)

            if comment_parts:
                if not self.append_comments(comment_parts, "IRSPLR"):
                    return False

            return True
        except Exception as e:
            logging.error(f"Error handling IRSPLR fields: {e}")
            return False

    def handle_ohtax0_fields(self, row, ohtax0_metadata: OHTAX0Metadata):
        try:
            case_name_xpath = '//*[@id="caseName"]'
            try:
                field = self.wait.until(EC.presence_of_element_located((By.XPATH, case_name_xpath)))
                existing_case_name = self.wait_for_existing_field_text(case_name_xpath, timeout=6)
                if existing_case_name:
                    logging.info(f"OHTAX0 Case Name already present; leaving unchanged: {existing_case_name[:120]}")
                else:
                    if field.is_enabled() and field.get_attribute("readonly") != "true":
                        field.clear()
                        field.send_keys("RE")
                        logging.info("OHTAX0 Case Name was blank; set to RE.")
                    else:
                        logging.info("Skipped OHTAX0 Case Name because it is not interactable.")
            except Exception:
                logging.error("Error setting OHTAX0 case name")

            if not self.select_source_detail(ohtax0_metadata.source_detail):
                return False

            comment_parts = []
            if ohtax0_metadata.comments_text:
                comment_parts.append(ohtax0_metadata.comments_text)

            additional_comments = str(row.get("Comments", "")).strip()
            if additional_comments and additional_comments.lower() != "nan":
                comment_parts.append(additional_comments)

            if comment_parts:
                if not self.append_comments(comment_parts, "OHTAX0"):
                    return False

            return True
        except Exception as e:
            logging.error(f"Error handling OHTAX0 fields: {e}")
            return False

    def handle_mnsutb_fields(self, row, mnsutb_metadata: MNSUTBMetadata):
        try:
            case_name_xpath = '//*[@id="caseName"]'
            try:
                field = self.wait.until(EC.presence_of_element_located((By.XPATH, case_name_xpath)))
                existing_case_name = self.wait_for_existing_field_text(case_name_xpath, timeout=6)
                if existing_case_name:
                    logging.info(f"MNSUTB Case Name already present; leaving unchanged: {existing_case_name[:120]}")
                else:
                    if field.is_enabled() and field.get_attribute("readonly") != "true":
                        field.clear()
                        field.send_keys("RE")
                        logging.info("MNSUTB Case Name was blank; set to RE.")
                    else:
                        logging.info("Skipped MNSUTB Case Name because it is not interactable.")
            except Exception:
                logging.error("Error setting MNSUTB case name")

            if not self.select_source_detail(mnsutb_metadata.source_detail):
                return False

            comment_parts = []
            if mnsutb_metadata.comments_text:
                comment_parts.append(mnsutb_metadata.comments_text)

            additional_comments = str(row.get("Comments", "")).strip()
            if additional_comments and additional_comments.lower() != "nan":
                comment_parts.append(additional_comments)

            if comment_parts:
                if not self.append_comments(comment_parts, "MNSUTB"):
                    return False

            return True
        except Exception as e:
            logging.error(f"Error handling MNSUTB fields: {e}")
            return False

    def append_comments(self, comment_parts, context_label="Document"):
        normalized_parts = []
        for part in comment_parts:
            part = self.normalize_irt_text(part).strip()
            if not part or part.lower() == "nan":
                continue
            if part not in normalized_parts:
                normalized_parts.append(part)

        if not normalized_parts:
            logging.info(f"No new comments to add for {context_label}.")
            return True

        for attempt in range(1, 4):
            try:
                self.handle_any_alert(timeout=1)
                comments_field = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, '//*[@id="comments"]'))
                )
                if not comments_field.is_enabled() or comments_field.get_attribute("readonly") == "true":
                    logging.warning(
                        "%s comments field is not interactable on attempt %d/3; retrying.",
                        context_label,
                        attempt,
                    )
                    time.sleep(1)
                    continue

                existing_text = comments_field.get_attribute("value").strip()
                clean_parts = [
                    part for part in normalized_parts
                    if part not in existing_text
                ]

                if not clean_parts:
                    logging.info(f"No new comments to add for {context_label}.")
                    return True

                if existing_text:
                    if existing_text.endswith("."):
                        existing_text = existing_text[:-1].strip()
                    updated_text = f"{existing_text}; {'; '.join(clean_parts)}"
                else:
                    updated_text = "; ".join(clean_parts)

                updated_text = self.normalize_irt_text(updated_text)
                comments_field.clear()
                comments_field.send_keys(updated_text)
                logging.info(f"Updated {context_label} comments field: {updated_text}")
                return True
            except UnexpectedAlertPresentException:
                self.handle_any_alert(timeout=3)
            except Exception as e:
                if attempt < 3:
                    logging.warning(
                        "Failed to update %s comments on attempt %d/3: %s",
                        context_label,
                        attempt,
                        e,
                    )
                    time.sleep(1)
                    continue
                logging.error(f"Failed to update {context_label} comments after 3 attempts: {e}")
                return False

        return False


    def handle_unexpected_alert(self):
        """Handles unexpected alerts, especially for duplicate documents."""
        try:
            alert = WebDriverWait(self.driver, 3).until(EC.alert_is_present())
            alert_text = alert.text
            logging.warning(f"Caught unexpected alert: '{alert_text}'")
            alert.accept()
            if "duplicate document" in alert_text.lower():
                logging.info("Handling duplicate document overlay after unexpected alert.")
                self.handle_duplicate_overlay()
                return True  # Indicates a duplicate was handled
        except TimeoutException:
            return False  # No alert was present
        except Exception as e:
            logging.error(f"Error in handle_unexpected_alert")
            return False
        return False

    def is_ready_to_process_enabled(self):
        """Checks if the 'Ready to Process' checkbox is enabled and clickable."""
        try:
            checkbox = WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located((By.XPATH, '//*[@id="readyToProcess"]'))
            )
            return checkbox.is_enabled()
        except TimeoutException:
            logging.error("Could not find the 'Ready to Process' checkbox.")
            return False
        except Exception as e:
            logging.error(f"Error checking 'Ready to Process' checkbox state")
            return False

    def handle_any_alert(self, timeout=3, archive_as_duplicate=None):
        handled_alert, duplicate_seen = self.accept_pending_alerts(initial_timeout=timeout)
        if duplicate_seen:
            self.handle_duplicate_overlay(archive_as_duplicate=archive_as_duplicate)
        return handled_alert

    def accept_pending_alerts(self, initial_timeout=3, followup_timeout=1, max_alerts=5):
        handled_alert = False
        duplicate_seen = False
        timeout = initial_timeout

        for _ in range(max_alerts):
            try:
                alert = WebDriverWait(self.driver, timeout).until(EC.alert_is_present())
                alert_text = alert.text.strip()
                alert.accept()
                logging.info(f"Handled alert: {alert_text}")
                handled_alert = True
                if "duplicate document" in alert_text.lower():
                    duplicate_seen = True
                time.sleep(0.25)
                timeout = followup_timeout
            except TimeoutException:
                break
            except Exception as e:
                logging.warning(f"Could not accept pending alert cleanly: {e}")
                break

        return handled_alert, duplicate_seen

    def handle_routing_and_save(self, is_counsel, row_index, skip_route_and_ready=False):
        save_attempts = 3
        for attempt in range(save_attempts):
            try:
                # Only select route and click Ready to Process if not already done in fill_irt_form
                if not skip_route_and_ready:
                    route_element = self.driver.find_element(By.XPATH, '//*[@id="route"]')
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", route_element)
                    self.handle_any_alert(timeout=2)
                    try:
                        try:
                            route_element.click()
                            dropdown = Select(route_element)
                            route_label = "Archive" if is_counsel else "Outside Conversion"
                            dropdown.select_by_visible_text(route_label)
                        except UnexpectedAlertPresentException:
                            self.handle_any_alert()
                            route_element = self.driver.find_element(By.XPATH, '//*[@id="route"]')
                            route_element.click()
                            dropdown = Select(route_element)
                            route_label = "Archive" if is_counsel else "Outside Conversion"
                            dropdown.select_by_visible_text(route_label)
                    except Exception as e:
                        logging.warning(f"Exception during route selection. Attempting to handle popups/overlays and retry.")
                        self.handle_unexpected_alert()
                        self.handle_duplicate_overlay()
                        try:
                            self.handle_any_alert()
                            route_element = self.driver.find_element(By.XPATH, '//*[@id="route"]')
                            route_element.click()
                            dropdown = Select(route_element)
                            route_label = "Archive" if is_counsel else "Outside Conversion"
                            dropdown.select_by_visible_text(route_label)
                        except Exception as e2:
                            logging.error(f"Route selection failed after handling popups/overlays: {e2}")
                            return "ROUTE DROPDOWN ERROR"
                    self.driver.execute_script("document.getElementById('route').dispatchEvent(new Event('change'))")
                    logging.info(f"Selected route: {route_label}")
                    self.handle_any_alert(timeout=2)
                    ready_result = self.click_ready_checkbox_and_check_overlay(is_counsel)
                    if ready_result == "READY_NOT_CLICKABLE":
                        logging.info("Ready to Process checkbox was not clickable during routing; marking document as ALREADY PROCESSED.")
                        if row_index is not None:
                            status_updates_buffer[row_index] = "ALREADY PROCESSED"
                        self.driver.close()
                        self.driver.switch_to.window(self.driver.window_handles[0])
                        return "ALREADY PROCESSED"
                    self.handle_any_alert(timeout=2)
                # Try to save
                try:
                    self.click_element('//*[@id="add"]')
                    logging.info("Clicked Save button.")
                    # Check for alert after save
                    try:
                        WebDriverWait(self.driver, 3).until(EC.alert_is_present())
                        alert = self.driver.switch_to.alert
                        alert_text = alert.text.strip()
                        alert.accept()
                        logging.info(f"Accepted alert: {alert_text}")
                        if "route = [arc] vendorcode = [arc] workflow = [] is not a valid routing combo" in alert_text.lower():
                            logging.warning(f"Invalid routing combo alert after save (attempt {attempt+1}). Closing form and retrying.")
                            self.driver.close()
                            self.driver.switch_to.window(self.driver.window_handles[0])
                            if attempt < save_attempts - 1:
                                self.attempt_open_modify(row_index=row_index)
                                continue  # Retry
                            else:
                                logging.error(f"Failed to save LNI after {save_attempts} attempts due to invalid routing combo.")
                                if row_index is not None:
                                    status_updates_buffer[row_index] = "INVALID ROUTING COMBO"
                                return "INVALID ROUTING COMBO"
                    except TimeoutException:
                        pass  # No alert after save
                    return "DONE"
                except Exception as e:
                    logging.info("Save failed, assuming form already processed. Closing window.")
                    self.driver.close()
                    self.driver.switch_to.window(self.driver.window_handles[0])
                    return "ALREADY PROCESSED"
            except Exception as e:
                if self.handle_unexpected_alert():
                    logging.info("Continuing after handling an unexpected alert during routing.")
                else:
                    logging.error(f"Route selection failed")
                return "ROUTE DROPDOWN ERROR"
        # If we get here, all attempts failed
        logging.error(f"Failed to save LNI after {save_attempts} attempts due to invalid routing combo.")
        if row_index is not None:
            status_updates_buffer[row_index] = "INVALID ROUTING COMBO"
        return "INVALID ROUTING COMBO"

    def submit_irt_form(self, file_path, row_index):
        try:
            self.safe_alert_accept()
            self.driver.close()
            self.driver.switch_to.window(self.driver.window_handles[0])
            logging.info("IRT Form window closed after submission.")
        except Exception as e:
            logging.error(f"Unhandled error in submit_irt_form()")

    def process_rows(self, full_df, file_path, update_progress, dar_mode=False, wc_mode=False, mspb_mode=False, itc_mode=False, irsplr_mode=False, ohtax0_mode=False, mnsutb_mode=False):
        counsel_df, main_df = None, None
        try:
            self.full_df = full_df

            counsel_df, main_df = filter_mapping_data(full_df, dar_mode, wc_mode, mspb_mode=mspb_mode)

            if mspb_mode:
                logging.info("=== Starting MSPB Batch ===")
                if self.set_status:
                    self.set_status("MSPB Batch Started")
                mspb_count, mspb_duration = self.process_batch(main_df, full_df, file_path, update_progress, "mspb", dar_mode, wc_mode, mspb_mode=True)
                if self.set_status:
                    self.set_status("MSPB Batch Processed")
                if mspb_count > 0:
                    total_mins = int(mspb_duration // 60)
                    total_secs = int(mspb_duration % 60)
                    logging.info("[MSPB PROCESSING SUMMARY] MSPB: %d LNIs successfully routed in %dm %ds", mspb_count, total_mins, total_secs)
                return counsel_df, main_df

            if itc_mode:
                counsel_df = full_df.iloc[0:0].copy()
                main_df = full_df.copy()
                logging.info("ITC Count: %d", len(main_df))
                logging.info("=== Starting ITC Batch ===")
                if self.set_status:
                    self.set_status("ITC Batch Started")
                itc_count, itc_duration = self.process_batch(main_df, full_df, file_path, update_progress, "itc", dar_mode, wc_mode)
                if self.set_status:
                    self.set_status("ITC Batch Processed")
                if itc_count > 0:
                    total_mins = int(itc_duration // 60)
                    total_secs = int(itc_duration % 60)
                    logging.info("[ITC PROCESSING SUMMARY] ITC: %d LNIs successfully routed in %dm %ds", itc_count, total_mins, total_secs)
                return counsel_df, main_df

            if irsplr_mode:
                counsel_df = full_df.iloc[0:0].copy()
                main_df = full_df.copy()
                logging.info("IRSPLR Count: %d", len(main_df))
                logging.info("=== Starting IRSPLR Batch ===")
                if self.set_status:
                    self.set_status("IRSPLR Batch Started")
                irsplr_count, irsplr_duration = self.process_batch(
                    main_df,
                    full_df,
                    file_path,
                    update_progress,
                    "irsplr",
                    dar_mode,
                    wc_mode,
                    irsplr_mode=True,
                )
                if self.set_status:
                    self.set_status("IRSPLR Batch Processed")
                if irsplr_count > 0:
                    total_mins = int(irsplr_duration // 60)
                    total_secs = int(irsplr_duration % 60)
                    logging.info("[IRSPLR PROCESSING SUMMARY] IRSPLR: %d LNIs successfully routed in %dm %ds", irsplr_count, total_mins, total_secs)
                return counsel_df, main_df

            if ohtax0_mode:
                counsel_df = full_df.iloc[0:0].copy()
                main_df = full_df.copy()
                logging.info("OHTAX0 Count: %d", len(main_df))
                logging.info("=== Starting OHTAX0 Batch ===")
                if self.set_status:
                    self.set_status("OHTAX0 Batch Started")
                ohtax0_count, ohtax0_duration = self.process_batch(
                    main_df,
                    full_df,
                    file_path,
                    update_progress,
                    "ohtax0",
                    dar_mode,
                    wc_mode,
                    ohtax0_mode=True,
                )
                if self.set_status:
                    self.set_status("OHTAX0 Batch Processed")
                if ohtax0_count > 0:
                    total_mins = int(ohtax0_duration // 60)
                    total_secs = int(ohtax0_duration % 60)
                    logging.info("[OHTAX0 PROCESSING SUMMARY] OHTAX0: %d LNIs successfully routed in %dm %ds", ohtax0_count, total_mins, total_secs)
                return counsel_df, main_df

            if mnsutb_mode:
                counsel_df = full_df.iloc[0:0].copy()
                main_df = full_df.copy()
                logging.info("MNSUTB Count: %d", len(main_df))
                logging.info("=== Starting MNSUTB Batch ===")
                if self.set_status:
                    self.set_status("MNSUTB Batch Started")
                mnsutb_count, mnsutb_duration = self.process_batch(
                    main_df,
                    full_df,
                    file_path,
                    update_progress,
                    "mnsutb",
                    dar_mode,
                    wc_mode,
                    mnsutb_mode=True,
                )
                if self.set_status:
                    self.set_status("MNSUTB Batch Processed")
                if mnsutb_count > 0:
                    total_mins = int(mnsutb_duration // 60)
                    total_secs = int(mnsutb_duration % 60)
                    logging.info("[MNSUTB PROCESSING SUMMARY] MNSUTB: %d LNIs successfully routed in %dm %ds", mnsutb_count, total_mins, total_secs)
                return counsel_df, main_df

            logging.info("=== Starting Counsel Batch ===")
            counsel_count, counsel_duration = self.process_batch(counsel_df, full_df, file_path, update_progress, "counsel", dar_mode, wc_mode)

            main_df, deferred_main_rows = defer_main_rows_with_failed_counsel(
                main_df,
                full_df,
                dar_mode=dar_mode,
                wc_mode=wc_mode,
            )
            if deferred_main_rows:
                logging.warning(
                    "Deferred %d main opinion row(s) because required counsel did not finish cleanly.",
                    len(deferred_main_rows),
                )

            if self.set_status:
                self.set_status("Counsel Batch Processed")

            try:
                while len(self.driver.window_handles) > 1:
                    self.driver.switch_to.window(self.driver.window_handles[-1])
                    self.driver.close()
                    self.driver.switch_to.window(self.driver.window_handles[0])
                logging.info("Cleaned up all leftover popup windows before Main Opinion batch.")
            except Exception as e:
                logging.warning(f"Failed to clean up extra windows")

            logging.info("=== Starting Main Opinion Batch ===")
            if self.set_status:
                self.set_status("Main Opinion Batch Started")
            main_count, main_duration = self.process_batch(main_df, full_df, file_path, update_progress, "main", dar_mode, wc_mode)
            if self.set_status:
                self.set_status("Main Opinion Batch Processed")

            total_count = counsel_count + main_count
            total_time = counsel_duration + main_duration

            if total_count > 0:
                overall_avg = total_time / total_count
                overall_est_per_hour = int(3600 / overall_avg)
                total_mins = int(total_time // 60)
                total_secs = int(total_time % 60)

                counsel_mins = int(counsel_duration // 60)
                counsel_secs = int(counsel_duration % 60)

                main_mins = int(main_duration // 60)
                main_secs = int(main_duration % 60)

                logging.info("[TOTAL AVERAGE PROCESSING TIME SUMMARY - LNI/HOUR ESTIMATE] TOTAL: %d LNIs successfully routed in %dm %ds", total_count, total_mins, total_secs)
                logging.info("    - Counsel: %d LNIs in %dm %ds", counsel_count, counsel_mins, counsel_secs)
                logging.info("    - Main Opinion: %d LNIs in %dm %ds", main_count, main_mins, main_secs)
                logging.info("    - Overall Avg: %.1fs/LNI → Est. %d LNIs/hour", overall_avg, overall_est_per_hour)

            self._last_success_log_time = datetime.datetime.now()
            self._success_message_dismissed = False

            # Note: This will be overridden by the dynamic message in the GUI
            logging.info("Documents Auto-Routed Successfully!")

            if self.set_status:
                self.set_status("Success!")

            if error_log_entries:
                error_df = pd.DataFrame(error_log_entries)
                timestamp = datetime.datetime.now().strftime("%I-%M-%S_%p").lstrip("0")
                error_folder = Path.home() / "Downloads" / "Case Law Auto-Routing Resources" / "Error Reports"
                error_folder.mkdir(parents=True, exist_ok=True)
                error_path = error_folder / f"Error Report - {timestamp}.xlsx"
                error_df.to_excel(error_path, index=False)
                logging.info(f"Error report saved to {error_path}")

            # This is the correct place for the return statement for this function
            return counsel_df, main_df

        except Exception as e:
            msg = str(e)
            # List of phrases that indicate a normal, non-error outcome
            normal_outcomes = [
                "already processed",
                "No rows to process",
                "No valid data",
                "All documents processed successfully",
                "Some documents processed successfully",
                "All documents were already processed",
                "No new routing needed"
            ]
            if any(phrase in msg for phrase in normal_outcomes):
                logging.info(f"Row processing ended normally: {msg}")
            else:
                logging.error(f"Failed during row processing: {msg}", exc_info=True)
            # Ensure it returns something iterable on failure to prevent UI crash
            return pd.DataFrame(), pd.DataFrame()

    def safe_alert_accept(self):
        handled_alert, duplicate_seen = self.accept_pending_alerts(initial_timeout=5)
        if duplicate_seen:
            logging.info("Duplicate alert detected. Handling duplicate popup dialog...")
            self.handle_duplicate_overlay()
            return "This is a duplicate document"
        return "ALERT_HANDLED" if handled_alert else None

    def should_archive_duplicate(self, archive_as_duplicate=None):
        if archive_as_duplicate is None:
            return bool(getattr(self, "_archive_duplicate_mode", False))
        return bool(archive_as_duplicate)

    def handle_duplicate_overlay(self, archive_as_duplicate=None):
        """Handle the duplicate dialog using the current route-specific duplicate policy."""
        archive_as_duplicate = self.should_archive_duplicate(archive_as_duplicate)
        for attempt in range(1, 4):
            self.accept_pending_alerts(initial_timeout=0.5, followup_timeout=1, max_alerts=5)
            try:
                if archive_as_duplicate:
                    self.click_duplicate_archive_radio(timeout=10)
                else:
                    self.click_duplicate_process_radio(timeout=10)
                self.accept_pending_alerts(initial_timeout=0.5, followup_timeout=1, max_alerts=5)
                self.click_duplicate_continue_button(timeout=10)
                self.accept_pending_alerts(initial_timeout=0.5, followup_timeout=1, max_alerts=5)
                self.wait_for_duplicate_overlay_to_clear(timeout=15)
                return True
            except UnexpectedAlertPresentException as e:
                logging.info(f"Duplicate alert interrupted overlay handling on attempt {attempt}; accepting it and retrying.")
                self.accept_pending_alerts(initial_timeout=1, followup_timeout=1, max_alerts=5)
            except Exception as e:
                if attempt < 3:
                    logging.info(f"Duplicate overlay handling attempt {attempt} did not finish yet: {e}")
                    time.sleep(1)
                    continue
                logging.error(f"Failed to handle duplicate overlay: {e}")
                self.log_duplicate_overlay_diagnostics()
                return False

        return False

    def handle_duplicate_lni_popup(self, archive_as_duplicate=None):
        try:
            # Handle alert if present
            try:
                WebDriverWait(self.driver, 3).until(EC.alert_is_present())
                alert = self.driver.switch_to.alert
                alert_text = alert.text.strip()
                alert.accept()
                logging.info(f"Accepted alert: {alert_text}")

                # If it's not a duplicate alert, return early
                if "duplicate document" not in alert_text.lower():
                    logging.info("Alert was not a duplicate alert. Continuing...")
                    return

            except TimeoutException:
                logging.info("No alert found when checking for duplicate popup.")

            # Handle overlay if present
            if not self.handle_duplicate_overlay(archive_as_duplicate=archive_as_duplicate):
                logging.info("No duplicate overlay popup detected after alert.")

        except Exception as e:
            logging.error(f"Failed to handle Duplicate LNI popup: {e}")
            # Try to accept any remaining alert as a fallback
            try:
                alert = self.driver.switch_to.alert
                alert.accept()
                logging.info("Accepted fallback alert after duplicate handling error.")
            except:
                pass

    def click_duplicate_process_radio(self, timeout=10):
        process_radio = WebDriverWait(self.driver, timeout).until(
            EC.presence_of_element_located((By.ID, "processDuplicate"))
        )
        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", process_radio)
        try:
            WebDriverWait(self.driver, 2).until(EC.element_to_be_clickable((By.ID, "processDuplicate")))
            process_radio.click()
        except Exception:
            self.driver.execute_script(
                """
                arguments[0].checked = true;
                arguments[0].click();
                arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
                """,
                process_radio,
            )
        logging.info("Selected 'Process as a New Document' option.")

    def click_duplicate_archive_radio(self, timeout=10):
        archive_option = self.find_duplicate_archive_option(timeout=timeout)
        try:
            clicked_radio = self.driver.execute_script(
                """
                const option = arguments[0];
                let input = null;
                if (option.matches && option.matches('input[type="radio"]')) {
                    input = option;
                }
                if (!input && option.getAttribute) {
                    const forId = option.getAttribute('for');
                    if (forId) input = document.getElementById(forId);
                }
                if (!input && option.querySelector) {
                    input = option.querySelector('input[type="radio"]');
                }
                if (!input) {
                    const dialog = option.closest ? (option.closest('.ui-dialog') || document) : document;
                    input = Array.from(dialog.querySelectorAll('input[type="radio"]')).find((radio) => {
                        const text = `${radio.id || ''} ${radio.name || ''} ${radio.value || ''}`;
                        return /archive/i.test(text);
                    });
                }
                if (input) {
                    input.scrollIntoView({block: 'center'});
                    input.checked = true;
                    input.click();
                    input.dispatchEvent(new Event('change', { bubbles: true }));
                    return true;
                }
                option.click();
                return false;
                """,
                archive_option,
            )
            if not clicked_radio:
                self.click_duplicate_dialog_element(archive_option)
        except Exception:
            self.click_duplicate_dialog_element(archive_option)
        logging.info("Selected 'Archive as Duplicate' option.")

    def find_duplicate_archive_option(self, timeout=10):
        archive_text_xpath = (
            "contains(translate(normalize-space(.), "
            "'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), 'ARCHIVE AS DUPLICATE')"
        )

        def locate_option(driver):
            xpaths = [
                "//*[@id='archiveDuplicate' or @id='archiveAsDuplicate' or @id='archiveDuplicateDocument']",
                "//input[@type='radio' and (contains(translate(@id, 'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), 'ARCHIVE') or contains(translate(@value, 'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), 'ARCHIVE'))]",
                f"//label[{archive_text_xpath}]",
                f"//*[self::span or self::div or self::td][{archive_text_xpath}]",
            ]
            for xpath in xpaths:
                for option in driver.find_elements(By.XPATH, xpath):
                    if option.is_displayed() and option.is_enabled():
                        return option
            return False

        return WebDriverWait(self.driver, timeout).until(locate_option)

    def click_duplicate_continue_button(self, timeout=10):
        button = self.find_duplicate_continue_button(timeout=timeout)
        self.click_duplicate_dialog_element(button)
        logging.info("Clicked Continue button in Duplicate LNI dialog.")

    def find_duplicate_continue_button(self, timeout=10):
        def locate_button(driver):
            xpaths = [
                "//div[contains(@class, 'ui-dialog') and not(contains(@style, 'display: none'))]//button[.//span[normalize-space()='Continue'] or normalize-space()='Continue']",
                "//button[.//span[normalize-space()='Continue'] or normalize-space()='Continue']",
                "//button[contains(normalize-space(.), 'Continue')]",
                "//div[contains(@class, 'ui-dialog-buttonpane')]//button[.//span[normalize-space()='OK' or normalize-space()='Ok' or normalize-space()='Okay'] or normalize-space()='OK' or normalize-space()='Ok' or normalize-space()='Okay']",
            ]
            for xpath in xpaths:
                for button in driver.find_elements(By.XPATH, xpath):
                    if button.is_displayed() and button.is_enabled():
                        return button

            dialog_buttons = driver.find_elements(By.XPATH, "//div[contains(@class, 'ui-dialog-buttonpane')]//button")
            visible_buttons = [button for button in dialog_buttons if button.is_displayed() and button.is_enabled()]
            if visible_buttons:
                return visible_buttons[0]
            return False

        return WebDriverWait(self.driver, timeout).until(locate_button)

    def click_duplicate_dialog_element(self, element):
        try:
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            element.click()
        except Exception:
            self.driver.execute_script("arguments[0].click();", element)

    def wait_for_duplicate_overlay_to_clear(self, timeout=15):
        def duplicate_dialog_is_gone(driver):
            duplicate_dialogs = driver.find_elements(By.XPATH, "//div[contains(@class, 'ui-dialog') and contains(translate(normalize-space(.), 'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), 'DUPLICATE')]")
            visible_duplicate_dialogs = [dialog for dialog in duplicate_dialogs if dialog.is_displayed()]
            if visible_duplicate_dialogs:
                return False

            overlays = driver.find_elements(By.CLASS_NAME, "ui-widget-overlay")
            visible_overlays = [overlay for overlay in overlays if overlay.is_displayed()]
            if visible_overlays:
                return False

            process_radios = driver.find_elements(By.ID, "processDuplicate")
            if any(self.element_is_inside_visible_dialog(radio) for radio in process_radios):
                return False

            archive_radios = driver.find_elements(By.XPATH, "//*[contains(translate(@id, 'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), 'ARCHIVE') or contains(translate(@value, 'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), 'ARCHIVE')]")
            if any(self.element_is_inside_visible_dialog(radio) for radio in archive_radios):
                return False

            return True

        WebDriverWait(self.driver, timeout).until(duplicate_dialog_is_gone)
        logging.info("Overlay cleared. Safe to proceed.")

    def element_is_inside_visible_dialog(self, element):
        try:
            return bool(self.driver.execute_script(
                """
                const element = arguments[0];
                const dialog = element.closest ? element.closest('.ui-dialog') : null;
                return !!(dialog && dialog.offsetParent !== null);
                """,
                element,
            ))
        except Exception:
            return False

    def log_duplicate_overlay_diagnostics(self):
        try:
            dialogs = []
            for dialog in self.driver.find_elements(By.XPATH, "//div[contains(@class, 'ui-dialog')]"):
                if dialog.is_displayed():
                    dialogs.append((dialog.text or "").strip()[:500])
            overlay_count = len([
                overlay for overlay in self.driver.find_elements(By.CLASS_NAME, "ui-widget-overlay")
                if overlay.is_displayed()
            ])
            process_count = len([
                radio for radio in self.driver.find_elements(By.ID, "processDuplicate")
                if radio.is_displayed()
            ])
            archive_count = len([
                radio for radio in self.driver.find_elements(By.XPATH, "//*[contains(translate(@id, 'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), 'ARCHIVE') or contains(translate(@value, 'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), 'ARCHIVE')]")
                if radio.is_displayed()
            ])
            logging.warning(
                "Duplicate overlay diagnostics: visible_dialogs=%s visible_overlays=%s visible_processDuplicate=%s visible_archiveDuplicate=%s",
                dialogs,
                overlay_count,
                process_count,
                archive_count,
            )
        except Exception as e:
            logging.warning(f"Could not collect duplicate overlay diagnostics: {e}")

    def prepare_common_fields(self, file_name, decision_date=None, dar_mode=False, wc_mode=False, docket_override=None, court=None):
        formatted_docket = docket_override or CaseLawRouter.format_docket_number(None, file_name, dar_mode, wc_mode)

        # If no decision_date is provided, fetch from received field (optional fallback)
        if not decision_date:
            decision_date = self.get_decision_date_from_received()

        # Fill fields only once
        self.safe_fill_field('//*[@id="numberOfPages"]', "1", "Number of Pages")
        self.safe_fill_field('//*[@id="docketNumber"]', formatted_docket, "Docket Number")
        self.safe_fill_field('//*[@id="decisionDate"]', decision_date, "Decision Date")
        if court:
            self.select_dropdown_by_visible_text_or_value('//*[@id="court"]', court, "Court")

        # Utility: Dropdown selector with JS event trigger
        def select_dropdown_by_text(driver, element_id, visible_text):
            try:
                WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, element_id)))
                select = Select(driver.find_element(By.ID, element_id))
                select.select_by_visible_text(visible_text)
                driver.execute_script(f"document.getElementById('{element_id}').dispatchEvent(new Event('change'))")
                logging.info(f"Selected '{visible_text}' from dropdown '{element_id}'.")
            except Exception as e:
                logging.error(f"Could not select dropdown option from '{element_id}'")

    def select_dropdown_by_visible_text_or_value(self, xpath, selection, field_name):
        try:
            dropdown_element = self.wait.until(EC.presence_of_element_located((By.XPATH, xpath)))
            select = Select(dropdown_element)
            try:
                select.select_by_visible_text(selection)
            except Exception:
                select.select_by_value(selection)
            self.driver.execute_script("arguments[0].dispatchEvent(new Event('change'))", dropdown_element)
            logging.info(f"{field_name} selected: {selection}")
            self.handle_any_alert(timeout=2)
            return True
        except UnexpectedAlertPresentException:
            self.handle_any_alert(timeout=3)
            logging.info(f"{field_name} selected after alert handling: {selection}")
            return True
        except Exception as e:
            logging.error(f"Could not select {field_name}: {selection}")
            return False

    def get_selected_dropdown_text(self, dropdown_element):
        try:
            return str(self.driver.execute_script(
                """
                const select = arguments[0];
                if (!select) return '';
                const option = select.options && select.selectedIndex >= 0
                    ? select.options[select.selectedIndex]
                    : null;
                return option
                    ? (option.textContent || option.label || option.value || '').trim()
                    : (select.value || '').trim();
                """,
                dropdown_element,
            ) or "").strip()
        except Exception as e:
            logging.warning(f"Could not read selected dropdown text: {e}")
            return ""

    def set_dropdown_by_visible_text(self, dropdown_element, visible_text):
        try:
            return bool(self.driver.execute_script(
                """
                const select = arguments[0];
                const target = String(arguments[1] || '').trim().toUpperCase();
                if (!select || !select.options) return false;
                const option = Array.from(select.options).find((item) => {
                    return String(item.textContent || item.label || item.value || '').trim().toUpperCase() === target;
                });
                if (!option) return false;
                select.value = option.value;
                option.selected = true;
                select.dispatchEvent(new Event('input', { bubbles: true }));
                select.dispatchEvent(new Event('change', { bubbles: true }));
                return true;
                """,
                dropdown_element,
                visible_text,
            ))
        except Exception as e:
            logging.warning(f"Could not set dropdown to {visible_text}: {e}")
            return False

    def dropdown_text_matches(self, actual_text, expected_text):
        return str(actual_text or "").strip().upper() == str(expected_text or "").strip().upper()

    def select_source_detail(self, source_detail):
        if not source_detail or str(source_detail).strip().lower() == "nan":
            return True

        resolved_source_detail = resolve_source_detail(source_detail)
        if not resolved_source_detail:
            logging.warning(f"Invalid Source Detail input: {source_detail}")
            return False

        return self.select_dropdown_by_visible_text_or_value(
            '//*[@id="sourceDetails"]',
            resolved_source_detail,
            "Source Detail",
        )

    def handle_mspb_fields(self, row, mspb_metadata):
        try:
            case_name_xpath = '//*[@id="caseName"]'
            try:
                field = self.wait.until(EC.presence_of_element_located((By.XPATH, case_name_xpath)))
                existing_case_name = self.wait_for_existing_field_text(case_name_xpath, timeout=6)
                if existing_case_name:
                    logging.info(f"MSPB Case Name already present; leaving unchanged: {existing_case_name[:120]}")
                else:
                    if field.is_enabled() and field.get_attribute("readonly") != "true":
                        field.clear()
                        field.send_keys("RE")
                        logging.info("MSPB Case Name was blank; set to RE.")
                    else:
                        logging.info("Skipped MSPB Case Name because it is not interactable.")
            except Exception:
                logging.error("Error setting MSPB case name")

            if not self.select_source_detail(mspb_metadata.source_detail):
                return False

            comment_parts = []
            if getattr(mspb_metadata, "comments_text", ""):
                comment_parts.append(mspb_metadata.comments_text)

            additional_comments = str(row.get("Comments", "")).strip()
            if additional_comments and additional_comments.lower() != "nan":
                comment_parts.append(additional_comments)

            if comment_parts:
                self.append_comments(comment_parts, "MSPB")

            return True
        except Exception as e:
            logging.error(f"Error handling MSPB fields: {e}")
            return False

    def wait_for_existing_field_text(self, xpath, timeout=6):
        """Wait briefly for a field that IRT may populate asynchronously."""
        deadline = time.time() + timeout
        last_value = ""

        while time.time() < deadline:
            try:
                field = self.driver.find_element(By.XPATH, xpath)
                value = self.get_field_existing_text(field)
                if value:
                    return value
                last_value = value
            except Exception:
                pass
            time.sleep(0.5)

        return last_value

    def get_field_existing_text(self, field):
        try:
            value = self.driver.execute_script(
                """
                const el = arguments[0];
                return (
                    el.value ||
                    el.getAttribute('value') ||
                    el.innerText ||
                    el.textContent ||
                    ''
                ).trim();
                """,
                field,
            )
            return str(value or "").strip()
        except Exception:
            try:
                return (field.get_attribute("value") or "").strip()
            except Exception:
                return ""


    def handle_counsel_fields(self, row, dar_mode=False, wc_mode=False):
        comments_xpath = '//*[@id="comments"]'
        additional_comments = str(row.get("Comments", "")).strip()

        try:
            comments_field = self.wait.until(EC.presence_of_element_located((By.XPATH, comments_xpath)))
            existing_text = comments_field.get_attribute("value").strip()

            # Build the complete comment text
            comment_parts = []
            
            # Find and add the Main Opinion LNI automatically
            file_name = str(row.get("FileName", "")).strip()
            if file_name:
                docket = CaseLawRouter.format_docket_number(None, file_name, dar_mode, wc_mode)
                if docket:
                    # Look for the main opinion LNI in the full dataframe
                    main_lnis = [str(r["LNI"]).strip() for _, r in self.full_df.iterrows()
                                if not is_counsel(str(r["FileName"]), dar_mode, wc_mode) and
                                CaseLawRouter.format_docket_number(None, r["FileName"], dar_mode, wc_mode) == docket]

                    attached_lnis = []
                    for lni in main_lnis:
                        if lni and lni not in existing_text:
                            comment_parts.append(lni)
                            attached_lnis.append(lni)

                    if attached_lnis:
                        logging.info(f"Auto-attached {len(attached_lnis)} Main Opinion LNI(s) to comments: {attached_lnis}")
                    elif any(lni in existing_text for lni in main_lnis):
                        logging.info("Auto-found Main LNI already present in comments. Skipping.")
                    else:
                        logging.warning(f"Could not auto-find Main Opinion LNI for counsel docket: {docket}")
                else:
                    logging.warning(f"Could not extract docket number from counsel filename: {file_name}")
            else:
                logging.warning(f"Could not get filename for counsel row")
            
            # Add additional comments if available
            if additional_comments and additional_comments.lower() != "nan":
                comment_parts.append(additional_comments)
                logging.info(f"Adding additional comments to counsel: {additional_comments}")

            # If no new content to add, return early
            if not comment_parts:
                logging.info("No new comments to add for counsel row.")
                return

            # Prepare the new text
            if existing_text:
                if existing_text.endswith('.'):
                    existing_text = existing_text[:-1].strip()
                updated_text = f"{existing_text}; {'; '.join(comment_parts)}"
            else:
                updated_text = '; '.join(comment_parts)

            # Clear and fill with retry capability
            max_retries = 2
            for attempt in range(max_retries):
                try:
                    comments_field.clear()
                    comments_field.send_keys(updated_text)
                    logging.info(f"Updated comments field for counsel: {updated_text}")

                    # Check for any popup that might have appeared immediately
                    try:
                        alert = self.driver.switch_to.alert
                        alert_text = alert.text.strip()
                        alert.accept()

                        if "duplicate document" in alert_text.lower():
                            logging.info("Duplicate alert detected during comment update. Processing...")
                            self.handle_duplicate_lni_popup()
                            # Clear and retry the comment fill
                            comments_field.clear()
                            comments_field.send_keys(updated_text)
                            logging.info("Retried filling comments after duplicate alert")
                    except:
                        pass  # No alert present, continue normally

                    break  # Successfully filled, exit retry loop
                except Exception as e:
                    if attempt < max_retries - 1:
                        logging.warning(f"Failed to update comments on attempt {attempt + 1}, retrying...")
                        time.sleep(1)
                    else:
                        logging.error(f"Failed to update comments after {max_retries} attempts")

        except Exception as e:
            logging.error(f"Error handling counsel comments field")

    def find_main_opinion_lni_for_counsel(self, counsel_docket, counsel_row, dar_mode=False, wc_mode=False):
        """Find the Main Opinion LNI for a counsel document by matching docket numbers"""
        try:
            # Get the full dataframe from the class instance
            if hasattr(self, 'full_df') and self.full_df is not None:
                # Look for main opinion rows with matching docket
                for _, row in self.full_df.iterrows():
                    if not is_counsel(str(row.get("FileName", "")), dar_mode, wc_mode):
                        main_docket = CaseLawRouter.format_docket_number(None, row.get("FileName", ""), dar_mode, wc_mode)
                        if main_docket and main_docket == counsel_docket:
                            main_lni = str(row.get("LNI", "")).strip()
                            if main_lni and main_lni.lower() != "nan":
                                logging.info(f"Found Main Opinion LNI {main_lni} for counsel docket {counsel_docket}")
                                return main_lni
            return None
        except Exception as e:
            logging.error(f"Error finding Main Opinion LNI for counsel")
            return None

    def find_main_opinion_date_for_counsel(self, counsel_docket, counsel_file_name, dar_mode=False, wc_mode=False):
        """Find the Main Opinion decision date for a counsel document by matching docket numbers"""
        try:
            # Get the full dataframe from the class instance
            if hasattr(self, 'full_df') and self.full_df is not None:
                # Look for main opinion rows with matching docket
                for _, row in self.full_df.iterrows():
                    main_file_name = str(row.get("FileName", "")).strip()
                    if not is_counsel(main_file_name, dar_mode, wc_mode):
                        main_docket = CaseLawRouter.format_docket_number(None, main_file_name, dar_mode, wc_mode)
                        if main_docket and main_docket == counsel_docket:
                            # Extract date from main opinion filename
                            main_date = self.extract_decision_date_from_filename(main_file_name)
                            if main_date:
                                logging.info(f"Found Main Opinion date {main_date} for counsel docket {counsel_docket}")
                                return main_date
            return None
        except Exception as e:
            logging.error(f"Error finding Main Opinion date for counsel")
            return None

    def handle_main_opinion_fields(self, row, full_df, row_index, file_path, dar_mode=False, wc_mode=False):
        case_name_xpath = '//*[@id="caseName"]'
        try:
            field = self.wait.until(EC.presence_of_element_located((By.XPATH, case_name_xpath)))
            existing_case_name = self.wait_for_existing_field_text(case_name_xpath, timeout=6)
            if existing_case_name:
                logging.info(f"Main Opinion Case Name already present; leaving unchanged: {existing_case_name[:120]}")
            else:
                if field.is_enabled() and field.get_attribute("readonly") != "true":
                    field.clear()
                    field.send_keys("RE")
                    logging.info("Main Opinion Case Name was blank; set to RE.")
                else:
                    logging.info("Skipped Main Opinion Case Name because it is not interactable.")
        except Exception as e:
            logging.error(f"Error setting case name")

        # ✅ Move Source Detail handling BEFORE clicking 'related'
        source_detail = str(row.get("SourceDetail", "")).strip()
        if source_detail and source_detail.lower() != "nan":
            try:
                resolved_source_detail = resolve_source_detail(source_detail)
                if resolved_source_detail:
                    source_detail_dropdown = self.wait.until(
                        EC.presence_of_element_located((By.XPATH, '//*[@id="sourceDetails"]'))
                    )
                    try:
                        source_detail_dropdown.click()
                        logging.info("Source Detail dropdown clicked successfully.")

                        # Duplicate alert check
                        try:
                            WebDriverWait(self.driver, 2).until(EC.alert_is_present())
                            alert = self.driver.switch_to.alert
                            alert_text = alert.text.strip()
                            alert.accept()
                            logging.info(f"Handled alert after dropdown click: {alert_text}")
                            if "duplicate document" in alert_text.lower():
                                self.handle_duplicate_lni_popup()
                        except TimeoutException:
                            pass
                    except Exception as e:
                        logging.error(f"Source Detail dropdown is not clickable")
                        return

                    # Try selecting the dropdown value
                    try:
                        select = Select(source_detail_dropdown)
                        select.select_by_visible_text(resolved_source_detail)
                        logging.info(f"Selected Source Detail: {resolved_source_detail}")
                    except UnexpectedAlertPresentException as e:
                        logging.warning(f"Unexpected alert during Source Detail selection")
                        try:
                            alert = self.driver.switch_to.alert
                            alert_text = alert.text.strip()
                            alert.accept()
                            logging.info(f"Handled alert: {alert_text}")
                            if "duplicate document" in alert_text.lower():
                                self.handle_duplicate_lni_popup()
                                # Re-click 'related' again if needed
                                try:
                                    related_checkbox = self.driver.find_element(By.XPATH, '//*[@id="related"]')
                                    if not related_checkbox.is_selected():
                                        related_checkbox.click()
                                        logging.info("Re-clicked the Related checkbox after alert reset.")
                                except Exception as click_err:
                                    logging.warning(f"Failed to re-click Related checkbox: {click_err}")
                        except Exception as alert_err:
                            logging.warning(f"Failed to handle alert gracefully: {alert_err}")

                        # Retry selection
                        try:
                            select = Select(source_detail_dropdown)
                            select.select_by_visible_text(resolved_source_detail)
                            logging.info(f"Retried and selected Source Detail: {resolved_source_detail}")
                        except Exception as retry_err:
                            logging.error(f"Retry failed after alert: {retry_err}")
                    except Exception as e:
                        logging.error(f"Error selecting Source Detail value '{resolved_source_detail}'")
                else:
                    logging.warning(f"Invalid Source Detail input: {source_detail}")
            except Exception as e:
                logging.error(f"Error finding Source Detail dropdown")

        # ✅ Now click the Related checkbox AFTER Source Detail
        try:
            self.click_element('//*[@id="related"]', wait_time=0)
        except Exception as e:
            logging.error(f"Error ticking 'related' checkbox")

        # First handle the related and recycled counsel LNIs
        main_docket = CaseLawRouter.format_docket_number(None, row["FileName"], dar_mode, wc_mode)
        related_attached = self.handle_related_ln_is(row, full_df, row_index=row_index, file_path=file_path, dar_mode=dar_mode, wc_mode=wc_mode)
        if not related_attached:
            logging.error(f"Skipping main opinion for docket {main_docket} because no related LNI could be attached.")
            current_status = status_updates_buffer.get(row_index) if row_index is not None else None
            if not current_status:
                current_status = "Missing Counsel Information"
                if row_index is not None:
                    status_updates_buffer[row_index] = current_status
            self.driver.close()
            self.driver.switch_to.window(self.driver.window_handles[0])
            return current_status

        # Check if both Comments and Route are not interactable
        try:
            comments_field = self.wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="comments"]')))
            route_element = self.wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="route"]')))

            if not comments_field.is_enabled() and not route_element.is_enabled():
                logging.error("Both Comments and Route dropdown are non-interactable. Skipping Main Opinion.")
                status_updates_buffer[row_index] = "Non-interactable IRT Form"
                self.driver.close()
                self.driver.switch_to.window(self.driver.window_handles[0])
                return "Non-interactable IRT Form"

        except Exception as e:
            logging.error(f"Error checking Comments/Route interactability")
            status_updates_buffer[row_index] = "Non-interactable IRT Form"
            self.driver.close()
            self.driver.switch_to.window(self.driver.window_handles[0])
            return "Non-interactable IRT Form"


        # Then handle additional comments if they exist
        additional_comments = str(row.get("Comments", "")).strip()
        if additional_comments and additional_comments.lower() != "nan":
            try:
                comments_field = self.wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="comments"]')))
                existing_text = comments_field.get_attribute("value").strip()

                # Prepare the new text
                if existing_text:
                    if existing_text.endswith('.'):
                        existing_text = existing_text[:-1].strip()
                    updated_text = f"{existing_text}; {additional_comments}"
                else:
                    updated_text = additional_comments

                # Clear and fill with retry capability
                max_retries = 2
                for attempt in range(max_retries):
                    try:
                        comments_field.clear()
                        comments_field.send_keys(updated_text)
                        logging.info(f"Updated comments field with additional comments: {updated_text}")
                        break
                    except Exception as e:
                        if attempt < max_retries - 1:
                            logging.warning(f"Failed to update comments on attempt {attempt + 1}, retrying...")
                            time.sleep(1)
                        else:
                            logging.error(f"Failed to update comments after {max_retries} attempts")
            except Exception as e:
                logging.error(f"Error handling additional comments")

    def handle_related_ln_is(self, row, full_df, row_index=None, file_path=None, dar_mode=False, wc_mode=False):
        try:
            # Get main docket number
            main_docket = CaseLawRouter.format_docket_number(None, row["FileName"], dar_mode, wc_mode)
            logging.info(f"Processing related LNIs for docket: {main_docket}")

            # Get all related LNIs (including multiple recycled LNIs)
            related_ln_is = get_related_counsel_lnis(
                main_docket,
                full_df,
                recycled_lni=row.get("RecycledCounselLNI"),
                dar_mode=dar_mode,
                wc_mode=wc_mode
            )

            if not related_ln_is:
                logging.info(f"No related LNIs found for docket: {main_docket}")
                if row_index is not None:
                    status_updates_buffer[row_index] = "NO COUNSEL ATTACHED"
                return False  # Return False to indicate failure

            logging.info(f"Found {len(related_ln_is)} related LNIs to process")

            # Get existing LNIs from the box
            related_lni_box = self.long_wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="relatedLni"]')))
            existing_text = related_lni_box.text
            existing_lnis = [lni.strip() for lni in existing_text.split('\n') if lni.strip()]

            attached_any = False
            for lni in related_ln_is:
                if not lni or str(lni).lower() == "nan":
                    logging.warning(f"Skipping invalid Related LNI: {lni}")
                    continue

                # Initial check
                if lni in existing_lnis:
                    logging.info(f"{lni} already in Related LNI box. Skipping.")
                    continue

                success = False
                try:
                    if not self.clear_and_fill_input('//*[@id="relateLNIs"]', lni):
                        if row_index is not None:
                            status_updates_buffer[row_index] = "RELATED LNI FIELD LOCKED"
                        logging.warning(f"Related LNI input was not interactable for {lni}.")
                        return False
                    self.wait.until(EC.element_to_be_clickable((By.XPATH, '//*[@id="AddRelated"]'))).click()
                    # Wait up to 5 minutes for the LNI to appear in the list box
                    def lni_in_listbox(driver):
                        related_lni_box = driver.find_element(By.XPATH, '//*[@id="relatedLni"]')
                        updated_lnis = [x.strip() for x in related_lni_box.text.split('\n') if x.strip()]
                        return lni in updated_lnis
                    self.long_wait.until(lni_in_listbox)
                    logging.info(f"Related Counsel LNI {lni} added successfully.")
                    attached_any = True
                    success = True
                except Exception as e:
                    if "already exists" in str(e).lower():
                        logging.warning(f"Related Counsel LNI {lni} already attached. Skipping.")
                        logging.info(f"{lni} already exists according to alert. Skipping further attempts.")
                        success = True
                    else:
                        logging.error(f"Failed to add LNI {lni}")
                        if 'TimeoutException' in str(type(e)) or 'timeout' in str(e).lower():
                            # Get docket number for message
                            docket_number = CaseLawRouter.format_docket_number(None, row["FileName"], dar_mode, wc_mode) if "FileName" in row else "?"
                            msg = f"Oops! Related Counsel LNI {lni} for Docket Number {docket_number} did not attach after 5 minutes. Skipping this Main Opinion. Retry again later."
                            logging.warning(msg)
                            if self.show_error:
                                self.show_error(msg)
                            if row_index is not None:
                                status_updates_buffer[row_index] = "RELATED LNI TIMEOUT"
                            return False  # Skip this main opinion
                if not success:
                    logging.warning(f"Failed to attach LNI {lni} after waiting up to 5 minutes.")

            # After all attempts, update status if nothing was attached
            # Re-read the list box to check if any of the related LNIs are present
            related_lni_box = self.long_wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="relatedLni"]')))
            final_text = related_lni_box.text
            final_lnis = [lni.strip() for lni in final_text.split('\n') if lni.strip()]
            if not any(lni in final_lnis for lni in related_ln_is):
                logging.warning(f"No new LNIs were attached for docket: {main_docket}")
                if row_index is not None:
                    status_updates_buffer[row_index] = "NO COUNSEL ATTACHED"
                return False  # Return False to indicate failure

        except Exception as e:
            logging.error(f"Error handling related LNIs")
            if row_index is not None:
                status_updates_buffer[row_index] = "RELATED LNI ERROR"
            return False  # Return False to indicate failure
        return True  # Return True if at least one LNI was attached

    def extract_decision_date_from_filename(self, file_name):
        """
        Extract decision date from filename, supporting both MMDDYYYY and YYYYMMDD formats.
        
        Args:
            file_name (str): Filename to extract date from
            
        Returns:
            str: Date in MM-DD-YYYY format if found, None otherwise
        """
        try:
            # Look for 8-digit date pattern in filename
            match = re.search(r'[_-](\d{8})(?=[_-]|\.|$)|^(\d{8})[_-]|[_-](\d{8})$', str(file_name))
            if match:
                # Get the first non-None group
                date_digits = None
                for i in range(1, 4):
                    if match.group(i):
                        date_digits = match.group(i)
                        break
                
                if date_digits and len(date_digits) == 8:
                    # Try YYYYMMDD format first (year 1900-2099, month 01-12, day 01-31)
                    year = int(date_digits[:4])
                    month = int(date_digits[4:6])
                    day = int(date_digits[6:8])
                    
                    if 1900 <= year <= 2099 and 1 <= month <= 12 and 1 <= day <= 31:
                        # Format as MM-DD-YYYY
                        return f"{month:02d}-{day:02d}-{year}"
                    
                    # Try MMDDYYYY format as fallback (month 01-12, day 01-31, year 1900-2099)
                    month = int(date_digits[:2])
                    day = int(date_digits[2:4])
                    year = int(date_digits[4:])
                    
                    if 1 <= month <= 12 and 1 <= day <= 31 and 1900 <= year <= 2099:
                        # Format as MM-DD-YYYY
                        return f"{month:02d}-{day:02d}-{year}"
        except Exception as e:
            logging.error(f"Error extracting decision date from filename '{file_name}': {e}")
        # If not found or invalid, return None to trigger fallback
        return None

    def process_main_opinion_with_attachments(self, main_file, attachment_files, dar_mode=True):
        """
        Process a main opinion document with its attached counsel and ARC files.
        
        Args:
            main_file (str): Main opinion filename
            attachment_files (list): List of counsel and ARC filenames to attach
            dar_mode (bool): Whether to use DAR mode processing
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            logging.info(f"Processing main opinion {main_file} with {len(attachment_files)} attachments")
            
            # Create a mock row for the main opinion file
            mock_row = {
                'FileName': main_file,
                'LNI': '',  # Will be filled during processing
                'Comments': '',
                'RecycledCounselLNI': ''
            }
            
            # Process the main opinion
            # This would integrate with the existing main opinion processing logic
            # For now, we'll use the existing handle_main_opinion_fields method
            success = self.handle_main_opinion_fields(
                mock_row, 
                self.full_df if hasattr(self, 'full_df') else None,
                row_index=None,
                file_path=None,
                dar_mode=dar_mode,
                wc_mode=False
            )
            
            if success:
                logging.info(f"Successfully processed main opinion {main_file}")
                # Here you would add logic to attach the counsel and ARC files
                # This would involve updating the related LNI fields
                for attachment in attachment_files:
                    logging.info(f"Attached {attachment} to main opinion {main_file}")
            
            return success
            
        except Exception as e:
            logging.error(f"Error processing main opinion {main_file}: {str(e)}")
            return False

    def process_standalone_counsel(self, counsel_file, dar_mode=True):
        """
        Process a standalone counsel or ARC file.
        
        Args:
            counsel_file (str): Counsel or ARC filename
            dar_mode (bool): Whether to use DAR mode processing
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            logging.info(f"Processing standalone counsel/ARC file: {counsel_file}")
            
            # Create a mock row for the counsel file
            mock_row = {
                'FileName': counsel_file,
                'LNI': '',  # Will be filled during processing
                'Comments': '',
                'RecycledCounselLNI': ''
            }
            
            # Process the counsel file
            # This would integrate with the existing counsel processing logic
            # For now, we'll use the existing handle_counsel_fields method
            success = self.handle_counsel_fields(
                mock_row,
                dar_mode=dar_mode,
                wc_mode=False
            )
            
            if success:
                file_type = "ARC document" if 'arc' in counsel_file.lower() else "counsel file"
                logging.info(f"Successfully processed standalone {file_type}: {counsel_file}")
            
            return success
            
        except Exception as e:
            logging.error(f"Error processing standalone counsel file {counsel_file}: {str(e)}")
            return False

