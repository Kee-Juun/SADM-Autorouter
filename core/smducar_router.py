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
from selenium.common.exceptions import NoAlertPresentException, NoSuchElementException, NoSuchWindowException, TimeoutException, UnexpectedAlertPresentException
import time
import threading
from urllib.parse import parse_qs, unquote, urljoin, urlparse

# Config and logging utilities
from .smducar_config import (
    status_updates_buffer,
    mspb_metadata_buffer,
    itc_content_fingerprint_buffer,
    mework_content_fingerprint_buffer,
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
    STATUS_DECISION_DATE_UPDATED,
    STATUS_DATE_UPDATE_UNCONFIRMED,
    STATUS_PROCESSING,
    STATUS_NEEDS_RERUN_INTERRUPTED,
    defer_main_rows_with_failed_counsel,
    is_completed_status,
    mark_row_processing,
    normalize_status,
    should_recheck_irsplr_comment_review,
    should_recheck_irsplr_pdf_review,
    should_recheck_smd_decision_date,
)

from .mspb_extractor import (
    parse_mspb_document_text,
    parse_mspb_pdf_bytes,
)

from .irt_duplicate_verifier import (
    IRTDocumentProfile,
    build_document_profile,
    compare_document_profiles,
)
from .irsplr_browser_check import confirm_browser_pdf

from .itc_extractor import (
    ITCMetadata,
    extract_itc_docket_from_filename,
    get_itc_court,
    is_itc_row,
    parse_itc_document_text,
    parse_itc_pdf_bytes,
)

from .irsplr_extractor import (
    IRSPLRCorruptDocument,
    IRSPLRDocumentReviewRequired,
    IRSPLRMetadata,
    build_irsplr_corrupt_exclusion_metadata,
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

from .mework_extractor import (
    MEWORKMetadata,
    is_mework_row,
    parse_mework_document_text,
    parse_mework_pdf_bytes,
)

from .mosu00_extractor import (
    MOSU00Metadata,
    find_mosu00_source_file,
    is_mosu00_table_row,
    parse_mosu00_html_file,
    parse_mosu00_html_text,
)
from .fcc_extractor import FCCMetadata, is_fcc_row, parse_fcc_document_text, parse_fcc_pdf_bytes
from .ferc_extractor import (
    FERCMetadata,
    is_ferc_row,
    parse_ferc_document_text,
    parse_ferc_docx_bytes,
    parse_ferc_pdf_bytes,
)
from .nlrb_extractor import (
    NLRBMetadata,
    is_nlrb_row,
    parse_nlrb_document_text,
    parse_nlrb_pdf_bytes,
)


_itc_duplicate_lock = threading.Lock()


def _has_explicit_metadata_router_mode(
    *,
    itc_mode=False,
    irsplr_mode=False,
    ohtax0_mode=False,
    mnsutb_mode=False,
    mework_mode=False,
    mosu00_mode=False,
    fcc_mode=False,
    ferc_mode=False,
    nlrb_mode=False,
):
    """Whether a selected router must take precedence over filename guesses."""
    return any((
        itc_mode,
        irsplr_mode,
        ohtax0_mode,
        mnsutb_mode,
        mework_mode,
        mosu00_mode,
        fcc_mode,
        ferc_mode,
        nlrb_mode,
    ))


class RouterSessionLostError(RuntimeError):
    """Raised when the active Selenium browser session can no longer be used."""


class IRTFormRecoveryError(RuntimeError):
    """A duplicate alert did not return a usable form; never continue to Save."""


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
        self.mework_download_dir = Path.home() / "Downloads" / "Case Law Auto-Routing Resources" / "MEWORK PDF Downloads"
        self.mework_download_dir.mkdir(parents=True, exist_ok=True)
        self.mosu00_download_dir = Path.home() / "Downloads" / "Case Law Auto-Routing Resources" / "MOSU00 HTML Downloads"
        self.mosu00_download_dir.mkdir(parents=True, exist_ok=True)
        self.fcc_download_dir = Path.home() / "Downloads" / "Case Law Auto-Routing Resources" / "FCC PDF Downloads"
        self.fcc_download_dir.mkdir(parents=True, exist_ok=True)
        self.ferc_download_dir = Path.home() / "Downloads" / "Case Law Auto-Routing Resources" / "FERC PDF Downloads"
        self.ferc_download_dir.mkdir(parents=True, exist_ok=True)
        self.nlrb_download_dir = Path.home() / "Downloads" / "Case Law Auto-Routing Resources" / "NLRB PDF Downloads"
        self.nlrb_download_dir.mkdir(parents=True, exist_ok=True)
        self._archive_duplicate_mode = False
        self._irsplr_unreadable_pdf_signatures = set()
        # Populated only after IRT raises its own duplicate alert.  Keeping this
        # cache per run avoids re-downloading the same candidate more than once.
        self._duplicate_profile_cache = {}
        self._active_duplicate_lni = None
        self._verified_duplicate_match = None
        # SADM and DARA counsel commonly resemble their main opinions closely
        # enough to produce routine IRT duplicate alerts.  Their run setup
        # turns content verification off, but specialized modes retain it.
        self._irt_duplicate_verification_enabled = True
        self._irsplr_duplicate_pdf_validation = False
        self._irsplr_browser_first = False
        self._irsplr_duplicate_review_reason = ""
        self._itc_duplicate_verification = False
        self._itc_duplicate_review_reason = ""

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
            if row_status in {"DONE", "ALREADY PROCESSED", STATUS_DECISION_DATE_UPDATED}:
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
            is_decision_date = field_name == "Decision Date" or xpath == '//*[@id="decisionDate"]'
            if is_decision_date:
                value = self.normalize_mapping_decision_date(value)
                if value is None:
                    logging.info("Skipped Decision Date because no requested date was available; leaving the IRT value unchanged.")
                    return
            value = self.normalize_irt_text(value)
            requested_date_key = self._saved_date_key(value) if is_decision_date else None
            element = self.long_wait.until(EC.presence_of_element_located((By.XPATH, xpath)))

            if not element.is_enabled() or element.get_attribute("readonly") == "true":
                logging.info(f"Skipped {field_name} because it's not interactable.")
                return

            current_val = element.get_attribute("value")
            if current_val and (
                current_val.strip() == str(value).strip()
                or (requested_date_key is not None and self._saved_date_key(current_val) == requested_date_key)
            ):
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
            "File Name": self.normalized_file_name(
                row.get("FileName", existing.get("File Name", ""))
            ),
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
            if metadata is None and metadata_status in {"Attempted", "Search Failed"}:
                mspb_metadata_buffer[row_index]["Route"] = "Not Routed"
            if metadata and getattr(metadata, "is_excluded", False):
                mspb_metadata_buffer[row_index]["Route"] = "Archive"

    def flag_irsplr_document_review(self, row, row_index, reason):
        """Leave failed source documents untouched and visible in review reporting."""
        status = f"MANUAL REVIEW REQUIRED - IRSPLR PDF: {reason}"
        if row_index is not None:
            status_updates_buffer[row_index] = status
            self.record_irsplr_metadata(row_index, row, row.get("LNI", ""), metadata_status=status)
            if row_index in mspb_metadata_buffer:
                mspb_metadata_buffer[row_index]["Route"] = "Not Routed"
        logging.warning("LNI %s: %s", row.get("LNI", ""), status)
        return status

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

    def record_mework_metadata(self, row_index, row, lni, metadata=None, metadata_status="Attempted"):
        """Capture MEWORK metadata used for the final workbook sheet."""
        self.record_mspb_metadata(row_index, row, lni, metadata=metadata, metadata_status=metadata_status)
        if row_index in mspb_metadata_buffer:
            mspb_metadata_buffer[row_index]["Metadata Type"] = "MEWORK"
            if metadata and (getattr(metadata, "is_true_duplicate", False) or getattr(metadata, "is_excluded", False)):
                mspb_metadata_buffer[row_index]["Route"] = "Archive"
            duplicate_lni = getattr(metadata, "duplicate_of_lni", "") if metadata else ""
            if duplicate_lni and not getattr(metadata, "is_excluded", False):
                prepared = mspb_metadata_buffer[row_index].get("Prepared Comments", "") or ""
                duplicate_comment = f"Dup of {duplicate_lni}"
                if duplicate_comment not in prepared:
                    mspb_metadata_buffer[row_index]["Prepared Comments"] = (
                        f"{prepared}; {duplicate_comment}" if prepared else duplicate_comment
                    )

    def record_mosu00_metadata(self, row_index, row, lni, metadata=None, metadata_status="Attempted"):
        """Capture MOSU00 table metadata used for the final workbook sheet."""
        self.record_mspb_metadata(row_index, row, lni, metadata=metadata, metadata_status=metadata_status)
        if row_index in mspb_metadata_buffer:
            mspb_metadata_buffer[row_index]["Metadata Type"] = "MOSU00"
            if metadata:
                child_dockets = getattr(metadata, "child_dockets", ()) or ()
                mspb_metadata_buffer[row_index]["Extracted Other Numbers"] = "; ".join(child_dockets)
                mspb_metadata_buffer[row_index]["Prepared Comments"] = getattr(metadata, "comments_text", "") or ""

    def record_fcc_metadata(self, row_index, row, lni, metadata=None, metadata_status="Attempted"):
        """Capture FCC extraction plus decisions that stop before IRT."""
        self.record_mspb_metadata(row_index, row, lni, metadata=metadata, metadata_status=metadata_status)
        if row_index in mspb_metadata_buffer:
            mspb_metadata_buffer[row_index]["Metadata Type"] = "FCC"
            if metadata and getattr(metadata, "is_excluded", False):
                mspb_metadata_buffer[row_index]["Route"] = "Archive"

    def record_ferc_metadata(self, row_index, row, lni, metadata=None, metadata_status="Attempted"):
        """Capture FERC extraction and review outcomes for the mapping sheet."""
        self.record_mspb_metadata(row_index, row, lni, metadata=metadata, metadata_status=metadata_status)
        if row_index in mspb_metadata_buffer:
            mspb_metadata_buffer[row_index]["Metadata Type"] = "FERC"

    def record_nlrb_metadata(self, row_index, row, lni, metadata=None, metadata_status="Attempted"):
        """Capture NLRB extraction and explicit review outcomes in the mapping sheet."""
        self.record_mspb_metadata(row_index, row, lni, metadata=metadata, metadata_status=metadata_status)
        if row_index in mspb_metadata_buffer:
            mspb_metadata_buffer[row_index]["Metadata Type"] = "NLRB"

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
                if current_lni and str(existing_lni).strip().upper() == current_lni.upper():
                    # Extraction precedes Modify. A pre-Save retry can see
                    # its own cached fingerprint; that is not another case.
                    logging.info("ITC fingerprint already belongs to this LNI; retaining normal routing on retry: %s", current_lni)
                    return metadata
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

    def mark_mework_duplicate_status(self, row_index, row, lni, metadata: MEWORKMetadata):
        """Mark only text-equivalent MEWORK decisions as duplicates within this run."""
        if not metadata or not getattr(metadata, "content_fingerprint", ""):
            return metadata
        if getattr(metadata, "is_excluded", False):
            logging.info("MEWORK document is excluded; exclusion takes priority over duplicate classification.")
            return metadata

        current_label = str(row.get("FileName", "")).strip() or str(lni or "").strip()
        current_lni = str(lni or "").strip()
        with _itc_duplicate_lock:
            existing = mework_content_fingerprint_buffer.get(metadata.content_fingerprint)
            if existing:
                existing_label = existing.get("label", "") if isinstance(existing, dict) else str(existing)
                existing_lni = existing.get("lni", "") if isinstance(existing, dict) else ""
                logging.warning(
                    "Confirmed MEWORK true duplicate by normalized PDF text fingerprint: %s duplicates %s",
                    current_label,
                    existing_label,
                )
                return replace(
                    metadata,
                    is_true_duplicate=True,
                    duplicate_of=existing_label,
                    duplicate_of_lni=existing_lni,
                )

            mework_content_fingerprint_buffer[metadata.content_fingerprint] = {
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
        except (IRSPLRDocumentReviewRequired, RouterSessionLostError):
            raise
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

    def extract_mework_metadata_from_search_result(self, row, row_index=None):
        """Open the result PDF from the File Name column and parse MEWORK metadata."""
        try:
            link_element = self.find_mspb_file_name_link(row)
            if link_element is None:
                logging.warning("MEWORK File Name link was not found in the search results.")
                return None

            metadata = self.open_mework_link_and_extract_metadata(link_element, row)
            if metadata and getattr(metadata, "has_text_content", False):
                return metadata

            logging.warning("MEWORK PDF did not expose readable text.")
            return None
        except Exception as e:
            logging.error(f"Error extracting MEWORK metadata from PDF: {e}")
            return None

    def extract_mosu00_metadata_from_search_result(self, row, row_index=None, file_path=None):
        """Open the result HTML from the File Name column and parse MOSU00 table metadata."""
        try:
            link_element = self.find_mspb_file_name_link(row)
            if link_element is not None:
                metadata = self.open_mosu00_link_and_extract_metadata(link_element, row)
                if metadata:
                    return metadata
                logging.warning("MOSU00 table HTML link opened, but metadata was not readable.")
            else:
                logging.warning("MOSU00 File Name link was not found in the search results.")

            file_name = str(row.get("FileName", "")).strip()
            local_file = find_mosu00_source_file(file_name, reference_path=file_path)
            if local_file:
                metadata = parse_mosu00_html_file(local_file)
                if metadata:
                    self.log_mosu00_metadata(metadata, f"local file {local_file.name}")
                    return metadata
                logging.warning("MOSU00 local HTML fallback could not parse required metadata: %s", local_file)

            return None
        except Exception as e:
            logging.error(f"Error extracting MOSU00 table metadata from HTML: {e}")
            return None

    def extract_fcc_metadata_from_search_result(self, row, row_index=None):
        try:
            link_element = self.find_mspb_file_name_link(row)
            if link_element is None:
                logging.warning("FCC File Name link was not found in the search results.")
                return None
            metadata = self.open_fcc_link_and_extract_metadata(link_element, row)
            return metadata if metadata and metadata.has_text_content else None
        except Exception as exc:
            logging.error("Error extracting FCC metadata from PDF: %s", exc)
            return None

    def extract_ferc_metadata_from_search_result(self, row, row_index=None):
        try:
            link_element = self.find_mspb_file_name_link(row)
            if link_element is None:
                logging.warning("FERC File Name link was not found in the search results.")
                return None
            metadata = self.open_ferc_link_and_extract_metadata(link_element, row)
            return metadata if metadata and metadata.has_text_content else None
        except Exception as exc:
            logging.error("Error extracting FERC metadata from PDF: %s", exc)
            return None

    def extract_nlrb_metadata_from_search_result(self, row, row_index=None):
        try:
            # NLRB mapping sheets are intentionally allowed to contain only
            # LNIs. Resolve the File Name anchor from that exact result row,
            # not from a generic table cell or a different visible result.
            link_element = self.find_nlrb_file_name_link(row)
            if link_element is None:
                logging.warning("NLRB File Name link was not found in the search results.")
                return None
            return self.open_nlrb_link_and_extract_metadata(link_element, row)
        except Exception as exc:
            logging.error("Error extracting NLRB metadata from PDF: %s", exc)
            return None

    def find_nlrb_file_name_link(self, row):
        """Return the PDF anchor on the current NLRB result row for its LNI."""
        lni = str(row.get("LNI", "") or "").strip()
        if lni and lni.lower() != "nan":
            lni_literal = self.xpath_literal(lni)
            row_xpath = (
                "//tr[.//td[contains(normalize-space(.), "
                f"{lni_literal})]]"
            )
            for result_row in self.driver.find_elements(By.XPATH, row_xpath):
                for link in result_row.find_elements(By.XPATH, ".//a[@href]"):
                    href = self._get_element_href(link)
                    if href:
                        self.capture_file_name_from_link(row, link)
                        return link
            logging.warning("NLRB result row for LNI %s did not contain a File Name hyperlink.", lni)
            return None

        # A filename is optional for NLRB, but retain the generic lookup for
        # manually prepared sheets that supply one.
        return self.find_mspb_file_name_link(row)

    def find_mspb_file_name_link(self, row):
        """Find the clickable document link under the File Name column in IRT results."""
        file_name = str(row.get("FileName", "")).strip()
        lni = str(row.get("LNI", "") or "").strip()

        # Mapping sheets may deliberately contain just Court Code and LNI.
        # In that case, anchor the lookup to the searched LNI's result row
        # before considering a generic table/file-name fallback.
        if lni and lni.lower() != "nan":
            lni_literal = self.xpath_literal(lni)
            row_xpath = (
                "//tr[.//td[contains(normalize-space(.), "
                f"{lni_literal})]]"
            )
            for result_row in self.driver.find_elements(By.XPATH, row_xpath):
                for link in result_row.find_elements(By.XPATH, ".//a[@href]"):
                    if self._get_element_href(link):
                        self.capture_file_name_from_link(row, link)
                        return link

        if file_name and file_name.lower() != "nan":
            for candidate in self.driver.find_elements(By.XPATH, f"//a[contains(normalize-space(.), {self.xpath_literal(file_name)})]"):
                if candidate.is_displayed():
                    self.capture_file_name_from_link(row, candidate)
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
                            self.capture_file_name_from_link(row, link)
                            return link
                    if file_cell.is_displayed():
                        self.capture_file_name_from_link(row, file_cell)
                        return file_cell
            except Exception:
                continue

        # Fallback: first visible PDF-looking link in the results.
        for candidate in self.driver.find_elements(By.XPATH, "//a[contains(translate(@href, 'PDF', 'pdf'), '.pdf')]"):
            if candidate.is_displayed():
                self.capture_file_name_from_link(row, candidate)
                return candidate

        # MOSU00 table rows can be HTML instead of PDF.
        for candidate in self.driver.find_elements(By.XPATH, "//a[contains(translate(@href, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '.html') or contains(translate(@href, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '.htm')]"):
            if candidate.is_displayed():
                self.capture_file_name_from_link(row, candidate)
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

    def open_fcc_link_and_extract_metadata(self, element, row):
        """Open the IRT File Name PDF and read its first-page FCC metadata.

        FCC documents are often returned by IRT as attachment downloads in
        headless Chrome.  In that case Chrome creates then immediately closes
        the viewer tab, so download-and-parse must happen before attempting to
        inspect browser-tab text.
        """
        main_tab = self.driver.current_window_handle
        before_handles = set(self.driver.window_handles)
        before_downloads = self.snapshot_fcc_downloads()
        opened_tab = None
        expected_filename = str(row.get("FileName", "")).strip()
        try:
            href = self._get_element_href(element)
            target_url = urljoin(self.driver.current_url, href) if href else None
            self.enable_chrome_downloads(self.fcc_download_dir)
            self.enable_browser_network_capture()
            if target_url:
                self.driver.execute_script("window.open(arguments[0], '_blank');", target_url)
            else:
                element.click()

            # IRT can serve File Name links as Content-Disposition attachments.
            # Reading that saved file is reliable even if Chrome closes its
            # transient PDF tab before Selenium can select it.
            downloaded_metadata = self.wait_for_fcc_downloaded_metadata(
                before_downloads,
                expected_filename,
                timeout=15,
            )
            if downloaded_metadata:
                return downloaded_metadata

            try:
                WebDriverWait(self.driver, 12).until(lambda d: len(d.window_handles) > len(before_handles))
                new_handles = set(self.driver.window_handles) - before_handles
                if new_handles:
                    opened_tab = new_handles.pop()
                    self.driver.switch_to.window(opened_tab)
            except TimeoutException:
                logging.info("FCC PDF did not open a readable tab; continuing with download/network fallback.")

            downloaded_metadata = self.wait_for_fcc_downloaded_metadata(
                before_downloads,
                expected_filename,
                timeout=15,
            )
            if downloaded_metadata:
                return downloaded_metadata

            deadline = time.time() + 45
            while time.time() < deadline:
                downloaded_metadata = self.wait_for_fcc_downloaded_metadata(
                    before_downloads,
                    expected_filename,
                    timeout=1,
                )
                if downloaded_metadata:
                    return downloaded_metadata
                self.wait_for_open_tab_load_state(timeout=5)
                pdf_bytes = self.get_opened_pdf_bytes_from_browser_network(target_url, timeout=1)
                if pdf_bytes:
                    metadata = parse_fcc_pdf_bytes(pdf_bytes, filename_hint=expected_filename)
                    if metadata and metadata.has_text_content:
                        self.log_fcc_metadata(metadata, "browser PDF response")
                        return metadata
                for source, text in (
                    ("Chrome accessibility tree", self.read_open_pdf_accessibility_text()),
                    ("browser PDF viewer clipboard", self.copy_open_pdf_tab_text()),
                    ("browser visible text", self.read_open_pdf_tab_text()),
                ):
                    metadata = parse_fcc_document_text(text, filename_hint=expected_filename)
                    if metadata and metadata.has_text_content:
                        self.log_fcc_metadata(metadata, source)
                        return metadata
                time.sleep(1)
            self.log_mspb_pdf_tab_diagnostics()
            return None
        except Exception as exc:
            logging.warning("Could not read FCC PDF in browser tab: %s", exc)
            return None
        finally:
            try:
                if opened_tab and opened_tab in self.driver.window_handles:
                    self.driver.close()
                if main_tab in self.driver.window_handles:
                    self.driver.switch_to.window(main_tab)
            except Exception:
                pass

    def open_ferc_link_and_extract_metadata(self, element, row):
        """Open an IRT File Name link and obtain FERC metadata from PDF or DOCX."""
        main_tab = self.driver.current_window_handle
        before_handles = set(self.driver.window_handles)
        before_downloads = self._snapshot_pdf_downloads(self.ferc_download_dir)
        opened_tab = None
        expected_filename = str(row.get("FileName", "")).strip()
        try:
            href = self._get_element_href(element)
            target_url = urljoin(self.driver.current_url, href) if href else None
            self.enable_chrome_downloads(self.ferc_download_dir)
            self.enable_browser_network_capture()
            if target_url:
                self.driver.execute_script("window.open(arguments[0], '_blank');", target_url)
            else:
                element.click()

            metadata = self._wait_for_ferc_downloaded_metadata(before_downloads, expected_filename, timeout=15)
            if metadata:
                return metadata
            try:
                WebDriverWait(self.driver, 12).until(lambda d: len(d.window_handles) > len(before_handles))
                new_handles = set(self.driver.window_handles) - before_handles
                if new_handles:
                    opened_tab = new_handles.pop()
                    self.driver.switch_to.window(opened_tab)
            except TimeoutException:
                logging.info("FERC document did not open a readable tab; continuing with download/network fallback.")

            metadata = self._wait_for_ferc_downloaded_metadata(before_downloads, expected_filename, timeout=15)
            if metadata:
                return metadata

            deadline = time.time() + 45
            while time.time() < deadline:
                metadata = self._wait_for_ferc_downloaded_metadata(before_downloads, expected_filename, timeout=1)
                if metadata:
                    return metadata
                self.wait_for_open_tab_load_state(timeout=5)
                pdf_bytes = self.get_opened_pdf_bytes_from_browser_network(target_url, timeout=1)
                if pdf_bytes:
                    metadata = parse_ferc_pdf_bytes(pdf_bytes, filename_hint=expected_filename)
                    if metadata and metadata.has_text_content:
                        self.log_ferc_metadata(metadata, "browser PDF response")
                        return metadata
                for source, text in (
                    ("Chrome accessibility tree", self.read_open_pdf_accessibility_text()),
                    ("browser PDF viewer clipboard", self.copy_open_pdf_tab_text()),
                    ("browser visible text", self.read_open_pdf_tab_text()),
                ):
                    metadata = parse_ferc_document_text(text, filename_hint=expected_filename)
                    if metadata and metadata.has_text_content:
                        self.log_ferc_metadata(metadata, source)
                        return metadata
                time.sleep(1)
            self.log_mspb_pdf_tab_diagnostics()
            return None
        except Exception as exc:
            logging.warning("Could not read FERC document in browser tab: %s", exc)
            return None
        finally:
            try:
                if opened_tab and opened_tab in self.driver.window_handles:
                    self.driver.close()
                if main_tab in self.driver.window_handles:
                    self.driver.switch_to.window(main_tab)
            except Exception:
                pass

    def open_nlrb_link_and_extract_metadata(self, element, row):
        """Open an NLRB File Name link and return parsed or review-safe metadata."""
        logging.info(
            "NLRB retrieval v2 active: authenticated browser fetch enabled; "
            "viewer-only text is rejected. source=%s",
            Path(__file__).resolve(),
        )
        main_tab = self.driver.current_window_handle
        before_handles = set(self.driver.window_handles)
        before_downloads = self._snapshot_pdf_downloads(self.nlrb_download_dir)
        opened_tab = None
        expected_filename = str(row.get("FileName", "")).strip()
        try:
            href = self._get_element_href(element)
            target_url = urljoin(self.driver.current_url, href) if href else None
            expected_filename = self.get_filename_from_document_href(href) or expected_filename
            logging.info(
                "NLRB file link resolved for LNI %s: url=%s, filename=%s",
                str(row.get("LNI", "") or "").strip(),
                "available" if target_url else "missing",
                expected_filename or "not supplied",
            )
            self.enable_chrome_downloads(self.nlrb_download_dir)
            self.enable_browser_network_capture()
            if target_url:
                self.driver.execute_script("window.open(arguments[0], '_blank');", target_url)
            else:
                element.click()

            metadata = self._wait_for_nlrb_downloaded_metadata(before_downloads, expected_filename, timeout=15)
            if metadata:
                return metadata
            try:
                WebDriverWait(self.driver, 12).until(lambda d: len(d.window_handles) > len(before_handles))
                new_handles = set(self.driver.window_handles) - before_handles
                if new_handles:
                    opened_tab = new_handles.pop()
                    self.driver.switch_to.window(opened_tab)
            except TimeoutException:
                logging.info("NLRB document did not open a readable tab; continuing with download/network fallback.")

            deadline = time.time() + 45
            while time.time() < deadline:
                metadata = self._wait_for_nlrb_downloaded_metadata(before_downloads, expected_filename, timeout=1)
                if metadata:
                    return metadata
                self.wait_for_open_tab_load_state(timeout=5)
                pdf_bytes = self.get_opened_pdf_bytes_from_browser_network(target_url, timeout=1)
                if pdf_bytes:
                    metadata = parse_nlrb_pdf_bytes(pdf_bytes, filename_hint=expected_filename)
                    self.log_nlrb_metadata(metadata, "browser PDF response")
                    return metadata

                # The IRT link uses the current authenticated browser session.
                # Fetch its response inside that same session before trusting
                # any Chrome PDF-viewer accessibility text. This avoids reading
                # toolbar labels (for example, only "Decision Date") as if
                # they were document contents.
                pdf_bytes = self.fetch_document_bytes_in_browser(target_url)
                if pdf_bytes:
                    metadata = parse_nlrb_pdf_bytes(pdf_bytes, filename_hint=expected_filename)
                    self.log_nlrb_metadata(metadata, "authenticated browser fetch")
                    return metadata
                for source, text in (
                    ("Chrome accessibility tree", self.read_open_pdf_accessibility_text()),
                    ("browser PDF viewer clipboard", self.copy_open_pdf_tab_text()),
                    ("browser visible text", self.read_open_pdf_tab_text()),
                ):
                    if self.looks_like_nlrb_text(text):
                        metadata = parse_nlrb_document_text(text, filename_hint=expected_filename)
                        self.log_nlrb_metadata(metadata, source)
                        return metadata
                time.sleep(1)
            self.log_mspb_pdf_tab_diagnostics()
            return None
        except Exception as exc:
            logging.warning("Could not read NLRB document in browser tab: %s", exc)
            return None
        finally:
            try:
                if opened_tab and opened_tab in self.driver.window_handles:
                    self.driver.close()
                if main_tab in self.driver.window_handles:
                    self.driver.switch_to.window(main_tab)
            except Exception:
                pass

    @staticmethod
    def _is_closed_irsplr_pdf_tab_error(error):
        """A vanished PDF target is not proof that its browser session died."""
        return isinstance(error, NoSuchWindowException) or any(
            marker in str(error).lower()
            for marker in ("no such window", "target window already closed", "web view not found")
        )

    def wait_for_irsplr_download_after_tab_close(self, main_tab, before_downloads, expected_filename, court_code, timeout=45):
        """Restore Inventory before waiting for a PDF-to-download handoff."""
        try:
            if main_tab not in self.driver.window_handles:
                raise RouterSessionLostError("No surviving Inventory tab remains after the IRSPLR PDF tab closed.")
            self.driver.switch_to.window(main_tab)
            # Check the surviving target, not the already-closed PDF target.
            _ = self.driver.current_url
        except RouterSessionLostError:
            raise
        except Exception as exc:
            raise RouterSessionLostError("Could not restore the Inventory tab after the IRSPLR PDF tab closed.") from exc
        if getattr(self, "_irsplr_browser_first", False) and not getattr(self, "_irsplr_viewer_passed", False):
            raise IRSPLRDocumentReviewRequired(
                "BROWSER CHECK UNCONFIRMED - PDF tab closed before Chrome loaded its pages; corruption is not verified"
            )
        logging.info(
            "IRSPLR PDF tab closed during download handoff; Inventory is still available. Waiting up to %s seconds for %s.",
            timeout, expected_filename or "the source PDF",
        )
        return self.wait_for_irsplr_downloaded_metadata(
            before_downloads, expected_filename, court_code, timeout=timeout,
        )

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
            self._irsplr_inventory_tab = main_tab
            self._irsplr_viewer_passed = False
            if getattr(self, "_irsplr_browser_first", False):
                self.set_irsplr_browser_downloads(allowed=False)
            else:
                self.enable_chrome_downloads(self.irsplr_download_dir)
            if href:
                target_url = urljoin(self.driver.current_url, href)
                self.enable_browser_network_capture()
                self.driver.execute_script("window.open(arguments[0], '_blank');", target_url)
            else:
                target_url = None
                self.enable_browser_network_capture()
                element.click()

            try:
                # Watch both outcomes: Chrome may keep a viewer tab or close
                # it immediately after starting a download. Compare viewer
                # errors with available bytes before classifying the failure.
                WebDriverWait(self.driver, 10).until(
                    lambda d: bool(set(d.window_handles) - before_handles)
                    or self.find_completed_irsplr_download(before_downloads, expected_filename)
                )
                new_handles = set(self.driver.window_handles) - before_handles
                if new_handles:
                    opened_tab = new_handles.pop()
                    self.driver.switch_to.window(opened_tab)
            except TimeoutException:
                logging.info("IRSPLR link has not exposed a viewer or completed download yet.")

            if opened_tab:
                logging.info("Opened IRSPLR PDF link in a browser tab.")
                metadata = self.wait_for_irsplr_metadata_from_open_tab(
                    target_url, before_downloads=before_downloads,
                    expected_filename=expected_filename, court_code=court_code, timeout=45,
                )
            else:
                if getattr(self, "_irsplr_browser_first", False):
                    raise IRSPLRDocumentReviewRequired(
                        "BROWSER CHECK UNCONFIRMED - no PDF viewer tab opened; retry or supply a working PDF; corruption is not verified"
                    )
                # Do not scrape the Search Inventory page or clipboard as if
                # they were the document when Chrome only made a download.
                metadata = self.wait_for_irsplr_downloaded_metadata(
                    before_downloads, expected_filename, court_code, timeout=45,
                )
            if metadata:
                return metadata
            raise IRSPLRDocumentReviewRequired(
                "UNAVAILABLE OR UNREADABLE - no usable source PDF and complete metadata could be confirmed; supply a working PDF"
            )
        except (IRSPLRDocumentReviewRequired, RouterSessionLostError):
            raise
        except Exception as e:
            if opened_tab and self._is_closed_irsplr_pdf_tab_error(e):
                metadata = self.wait_for_irsplr_download_after_tab_close(
                    main_tab, before_downloads, expected_filename, court_code,
                )
                if metadata:
                    return metadata
                raise IRSPLRDocumentReviewRequired(
                    "UNAVAILABLE - the PDF tab closed and no usable completed download was confirmed; corruption is not verified"
                ) from e
            self._raise_if_invalid_session_error(e, "reading IRSPLR source PDF")
            raise IRSPLRDocumentReviewRequired(
                "UNAVAILABLE - the source PDF could not be opened or downloaded; supply a working PDF"
            ) from e
        finally:
            try:
                if opened_tab and opened_tab != main_tab and opened_tab in self.driver.window_handles:
                    # Recovery may have focused Inventory. Never close the
                    # current window without explicitly selecting the PDF.
                    self.driver.switch_to.window(opened_tab)
                    self.driver.close()
            except Exception:
                pass
            try:
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

    def open_mework_link_and_extract_metadata(self, element, row):
        """Open the linked PDF in a browser tab and parse MEWORK metadata."""
        main_tab = self.driver.current_window_handle
        before_handles = set(self.driver.window_handles)
        before_downloads = self.snapshot_mework_downloads()
        opened_tab = None
        file_name = str(row.get("FileName", "")).strip()

        try:
            href = self._get_element_href(element)
            expected_filename = self.get_filename_from_document_href(href) or file_name
            self.enable_chrome_downloads(self.mework_download_dir)
            self.enable_browser_network_capture()
            if href:
                target_url = urljoin(self.driver.current_url, href)
                self.driver.execute_script("window.open(arguments[0], '_blank');", target_url)
            else:
                target_url = None
                element.click()

            downloaded_metadata = self.wait_for_mework_downloaded_metadata(
                before_downloads, expected_filename, timeout=20
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
                logging.info("MEWORK link did not open a readable tab yet; continuing to watch for download.")

            downloaded_metadata = self.wait_for_mework_downloaded_metadata(
                before_downloads, expected_filename, timeout=25
            )
            if downloaded_metadata:
                return downloaded_metadata

            logging.info("Opened MEWORK PDF link in a browser tab.")
            metadata = self.wait_for_mework_metadata_from_open_tab(
                target_url,
                before_downloads=before_downloads,
                expected_filename=expected_filename,
                timeout=45,
            )
            if metadata:
                return metadata

            logging.warning("MEWORK PDF tab opened, but metadata could not be extracted.")
            return None
        except Exception as e:
            logging.warning(f"Could not read MEWORK document in browser tab: {e}")
            return None
        finally:
            try:
                if opened_tab and opened_tab in self.driver.window_handles:
                    self.driver.close()
                if main_tab in self.driver.window_handles:
                    self.driver.switch_to.window(main_tab)
            except Exception:
                pass

    def open_mosu00_link_and_extract_metadata(self, element, row):
        """Open the linked MOSU00 HTML document in a browser tab and parse table metadata."""
        main_tab = self.driver.current_window_handle
        main_url = ""
        try:
            main_url = self.driver.current_url
        except Exception:
            pass
        before_handles = set(self.driver.window_handles)
        before_downloads = self.snapshot_mosu00_downloads()
        opened_tab = None
        file_name = str(row.get("FileName", "")).strip()

        try:
            href = self._get_element_href(element)
            expected_filename = self.get_filename_from_document_href(href) or file_name
            self.enable_chrome_downloads(self.mosu00_download_dir)
            if href:
                target_url = urljoin(self.driver.current_url, href)
                self.driver.execute_script("window.open(arguments[0], '_blank');", target_url)
            else:
                target_url = None
                element.click()

            downloaded_metadata = self.wait_for_mosu00_downloaded_metadata(
                before_downloads,
                expected_filename,
                timeout=8,
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
                logging.info("MOSU00 table link did not open a new tab; trying to read the current browser context.")

            downloaded_metadata = self.wait_for_mosu00_downloaded_metadata(
                before_downloads,
                expected_filename,
                timeout=12,
            )
            if downloaded_metadata:
                return downloaded_metadata

            metadata = self.wait_for_mosu00_metadata_from_open_tab(
                target_url,
                expected_filename=expected_filename,
                timeout=30,
            )
            if metadata:
                return metadata

            logging.warning("MOSU00 HTML tab opened, but metadata could not be extracted from the browser-rendered document.")
            return None
        except Exception as e:
            logging.warning(f"Could not read MOSU00 table document in browser tab: {e}")
            return None
        finally:
            try:
                if opened_tab and opened_tab in self.driver.window_handles:
                    self.driver.close()
                if main_tab in self.driver.window_handles:
                    self.driver.switch_to.window(main_tab)
                    if not opened_tab and main_url:
                        try:
                            current_url = self.driver.current_url
                            if current_url != main_url:
                                self.driver.back()
                                self.wait_for_open_tab_load_state(timeout=10)
                                logging.info("Returned to Search Inventory after reading MOSU00 HTML in the same tab.")
                        except Exception as exc:
                            logging.warning("Could not return to Search Inventory after MOSU00 HTML read: %s", exc)
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

    def read_irsplr_pdf_viewer_error(self):
        """Read visible Chrome PDF errors, including errors inside shadow DOM.

        Do not search hidden textContent: Chrome keeps its error dialog in
        the DOM even when a healthy PDF is displayed.
        """
        try:
            message = self.driver.execute_script(r"""
                const failure = /failed\s+to\s+load\s+pdf(?:\s+document)?/i;
                function visible(element) {
                    if (!element.getClientRects().length) return false;
                    for (let node = element; node; node = node.parentElement || node.getRootNode().host) {
                        const style = getComputedStyle(node);
                        if (node.hidden || node.getAttribute('aria-hidden') === 'true' ||
                            style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
                    }
                    return true;
                }
                function scan(root, inErrorDialog = false) {
                    for (const element of root.querySelectorAll('*')) {
                        const errorDialog = inErrorDialog || element.tagName === 'VIEWER-ERROR-DIALOG' ||
                            element.tagName === 'DIALOG' || ['dialog', 'alertdialog', 'alert'].includes(element.getAttribute('role'));
                        if (errorDialog && visible(element)) {
                            const text = (element.innerText || '').trim();
                            if (text.length < 600 && failure.test(text)) return 'Failed to load PDF document.';
                        }
                        if (element.shadowRoot) {
                            const error = scan(element.shadowRoot, errorDialog);
                            if (error) return error;
                        }
                    }
                    return '';
                }
                return scan(document);
            """)
            if isinstance(message, str) and message:
                return message
            # A cross-origin PDF viewer may expose its modal through Chrome's
            # accessibility tree rather than the outer page's DOM.
            def error_in_tree(tree):
                nodes = tree.get("nodes", [])
                by_id = {node["nodeId"]: node for node in nodes if "nodeId" in node}

                def dialog_text(node, seen):
                    node_id = node.get("nodeId")
                    if node.get("ignored") or node_id in seen:
                        return ""
                    seen.add(node_id)
                    text = " ".join(str(node.get(key, {}).get("value", "")) for key in ("name", "description", "value"))
                    return text + " " + " ".join(
                        dialog_text(by_id[child], seen) for child in node.get("childIds", []) if child in by_id
                    )

                for node in nodes:
                    if node.get("role", {}).get("value") in {"dialog", "alertdialog", "alert"} and re.search(
                        r"failed\s+to\s+load\s+pdf(?:\s+document)?", dialog_text(node, set()), re.I,
                    ):
                        return "Failed to load PDF document."
                return ""

            error = error_in_tree(self.driver.execute_cdp_cmd("Accessibility.getFullAXTree", {}))
            if error:
                return error
            # Built-in PDF viewers can live in a cross-origin child frame.
            # Read its accessibility tree rather than bypassing DOM security.
            def child_frames(frame_tree):
                for child in frame_tree.get("childFrames", []):
                    yield child["frame"]["id"]
                    yield from child_frames(child)

            frame_tree = self.driver.execute_cdp_cmd("Page.getFrameTree", {}).get("frameTree", {})
            for frame_id in child_frames(frame_tree):
                error = error_in_tree(self.driver.execute_cdp_cmd("Accessibility.getFullAXTree", {"frameId": frame_id}))
                if error:
                    return error
        except Exception as exc:
            if self._is_closed_irsplr_pdf_tab_error(exc):
                # Let the opener restore Inventory and await the download;
                # do not promote this target-only error to session loss.
                raise
            self._raise_if_invalid_session_error(exc, "checking IRSPLR PDF viewer")
            logging.debug("IRSPLR PDF viewer error check was unavailable: %s", exc)
        return ""

    def set_irsplr_browser_downloads(self, *, allowed):
        """Keep source bytes out of local downloads until Chrome passes the check."""
        parameters = {"behavior": "allow" if allowed else "deny"}
        if allowed:
            parameters["downloadPath"] = str(self.irsplr_download_dir)
        try:
            self.driver.execute_cdp_cmd("Browser.setDownloadBehavior", parameters)
        except Exception:
            try:
                self.driver.execute_cdp_cmd("Page.setDownloadBehavior", parameters)
            except Exception as exc:
                self._raise_if_invalid_session_error(exc, "configuring IRSPLR browser-first PDF check")
                raise IRSPLRDocumentReviewRequired(
                    "BROWSER CHECK UNAVAILABLE - download behavior could not be configured; retry this document"
                ) from exc

    def irsplr_source_headers(self, target_url):
        """Check only response headers, from authenticated Inventory, without a download."""
        viewer_tab = self.driver.current_window_handle
        inventory_tab = getattr(self, "_irsplr_inventory_tab", None) or getattr(self, "_main_tab", None)
        try:
            if inventory_tab and inventory_tab in self.driver.window_handles:
                self.driver.switch_to.window(inventory_tab)
            if not target_url:
                return {}
            return self.driver.execute_async_script("""
                const done = arguments[arguments.length - 1];
                const controller = new AbortController();
                const timer = setTimeout(() => controller.abort(), 10000);
                fetch(arguments[0], {method: 'HEAD', credentials: 'same-origin', signal: controller.signal})
                  .then(response => done({ok: response.ok, status: response.status,
                    content_type: response.headers.get('content-type') || '',
                    content_length: response.headers.get('content-length') || ''}))
                  .catch(() => done({ok: false}))
                  .finally(() => clearTimeout(timer));
            """, target_url) or {}
        except Exception as exc:
            self._raise_if_invalid_session_error(exc, "checking IRSPLR source access")
            logging.warning("IRSPLR source headers could not be confirmed: %s", exc)
            return {}
        finally:
            if viewer_tab in self.driver.window_handles:
                self.driver.switch_to.window(viewer_tab)

    def validate_irsplr_browser_pdf(self, target_url, *, timeout=45):
        confirm_browser_pdf(
            self.driver, self.read_irsplr_pdf_viewer_error,
            lambda: self.irsplr_source_headers(target_url), timeout=timeout,
        )

    def _store_browser_verified_irsplr_pdf(self, pdf_bytes, expected_filename):
        """Preserve the original bytes only after the browser check has passed."""
        if not getattr(self, "_irsplr_viewer_passed", False):
            raise IRSPLRDocumentReviewRequired("BROWSER CHECK UNCONFIRMED - local PDF download blocked")
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(expected_filename or "IRSPLR.pdf"))
        name = name.rstrip(" .") or "IRSPLR.pdf"
        if not name.lower().endswith(".pdf"):
            name += ".pdf"
        directory = Path(self.irsplr_download_dir)
        directory.mkdir(parents=True, exist_ok=True)
        base = Path(name)
        for suffix in range(10000):
            path = directory / (name if suffix == 0 else f"{base.stem} ({suffix}){base.suffix}")
            try:
                with path.open("xb") as output:
                    output.write(pdf_bytes)
                logging.info("IRSPLR browser-verified PDF saved: %s", path)
                return path
            except FileExistsError:
                if path.read_bytes() == pdf_bytes:
                    return path
        raise OSError("No available IRSPLR PDF download filename")

    def read_browser_verified_irsplr_metadata(self, target_url, expected_filename, court_code, *, timeout=45):
        # Validation always precedes network-response extraction, local files,
        # metadata parsing and OCR. The viewer itself necessarily fetches the PDF.
        self._irsplr_viewer_passed = False
        self._mspb_pdf_request_ids = set()
        self._mspb_pdf_checked_request_ids = set()
        self.validate_irsplr_browser_pdf(target_url, timeout=timeout)
        self._irsplr_viewer_passed = True
        self.set_irsplr_browser_downloads(allowed=True)
        pdf_bytes = self.get_opened_pdf_bytes_from_browser_network(target_url, timeout=5)
        if not pdf_bytes:
            viewer_tab = self.driver.current_window_handle
            inventory_tab = getattr(self, "_irsplr_inventory_tab", None) or getattr(self, "_main_tab", None)
            try:
                if inventory_tab and inventory_tab in self.driver.window_handles:
                    self.driver.switch_to.window(inventory_tab)
                if target_url:
                    pdf_bytes = self._fetch_irt_pdf_in_current_browser(target_url, allow_non_pdf=True)
            finally:
                if viewer_tab in self.driver.window_handles:
                    self.driver.switch_to.window(viewer_tab)
        if not pdf_bytes:
            raise IRSPLRDocumentReviewRequired(
                "UNAVAILABLE - browser opened the PDF but its source bytes could not be retrieved; corruption is not verified"
            )
        metadata = parse_irsplr_pdf_bytes(pdf_bytes, filename_hint=expected_filename, court_code_hint=court_code)
        self._store_browser_verified_irsplr_pdf(pdf_bytes, expected_filename)
        if not metadata or not metadata.has_text_content:
            raise IRSPLRDocumentReviewRequired(
                "UNREADABLE - browser opened the PDF but native text/OCR did not supply complete metadata; supply the missing ruling number or decision date"
            )
        self.log_irsplr_metadata(metadata, "browser-verified source PDF")
        return metadata

    def inspect_irsplr_duplicate_in_browser(self, href):
        """Inspect an existing LNI without editing it or downloading its PDF."""
        inventory_tab = self.driver.current_window_handle
        before_handles = set(self.driver.window_handles)
        owned_tab = None
        target_url = urljoin(self.driver.current_url, href)
        try:
            self.set_irsplr_browser_downloads(allowed=False)
            self.driver.execute_script("window.open(arguments[0], '_blank');", target_url)
            handles = WebDriverWait(self.driver, 15).until(lambda d: set(d.window_handles) - before_handles)
            owned_tab = next(iter(handles))
            self.driver.switch_to.window(owned_tab)
            self._irsplr_inventory_tab = inventory_tab
            self.validate_irsplr_browser_pdf(target_url)
        except Exception as exc:
            if self._is_closed_irsplr_pdf_tab_error(exc):
                raise IRSPLRDocumentReviewRequired(
                    "BROWSER CHECK UNCONFIRMED - candidate PDF viewer closed before its pages could be checked; corruption is not verified"
                ) from exc
            self._raise_if_invalid_session_error(exc, "checking IRSPLR duplicate PDF viewer")
            raise
        finally:
            try:
                if owned_tab and owned_tab in self.driver.window_handles:
                    self.driver.switch_to.window(owned_tab)
                    self.driver.close()
            except Exception:
                logging.debug("IRSPLR candidate viewer cleanup unavailable.", exc_info=True)
            finally:
                if inventory_tab in self.driver.window_handles:
                    self.driver.switch_to.window(inventory_tab)

    def wait_for_irsplr_metadata_from_open_tab(self, target_url=None, before_downloads=None, expected_filename=None, court_code=None, timeout=45):
        if getattr(self, "_irsplr_browser_first", False):
            return self.read_browser_verified_irsplr_metadata(
                target_url, expected_filename, court_code, timeout=timeout,
            )
        deadline = time.time() + timeout
        self._mspb_pdf_request_ids = set()
        self._mspb_pdf_checked_request_ids = set()
        last_status_log = 0
        validated_pdf = False
        consecutive_viewer_errors = 0
        last_viewer_error = ""

        while time.time() < deadline:
            self.wait_for_open_tab_load_state(timeout=5)

            viewer_error = self.read_irsplr_pdf_viewer_error()
            consecutive_viewer_errors = consecutive_viewer_errors + 1 if viewer_error else 0
            last_viewer_error = viewer_error

            downloaded_metadata = self.wait_for_irsplr_downloaded_metadata(
                before_downloads or {},
                expected_filename,
                court_code,
                timeout=1,
            )
            validated_pdf = validated_pdf or getattr(self, "_irsplr_last_download_validated", False)
            if downloaded_metadata:
                if viewer_error:
                    raise IRSPLRDocumentReviewRequired(
                        "VIEWER LOAD FAILED BUT PDF VALIDATED - downloaded PDF metadata is readable; verify the viewer/source manually; corruption is not verified"
                    )
                return downloaded_metadata

            pdf_bytes = self.get_opened_pdf_bytes_from_browser_network(target_url, timeout=1)
            if pdf_bytes:
                pdf_signature = ("network", hashlib.sha1(pdf_bytes).hexdigest())
                if pdf_signature in self._irsplr_unreadable_pdf_signatures:
                    validated_pdf = True
                else:
                    metadata = parse_irsplr_pdf_bytes(pdf_bytes, filename_hint=expected_filename, court_code_hint=court_code)
                    validated_pdf = True
                    if metadata and metadata.has_text_content:
                        if viewer_error:
                            raise IRSPLRDocumentReviewRequired(
                                "VIEWER LOAD FAILED BUT PDF VALIDATED - PDF bytes have readable metadata; verify the viewer/source manually; corruption is not verified"
                            )
                        self.log_irsplr_metadata(metadata, "browser PDF tab")
                        return metadata
                    self._irsplr_unreadable_pdf_signatures.add(pdf_signature)
                    logging.warning(
                        "IRSPLR browser PDF passed validation but native text/OCR did not provide complete metadata; this does not prove corruption."
                    )

            if viewer_error:
                if validated_pdf:
                    raise IRSPLRDocumentReviewRequired(
                        "VIEWER LOAD FAILED BUT PDF VALIDATED - PDF structure is readable but metadata/OCR needs review; corruption is not verified"
                    )
                # A temporary viewer error can disappear or be followed by a
                # valid download. Allow the full retrieval window first.
                time.sleep(0.5)
                continue

            if not validated_pdf:
                # Viewer/clipboard text alone is not proof of a usable source
                # file. A failed download must not become a normal routing.
                time.sleep(0.5)
                continue

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

        if consecutive_viewer_errors >= 2 and not validated_pdf:
            raise IRSPLRCorruptDocument(
                f"LOAD FAILED - {last_viewer_error}; the viewer repeatedly failed and no usable PDF could be opened or downloaded during the retrieval window"
            )
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

    def wait_for_mework_metadata_from_open_tab(self, target_url=None, before_downloads=None, expected_filename=None, timeout=45):
        deadline = time.time() + timeout
        self._mspb_pdf_request_ids = set()
        self._mspb_pdf_checked_request_ids = set()
        last_status_log = 0

        while time.time() < deadline:
            self.wait_for_open_tab_load_state(timeout=5)

            downloaded_metadata = self.wait_for_mework_downloaded_metadata(
                before_downloads or {}, expected_filename, timeout=1
            )
            if downloaded_metadata:
                return downloaded_metadata

            pdf_bytes = self.get_opened_pdf_bytes_from_browser_network(target_url, timeout=1)
            if pdf_bytes:
                metadata = parse_mework_pdf_bytes(pdf_bytes, filename_hint=expected_filename)
                if metadata and metadata.has_text_content:
                    self.log_mework_metadata(metadata, "browser PDF tab")
                    return metadata

            for source, browser_text in (
                ("Chrome accessibility tree", self.read_open_pdf_accessibility_text()),
                ("browser PDF viewer clipboard", self.copy_open_pdf_tab_text()),
                ("browser visible text", self.read_open_pdf_tab_text()),
            ):
                if self.looks_like_mework_text(browser_text):
                    metadata = parse_mework_document_text(browser_text, filename_hint=expected_filename)
                    if metadata and metadata.has_text_content:
                        self.log_mework_metadata(metadata, source)
                        return metadata

            if time.time() - last_status_log >= 10:
                logging.info("Waiting for MEWORK PDF tab to finish loading/expose text...")
                last_status_log = time.time()
            time.sleep(2)

        self.log_mspb_pdf_tab_diagnostics("MEWORK")
        return None

    def wait_for_mosu00_metadata_from_open_tab(self, target_url=None, expected_filename=None, timeout=30):
        deadline = time.time() + timeout
        last_status_log = 0

        while time.time() < deadline:
            self.wait_for_open_tab_load_state(timeout=5)

            visible_text = self.read_open_pdf_tab_text()
            metadata = parse_mosu00_html_text(visible_text, filename_hint=expected_filename)
            if metadata:
                self.log_mosu00_metadata(metadata, "browser visible HTML")
                return metadata

            page_source = ""
            try:
                page_source = self.driver.page_source or ""
            except Exception:
                page_source = ""
            metadata = parse_mosu00_html_text(page_source, filename_hint=expected_filename)
            if metadata:
                self.log_mosu00_metadata(metadata, "browser page source")
                return metadata

            if time.time() - last_status_log >= 10:
                logging.info("Waiting for MOSU00 HTML document to finish loading/expose table text...")
                last_status_log = time.time()

            time.sleep(1.5)

        self.log_mspb_pdf_tab_diagnostics("MOSU00")
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

    def snapshot_fcc_downloads(self):
        """Capture the FCC download directory before opening one IRT file."""
        self.fcc_download_dir.mkdir(parents=True, exist_ok=True)
        snapshot = {}
        for path in self.fcc_download_dir.glob("*"):
            if path.is_file():
                try:
                    stat = path.stat()
                    snapshot[path.name.lower()] = (stat.st_mtime, stat.st_size)
                except Exception:
                    continue
        return snapshot

    @staticmethod
    def _snapshot_pdf_downloads(download_dir):
        download_dir.mkdir(parents=True, exist_ok=True)
        snapshot = {}
        for path in download_dir.glob("*"):
            if path.is_file():
                try:
                    stat = path.stat()
                    snapshot[path.name.lower()] = (stat.st_mtime, stat.st_size)
                except Exception:
                    continue
        return snapshot

    def _wait_for_ferc_downloaded_metadata(self, before_downloads, expected_filename=None, timeout=30):
        deadline = time.time() + timeout
        while time.time() < deadline:
            document_path = self._find_completed_pdf_download(
                self.ferc_download_dir,
                before_downloads,
                expected_filename,
                allowed_suffixes=(".pdf", ".docx"),
            )
            if document_path:
                try:
                    parser = parse_ferc_docx_bytes if document_path.suffix.lower() == ".docx" else parse_ferc_pdf_bytes
                    metadata = parser(document_path.read_bytes(), filename_hint=document_path.name)
                    if metadata and metadata.has_text_content:
                        self.log_ferc_metadata(metadata, f"downloaded {document_path.suffix.upper().lstrip('.')} {document_path.name}")
                        return metadata
                    logging.warning("Downloaded FERC document %s did not expose readable text.", document_path.name)
                    return None
                except Exception as exc:
                    logging.warning("Downloaded FERC document could not be parsed: %s (%s)", document_path, exc)
                    return None
            time.sleep(0.5)
        return None

    def _wait_for_nlrb_downloaded_metadata(self, before_downloads, expected_filename=None, timeout=30):
        deadline = time.time() + timeout
        while time.time() < deadline:
            document_path = self._find_completed_pdf_download(
                self.nlrb_download_dir,
                before_downloads,
                expected_filename,
                allowed_suffixes=(".pdf",),
            )
            if document_path:
                try:
                    metadata = parse_nlrb_pdf_bytes(document_path.read_bytes(), filename_hint=document_path.name)
                    self.log_nlrb_metadata(metadata, f"downloaded PDF {document_path.name}")
                    return metadata
                except Exception as exc:
                    logging.warning("Downloaded NLRB document could not be parsed: %s (%s)", document_path, exc)
                    return None
            time.sleep(0.5)
        return None

    def wait_for_fcc_downloaded_metadata(self, before_downloads, expected_filename=None, timeout=30):
        """Return parsed FCC metadata for the newly completed expected PDF."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            pdf_path = self.find_completed_fcc_download(before_downloads, expected_filename)
            if pdf_path:
                try:
                    metadata = parse_fcc_pdf_bytes(pdf_path.read_bytes(), filename_hint=pdf_path.name)
                    if metadata and metadata.has_text_content:
                        self.log_fcc_metadata(metadata, f"downloaded PDF {pdf_path.name}")
                        return metadata
                    logging.warning("Downloaded FCC PDF %s did not expose readable text.", pdf_path.name)
                    return None
                except Exception as exc:
                    logging.warning("Downloaded FCC PDF could not be parsed: %s (%s)", pdf_path, exc)
                    return None
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

    def snapshot_mework_downloads(self):
        self.mework_download_dir.mkdir(parents=True, exist_ok=True)
        snapshot = {}
        for path in self.mework_download_dir.glob("*"):
            if path.is_file():
                try:
                    stat = path.stat()
                    snapshot[path.name.lower()] = (stat.st_mtime, stat.st_size)
                except Exception:
                    continue
        return snapshot

    def snapshot_mosu00_downloads(self):
        self.mosu00_download_dir.mkdir(parents=True, exist_ok=True)
        snapshot = {}
        for path in self.mosu00_download_dir.glob("*"):
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
        self._irsplr_last_download_validated = False
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
                    self._irsplr_last_download_validated = True
                    return None
                try:
                    metadata = parse_irsplr_pdf_bytes(
                        pdf_path.read_bytes(),
                        filename_hint=pdf_path.name,
                        court_code_hint=court_code,
                    )
                    self._irsplr_last_download_validated = True
                    if metadata and metadata.has_text_content:
                        self.log_irsplr_metadata(metadata, f"downloaded PDF {pdf_path.name}")
                        return metadata
                    self._irsplr_unreadable_pdf_signatures.add(file_signature)
                    logging.warning(
                        "Downloaded IRSPLR PDF %s passed validation but native text/OCR did not provide complete metadata; this does not prove corruption.",
                        pdf_path.name,
                    )
                    return None
                except IRSPLRDocumentReviewRequired:
                    raise
                except Exception as e:
                    raise IRSPLRDocumentReviewRequired(
                        "EXTRACTION UNAVAILABLE - the downloaded PDF could not be read; verify the file/OCR setup manually; corruption is not verified"
                    ) from e
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

    def wait_for_mework_downloaded_metadata(self, before_downloads, expected_filename=None, timeout=30):
        deadline = time.time() + timeout
        while time.time() < deadline:
            pdf_path = self.find_completed_mework_download(before_downloads, expected_filename)
            if pdf_path:
                try:
                    metadata = parse_mework_pdf_bytes(pdf_path.read_bytes(), filename_hint=pdf_path.name)
                    if metadata and metadata.has_text_content:
                        self.log_mework_metadata(metadata, f"downloaded PDF {pdf_path.name}")
                        return metadata
                    logging.warning("Downloaded MEWORK PDF %s did not expose readable text.", pdf_path.name)
                    return None
                except Exception as e:
                    logging.warning(f"Downloaded MEWORK PDF could not be parsed: {pdf_path} ({e})")
            time.sleep(0.5)
        return None

    def wait_for_mosu00_downloaded_metadata(self, before_downloads, expected_filename=None, timeout=20):
        deadline = time.time() + timeout
        while time.time() < deadline:
            html_path = self.find_completed_mosu00_download(before_downloads, expected_filename)
            if html_path:
                try:
                    metadata = parse_mosu00_html_file(html_path)
                    if metadata:
                        self.log_mosu00_metadata(metadata, f"downloaded HTML {html_path.name}")
                        return metadata
                    logging.warning("Downloaded MOSU00 HTML %s did not contain required table metadata.", html_path.name)
                    return None
                except Exception as e:
                    logging.warning(f"Downloaded MOSU00 HTML could not be parsed: {html_path} ({e})")
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
        active_downloads = set()
        for partial in self.irsplr_download_dir.glob("*.crdownload"):
            try:
                stat = partial.stat()
            except OSError:
                continue
            # An unchanged partial from a failed earlier run must not block
            # a new completed PDF with the same expected filename.
            if before_downloads.get(partial.name.lower()) != (stat.st_mtime, stat.st_size):
                active_downloads.add(partial.name.lower())
        candidates = []

        for path in self.irsplr_download_dir.glob("*"):
            if not path.is_file() or not (
                path.suffix.lower() == ".pdf" or re.fullmatch(r".+\.pdf\s*\(\d+\)", path.name, re.I)
            ):
                continue
            try:
                stat = path.stat()
            except Exception:
                continue

            prior = before_downloads.get(path.name.lower())
            changed = prior is None or prior != (stat.st_mtime, stat.st_size)
            expected_match = self.path_matches_expected_download(path, expected_lower) or bool(
                expected_lower and re.fullmatch(rf"{re.escape(expected_lower)}\s*\(\d+\)", path.name.lower())
            )
            if expected_lower and not expected_match:
                continue

            if (expected_match and changed) or (not expected_lower and changed):
                if path.name.lower() + ".crdownload" not in active_downloads:
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

    def find_completed_mework_download(self, before_downloads, expected_filename=None):
        expected_lower = expected_filename.lower() if expected_filename else None
        active_downloads = list(self.mework_download_dir.glob("*.crdownload"))
        candidates = []
        for path in self.mework_download_dir.glob("*.pdf"):
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

    def find_completed_mosu00_download(self, before_downloads, expected_filename=None):
        expected_lower = expected_filename.lower() if expected_filename else None
        active_downloads = list(self.mosu00_download_dir.glob("*.crdownload"))
        candidates = []

        for path in list(self.mosu00_download_dir.glob("*.htm")) + list(self.mosu00_download_dir.glob("*.html")):
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

    def find_completed_fcc_download(self, before_downloads, expected_filename=None):
        """Find only the new completed download belonging to the FCC row."""
        expected_lower = expected_filename.lower() if expected_filename else None
        active_downloads = list(self.fcc_download_dir.glob("*.crdownload"))
        candidates = []

        for path in self.fcc_download_dir.glob("*.pdf"):
            try:
                stat = path.stat()
            except Exception:
                continue

            prior = before_downloads.get(path.name.lower())
            changed = prior is None or prior != (stat.st_mtime, stat.st_size)
            expected_match = self.path_matches_expected_download(path, expected_lower)
            if expected_lower and not expected_match:
                continue
            if not changed:
                continue
            if any(str(download).lower().startswith(str(path).lower()) for download in active_downloads):
                continue
            candidates.append(path)

        if not candidates:
            return None
        candidates.sort(key=lambda candidate: candidate.stat().st_mtime, reverse=True)
        return candidates[0]

    def _find_completed_pdf_download(self, download_dir, before_downloads, expected_filename=None, allowed_suffixes=(".pdf",)):
        expected_lower = expected_filename.lower() if expected_filename else None
        active_downloads = list(download_dir.glob("*.crdownload"))
        candidates = []
        allowed_suffixes = tuple(suffix.lower() for suffix in allowed_suffixes)
        for path in download_dir.glob("*"):
            if not path.is_file() or path.suffix.lower() not in allowed_suffixes:
                continue
            try:
                stat = path.stat()
            except Exception:
                continue
            if expected_lower and not self.path_matches_expected_download(path, expected_lower):
                continue
            prior = before_downloads.get(path.name.lower())
            if prior == (stat.st_mtime, stat.st_size):
                continue
            if any(str(download).lower().startswith(str(path).lower()) for download in active_downloads):
                continue
            candidates.append(path)
        if not candidates:
            return None
        return max(candidates, key=lambda candidate: candidate.stat().st_mtime)

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
            return name if name.lower().endswith((".pdf", ".htm", ".html")) else None
        except Exception:
            return None

    @staticmethod
    def normalized_file_name(value):
        """Return a usable workbook filename, never pandas' ``nan`` placeholder."""
        file_name = str(value or "").strip()
        return "" if file_name.lower() in {"nan", "none", "nat"} else file_name

    def capture_file_name_from_link(self, row, element):
        """Store the actual IRT document filename on the mapping row when available."""
        href = self._get_element_href(element)
        candidates = []
        try:
            candidates.append(element.get_attribute("textContent") or "")
        except Exception:
            pass
        try:
            candidates.append(element.text or "")
        except Exception:
            pass
        candidates.append(self.get_filename_from_document_href(href) or "")

        for candidate in candidates:
            file_name = self.normalized_file_name(candidate)
            # IRT File Name links display the full document filename. Require
            # an expected document extension so labels such as "View" or an
            # LNI link can never overwrite the mapping-sheet File Name field.
            if file_name.lower().endswith((".pdf", ".docx", ".htm", ".html")):
                previous = self.normalized_file_name(row.get("FileName", ""))
                row["FileName"] = file_name
                if file_name != previous:
                    logging.info("Captured IRT File Name for LNI %s: %s", row.get("LNI", ""), file_name)
                return file_name
        return self.normalized_file_name(row.get("FileName", ""))

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

    def fetch_document_bytes_in_browser(self, target_url, timeout=15):
        """Return a PDF fetched with the authenticated browser session.

        IRT serves some file links as downloads instead of opening a PDF tab.
        An in-page fetch keeps the session cookies and produces raw PDF bytes
        without relying on the PDF viewer or its accessibility tree.
        """
        if not target_url or str(target_url).lower().startswith("javascript:"):
            return None
        try:
            self.driver.set_script_timeout(timeout)
            result = self.driver.execute_async_script(
                """
                const url = arguments[0];
                const done = arguments[arguments.length - 1];
                fetch(url, { credentials: 'include', redirect: 'follow' })
                    .then(async response => {
                        const bytes = new Uint8Array(await response.arrayBuffer());
                        if (!response.ok || bytes.length > 15 * 1024 * 1024) {
                            done({ ok: false, status: response.status, size: bytes.length });
                            return;
                        }
                        let binary = '';
                        const chunkSize = 0x8000;
                        for (let start = 0; start < bytes.length; start += chunkSize) {
                            binary += String.fromCharCode(...bytes.subarray(start, start + chunkSize));
                        }
                        done({ ok: true, status: response.status, body: btoa(binary) });
                    })
                    .catch(error => done({ ok: false, error: String(error) }));
                """,
                target_url,
            )
            if result and result.get("ok"):
                payload = base64.b64decode(result.get("body", ""))
                if self.is_pdf_bytes(payload):
                    return payload
                logging.info("NLRB authenticated fetch returned a non-PDF response; continuing with other retrieval paths.")
            elif result:
                logging.info(
                    "NLRB authenticated PDF fetch was unavailable (status=%s, size=%s).",
                    result.get("status", "n/a"),
                    result.get("size", "n/a"),
                )
        except Exception as exc:
            logging.info("NLRB authenticated PDF fetch could not be used: %s", exc)
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

    @staticmethod
    def looks_like_nlrb_text(text):
        """Reject Chrome PDF-viewer labels while allowing genuine NLRB text."""
        value = str(text or "")
        upper = value.upper()
        has_docket = bool(re.search(r"\b\d{1,2}\s*[-–]\s*[A-Z]{1,3}\s*[-–]\s*\d{3,6}\b", upper))
        has_heading = bool(re.search(r"(?m)^\s*(?:ORDER|DECISION|SUPPLEMENTAL DECISION)\b", value, re.I))
        return (
            len(value.strip()) >= 200
            and "NATIONAL LABOR RELATIONS BOARD" in upper
            and has_docket
            and has_heading
        )

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

    @staticmethod
    def looks_like_mework_text(text):
        if not text:
            return False
        text_upper = text.upper()
        return "WORKERS' COMPENSATION BOARD" in text_upper or "WCB#" in text_upper or "WCB NO" in text_upper

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

    def log_fcc_metadata(self, metadata, source):
        logging.info(
            "Extracted FCC metadata from %s: docket=%s decision_date=%s source_detail=%s title=%s review=%s",
            source,
            metadata.docket_number,
            metadata.decision_date,
            metadata.source_detail,
            metadata.title_hint,
            getattr(metadata, "review_status", ""),
        )

    def log_ferc_metadata(self, metadata, source):
        logging.info(
            "Extracted FERC metadata from %s: docket=%s decision_date=%s source_detail=%s other_numbers=%s title=%s review=%s",
            source,
            metadata.docket_number,
            metadata.decision_date,
            metadata.source_detail,
            "; ".join(metadata.other_numbers or ()),
            metadata.title_hint,
            getattr(metadata, "review_status", ""),
        )

    def log_nlrb_metadata(self, metadata, source):
        logging.info(
            "Extracted NLRB metadata from %s: docket=%s decision_date=%s source_detail=%s other_numbers=%s title=%s review=%s",
            source,
            metadata.docket_number,
            metadata.decision_date,
            metadata.source_detail,
            "; ".join(metadata.other_numbers or ()),
            metadata.title_hint,
            getattr(metadata, "review_status", ""),
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

    def log_mework_metadata(self, metadata, source):
        logging.info(
            "Extracted MEWORK metadata from %s: court=%s docket=%s decision_date=%s source_detail=%s other_numbers=%s excluded=%s",
            source,
            metadata.court,
            metadata.docket_number,
            metadata.decision_date,
            metadata.source_detail,
            "; ".join(metadata.other_numbers or ()),
            getattr(metadata, "is_excluded", False),
        )

    def log_mosu00_metadata(self, metadata, source):
        logging.info(
            "Extracted MOSU00 table metadata from %s: court=%s parent_docket=%s decision_date=%s source_detail=%s child_dockets=%s",
            source,
            metadata.court,
            metadata.docket_number,
            metadata.decision_date,
            metadata.source_detail,
            "; ".join(metadata.child_dockets or ()),
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

    def open_and_process_form(self, row, full_df, row_index, file_path, retry_count=0, dar_mode=False, wc_mode=False, mspb_mode=False, mspb_metadata=None, itc_metadata=None, irsplr_metadata=None, ohtax0_metadata=None, mnsutb_metadata=None, mework_metadata=None, mosu00_metadata=None):
        max_modify_attempts = 3
        self._active_duplicate_lni = str(row.get("LNI", "")).strip().upper()
        self._verified_duplicate_match = None
        self._active_duplicate_row = row
        self._active_irsplr_corrupt_exclusion = bool(getattr(irsplr_metadata, "is_verified_corrupt", False))
        self._irsplr_duplicate_review_reason = ""
        self._itc_duplicate_review_reason = ""
        # Store current tab state
        main_tab = getattr(self, '_main_tab', self.driver.current_window_handle)
        opened_tab = getattr(self, '_opened_tab', None)

        smd_cleanup_allowed = not any((dar_mode, wc_mode, mspb_mode)) and all(
            item is None for item in (
                mspb_metadata, itc_metadata, irsplr_metadata, ohtax0_metadata,
                mnsutb_metadata, mework_metadata, mosu00_metadata,
            )
        ) and not any(check(row) for check in (
            is_itc_row, is_irsplr_row, is_ohtax0_row, is_mnsutb_row, is_mework_row,
            is_mosu00_table_row, is_fcc_row, is_ferc_row, is_nlrb_row,
        ))
        cleanup_requested = smd_cleanup_allowed and bool(normalize_status(row.get("Decision Date")))
        cleanup_required = should_recheck_smd_decision_date(row, smd_mode=cleanup_requested)
        before_modify_cleanup = None

        def date_cleanup(snapshot, *, already_modified=False):
            try:
                return self.update_smd_processed_decision_date(
                    row, row_index, snapshot, already_modified=already_modified,
                    original_snapshot=before_modify_cleanup if already_modified else None,
                )
            finally:
                try:
                    self._accept_smd_date_cleanup_alerts(timeout=0.25)
                except Exception:
                    logging.debug("Could not acknowledge a final SMD date-cleanup notice.", exc_info=True)
                self._cleanup_tabs(getattr(self, "_opened_tab", opened_tab), main_tab)

        if cleanup_requested:
            try:
                saved = self.read_smd_date_cleanup_snapshot()
                if saved is None:
                    saved = WebDriverWait(self.driver, 20).until(
                        lambda _driver: self.read_smd_date_cleanup_snapshot()
                    )
            except Exception as exc:
                self._raise_if_invalid_session_error(exc, "inspecting SMD date cleanup")
                saved = None
            before_modify_cleanup = saved
            requested_key = self._saved_date_key(row.get("Decision Date"))
            saved_key = self._saved_date_key(saved.get("decision_date")) if isinstance(saved, dict) else None
            if (cleanup_required and saved is None) or (
                isinstance(saved, dict) and saved.get("ready") is True
                and (cleanup_required or requested_key != saved_key)
            ):
                return date_cleanup(saved)

        if irsplr_metadata is not None and (
            getattr(irsplr_metadata, "is_text_fallback", False)
            or not getattr(irsplr_metadata, "has_text_content", False)
        ) and not getattr(irsplr_metadata, "is_verified_corrupt", False):
            status = self.flag_irsplr_document_review(
                row, row_index, "UNREADABLE - a usable source PDF was not verified; supply a working PDF",
            )
            self._cleanup_tabs(opened_tab, main_tab)
            return status
        
        # Let the outer form-opening wrapper own Modify retries. If the current
        # IRT tab is stale, one failed wait is enough; the next attempt should
        # reopen the LNI from Search Inventory instead of waiting in-place again.
        found_modify = self.attempt_open_modify(row_index=row_index, max_attempts=1)

        if getattr(self, "_itc_duplicate_review_reason", ""):
            status = "MANUAL REVIEW REQUIRED - ITC " + self._itc_duplicate_review_reason
            status_updates_buffer[row_index] = status
            self._cleanup_tabs(opened_tab, main_tab)
            return status
        if getattr(self, "_irsplr_duplicate_review_reason", ""):
            status = self.flag_irsplr_document_review(row, row_index, self._irsplr_duplicate_review_reason)
            self._cleanup_tabs(opened_tab, main_tab)
            return status

        if getattr(self, "_modify_blocked_ready", False):
            # IRT found Modify but refused editing because Ready is already
            # on. Inspect the saved record once; reopening cannot resolve a
            # saved-state mismatch and must not conceal it as a missing button.
            metadata = next((item for item in (
                mspb_metadata, itc_metadata, irsplr_metadata, ohtax0_metadata,
                mnsutb_metadata, mework_metadata, mosu00_metadata,
            ) if item is not None), None)
            if cleanup_requested:
                saved = self.read_smd_date_cleanup_snapshot()
                if cleanup_required or (
                    isinstance(saved, dict)
                    and self._saved_date_key(row.get("Decision Date")) != self._saved_date_key(saved.get("decision_date"))
                ):
                    logging.info("SMD date cleanup: processed state confirmed after Modify; correcting only the explicit sheet date.")
                    return date_cleanup(saved, already_modified=True)
            status = self.verify_ready_locked_form(
                row, full_df, dar_mode=dar_mode, wc_mode=wc_mode, metadata=metadata,
            )
            status_updates_buffer[row_index] = status
            self._cleanup_tabs(opened_tab, main_tab)
            return status
        
        if found_modify:
            if cleanup_required:
                # A completed row must never fall back to normal routing just
                # because its view did not expose Ready until Modify.
                return date_cleanup(self.read_smd_date_cleanup_snapshot(), already_modified=True)
            if self._verified_duplicate_match:
                status = self.save_verified_duplicate(row_index)
            else:
                # Proceed with usual workflow only when IRT did not confirm a
                # content-verified duplicate.
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
                    mework_metadata=mework_metadata,
                    mosu00_metadata=mosu00_metadata,
                )
            if getattr(self, "_irsplr_duplicate_review_reason", ""):
                status = self.flag_irsplr_document_review(row, row_index, self._irsplr_duplicate_review_reason)
            if getattr(self, "_itc_duplicate_review_reason", ""):
                status = "MANUAL REVIEW REQUIRED - ITC " + self._itc_duplicate_review_reason
                status_updates_buffer[row_index] = status
            if status == "DONE" and self._verified_duplicate_match:
                status = self.duplicate_status_label()
            if status == "DONE" or str(status).upper().startswith("DUPLICATE OF "):
                self.submit_irt_form(file_path, row_index)
                status_updates_buffer[row_index] = status
            
            # After successful processing, clean up tabs
            self._cleanup_tabs(opened_tab, main_tab)
            return status
            
        else:
            # Could not find Modify button - implement fresh start strategy
            retry_reason = "IRT form not editable after Modify" if getattr(self, "_modify_transition_incomplete", False) else "Modify button not found"
            logging.warning("%s on attempt %d/%d", retry_reason, retry_count + 1, max_modify_attempts)
            
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
                if not self.refresh_search_inventory_for_retry(reason=f"{retry_reason} for LNI {lni}"):
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
                        mework_metadata=mework_metadata,
                        mosu00_metadata=mosu00_metadata,
                    )
                else:
                    logging.error(f"Failed to re-search LNI before Modify retry {retry_count + 2}/{max_modify_attempts}")
                    status_updates_buffer[row_index] = "ERROR: LNI RE-SEARCH FAILED"
                    return "ERROR: LNI RE-SEARCH FAILED"
            else:
                # All 3 attempts failed - log error and move on
                logging.error(f"All 3 attempts failed for row {row_index}. Moving on to next LNI.")
                status = "ERROR: IRT FORM NOT EDITABLE AFTER 3 ATTEMPTS" if getattr(self, "_modify_transition_incomplete", False) else "ERROR: MODIFY BUTTON NOT FOUND AFTER 3 ATTEMPTS"
                status_updates_buffer[row_index] = status
                return status
    
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
        mework_metadata=None,
        mosu00_metadata=None,
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
            mework_metadata=mework_metadata,
            mosu00_metadata=mosu00_metadata,
        )

    def process_batch(self, df, full_df, file_path, update_progress, batch_type, dar_mode=False, wc_mode=False, mspb_mode=False, irsplr_mode=False, ohtax0_mode=False, mnsutb_mode=False, mework_mode=False, mosu00_mode=False, fcc_mode=False, ferc_mode=False, nlrb_mode=False, *, itc_mode=False):
        # Older callers identify ITC through the batch name. Keep that API
        # working while accepting an explicit flag from current callers.
        itc_mode = itc_mode or batch_type == "itc"
        explicit_metadata_router_mode = _has_explicit_metadata_router_mode(
            itc_mode=itc_mode,
            irsplr_mode=irsplr_mode,
            ohtax0_mode=ohtax0_mode,
            mnsutb_mode=mnsutb_mode,
            mework_mode=mework_mode,
            mosu00_mode=mosu00_mode,
            fcc_mode=fcc_mode,
            ferc_mode=ferc_mode,
            nlrb_mode=nlrb_mode,
        )
        smd_date_cleanup = batch_type in {"counsel", "main"} and not any((
            dar_mode, wc_mode, mspb_mode, explicit_metadata_router_mode,
        ))
        if smd_date_cleanup:
            logging.info("SMD decision-date cleanup v2 active: explicit sheet dates are checked before and after Modify.")
        # Standard SADM/DAR counsel and main-opinion batches may be invoked
        # directly by a parallel worker.  Explicitly retain their expected
        # Process-as-New behavior even if a caller skipped process_rows().
        if irsplr_mode:
            self.configure_irt_duplicate_verification(irsplr_mode=True)
        elif batch_type in {"counsel", "main"} and not mosu00_mode:
            self.configure_irt_duplicate_verification()
        self.safe_alert_accept()

        processed_rows = 0
        total_rows = len(df)
        batch_start_time = time.time()
        processed_count = 0
        total_duration = 0

        # Emit 0/total progress at the start so UI shows batch start immediately
        if update_progress and batch_type in ["counsel", "main", "mspb", "itc", "irsplr", "ohtax0", "mnsutb", "mework", "mosu00", "fcc", "ferc", "nlrb"]:
            update_progress(batch_type, 0, total_rows)

        stop_batch = False
        for full_index in df.index:
            row = df.loc[full_index]
            try:
                row_status = str(row.get("Status", "")).strip().upper()
                recheck_old_comment_review = should_recheck_irsplr_comment_review(row, row_status)
                recheck_pdf_review = should_recheck_irsplr_pdf_review(row, row_status)
                recheck_date = should_recheck_smd_decision_date(row, row_status, smd_mode=smd_date_cleanup)
                if is_completed_status(row_status) and not recheck_old_comment_review and not recheck_pdf_review and not recheck_date:
                    logging.info(f"Skipping completed row {full_index + 2} with status: {row_status}.")
                    status_updates_buffer[full_index] = row_status
                    continue

                if recheck_date:
                    logging.info("Checking only the requested Decision Date on completed SMD row %d.", full_index + 2)
                    status_updates_buffer.pop(full_index, None)

                if recheck_pdf_review:
                    logging.info("Revalidating previous IRSPLR EOF-only review on row %d with structural and page-render checks.", full_index + 2)
                    status_updates_buffer.pop(full_index, None)

                if recheck_old_comment_review:
                    logging.info("Rechecking previous IRSPLR comment-only review for row %d under the already-processed skip policy.", full_index + 2)
                    if should_recheck_irsplr_comment_review(row, status_updates_buffer.get(full_index, "")):
                        status_updates_buffer.pop(full_index, None)

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
                mework_metadata = None
                mosu00_metadata = None
                fcc_metadata = None
                ferc_metadata = None
                nlrb_metadata = None
                row_is_itc = is_itc_row(row)
                row_is_irsplr = is_irsplr_row(row)
                row_is_ohtax0 = is_ohtax0_row(row)
                row_is_mnsutb = is_mnsutb_row(row)
                row_is_mework = is_mework_row(row)
                row_is_mosu00_table = is_mosu00_table_row(row)
                row_is_fcc = is_fcc_row(row)
                row_is_ferc = is_ferc_row(row)
                row_is_nlrb = is_nlrb_row(row)
                # The batch's explicit mode takes priority over these
                # overlapping filename hints (including LDC_BC_ OHTAX0 PDFs).
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
                elif itc_mode or (row_is_itc and not explicit_metadata_router_mode):
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
                    self._archive_duplicate_mode = bool(getattr(itc_metadata, "is_true_duplicate", False))
                    self.click_matching_result()
                elif fcc_mode or (row_is_fcc and not explicit_metadata_router_mode):
                    self.record_fcc_metadata(full_index, row, lni, metadata_status="Attempted")
                    if not self.search_lni(lni) or not self.check_result_available():
                        self.record_fcc_metadata(full_index, row, lni, metadata_status="Search Failed")
                        status_updates_buffer[full_index] = "ERROR: LNI NOT FOUND"
                        continue
                    fcc_metadata = self.extract_fcc_metadata_from_search_result(row, full_index)
                    if not fcc_metadata:
                        self.record_fcc_metadata(full_index, row, lni, metadata_status="Not Extracted")
                        status_updates_buffer[full_index] = "NEEDS REVIEW"
                        logging.warning("FCC row %d has no usable PDF metadata; no IRT changes made.", full_index + 2)
                        continue
                    self.record_fcc_metadata(full_index, row, lni, metadata=fcc_metadata, metadata_status="Extracted")
                    if getattr(fcc_metadata, "requires_review", False):
                        status = getattr(fcc_metadata, "review_status", "NEEDS REVIEW") or "NEEDS REVIEW"
                        status_updates_buffer[full_index] = status
                        logging.info("FCC row %d marked %s before IRT processing.", full_index + 2, status)
                        continue
                    # FCC has the same one-document form shape as ITC. Pass the
                    # strongly typed FCC metadata through that shared form path.
                    itc_metadata = fcc_metadata
                    self.click_matching_result()
                elif ferc_mode or (row_is_ferc and not explicit_metadata_router_mode):
                    self.record_ferc_metadata(full_index, row, lni, metadata_status="Attempted")
                    if not self.search_lni(lni) or not self.check_result_available():
                        self.record_ferc_metadata(full_index, row, lni, metadata_status="Search Failed")
                        status_updates_buffer[full_index] = "ERROR: LNI NOT FOUND"
                        continue
                    ferc_metadata = self.extract_ferc_metadata_from_search_result(row, full_index)
                    if not ferc_metadata:
                        self.record_ferc_metadata(full_index, row, lni, metadata_status="Not Extracted")
                        status_updates_buffer[full_index] = "NEEDS REVIEW"
                        logging.warning("FERC row %d has no usable PDF metadata; no IRT changes made.", full_index + 2)
                        continue
                    self.record_ferc_metadata(full_index, row, lni, metadata=ferc_metadata, metadata_status="Extracted")
                    if getattr(ferc_metadata, "requires_review", False):
                        status = getattr(ferc_metadata, "review_status", "NEEDS REVIEW") or "NEEDS REVIEW"
                        status_updates_buffer[full_index] = status
                        logging.info("FERC row %d marked %s before IRT processing.", full_index + 2, status)
                        continue
                    itc_metadata = ferc_metadata
                    self.click_matching_result()
                elif nlrb_mode or (row_is_nlrb and not explicit_metadata_router_mode):
                    self.record_nlrb_metadata(full_index, row, lni, metadata_status="Attempted")
                    if not self.search_lni(lni) or not self.check_result_available():
                        self.record_nlrb_metadata(full_index, row, lni, metadata_status="Search Failed")
                        status_updates_buffer[full_index] = "ERROR: LNI NOT FOUND"
                        continue
                    nlrb_metadata = self.extract_nlrb_metadata_from_search_result(row, full_index)
                    if not nlrb_metadata:
                        self.record_nlrb_metadata(full_index, row, lni, metadata_status="Not Extracted")
                        status_updates_buffer[full_index] = "MANUAL REVIEW REQUIRED — DOCUMENT CONTENT UNREADABLE"
                        logging.warning("NLRB row %d has no usable PDF metadata; no IRT changes made.", full_index + 2)
                        continue
                    self.record_nlrb_metadata(full_index, row, lni, metadata=nlrb_metadata, metadata_status="Extracted")
                    if getattr(nlrb_metadata, "requires_review", False):
                        status = getattr(nlrb_metadata, "review_status", "MANUAL REVIEW REQUIRED") or "MANUAL REVIEW REQUIRED"
                        status_updates_buffer[full_index] = status
                        logging.info("NLRB row %d marked %s before IRT processing.", full_index + 2, status)
                        continue
                    itc_metadata = nlrb_metadata
                    self.click_matching_result()
                elif irsplr_mode or (row_is_irsplr and not explicit_metadata_router_mode):
                    self.record_irsplr_metadata(full_index, row, lni, metadata_status="Attempted")

                    if not self.search_lni(lni) or not self.check_result_available():
                        self.record_irsplr_metadata(full_index, row, lni, metadata_status="Search Failed")
                        status_updates_buffer[full_index] = "ERROR: LNI NOT FOUND"
                        continue

                    try:
                        irsplr_metadata = self.extract_irsplr_metadata_from_search_result(row, full_index)
                    except IRSPLRCorruptDocument as exc:
                        irsplr_metadata = build_irsplr_corrupt_exclusion_metadata(
                            court_code_hint=row.get("CourtCode", ""), reason=str(exc),
                        )
                        logging.warning("LNI %s: verified PDF failure; routing Excluded / Archive with comment Exclude - Corrupt File. Reason: %s", lni, exc)
                    if not irsplr_metadata:
                        raise IRSPLRDocumentReviewRequired(
                            "UNREADABLE OR UNAVAILABLE - PDF content and complete metadata could not be verified; supply a working PDF"
                        )
                    else:
                        self.record_irsplr_metadata(
                            full_index, row, lni, metadata=irsplr_metadata,
                            metadata_status=(f"Verified Corrupt File - {irsplr_metadata.exclusion_reason}"
                                             if getattr(irsplr_metadata, "is_verified_corrupt", False) else "Extracted"),
                        )

                    self.click_matching_result()
                elif ohtax0_mode or (row_is_ohtax0 and not explicit_metadata_router_mode):
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
                elif mnsutb_mode or (row_is_mnsutb and not explicit_metadata_router_mode):
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
                elif mework_mode or (row_is_mework and not explicit_metadata_router_mode):
                    self.record_mework_metadata(full_index, row, lni, metadata_status="Attempted")

                    if not self.search_lni(lni) or not self.check_result_available():
                        self.record_mework_metadata(full_index, row, lni, metadata_status="Search Failed")
                        status_updates_buffer[full_index] = "ERROR: LNI NOT FOUND"
                        continue

                    mework_metadata = self.extract_mework_metadata_from_search_result(row, full_index)
                    if not mework_metadata:
                        self.record_mework_metadata(full_index, row, lni, metadata_status="Not Extracted")
                        status_updates_buffer[full_index] = "SKIPPED: MEWORK PDF DATA NOT FOUND"
                        logging.warning(f"Skipping MEWORK row {full_index + 2}: required PDF metadata could not be extracted.")
                        continue

                    mework_metadata = self.mark_mework_duplicate_status(full_index, row, lni, mework_metadata)
                    self.record_mework_metadata(full_index, row, lni, metadata=mework_metadata, metadata_status="Extracted")
                    self._archive_duplicate_mode = bool(getattr(mework_metadata, "is_true_duplicate", False))
                    self.click_matching_result()
                elif mosu00_mode and row_is_mosu00_table:
                    self.record_mosu00_metadata(full_index, row, lni, metadata_status="Attempted")

                    if not self.search_lni(lni) or not self.check_result_available():
                        self.record_mosu00_metadata(full_index, row, lni, metadata_status="Search Failed")
                        status_updates_buffer[full_index] = "ERROR: LNI NOT FOUND"
                        continue

                    mosu00_metadata = self.extract_mosu00_metadata_from_search_result(row, full_index, file_path=file_path)
                    if not mosu00_metadata:
                        self.record_mosu00_metadata(full_index, row, lni, metadata_status="Not Extracted")
                        status_updates_buffer[full_index] = "SKIPPED: MOSU00 HTML DATA NOT FOUND"
                        logging.warning(f"Skipping MOSU00 row {full_index + 2}: required table HTML metadata could not be extracted.")
                        continue

                    self.record_mosu00_metadata(full_index, row, lni, metadata=mosu00_metadata, metadata_status="Extracted")
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
                    mework_metadata=mework_metadata,
                    mosu00_metadata=mosu00_metadata,
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
                        mework_metadata=mework_metadata,
                        mosu00_metadata=mosu00_metadata,
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
                    error_log_entries.append({
                        "Row": full_index + 2,
                        "LNI": row.get("LNI", ""),
                        "File Name": row.get("FileName", "") or row.get("File Name", ""),
                        "Status": final_status or "UNKNOWN",
                        "Error Message": f"Ended as {final_status or 'UNKNOWN'} during {batch_type} batch."
                    })


            except IRSPLRDocumentReviewRequired as exc:
                # A source-document defect is a review stop for this row,
                # not permission to Modify/Save it or stop other documents.
                self.flag_irsplr_document_review(row, full_index, str(exc))
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
                logging.exception("Error processing row %d: %s", full_index + 2, e)
                # Persist the primary error before optional diagnostics. A
                # metadata-reporting failure must not leave PROCESSING rows
                # absent from the final error report.
                status_updates_buffer[full_index] = "ERROR"
                error_log_entries.append({
                    "Row": full_index + 2,
                    "LNI": row.get("LNI", ""),
                    "File Name": row.get("FileName", ""),
                    "Status": "ERROR",
                    "Error Message": str(e)
                })
                try:
                    existing_status = mspb_metadata_buffer.get(full_index, {}).get("Metadata Status", "")
                    metadata_status = "Extracted" if existing_status == "Extracted" else "Error"
                    if mspb_mode:
                        self.record_mspb_metadata(full_index, row, row.get("LNI", ""), metadata_status=metadata_status)
                    elif itc_mode or (is_itc_row(row) and not explicit_metadata_router_mode):
                        self.record_itc_metadata(full_index, row, row.get("LNI", ""), metadata_status=metadata_status)
                    elif irsplr_mode or (is_irsplr_row(row) and not explicit_metadata_router_mode):
                        self.record_irsplr_metadata(full_index, row, row.get("LNI", ""), metadata_status=metadata_status)
                    elif ohtax0_mode or (is_ohtax0_row(row) and not explicit_metadata_router_mode):
                        self.record_ohtax0_metadata(full_index, row, row.get("LNI", ""), metadata_status=metadata_status)
                    elif mnsutb_mode or (is_mnsutb_row(row) and not explicit_metadata_router_mode):
                        self.record_mnsutb_metadata(full_index, row, row.get("LNI", ""), metadata_status=metadata_status)
                    elif mework_mode or (is_mework_row(row) and not explicit_metadata_router_mode):
                        self.record_mework_metadata(full_index, row, row.get("LNI", ""), metadata_status=metadata_status)
                    elif is_mosu00_table_row(row):
                        self.record_mosu00_metadata(full_index, row, row.get("LNI", ""), metadata_status=metadata_status)
                except Exception:
                    logging.warning("Could not record metadata diagnostics for row %d.", full_index + 2, exc_info=True)
                try:
                    self.driver.close()
                    self.driver.switch_to.window(self.driver.window_handles[0])
                except:
                    pass
            finally:
                self._archive_duplicate_mode = False
                # ✅ Always update progress, regardless of success or error
                processed_rows += 1
                if update_progress and batch_type in ["counsel", "main", "mspb", "itc", "irsplr", "ohtax0", "mnsutb", "mework", "mosu00", "fcc", "ferc", "nlrb"]:
                    update_progress(batch_type, processed_rows, total_rows)

        # ✅ ⏱ Final summary log: outside the loop
            if stop_batch:
                if update_progress and batch_type in ["counsel", "main", "mspb", "itc", "irsplr", "ohtax0", "mnsutb", "mework", "mosu00", "fcc", "ferc", "nlrb"]:
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

    def uses_irt_modify_recovery(self):
        """ITC and NLRB share delayed/replaced IRT form controls."""
        return bool(getattr(self, "_itc_duplicate_verification", False)
                    or getattr(self, "_itc_field_recovery_active", False)
                    or getattr(self, "_nlrb_form_recovery", False))

    def attempt_open_modify(self, file_path=None, row_index=None, max_attempts=3):
        self._modify_blocked_ready = False
        self._modify_transition_incomplete = False
        for attempt in range(1, max_attempts + 1):
            try:
                # Check session validity before attempting to find Modify button
                if not self.check_session_validity():
                    logging.error("Invalid session detected. Cannot proceed with Modify button click.")
                    raise RouterSessionLostError("Router browser session is no longer valid before Modify click.")

                # A duplicate notice may already be waiting when the form
                # opens. Accept it before a WebDriver lookup can dismiss it.
                pending = self._accept_modify_transition_alerts()
                if pending:
                    state = self.settle_irt_modify_transition(initial_alerts=pending)
                    if state == "EDITABLE":
                        return True
                    if state == "READY_LOCKED":
                        self._modify_blocked_ready = True
                        return False
                    # An accepted duplicate warning starts a required dialog
                    # workflow. If it times out, let the caller reopen the
                    # record; do not click Modify again behind that dialog.
                    return False
                
                logging.info(f"Attempt {attempt}/{max_attempts}: Waiting for Modify button...")
                itc_recovery = self.uses_irt_modify_recovery()
                modify_condition = (
                    (lambda driver: next((button for button in driver.find_elements(By.ID, "modify")
                                          if button.is_displayed() and button.is_enabled()), False))
                    if itc_recovery else EC.element_to_be_clickable((By.XPATH, '//*[@id="modify"]'))
                )
                modify_btn = WebDriverWait(self.driver, 120).until(  # Reduced to 2 minutes (120 seconds) for faster failure detection
                    modify_condition
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

                    if self.is_ready_locked_alert(alert_text):
                        state = self.settle_irt_modify_transition(initial_alerts=[alert_text])
                        self._modify_blocked_ready = state == "READY_LOCKED"
                        return state == "EDITABLE"
                    # Handle duplicate document alert
                    if "duplicate document" in alert_text.lower():
                        state = self.settle_irt_modify_transition(initial_alerts=[alert_text])
                        self._modify_blocked_ready = state == "READY_LOCKED"
                        return state == "EDITABLE"
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

                            if self.is_ready_locked_alert(additional_alert_text):
                                state = self.settle_irt_modify_transition(initial_alerts=[additional_alert_text])
                                self._modify_blocked_ready = state == "READY_LOCKED"
                                return state == "EDITABLE"
                            
                            # If it's a duplicate document alert, handle it
                            if "duplicate document" in additional_alert_text.lower():
                                state = self.settle_irt_modify_transition(initial_alerts=[additional_alert_text])
                                self._modify_blocked_ready = state == "READY_LOCKED"
                                return state == "EDITABLE"
                            # The DSAR notice and any non-document follow-up
                            # were accepted. Modify mode is now usable.
                            state = self.settle_irt_modify_transition()
                            self._modify_blocked_ready = state == "READY_LOCKED"
                            return state == "EDITABLE"
                        except TimeoutException:
                            logging.info("No additional alert found after DSAR duplicate alert.")
                            # DSAR is informational for SADM/DARA, but still
                            # confirm edit mode before using the form.
                            state = self.settle_irt_modify_transition()
                            self._modify_blocked_ready = state == "READY_LOCKED"
                            return state == "EDITABLE"
                    state = self.settle_irt_modify_transition(initial_alerts=[alert_text])
                    self._modify_blocked_ready = state == "READY_LOCKED"
                    return state == "EDITABLE"
                except TimeoutException:
                    # No native alert appeared; confirm that Modify completed.
                    state = self.settle_irt_modify_transition()
                    self._modify_blocked_ready = state == "READY_LOCKED"
                    return state == "EDITABLE"

            except UnexpectedAlertPresentException as exc:
                # A warning can interrupt the Modify click itself. Preserve
                # the overlay requirement even if Chrome already dismissed
                # the native alert before returning this exception.
                state = self.settle_irt_modify_transition(
                    initial_alerts=[str(getattr(exc, "alert_text", None) or exc)],
                )
                self._modify_blocked_ready = state == "READY_LOCKED"
                return state == "EDITABLE"
            except Exception as e:
                error_msg = str(e)
                logging.warning(f"Attempt {attempt}/{max_attempts} to click Modify button failed: {error_msg}")
                
                # Check if it's a session-related error
                if self._is_invalid_session_error(e):
                    logging.error("Session invalid. Cannot retry - browser connection lost.")
                    raise RouterSessionLostError("Router browser session lost while opening Modify mode.") from e
                if self.uses_irt_modify_recovery():
                    try:
                        snapshot = self.read_ready_locked_form()
                    except Exception as diagnostic_error:
                        self._raise_if_invalid_session_error(diagnostic_error, "reading ITC Modify failure diagnostics")
                        snapshot = {}
                    self.log_irt_modify_recovery_state(snapshot, phase="Modify button lookup/click", timeout=120)
                
                time.sleep(2) # Brief pause before the next attempt in the loop

        # If all attempts fail (loop finishes without returning True)
        logging.error(f"Failed to enter modify mode after {max_attempts} attempts.")
        if row_index is not None:
            status_updates_buffer[row_index] = "ERROR: MODIFY FAILED"
        return False

    @staticmethod
    def is_ready_locked_alert(text):
        return bool(re.search(r"ready\s+to\s+process\s*=\s*\[\s*on\s*\]", str(text), re.IGNORECASE))

    def _accept_modify_transition_alerts(self):
        """Drain native notices before inspecting controls behind the alerts."""
        texts = []
        for _ in range(5):
            try:
                alert = self.driver.switch_to.alert
                alert_text = alert.text
                if not isinstance(alert_text, str):
                    break
                alert.accept()
                texts.append(alert_text.strip())
                logging.info("Accepted IRT form transition alert: %s", alert_text.strip())
            except NoAlertPresentException:
                break
            except Exception as exc:
                self._raise_if_invalid_session_error(exc, "accepting IRT form transition alert")
                raise
        return texts

    def settle_irt_modify_transition(self, *, initial_alerts=(), timeout=None, allow_modify_retry=True, duplicate_overlay_timeout=30):
        """Clear delayed duplicate UI and wait for a stable editing/Ready state.

        A native duplicate warning always requires its following overlay to
        appear and finish, even if the underlying form looks editable first.
        Only after that workflow may we inspect the form's editing/Ready state.
        """
        self._last_transition_duplicate_cleared = False
        self._modify_transition_incomplete = False
        itc_recovery = self.uses_irt_modify_recovery()
        timeout = (30 if itc_recovery else 8) if timeout is None else timeout
        ready_warning = itc_recovery and any(self.is_ready_locked_alert(text) for text in initial_alerts)
        ready_modify_retries = 0
        next_ready_modify = time.monotonic() + 1
        last_snapshot = {}
        retried_modify = False
        stable_state = None
        stable_since = None
        deadline = time.monotonic() + timeout
        overlay_pending = False
        overlay_deadline = None

        def expect_duplicate_overlay():
            nonlocal overlay_pending, overlay_deadline, stable_since
            if not overlay_pending:
                overlay_deadline = time.monotonic() + duplicate_overlay_timeout
                logging.info(
                    "Duplicate warning accepted; waiting up to %s seconds for its required overlay before using the IRT form.",
                    duplicate_overlay_timeout,
                )
            overlay_pending = True
            self._last_transition_duplicate_cleared = False
            stable_since = None

        if any("duplicate document" in text.lower() for text in initial_alerts):
            expect_duplicate_overlay()

        while time.monotonic() < (overlay_deadline if overlay_pending else deadline):
            try:
                alerts = self._accept_modify_transition_alerts()
                if alerts:
                    stable_since = None
                    if any("duplicate document" in text.lower() for text in alerts):
                        expect_duplicate_overlay()
                    if itc_recovery and not ready_warning and any(self.is_ready_locked_alert(text) for text in alerts):
                        ready_warning = True
                        deadline = max(deadline, time.monotonic() + timeout)
                radios = self.driver.find_elements(By.ID, "processDuplicate")
                if any(radio.is_displayed() for radio in radios):
                    if not self.handle_duplicate_overlay():
                        logging.warning("Required duplicate overlay workflow failed; not proceeding with the IRT form.")
                        self._modify_transition_incomplete = True
                        return "NOT_READY"
                    stable_since = None
                    overlay_pending = False
                    overlay_deadline = None
                    self._last_transition_duplicate_cleared = True
                    # Overlay handling can outlast the normal form wait. Give
                    # the replacement form a fresh settling window afterward.
                    deadline = time.monotonic() + timeout
                    logging.info("Required duplicate overlay workflow completed; waiting for the IRT form to settle.")
                if overlay_pending:
                    # The form may be enabled while the overlay is still
                    # loading. Never read/classify it or retry Modify here.
                    time.sleep(0.2)
                    continue
                snapshot = self.read_ready_locked_form()
                if not isinstance(snapshot, dict):
                    stable_since = None
                    time.sleep(0.2)
                    continue
                last_snapshot = snapshot
                loaded = snapshot.get("docket") is not None and bool(snapshot.get("route"))
                if itc_recovery and (snapshot.get("blocking_dialog") or snapshot.get("ready_visible") is False):
                    loaded = False
                state = None
                if loaded and snapshot.get("ready") is True:
                    state = "READY_LOCKED"
                elif loaded and snapshot.get("ready") is False and snapshot.get("route_enabled") and snapshot.get("comments_enabled"):
                    state = "EDITABLE"
                if state:
                    if stable_state != state or stable_since is None:
                        stable_state, stable_since = state, time.monotonic()
                    if time.monotonic() - stable_since >= (1.0 if state == "READY_LOCKED" else 0.4):
                        logging.info("IRT form settled after Modify: %s", state)
                        return state
                else:
                    stable_state, stable_since = None, None
                    retry_ready_warning = (
                        ready_warning and loaded and snapshot.get("ready") is False
                        and ready_modify_retries < 2 and time.monotonic() >= next_ready_modify
                    )
                    retry_after_duplicate = self._last_transition_duplicate_cleared and not retried_modify
                    if allow_modify_retry and snapshot.get("ready") is False and not snapshot.get("blocking_dialog") and (retry_after_duplicate or retry_ready_warning):
                        buttons = self.driver.find_elements(By.ID, "modify")
                        for button in buttons:
                            if button.is_displayed() and button.is_enabled():
                                # Count before click: a native warning may
                                # interrupt it, and retries must stay bounded.
                                if retry_ready_warning:
                                    ready_modify_retries += 1
                                    next_ready_modify = time.monotonic() + 3
                                    logging.info("IRT Ready warning cleared and visible Ready is unchecked; retrying Modify on the same form (%d/2).", ready_modify_retries)
                                if retry_after_duplicate:
                                    retried_modify = True
                                    logging.info("Duplicate notice cleared; entering Modify mode on the same IRT form.")
                                button.click()
                                break
                time.sleep(0.2)
            except UnexpectedAlertPresentException as exc:
                # A delayed alert arrived between the DOM check and read.
                stable_since = None
                # Chrome may dismiss-and-notify before the next alert read.
                # Preserve its duplicate warning instead of losing the gate.
                if "duplicate document" in str(getattr(exc, "alert_text", None) or exc).lower():
                    expect_duplicate_overlay()
                elif itc_recovery and not ready_warning and self.is_ready_locked_alert(getattr(exc, "alert_text", None) or exc):
                    ready_warning = True
                    deadline = max(deadline, time.monotonic() + timeout)
                time.sleep(0.2)
            except Exception as exc:
                self._raise_if_invalid_session_error(exc, "settling IRT Modify mode")
                logging.warning("IRT form transition has not settled yet: %s", exc)
                time.sleep(0.2)
        if overlay_pending:
            logging.warning("Timed out waiting for the required duplicate overlay after its warning; not filling or saving this IRT form.")
        else:
            logging.warning("IRT form did not settle into an editable or confirmed Ready-locked state.")
        self.log_irt_modify_recovery_state(last_snapshot, ready_warning=ready_warning, overlay_pending=overlay_pending,
                                          retries=ready_modify_retries, timeout=timeout)
        self._modify_transition_incomplete = True
        return "NOT_READY"

    def log_irt_modify_recovery_state(self, snapshot, *, phase="settling", ready_warning=False,
                                      overlay_pending=False, retries=0, timeout=None):
        snapshot = snapshot if isinstance(snapshot, dict) else {}
        logging.warning(
            "IRT Modify recovery state: phase=%s lni=%s docket=%r ready=%r ready_visible=%r ready_enabled=%r route=%r route_enabled=%r "
            "comments_enabled=%r page_state=%r page_url=%r blocking_dialog=%r ready_warning=%s "
            "duplicate_overlay_required=%s same_form_retries=%d timeout=%s",
            phase, getattr(self, "_active_duplicate_lni", ""), snapshot.get("docket"), snapshot.get("ready"),
            snapshot.get("ready_visible"), snapshot.get("ready_enabled"), snapshot.get("route"),
            snapshot.get("route_enabled"), snapshot.get("comments_enabled"),
            snapshot.get("page_state"), snapshot.get("page_url"), snapshot.get("blocking_dialog"),
            ready_warning, overlay_pending, retries, timeout,
        )

    def read_ready_locked_form(self):
        """Read saved form values without enabling, changing, or submitting them."""
        return self.driver.execute_script(r"""
            const preferVisible = arguments[0];
            const visible = element => !!element && getComputedStyle(element).display !== 'none'
                && getComputedStyle(element).visibility !== 'hidden' && element.getClientRects().length > 0;
            const field = id => preferVisible
                ? Array.from(document.querySelectorAll('[id="' + id + '"]')).find(visible) || null
                : document.getElementById(id);
            const value = id => {
                const element = field(id);
                return element ? String(element.value || '').trim() : null;
            };
            const selected = id => {
                const element = field(id);
                if (!element) return null;
                const option = element.options && element.selectedIndex >= 0
                    ? element.options[element.selectedIndex] : null;
                return String(option ? (option.textContent || option.label || option.value || '')
                    : (element.value || '')).trim();
            };
            const related = field('relatedLni');
            const ready = field('readyToProcess');
            const route = field('route');
            const comments = field('comments');
            return {
                ready: ready ? ready.checked : null,
                route: selected('route'),
                source_detail: selected('sourceDetails'),
                docket: value('docketNumber'),
                decision_date: value('decisionDate'),
                comments: value('comments'),
                route_enabled: !!route && !route.disabled,
                comments_enabled: !!comments && !comments.disabled && (!preferVisible || !comments.readOnly),
                ready_enabled: !!ready && !ready.disabled,
                ready_visible: visible(ready),
                page_state: document.readyState,
                page_url: location.href.split(/[?#]/)[0],
                blocking_dialog: preferVisible && Array.from(document.querySelectorAll('[role="dialog"], .ui-dialog, .ui-widget-overlay'))
                    .some(element => visible(element) && !element.contains(ready) && !element.contains(route)),
                related_lnis: !related ? null : related.options
                    ? Array.from(related.options).map(option => option.textContent || option.label || option.value || '').join('\n')
                    : (related.textContent || '')
            };
        """, self.uses_irt_modify_recovery())

    def read_smd_date_cleanup_snapshot(self):
        """Read business values without enabling or changing any form control."""
        return self.driver.execute_script(r"""
            const date = document.getElementById('decisionDate');
            const ready = document.getElementById('readyToProcess');
            if (!date || !ready) return null;
            const controls = Array.from(document.querySelectorAll('input, select, textarea'));
            const protectedFields = {};
            const recordLnis = new Set();
            const lniPattern = /^[A-Z0-9]{4}(?:-[A-Z0-9]{4}){3}-[A-Z0-9]{5}-[A-Z0-9]{2}$/i;
            controls.forEach((element, index) => {
                const key = element.id || element.name || ('control-' + index);
                const identity = String(element.id || '') + ' ' + String(element.name || '');
                const value = String(element.value || '');
                if (/lni/i.test(identity) && !/related|relate|search|parent|child|counsel|duplicate|original|recycled/i.test(identity)
                    && lniPattern.test(value.trim())) recordLnis.add(value.trim().toUpperCase());
                if (element === date || /^(hidden|button|submit|reset|file|password)$/i.test(element.type || '')) return;
                // Server-generated audit and request tokens naturally change
                // on Save; all other form values remain protected.
                if (/lastmodified|modifiedby|modification|documenthistory|csrf|token|viewstate|eventvalidation|ui-datepicker/i.test(identity)) return;
                protectedFields[key] = {
                    value: value,
                    checked: /^(checkbox|radio)$/i.test(element.type || '') ? !!element.checked : null,
                    options: element.tagName === 'SELECT' && /relatedlni|tablecase/i.test(identity)
                        ? Array.from(element.options || []).map(option => [option.value, option.textContent]) : null
                };
            });
            // Some IRT versions show the document LNI as text beside its
            // label instead of an input. Never infer identity from Comments
            // or from a Related LNI list.
            Array.from(document.querySelectorAll('label, td, th')).forEach(label => {
                if (!/^(document\s*)?LNI\s*:?$/i.test(String(label.textContent || '').trim())) return;
                const target = label.htmlFor ? document.getElementById(label.htmlFor) : label.nextElementSibling;
                if (!target) return;
                if (/related|relate|search|parent|child|counsel|duplicate|original|recycled/i.test(
                    String(target.id || '') + ' ' + String(target.name || ''))) return;
                const value = String(target.value || target.textContent || '').trim();
                if (lniPattern.test(value)) recordLnis.add(value.toUpperCase());
            });
            const visibleDialogs = Array.from(document.querySelectorAll('[role="dialog"], .ui-dialog, .ui-widget-overlay'))
                .some(element => {
                    const style = getComputedStyle(element);
                    return style.display !== 'none' && style.visibility !== 'hidden'
                        && element.getClientRects().length > 0;
                });
            return {
                ready: !!ready.checked,
                decision_date: String(date.value || '').trim(),
                docket: String((document.getElementById('docketNumber') || {}).value || '').trim(),
                record_lni: recordLnis.size === 1 ? Array.from(recordLnis)[0] : null,
                protected_fields: protectedFields,
                blocking_dialog: visibleDialogs
            };
        """)

    def _accept_smd_date_cleanup_alerts(self, timeout=1):
        """Acknowledge notices without executing duplicate/routing workflows."""
        notices = []
        try:
            alert = WebDriverWait(self.driver, timeout).until(EC.alert_is_present())
        except TimeoutException:
            return notices
        except NoSuchWindowException:
            if getattr(self, "_main_tab", None) in self.driver.window_handles:
                return notices
            raise
        for _ in range(5):
            text = str(alert.text or "").strip()
            alert.accept()
            notices.append(text)
            logging.info("SMD date cleanup notice: %s", text)
            try:
                alert = self.driver.switch_to.alert
            except NoAlertPresentException:
                return notices
        raise ValueError("repeated IRT alerts prevented date-only cleanup")

    def update_smd_processed_decision_date(self, row, row_index, before, *, already_modified=False, original_snapshot=None):
        """Modify only an explicit date on a saved record, then verify a fresh read."""
        lni = str(row.get("LNI", "")).strip().upper()
        save_attempted = False

        def finish(status, detail=""):
            status_updates_buffer[row_index] = status
            logging.info("SMD date cleanup LNI %s: %s%s", lni, status, (" - " + detail) if detail else "")
            return status

        def review(reason):
            if save_attempted:
                return finish(STATUS_DATE_UPDATE_UNCONFIRMED, reason)
            return finish("MANUAL REVIEW REQUIRED - SMD DATE CLEANUP: " + reason)

        def unchanged(snapshot):
            return isinstance(snapshot, dict) and snapshot.get("protected_fields") == before.get("protected_fields")

        try:
            requested_key = self._saved_date_key(row.get("Decision Date"))
            if not requested_key:
                return review("supply a valid Decision Date in the mapping sheet; no date was changed")
            target = datetime.datetime.strptime(requested_key, "%Y-%m-%d").strftime("%m-%d-%Y")
            if not isinstance(before, dict) or not before.get("protected_fields"):
                return review("the existing IRT form could not be verified; no date was changed")
            if before.get("ready") is not True or before.get("blocking_dialog"):
                return review("the form is not a confirmed processed record or a dialog is still open; no date was changed")
            if before.get("record_lni") != lni:
                return review("the open IRT form's LNI does not match or could not be confirmed; no date was changed")
            if already_modified and isinstance(original_snapshot, dict) and original_snapshot.get("protected_fields"):
                original_fields = dict(original_snapshot["protected_fields"])
                current_fields = dict(before["protected_fields"])
                if original_snapshot.get("ready") is False and before.get("ready") is True:
                    # IRT can expose its saved Ready state only after Modify.
                    # The bot never toggles Ready during date cleanup.
                    original_fields.pop("readyToProcess", None)
                    current_fields.pop("readyToProcess", None)
                if original_fields != current_fields:
                    return review("another form value changed while Modify revealed the saved record; Save was not clicked")
            expected_docket = extract_docket_number(str(row.get("FileName", "")))
            docket_key = lambda value: re.sub(r"\s+", "", self.normalize_irt_text(value)).upper()
            if not expected_docket or docket_key(expected_docket) != docket_key(before.get("docket", "")):
                return review("the saved docket does not match the mapping filename; no date was changed")
            if self._saved_date_key(before.get("decision_date")) == requested_key:
                if normalize_status(row.get("Status")) == STATUS_DATE_UPDATE_UNCONFIRMED:
                    return review("the date matches after a previously unconfirmed Save; check the prior run's saved-state warning before treating the record as complete")
                return finish("ALREADY PROCESSED", "Decision Date already matches the sheet; no Modify or Save")

            if not already_modified:
                modify = WebDriverWait(self.driver, 20).until(EC.element_to_be_clickable((By.ID, "modify")))
                modify.click()
                notices = self._accept_smd_date_cleanup_alerts(timeout=3)
                if any("duplicate" in notice.lower() for notice in notices):
                    return review("a duplicate notice requires review; date cleanup did not enter its routing workflow")
            def editable_date(driver):
                field = driver.find_element(By.ID, "decisionDate")
                return field if field.is_enabled() and field.get_attribute("readonly") in (None, False, "false") else False

            try:
                date_field = WebDriverWait(self.driver, 10).until(editable_date)
            except TimeoutException:
                return review("Decision Date remains locked after Modify/Correction; no date was changed")
            editable = self.read_smd_date_cleanup_snapshot()
            if not unchanged(editable) or editable.get("blocking_dialog"):
                return review("IRT changed another form value or opened a dialog after Modify; Save was not clicked")
            date_field.clear()
            date_field.send_keys(target)
            date_field.send_keys(Keys.TAB)
            notices = self._accept_smd_date_cleanup_alerts(timeout=1)
            if notices:
                return review("IRT raised a notice while editing the date; verify it manually; Save was not clicked")
            prepared = self.read_smd_date_cleanup_snapshot()
            if not unchanged(prepared) or prepared.get("blocking_dialog"):
                return review("another form value changed while entering the date; Save was not clicked")
            if self._saved_date_key(prepared.get("decision_date")) != requested_key:
                return review("IRT did not retain the requested date; Save was not clicked")

            save_button = WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable((By.ID, "add")))
            save_attempted = True
            save_button.click()
            notices = self._accept_smd_date_cleanup_alerts(timeout=2)
            if any(re.search(r"\b(cannot|failed|invalid|error|duplicate)\b|\bnot\s+(saved|updated|valid)\b", notice, re.IGNORECASE)
                   for notice in notices):
                return review("IRT did not confirm the date-only Save")

            # The edited input alone is not proof of persistence. Reopen the
            # same LNI from Inventory without Modify and inspect saved values.
            self._cleanup_tabs(self._opened_tab, self._main_tab)
            if not self.handle_lni_search(lni):
                return review("could not reopen the LNI to verify the saved date")

            def loaded(_driver):
                snapshot = self.read_smd_date_cleanup_snapshot()
                return snapshot if isinstance(snapshot, dict) and snapshot.get("decision_date") else False

            after = WebDriverWait(self.driver, 20).until(loaded)
            if after.get("record_lni") != lni:
                return review("reopened IRT form did not match the requested LNI")
            if self._saved_date_key(after.get("decision_date")) != requested_key:
                return review("the requested Decision Date was not confirmed after reopening")
            if not unchanged(after) or after.get("blocking_dialog"):
                return review("other saved form values differ after reopening; inspect IRT manually")
            return finish(STATUS_DECISION_DATE_UPDATED, f"{before.get('decision_date') or 'blank'} -> {target}; saved and rechecked")
        except Exception as exc:
            if save_attempted:
                status_updates_buffer[row_index] = STATUS_DATE_UPDATE_UNCONFIRMED
            self._raise_if_invalid_session_error(exc, "updating SMD Decision Date only")
            logging.warning("SMD date cleanup could not finish for LNI %s: %s", lni, exc)
            return review("date-only cleanup could not be verified; " + str(exc))

    @staticmethod
    def _saved_date_key(value):
        if isinstance(value, (datetime.date, datetime.datetime)):
            return value.strftime("%Y-%m-%d")
        text = str(value or "").strip()
        for fmt in ("%m-%d-%Y", "%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%Y/%m/%d"):
            try:
                return datetime.datetime.strptime(text, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        return None

    def verify_ready_locked_form(self, row, full_df, *, dar_mode=False, wc_mode=False, metadata=None):
        """Verify a Ready-locked record against this run's intended fields/links."""
        issues = []
        try:
            saved = self.read_ready_locked_form()
            if not isinstance(saved, dict):
                raise ValueError("saved form values unavailable")
            name = str(row.get("FileName", "")).strip()
            counsel = metadata is None and is_counsel(name, dar_mode, wc_mode)
            expected_route = "Archive" if counsel or (
                metadata is not None and (
                    getattr(metadata, "is_excluded", False) or getattr(metadata, "is_true_duplicate", False)
                )
            ) else "Outside Conversion"
            expected_docket = getattr(metadata, "docket_number", None) if metadata is not None else extract_docket_number(name, dar_mode, wc_mode)
            expected_date = getattr(metadata, "decision_date", None) if metadata is not None else None
            if metadata is None:
                if counsel:
                    expected_date = self.find_main_opinion_date_for_counsel(
                        expected_docket, name, dar_mode, wc_mode, full_df=full_df,
                    )
                expected_date = expected_date or self.normalize_mapping_decision_date(row.get("Decision Date")) or self.extract_decision_date_from_filename(name)
            expected_source = getattr(metadata, "source_detail", None) if metadata is not None else resolve_source_detail(row.get("SourceDetail", row.get("Source Detail", "")))

            if saved.get("ready") is not True:
                issues.append("saved Ready to Process state could not be confirmed")
            if not self.dropdown_text_matches(saved.get("route"), expected_route):
                issues.append(f"Route expected {expected_route}, found {saved.get('route') or 'blank/unavailable'}")
            if not getattr(metadata, "is_verified_corrupt", False):
                docket_key = lambda value: re.sub(r"\s+", "", self.normalize_irt_text(value)).upper()
                if not expected_docket:
                    issues.append("expected docket number unavailable")
                elif docket_key(saved.get("docket")) != docket_key(expected_docket):
                    issues.append(f"Docket expected {expected_docket}, found {saved.get('docket') or 'blank/unavailable'}")
                if not self._saved_date_key(expected_date):
                    issues.append("expected decision date unavailable")
                elif self._saved_date_key(saved.get("decision_date")) != self._saved_date_key(expected_date):
                    issues.append(f"Decision Date expected {expected_date}, found {saved.get('decision_date') or 'blank/unavailable'}")
            if expected_source and not self.dropdown_text_matches(saved.get("source_detail"), expected_source):
                issues.append(f"Source Detail expected {expected_source}, found {saved.get('source_detail') or 'blank/unavailable'}")

            lni_pattern = r"\b[A-Z0-9]{4}(?:-[A-Z0-9]{4}){3}-[A-Z0-9]{5}-[A-Z0-9]{2}\b"
            comments = str(saved.get("comments") or "")
            if metadata is None and full_df is not None:
                if counsel:
                    expected_lnis = {
                        str(candidate.get("LNI", "")).strip().upper()
                        for _, candidate in full_df.iterrows()
                        if not is_counsel(candidate.get("FileName", ""), dar_mode, wc_mode)
                        and extract_docket_number(candidate.get("FileName", ""), dar_mode, wc_mode) == expected_docket
                    }
                    actual_lnis = set(re.findall(lni_pattern, comments.upper()))
                    label = "main opinion LNI in Comments"
                else:
                    expected_lnis = set(get_related_counsel_lnis(
                        expected_docket, full_df, recycled_lni=row.get("RecycledCounselLNI"),
                        dar_mode=dar_mode, wc_mode=wc_mode,
                    ))
                    expected_lnis = {lni.upper() for lni in expected_lnis}
                    actual_lnis = set(re.findall(lni_pattern, str(saved.get("related_lnis") or "").upper()))
                    label = "related counsel LNI"
                expected_lnis.discard("")
                expected_lnis.discard("NAN")
                if not expected_lnis:
                    issues.append(f"expected {label} unavailable in mapping")
                elif expected_lnis - actual_lnis:
                    issues.append(f"missing {label}: {', '.join(sorted(expected_lnis - actual_lnis))}")
            elif metadata is None:
                issues.append("mapping unavailable to verify counsel/main LNI links")

            # This is a saved Ready-locked record, not a new exclusion. Do
            # not retroactively require the newly introduced corrupt-file
            # comment. New exclusions still verify that comment before Save.
            generated_comment = None if getattr(metadata, "is_verified_corrupt", False) else getattr(metadata, "comments_text", "")
            for expected_comment in (row.get("Comments"), generated_comment):
                if expected_comment is not None and str(expected_comment).strip().lower() not in {"", "nan", "none"}:
                    compact = lambda value: re.sub(r"\s+", " ", self.normalize_irt_text(value)).strip().casefold()
                    if compact(expected_comment) not in compact(comments):
                        issues.append("required Comments text missing")
        except Exception as exc:
            self._raise_if_invalid_session_error(exc, "verifying Ready-locked IRT form")
            logging.warning("Could not verify Ready-locked record: %s", exc)
            issues.append("saved routing details unavailable; inspect IRT manually")

        if issues:
            status = "MANUAL REVIEW REQUIRED - READY TO PROCESS LOCKED: " + "; ".join(issues)
            logging.warning("LNI %s: %s", row.get("LNI", ""), status)
            return status
        logging.info("LNI %s is Ready-locked and saved routing details match; ALREADY PROCESSED.", row.get("LNI", ""))
        return "ALREADY PROCESSED"

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

    def ensure_related_lni_input_ready(self, timeout=12):
        """Restore Related state after an IRT duplicate dialog re-renders the form."""
        related_xpath = '//*[@id="related"]'
        related_lni_xpath = '//*[@id="relateLNIs"]'

        def controls_are_ready(driver):
            try:
                checkbox = driver.find_element(By.XPATH, related_xpath)
                field = driver.find_element(By.XPATH, related_lni_xpath)
                return (
                    checkbox.is_selected()
                    and field.is_displayed()
                    and field.is_enabled()
                    and field.get_attribute("readonly") != "true"
                )
            except Exception:
                return False

        def click_checkbox(checkbox):
            try:
                checkbox.click()
            except Exception:
                self.driver.execute_script("arguments[0].click();", checkbox)

        try:
            # IRT has been observed to clear Related *after* dismissing the
            # duplicate dialog. Re-arm it once, using a newly located element,
            # rather than waiting against the stale pre-dialog form.
            for attempt in range(1, 3):
                related_checkbox = WebDriverWait(self.driver, timeout).until(
                    EC.presence_of_element_located((By.XPATH, related_xpath))
                )
                if controls_are_ready(self.driver):
                    logging.info("Related LNI controls are enabled and ready.")
                    return True

                if related_checkbox.is_selected():
                    # A checked box with a locked input is IRT's post-dialog
                    # half-state. Toggle it off before selecting it afresh.
                    click_checkbox(related_checkbox)
                    WebDriverWait(self.driver, 3).until(
                        lambda driver: not driver.find_element(By.XPATH, related_xpath).is_selected()
                    )
                    related_checkbox = WebDriverWait(self.driver, timeout).until(
                        EC.presence_of_element_located((By.XPATH, related_xpath))
                    )

                if not related_checkbox.is_selected():
                    click_checkbox(related_checkbox)
                    logging.info("Selected Related (recovery pass %d/2).", attempt)

                # Selecting Related can reopen IRT's duplicate alert. Resolve
                # it, then re-read the replacement controls on the next pass.
                self.handle_any_alert(timeout=2)
                try:
                    WebDriverWait(self.driver, max(2, timeout // 3)).until(controls_are_ready)
                    logging.info("Related LNI controls are enabled and ready.")
                    return True
                except TimeoutException:
                    logging.warning(
                        "Related LNI controls remained locked after recovery pass %d/2; rechecking IRT form.",
                        attempt,
                    )

            logging.warning("Related LNI controls remained locked after both recovery passes.")
            return False
        except Exception as e:
            logging.warning("Related LNI controls did not become ready: %s", e)
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
                        state = self.settle_irt_modify_transition(allow_modify_retry=False)
                        if state == "EDITABLE" and getattr(self, "_last_transition_duplicate_cleared", False) and not getattr(self, "_irt_duplicate_verification_enabled", True):
                            # Process-as-New can reset Related/Route. Let the
                            # caller refill the normal form before Ready/Save.
                            return "DUPLICATE_FORM_RETRY"
            else:
                logging.warning("Ready to Process remains unavailable after clearing pending form dialogs; not treating this as prior processing.")
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
                    logging.info("Duplicate overlay cleared after handling; caller will save the form.")
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
            logging.warning("Ready to Process was not clicked; control availability does not prove prior processing.")
            return "READY_NOT_CLICKABLE"

    def fill_irt_form(self, row, full_df, row_index, file_path, skip_ready_check=False, dar_mode=False, wc_mode=False, mspb_mode=False, mspb_metadata=None, itc_metadata=None, irsplr_metadata=None, ohtax0_metadata=None, mnsutb_metadata=None, mework_metadata=None, mosu00_metadata=None, _duplicate_recovery_attempt=0):
        try:
            file_name = str(row["FileName"]).strip()
            is_counsel_file = is_counsel(file_name, dar_mode, wc_mode)
            lni = str(row["LNI"]).strip()

            if mspb_mode:
                return self.fill_mspb_irt_form(row, row_index, mspb_metadata)
            if itc_metadata:
                context_label = (
                    "FERC" if getattr(itc_metadata, "court", "") == "FDFERC00"
                    else "FCC" if getattr(itc_metadata, "court", "") == "FDFCC000"
                    else "NLRB" if getattr(itc_metadata, "court", "") == "FDNLRB00"
                    else "ITC"
                )
                return self.fill_itc_irt_form(row, row_index, itc_metadata, context_label=context_label)
            if irsplr_metadata:
                return self.fill_irsplr_irt_form(row, row_index, irsplr_metadata)
            if ohtax0_metadata:
                return self.fill_ohtax0_irt_form(row, row_index, ohtax0_metadata)
            if mnsutb_metadata:
                return self.fill_mnsutb_irt_form(row, row_index, mnsutb_metadata)
            if mework_metadata:
                return self.fill_itc_irt_form(row, row_index, mework_metadata, context_label="MEWORK")
            if mosu00_metadata:
                return self.fill_mosu00_table_irt_form(row, row_index, mosu00_metadata)

            def refill_after_duplicate():
                if _duplicate_recovery_attempt >= 1:
                    status = "ERROR: DUPLICATE FORM RECOVERY FAILED"
                    status_updates_buffer[row_index] = status
                    return status
                logging.info("Duplicate notice cleared; refilling routing details and LNI links on the same form before Ready/Save.")
                return self.fill_irt_form(
                    row, full_df, row_index, file_path,
                    skip_ready_check=skip_ready_check, dar_mode=dar_mode, wc_mode=wc_mode,
                    _duplicate_recovery_attempt=_duplicate_recovery_attempt + 1,
                )
            
            # A matched main opinion is the decision-date authority for a
            # counsel record.  Counsel is intentionally processed first, but
            # must carry the date that will later be used by its main opinion.
            manual_decision_raw = row.get("Decision Date")
            decision_date = None

            if is_counsel_file:
                counsel_docket = CaseLawRouter.format_docket_number(None, file_name, dar_mode, wc_mode)
                if counsel_docket:
                    decision_date = self.find_main_opinion_date_for_counsel(
                        counsel_docket,
                        file_name,
                        dar_mode,
                        wc_mode,
                        full_df=full_df,
                    )
                    if decision_date:
                        logging.info(
                            "Using matched Main Opinion decision date for counsel: %s",
                            decision_date,
                        )

            # A row-level mapping date remains authoritative only when there
            # is no matching main opinion (or the row itself is the main).
            if not decision_date:
                decision_date = self.normalize_mapping_decision_date(manual_decision_raw)
                if decision_date:
                    logging.info(f"Using manual Decision Date from mapping sheet: {decision_date}")

            # Next use the relevant filename.  The main-opinion lookup above
            # already ran for counsel, so this is only its local fallback.
            if not decision_date:
                special_decision_date = None
                if is_counsel_file:
                    special_decision_date = self.extract_decision_date_from_filename(file_name)
                else:
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
                        # Main-opinion preparation may decline routing when its
                        # required counsel LNI cannot be attached.  That is a
                        # terminal row outcome, not an interactability retry;
                        # continuing here after the form has been abandoned
                        # previously caused the invalid-session cascade.
                        main_status = self.handle_main_opinion_fields(
                            row, full_df, row_index, file_path, dar_mode, wc_mode
                        )
                        if main_status:
                            return main_status

                    self.handle_any_alert()

                    # Check Comments and Route fields
                    comments_xpath = '//*[@id="comments"]'
                    route_xpath = '//*[@id="route"]'
                    comments_field = self.wait.until(EC.presence_of_element_located((By.XPATH, comments_xpath)))
                    route_field = self.wait.until(EC.presence_of_element_located((By.XPATH, route_xpath)))

                    comments_enabled = comments_field.is_enabled()
                    route_enabled = route_field.is_enabled()

                    # A late duplicate notice can disable Route. This is a
                    # fresh editing session, so neither a locked control nor
                    # an unsaved Ready toggle proves prior processing.
                    if not route_enabled and comments_enabled:
                        state = self.settle_irt_modify_transition(allow_modify_retry=False)
                        if state != "EDITABLE":
                            raise RuntimeError("IRT form controls remained unavailable after clearing duplicate UI")
                        if getattr(self, "_last_transition_duplicate_cleared", False) and not getattr(self, "_irt_duplicate_verification_enabled", True):
                            return refill_after_duplicate()

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
            if overlay_appeared == "DUPLICATE_FORM_RETRY":
                return refill_after_duplicate()
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
                # We entered this path on a fresh editable form. A disabled
                # checkbox (even one changed by an interrupted click) is not
                # evidence of a saved record. Reopen safely on the retry path.
                status = "NON-INTERACTABLE IRT FORM"
                status_updates_buffer[row_index] = status
                return status

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

    def is_route_locked_already_processed(self, context_label="Document"):
        """Return True only for the high-confidence route-locked already-processed state."""
        try:
            comments_field = self.wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="comments"]')))
            route_field = self.wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="route"]')))
            if not route_field.is_enabled() and comments_field.is_enabled():
                logging.info("%s route dropdown is disabled; treating document as ALREADY PROCESSED.", context_label)
                return True
        except Exception as e:
            logging.debug("Could not inspect route-locked already-processed state for %s: %s", context_label, e)
        return False

    def fill_itc_irt_form(self, row, row_index, itc_metadata: ITCMetadata, context_label="ITC"):
        """Fill an IRT form for a single-document mode with ITC-style routing rules."""
        previous_archive_duplicate_mode = self._archive_duplicate_mode
        previous_recovery = getattr(self, "_itc_field_recovery_active", False)
        previous_failure = getattr(self, "_itc_field_failure_reason", "")
        previous_ready_attempted = getattr(self, "_itc_ready_attempted", False)
        self._itc_field_recovery_active = context_label in {"ITC", "NLRB"}
        self._itc_field_failure_reason = ""
        self._itc_ready_attempted = False
        self._archive_duplicate_mode = bool(getattr(itc_metadata, "is_true_duplicate", False))
        try:
            if not itc_metadata:
                logging.warning("Skipping %s row because extracted metadata is missing.", context_label)
                if row_index is not None:
                    status_updates_buffer[row_index] = f"SKIPPED: {context_label} PDF DATA NOT FOUND"
                return f"SKIPPED: {context_label} PDF DATA NOT FOUND"

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

            if self._itc_field_recovery_active and getattr(self, "_verified_duplicate_match", None):
                return self.save_verified_duplicate(row_index)
            if self._itc_field_failure_reason:
                raise IRTFormRecoveryError(self._itc_field_failure_reason)

            if getattr(itc_metadata, "is_excluded", False) and self.is_locked_archive_excluded_form(context_label):
                status_updates_buffer[row_index] = "ALREADY PROCESSED"
                self.driver.close()
                self.driver.switch_to.window(self.driver.window_handles[0])
                return "ALREADY PROCESSED"

            # IRT leaves the route control locked for an already completed
            # document.  Detect that state before Source Detail, Case Name, or
            # Comments are touched; a rerun must be read-only for those rows.
            if self.is_route_locked_already_processed(context_label):
                status_updates_buffer[row_index] = "ALREADY PROCESSED"
                self.driver.close()
                self.driver.switch_to.window(self.driver.window_handles[0])
                return "ALREADY PROCESSED"

            if not self.handle_itc_fields(row, itc_metadata, context_label=context_label):
                if row_index is not None:
                    status_updates_buffer[row_index] = f"SKIPPED: {context_label} FORM FILL ERROR"
                return f"SKIPPED: {context_label} FORM FILL ERROR"

            if self._itc_field_recovery_active and getattr(self, "_verified_duplicate_match", None):
                return self.save_verified_duplicate(row_index)

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
                        logging.info("Route dropdown is disabled - %s document already processed.", context_label)
                        status_updates_buffer[row_index] = "ALREADY PROCESSED"
                        self.driver.close()
                        self.driver.switch_to.window(self.driver.window_handles[0])
                        return "ALREADY PROCESSED"

                if not comments_field.is_enabled() and not route_field.is_enabled():
                    logging.error("%s IRT form is non-interactable.", context_label)
                    status_updates_buffer[row_index] = "NON-INTERACTABLE IRT FORM"
                    self.driver.close()
                    self.driver.switch_to.window(self.driver.window_handles[0])
                    return "NON-INTERACTABLE IRT FORM"
            except Exception:
                logging.error("Could not verify %s form interactability.", context_label)
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
                if route_element.is_enabled() and self._itc_field_recovery_active:
                    if not self.select_dropdown_by_visible_text_or_value('//*[@id="route"]', route_label, "Route"):
                        raise IRTFormRecoveryError("ITC Route selection was not confirmed")
                    if getattr(self, "_verified_duplicate_match", None):
                        return self.save_verified_duplicate(row_index)
                elif route_element.is_enabled():
                    route_element = WebDriverWait(self.driver, 3).until(EC.element_to_be_clickable((By.XPATH, '//*[@id="route"]')))
                    route_element.click()
                    self.handle_any_alert()
                    dropdown = Select(route_element)
                    dropdown.select_by_visible_text(route_label)
                    self.handle_any_alert()
                    logging.info("Selected %s route: %s", context_label, route_label)
                    self.driver.execute_script("document.getElementById('route').dispatchEvent(new Event('change'))")
                    self.handle_any_alert()
                elif route_label == "Archive" and getattr(itc_metadata, "is_excluded", False):
                    selected_route = self.get_selected_dropdown_text(route_element)
                    if self.dropdown_text_matches(selected_route, "Archive"):
                        logging.info("Confirmed disabled %s route dropdown is Archive for Excluded source detail.", context_label)
                    else:
                        logging.warning(
                            "Disabled %s route dropdown is not Archive after Source Detail Excluded; selected route is: %s",
                            context_label,
                            selected_route or "(blank)",
                        )
                        if not self.set_dropdown_by_visible_text(route_element, "Archive"):
                            raise Exception(f"Disabled {context_label} route dropdown could not be set to Archive")
                        selected_route = self.get_selected_dropdown_text(route_element)
                        if not self.dropdown_text_matches(selected_route, "Archive"):
                            raise Exception(f"Disabled ITC route dropdown did not confirm Archive; selected route is {selected_route!r}")
                        logging.info("Set and confirmed disabled %s route dropdown is Archive for Excluded source detail.", context_label)
                else:
                    raise Exception(f"{context_label} route dropdown is disabled before route selection")
            except Exception as e:
                logging.error(f"Failed to select {context_label} route before Ready to Process: {e}")
                status_updates_buffer[row_index] = "ROUTE ERROR"
                self.driver.close()
                self.driver.switch_to.window(self.driver.window_handles[0])
                return "ROUTE ERROR"

            self._itc_ready_attempted = True
            overlay_appeared = self.click_ready_checkbox_and_check_overlay(False)
            self.handle_any_alert()
            if self._itc_field_recovery_active and getattr(self, "_verified_duplicate_match", None):
                return self.save_verified_duplicate(row_index)
            if overlay_appeared == "ROUTE_ERROR":
                self.driver.close()
                self.driver.switch_to.window(self.driver.window_handles[0])
                return "ROUTE ERROR"
            if overlay_appeared == "ALERT_HANDLED":
                self.driver.close()
                self.driver.switch_to.window(self.driver.window_handles[0])
                return "ALERT_HANDLED"
            if overlay_appeared == "READY_NOT_CLICKABLE":
                if self._itc_field_recovery_active:
                    status_updates_buffer[row_index] = f"ERROR: {context_label} READY TO PROCESS UNCONFIRMED"
                    return status_updates_buffer[row_index]
                logging.info("Ready to Process checkbox was not clickable for %s; marking document as ALREADY PROCESSED.", context_label)
                status_updates_buffer[row_index] = "ALREADY PROCESSED"
                self.driver.close()
                self.driver.switch_to.window(self.driver.window_handles[0])
                return "ALREADY PROCESSED"

            if self._itc_field_recovery_active and not self.verify_itc_values_before_save(row, itc_metadata):
                status_updates_buffer[row_index] = f"ERROR: {context_label} FORM VALUES UNCONFIRMED"
                return status_updates_buffer[row_index]
            return self.handle_routing_and_save(False, row_index, skip_route_and_ready=True)
        except Exception as e:
            logging.error("Error filling %s IRT form: %s", context_label, e)
            if row_index is not None:
                status_updates_buffer[row_index] = "ERROR"
            return "ERROR"
        finally:
            self._archive_duplicate_mode = previous_archive_duplicate_mode
            self._itc_field_recovery_active = previous_recovery
            self._itc_field_failure_reason = previous_failure
            self._itc_ready_attempted = previous_ready_attempted

    def fill_irsplr_irt_form(self, row, row_index, irsplr_metadata: IRSPLRMetadata):
        """Fill an IRT form for IRSPLR using metadata extracted from the linked PDF."""
        try:
            if not irsplr_metadata:
                return self.flag_irsplr_document_review(
                    row, row_index, "UNREADABLE OR UNAVAILABLE - verified PDF metadata is missing; supply a working PDF",
                )

            verified_corrupt = bool(getattr(irsplr_metadata, "is_verified_corrupt", False))
            if (getattr(irsplr_metadata, "is_text_fallback", False) or not irsplr_metadata.has_text_content) and not verified_corrupt:
                return self.flag_irsplr_document_review(
                    row, row_index, "UNREADABLE - a usable source PDF was not verified; supply a working PDF",
                )

            file_name = str(row.get("FileName", "")).strip()
            if not verified_corrupt:
                self.prepare_common_fields(
                    file_name,
                    decision_date=irsplr_metadata.decision_date,
                    dar_mode=False,
                    wc_mode=False,
                    docket_override=irsplr_metadata.docket_number,
                    court=irsplr_metadata.court,
                )
            else:
                logging.info("Verified corrupt IRSPLR source: preserving existing docket/date/court; applying exclusion only.")
            self.handle_any_alert()

            if not verified_corrupt and getattr(irsplr_metadata, "is_excluded", False) and self.is_locked_archive_excluded_form("IRSPLR"):
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
                if verified_corrupt:
                    # Do not claim the required comment was saved merely
                    # because this fresh exclusion form is non-interactable.
                    status_updates_buffer[row_index] = "NON-INTERACTABLE IRT FORM"
                    return "NON-INTERACTABLE IRT FORM"
                logging.info("Ready to Process checkbox was not clickable for IRSPLR; marking document as ALREADY PROCESSED.")
                status_updates_buffer[row_index] = "ALREADY PROCESSED"
                self.driver.close()
                self.driver.switch_to.window(self.driver.window_handles[0])
                return "ALREADY PROCESSED"

            if verified_corrupt:
                configured = self.read_ready_locked_form()
                if not isinstance(configured, dict) or not (
                    configured.get("ready") is True
                    and self.dropdown_text_matches(configured.get("source_detail"), "Excluded")
                    and self.dropdown_text_matches(configured.get("route"), "Archive")
                    and "Exclude - Corrupt File" in str(configured.get("comments") or "")
                ):
                    status_updates_buffer[row_index] = "ERROR: CORRUPT FILE EXCLUSION NOT CONFIRMED"
                    logging.error("Corrupt exclusion source/route/comment/Ready state was not confirmed; not saving.")
                    return "ERROR: CORRUPT FILE EXCLUSION NOT CONFIRMED"
            result = self.handle_routing_and_save(False, row_index, skip_route_and_ready=True)
            if verified_corrupt and result == "ALREADY PROCESSED":
                status_updates_buffer[row_index] = "ERROR: CORRUPT FILE EXCLUSION SAVE UNCONFIRMED"
                return "ERROR: CORRUPT FILE EXCLUSION SAVE UNCONFIRMED"
            return result
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

    def fill_mosu00_table_irt_form(self, row, row_index, mosu00_metadata: MOSU00Metadata):
        """Fill an IRT form for MOSU00 table-case routing."""
        try:
            if not mosu00_metadata:
                logging.warning("Skipping MOSU00 table row because extracted metadata is missing.")
                if row_index is not None:
                    status_updates_buffer[row_index] = "SKIPPED: MOSU00 HTML DATA NOT FOUND"
                return "SKIPPED: MOSU00 HTML DATA NOT FOUND"

            file_name = str(row.get("FileName", "")).strip()
            self.prepare_common_fields(
                file_name,
                decision_date=mosu00_metadata.decision_date,
                dar_mode=False,
                wc_mode=False,
                docket_override=mosu00_metadata.docket_number,
                court=None,
            )
            self.handle_any_alert()

            if not self.handle_mosu00_table_fields(row, mosu00_metadata):
                if self.is_route_locked_already_processed("MOSU00"):
                    status_updates_buffer[row_index] = "ALREADY PROCESSED"
                    self.driver.close()
                    self.driver.switch_to.window(self.driver.window_handles[0])
                    return "ALREADY PROCESSED"
                if row_index is not None:
                    status_updates_buffer[row_index] = "SKIPPED: MOSU00 TABLE FORM FILL ERROR"
                return "SKIPPED: MOSU00 TABLE FORM FILL ERROR"

            try:
                comments_field = self.wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="comments"]')))
                route_field = self.wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="route"]')))

                if not route_field.is_enabled() and comments_field.is_enabled():
                    logging.info("Route dropdown is disabled - MOSU00 table document already processed.")
                    status_updates_buffer[row_index] = "ALREADY PROCESSED"
                    self.driver.close()
                    self.driver.switch_to.window(self.driver.window_handles[0])
                    return "ALREADY PROCESSED"

                if not comments_field.is_enabled() and not route_field.is_enabled():
                    logging.error("MOSU00 table IRT form is non-interactable.")
                    status_updates_buffer[row_index] = "NON-INTERACTABLE IRT FORM"
                    self.driver.close()
                    self.driver.switch_to.window(self.driver.window_handles[0])
                    return "NON-INTERACTABLE IRT FORM"
            except Exception:
                logging.error("Could not verify MOSU00 table form interactability.")
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
                    logging.info("Selected MOSU00 table route: Outside Conversion")
                    self.driver.execute_script("document.getElementById('route').dispatchEvent(new Event('change'))")
                    self.handle_any_alert()
                else:
                    raise Exception("MOSU00 table route dropdown is disabled before route selection")
            except Exception as e:
                logging.error(f"Failed to select MOSU00 route before Ready to Process: {e}")
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
                logging.info("Ready to Process checkbox was not clickable for MOSU00; marking document as ALREADY PROCESSED.")
                status_updates_buffer[row_index] = "ALREADY PROCESSED"
                self.driver.close()
                self.driver.switch_to.window(self.driver.window_handles[0])
                return "ALREADY PROCESSED"

            return self.handle_routing_and_save(False, row_index, skip_route_and_ready=True)
        except Exception as e:
            logging.error(f"Error in fill_mosu00_table_irt_form(): {e}")
            if row_index is not None:
                status_updates_buffer[row_index] = "ERROR"
            return "ERROR"

    def handle_mosu00_table_fields(self, row, mosu00_metadata: MOSU00Metadata):
        try:
            case_name_xpath = '//*[@id="caseName"]'
            try:
                field = self.wait.until(EC.presence_of_element_located((By.XPATH, case_name_xpath)))
                existing_case_name = self.wait_for_existing_field_text(case_name_xpath, timeout=6)
                if existing_case_name:
                    logging.info(f"MOSU00 Case Name already present; leaving unchanged: {existing_case_name[:120]}")
                else:
                    if field.is_enabled() and field.get_attribute("readonly") != "true":
                        field.clear()
                        field.send_keys("RE")
                        logging.info("MOSU00 Case Name was blank; set to RE.")
                    else:
                        logging.info("Skipped MOSU00 Case Name because it is not interactable.")
            except Exception:
                logging.error("Error setting MOSU00 case name")

            if not self.select_source_detail(mosu00_metadata.source_detail):
                return False

            comment_parts = []
            if mosu00_metadata.comments_text:
                comment_parts.append(mosu00_metadata.comments_text)

            additional_comments = str(row.get("Comments", "")).strip()
            if additional_comments and additional_comments.lower() != "nan":
                comment_parts.append(additional_comments)

            if comment_parts and not self.append_comments(comment_parts, "MOSU00"):
                return False

            return self.configure_mosu00_table_case(mosu00_metadata)
        except Exception as e:
            logging.error(f"Error handling MOSU00 table fields: {e}")
            return False

    def configure_mosu00_table_case(self, mosu00_metadata: MOSU00Metadata, _save_recovery=False):
        """Populate and save the MOSU00 child-docket dialog.

        Some IRT versions close the modal when focus is tabbed away from the
        final child-docket field.  The final field is therefore committed with
        blur/change events instead of TAB.  If an older IRT build still closes
        the modal, reopen it once and rebuild the unsaved child-docket list.
        """
        child_dockets = [str(docket).strip() for docket in (mosu00_metadata.child_dockets or ()) if str(docket).strip()]
        if not child_dockets:
            logging.error("MOSU00 table metadata does not contain child docket numbers.")
            return False

        try:
            table_checkbox = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.XPATH, '//*[@id="tableCases"]'))
            )
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", table_checkbox)
            if not table_checkbox.is_selected():
                try:
                    table_checkbox.click()
                except Exception:
                    self.driver.execute_script("arguments[0].click();", table_checkbox)
                logging.info("Enabled MOSU00 Table Case checkbox.")
            else:
                logging.info("MOSU00 Table Case checkbox was already enabled.")

            if not self.click_mosu00_table_create_button():
                return False
            logging.info("Opened MOSU00 Table Case Entry form.")

            self.wait_for_mosu00_table_case_form()

            if not self.clear_and_fill_input('//*[@id="tableCaseNums"]', str(len(child_dockets))):
                logging.error("Could not fill MOSU00 child LNI count.")
                return False

            if not self.click_mosu00_table_submit_button():
                return False
            logging.info("Submitted MOSU00 child LNI count: %d", len(child_dockets))
            self.wait_for_mosu00_table_case_spinner(timeout=20)

            for index, docket in enumerate(child_dockets):
                field_xpath = f'//*[@id="tcDocketNum{index}"]'
                field = WebDriverWait(self.driver, 30).until(
                    EC.presence_of_element_located((By.XPATH, field_xpath))
                )
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", field)
                WebDriverWait(self.driver, 10).until(lambda d, item=field: item.is_enabled() and item.get_attribute("readonly") != "true")
                field.clear()
                field.send_keys(docket)
                logging.info("Filled MOSU00 child docket %d/%d: %s", index + 1, len(child_dockets), docket)
                if index < len(child_dockets) - 1:
                    field.send_keys(Keys.TAB)
                else:
                    # Tabbing away from the last input has been observed to
                    # dismiss the entire dialog before its Save button can be
                    # reached.  Commit the value without moving focus outside
                    # the dialog instead.
                    self.driver.execute_script(
                        """
                        arguments[0].dispatchEvent(new Event('change', {bubbles: true}));
                        arguments[0].dispatchEvent(new Event('blur', {bubbles: true}));
                        arguments[0].blur();
                        """,
                        field,
                    )
                    logging.info("Committed final MOSU00 child docket without tabbing out of the dialog.")
                self.wait_for_mosu00_table_case_spinner(timeout=20)

            if not self.is_mosu00_table_case_form_visible():
                if not _save_recovery:
                    logging.warning(
                        "MOSU00 Table Case Entry dialog disappeared before Save; reopening it once and rebuilding the child docket list."
                    )
                    return self.configure_mosu00_table_case(mosu00_metadata, _save_recovery=True)
                logging.error("MOSU00 Table Case Entry dialog disappeared again before Save; stopping safely.")
                return False

            if not self.click_mosu00_table_case_save_button():
                return False

            self.accept_mosu00_table_case_save_confirmation(expected_count=len(child_dockets))
            self.wait_for_mosu00_table_case_spinner(timeout=25)
            logging.info("MOSU00 table child docket form saved successfully.")
            return True
        except Exception as e:
            logging.error(f"Error configuring MOSU00 table child LNIs: {e}")
            return False

    def click_mosu00_table_create_button(self):
        return self.click_mosu00_table_dialog_button(
            '//*[@id="Create"]',
            "Create/Edit",
            "MOSU00 Table Case Entry Create/Edit",
        )

    def click_mosu00_table_submit_button(self):
        return self.click_mosu00_table_dialog_button(
            '//*[@id="addTableCaseNumber"]',
            "Submit",
            "MOSU00 child LNI count Submit",
        )

    def click_mosu00_table_dialog_button(self, xpath, button_name, log_label):
        """Click MOSU00 table-case buttons even when the IRT fieldset intercepts native clicks."""
        try:
            button = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.XPATH, xpath))
            )
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'center'});", button)
            self.wait_for_mosu00_table_case_spinner(timeout=8)

            if not button.is_enabled():
                logging.error("%s button is present but disabled.", log_label)
                return False

            click_attempts = (
                ("native", lambda item: item.click()),
                ("action", lambda item: ActionChains(self.driver).move_to_element(item).pause(0.2).click().perform()),
                ("javascript", lambda item: self.driver.execute_script("arguments[0].click();", item)),
            )
            for method_name, click_method in click_attempts:
                try:
                    click_method(button)
                    logging.info("Clicked %s button using %s click.", log_label, method_name)
                    return True
                except Exception as exc:
                    logging.info("%s %s click failed: %s", log_label, method_name, exc)

            logging.error("Could not click %s button after native/action/javascript attempts.", log_label)
            return False
        except Exception as e:
            logging.error("Could not locate MOSU00 table %s button: %s", button_name, e)
            return False

    def wait_for_mosu00_table_case_form(self):
        header_xpath = "//*[contains(normalize-space(.), 'Choose Number of Child LNIs')]"
        WebDriverWait(self.driver, 20).until(EC.presence_of_element_located((By.XPATH, header_xpath)))
        logging.info("MOSU00 Table Case Entry form is visible.")

    def is_mosu00_table_case_form_visible(self):
        """Return whether the active MOSU00 table-case modal is still visible."""
        try:
            return bool(self.driver.execute_script(
                """
                const visible = (element) => {
                    if (!element) return false;
                    const style = window.getComputedStyle(element);
                    const rect = element.getBoundingClientRect();
                    return style.display !== 'none' && style.visibility !== 'hidden'
                        && style.opacity !== '0' && rect.width > 0 && rect.height > 0;
                };
                const tableInputVisible = Array.from(document.querySelectorAll(
                    '#tableCaseNums, [id^="tcDocketNum"]'
                )).some(visible);
                if (tableInputVisible) return true;
                return Array.from(document.querySelectorAll('.ui-dialog, [role="dialog"]')).some((dialog) => {
                    if (!visible(dialog)) return false;
                    const text = (dialog.innerText || dialog.textContent || '').toLowerCase();
                    return text.includes('choose number of child lnis')
                        || Boolean(dialog.querySelector('#tableCaseNums, [id^="tcDocketNum"]'));
                });
                """
            ))
        except Exception as exc:
            logging.info("Could not verify MOSU00 Table Case Entry dialog visibility: %s", exc)
            return False

    def wait_for_mosu00_table_case_spinner(self, timeout=15):
        try:
            WebDriverWait(self.driver, timeout).until(
                lambda d: d.execute_script(
                    """
                    const selectors = [
                        '.blockUI', '.ui-progressbar',
                        '.throbber', '.spinner', '.loading', '.ajax-loader',
                        '#throbber', '#loading'
                    ];
                    const visible = selectors.some((selector) => {
                        return Array.from(document.querySelectorAll(selector)).some((el) => {
                            const style = window.getComputedStyle(el);
                            const rect = el.getBoundingClientRect();
                            return style.display !== 'none'
                                && style.visibility !== 'hidden'
                                && style.opacity !== '0'
                                && rect.width > 0
                                && rect.height > 0;
                        });
                    });
                    const jqueryBusy = window.jQuery ? window.jQuery.active > 0 : false;
                    return !visible && !jqueryBusy;
                    """
                )
            )
            time.sleep(0.4)
            return True
        except Exception:
            logging.info("MOSU00 table form spinner/loading wait timed out; proceeding with field checks.")
            return False

    def click_mosu00_table_case_save_button(self):
        self.clear_mosu00_duplicate_dialog_before_table_save()
        self.wait_for_mosu00_table_case_spinner(timeout=8)
        if not self.is_mosu00_table_case_form_visible():
            logging.error("MOSU00 Table Case Entry dialog is not visible before Save; not attempting an unrelated page click.")
            return False
        if self.click_mosu00_table_save_with_dom_fallback():
            return True

        uppercase = "'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'"
        save_xpaths = [
            # Current IRT MOSU00 table-case dialog.  This control is rendered
            # outside the dialog body, so the DOM-context fallback cannot see
            # it when the dialog itself has no visible button pane.
            "/html/body/div[17]/div[3]/div/button[1]/span",
            "/html/body/div[17]/div[3]/div/button[1]",
            (
                "//div[contains(@class, 'ui-dialog') and .//*[contains(normalize-space(.), 'Choose Number of Child LNIs')]]"
                f"//button[.//span[translate(normalize-space(.), {uppercase})='SAVE'] or translate(normalize-space(.), {uppercase})='SAVE']"
            ),
            f"//span[contains(@class, 'ui-button-text') and translate(normalize-space(.), {uppercase})='SAVE']/ancestor::button[1]",
            f"//span[contains(@class, 'ui-button-text') and translate(normalize-space(.), {uppercase})='SAVE']",
            f"//button[.//span[translate(normalize-space(.), {uppercase})='SAVE'] or translate(normalize-space(.), {uppercase})='SAVE']",
            "/html/body/div[16]/div[11]/div/button[1]",
            "/html/body/div[16]/div[11]/div/button[1]/span",
            "/html/body/div[17]/div[11]/div/button[1]",
            "/html/body/div[17]/div[11]/div/button[1]/span",
        ]

        for xpath in save_xpaths:
            try:
                button = WebDriverWait(self.driver, 3).until(EC.element_to_be_clickable((By.XPATH, xpath)))
                button.click()
                logging.info("Clicked MOSU00 Table Case Entry Save button.")
                return True
            except Exception:
                continue

        self.log_mosu00_table_dialog_diagnostics()
        logging.error("Could not click MOSU00 Table Case Entry Save button.")
        return False

    def clear_mosu00_duplicate_dialog_before_table_save(self):
        """Clear duplicate dialogs that can appear after MOSU00 child docket entry."""
        try:
            duplicate_visible = self.driver.execute_script(
                """
                const isVisible = (el) => {
                    if (!el) return false;
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return style.display !== 'none'
                        && style.visibility !== 'hidden'
                        && style.opacity !== '0'
                        && rect.width > 0
                        && rect.height > 0;
                };
                const dialogs = Array.from(document.querySelectorAll('.ui-dialog, [role="dialog"]')).filter(isVisible);
                return dialogs.some((dialog) => /duplicate/i.test(dialog.innerText || dialog.textContent || ''))
                    || Array.from(document.querySelectorAll('#processDuplicate')).some((el) => {
                        const dialog = el.closest ? el.closest('.ui-dialog') : null;
                        return dialog && isVisible(dialog);
                    });
                """
            )
            if duplicate_visible:
                logging.info("MOSU00 table Save is blocked by a duplicate dialog; processing it as New before saving child LNIs.")
                self.handle_duplicate_overlay(archive_as_duplicate=False)
        except Exception as e:
            logging.info("MOSU00 duplicate-dialog pre-save check failed; continuing to Save attempts: %s", e)

    def click_mosu00_table_save_with_dom_fallback(self):
        """Find and click the Save button in the active MOSU00 table dialog by DOM context."""
        try:
            result = self.driver.execute_script(
                """
                const isVisible = (el) => {
                    if (!el) return false;
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return style.display !== 'none'
                        && style.visibility !== 'hidden'
                        && style.opacity !== '0'
                        && rect.width > 0
                        && rect.height > 0;
                };
                const labelFor = (el) => {
                    return (el.innerText || el.textContent || el.value || el.getAttribute('aria-label') || '').trim();
                };
                const dialogs = Array.from(document.querySelectorAll('.ui-dialog, [role="dialog"]')).filter(isVisible);
                const dialog = dialogs.find((item) => {
                    const text = (item.innerText || item.textContent || '').toLowerCase();
                    return text.includes('choose number of child lnis')
                        || item.querySelector('#tableCaseNums')
                        || item.querySelector('[id^="tcDocketNum"]');
                }) || dialogs[dialogs.length - 1] || document;

                const candidates = Array.from(dialog.querySelectorAll(
                    'button, input[type="button"], input[type="submit"], a, span.ui-button-text'
                )).filter(isVisible);

                const saveTextCandidate = candidates.find((item) => /\\bsave\\b/i.test(labelFor(item)));
                let target = saveTextCandidate || null;
                if (target && target.tagName && target.tagName.toLowerCase() === 'span') {
                    target = target.closest('button, a') || target;
                }

                if (!target) {
                    const paneButton = Array.from(dialog.querySelectorAll('.ui-dialog-buttonpane button')).find(isVisible);
                    target = paneButton || null;
                }

                if (!target) {
                    return {
                        clicked: false,
                        reason: 'No visible Save candidate found',
                        dialogText: (dialog.innerText || dialog.textContent || '').trim().slice(0, 500),
                        buttons: candidates.map(labelFor).filter(Boolean).slice(0, 20)
                    };
                }

                target.scrollIntoView({block: 'center', inline: 'center'});
                target.click();
                return {
                    clicked: true,
                    label: labelFor(target),
                    tag: target.tagName,
                    id: target.id || '',
                    className: target.className || ''
                };
                """
            )
            if isinstance(result, dict) and result.get("clicked"):
                logging.info("Clicked MOSU00 Table Case Entry Save button using DOM fallback: %s", result)
                return True
            logging.info("MOSU00 Table Case Entry Save DOM fallback did not click: %s", result)
            return False
        except Exception as e:
            logging.info("MOSU00 Table Case Entry Save DOM fallback failed: %s", e)
            return False

    def log_mosu00_table_dialog_diagnostics(self):
        try:
            diagnostics = self.driver.execute_script(
                """
                const isVisible = (el) => {
                    if (!el) return false;
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return style.display !== 'none'
                        && style.visibility !== 'hidden'
                        && style.opacity !== '0'
                        && rect.width > 0
                        && rect.height > 0;
                };
                return Array.from(document.querySelectorAll('.ui-dialog, [role="dialog"]'))
                    .filter(isVisible)
                    .map((dialog) => ({
                        id: dialog.id || '',
                        className: dialog.className || '',
                        text: (dialog.innerText || dialog.textContent || '').trim().slice(0, 700),
                        buttons: Array.from(dialog.querySelectorAll('button, input[type="button"], input[type="submit"], a, span.ui-button-text'))
                            .filter(isVisible)
                            .map((button) => ({
                                tag: button.tagName,
                                id: button.id || '',
                                className: button.className || '',
                                text: (button.innerText || button.textContent || button.value || button.getAttribute('aria-label') || '').trim()
                            }))
                    }))
                    .slice(0, 5);
                """
            )
            logging.warning("MOSU00 table dialog diagnostics before save failure: %s", diagnostics)
        except Exception as e:
            logging.warning("Could not collect MOSU00 table dialog diagnostics: %s", e)

    def accept_mosu00_table_case_save_confirmation(self, expected_count=None):
        try:
            alert = WebDriverWait(self.driver, 6).until(EC.alert_is_present())
            alert_text = alert.text.strip()
            alert.accept()
            logging.info("Accepted MOSU00 table save confirmation alert: %s", alert_text)
            return True
        except TimeoutException:
            pass
        except Exception as e:
            logging.info("MOSU00 table save browser alert check failed: %s", e)

        uppercase = "'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'"
        ok_xpaths = [
            (
                "//div[contains(@class, 'ui-dialog') and "
                "contains(translate(normalize-space(.), 'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), 'SAVE')]"
                f"//button[.//span[translate(normalize-space(.), {uppercase})='OK'] or translate(normalize-space(.), {uppercase})='OK']"
            ),
            f"//button[.//span[translate(normalize-space(.), {uppercase})='OK'] or translate(normalize-space(.), {uppercase})='OK']",
        ]

        for xpath in ok_xpaths:
            try:
                ok_button = WebDriverWait(self.driver, 6).until(EC.element_to_be_clickable((By.XPATH, xpath)))
                ok_button.click()
                logging.info("Accepted MOSU00 table save confirmation popup.")
                return True
            except Exception:
                continue

        logging.info("No MOSU00 table save confirmation popup was visible.")
        return False

    def handle_itc_fields(self, row, itc_metadata: ITCMetadata, context_label="ITC"):
        try:
            case_name_xpath = '//*[@id="caseName"]'
            try:
                field = self.wait.until(EC.presence_of_element_located((By.XPATH, case_name_xpath)))
                existing_case_name = self.wait_for_existing_field_text(case_name_xpath, timeout=6)
                if existing_case_name:
                    logging.info(f"{context_label} Case Name already present; leaving unchanged: {existing_case_name[:120]}")
                else:
                    if field.is_enabled() and field.get_attribute("readonly") != "true":
                        field.clear()
                        field.send_keys("RE")
                        logging.info("%s Case Name was blank; set to RE.", context_label)
                    else:
                        logging.info("Skipped %s Case Name because it is not interactable.", context_label)
            except Exception:
                logging.error("Error setting %s case name", context_label)

            if not self.select_source_detail(itc_metadata.source_detail):
                return False
            if getattr(self, "_itc_field_recovery_active", False) and getattr(self, "_verified_duplicate_match", None):
                return True

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
                if not self.append_comments(comment_parts, context_label):
                    return False

            return True
        except Exception as e:
            logging.error("Error handling %s fields: %s", context_label, e)
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
                recover_itc = bool(getattr(self, "_itc_field_recovery_active", False))
                if recover_itc and getattr(self, "_verified_duplicate_match", None):
                    return True
                comments_field = self.wait_for_itc_editable_control('//*[@id="comments"]') if recover_itc else WebDriverWait(self.driver, 10).until(
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
                    if (not re.search(r"(?<!\w)" + re.escape(part) + r"(?!\w)", self.normalize_irt_text(existing_text), re.I)
                        if recover_itc else part not in existing_text)
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
                if recover_itc:
                    comments_field.send_keys(Keys.TAB)
                    self.handle_any_alert(timeout=1)
                    if getattr(self, "_verified_duplicate_match", None):
                        return True
                    fresh = self.wait_for_itc_editable_control('//*[@id="comments"]')
                    actual = self.normalize_irt_text(fresh.get_attribute("value") or "").strip()
                    if actual != updated_text:
                        raise IRTFormRecoveryError("ITC Comments did not retain the requested text after alert handling")
                logging.info(f"Updated {context_label} comments field: {updated_text}")
                return True
            except UnexpectedAlertPresentException as exc:
                self.handle_any_alert(timeout=3, initial_alert_text=getattr(exc, "alert_text", None))
            except IRTFormRecoveryError:
                raise
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

    def handle_any_alert(self, timeout=3, archive_as_duplicate=None, initial_alert_text=None):
        handled_alert, duplicate_seen = self.accept_pending_alerts(initial_timeout=timeout)
        duplicate_seen = duplicate_seen or "duplicate document" in str(initial_alert_text or "").lower()
        if duplicate_seen:
            if getattr(self, "_itc_field_recovery_active", False):
                state = self.settle_irt_modify_transition(initial_alerts=["This is a duplicate document"])
                if state != "EDITABLE" and not (state == "READY_LOCKED" and getattr(self, "_itc_ready_attempted", False)):
                    self._itc_field_failure_reason = "ITC duplicate workflow did not restore a confirmed editable form"
                    raise IRTFormRecoveryError(self._itc_field_failure_reason)
            else:
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
        if getattr(self, "_itc_duplicate_review_reason", ""):
            status_updates_buffer[row_index] = "MANUAL REVIEW REQUIRED - ITC " + self._itc_duplicate_review_reason
            return status_updates_buffer[row_index]
        if getattr(self, "_itc_field_recovery_active", False) and getattr(self, "_itc_field_failure_reason", ""):
            status_updates_buffer[row_index] = "ERROR: ITC DUPLICATE FORM RECOVERY FAILED"
            return status_updates_buffer[row_index]
        if getattr(self, "_irsplr_duplicate_review_reason", ""):
            # Some legacy field/alert helpers catch dialog exceptions. This
            # final gate must still prevent an unresolved comparison being saved.
            return self.flag_irsplr_document_review(
                getattr(self, "_active_duplicate_row", {"LNI": getattr(self, "_active_duplicate_lni", "")}),
                row_index, self._irsplr_duplicate_review_reason,
            )
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

    def process_rows(self, full_df, file_path, update_progress, dar_mode=False, wc_mode=False, mspb_mode=False, itc_mode=False, irsplr_mode=False, ohtax0_mode=False, mnsutb_mode=False, mework_mode=False, mosu00_mode=False, fcc_mode=False, ferc_mode=False, nlrb_mode=False):
        counsel_df, main_df = None, None
        try:
            self.full_df = full_df
            self.configure_irt_duplicate_verification(
                mspb_mode=mspb_mode,
                itc_mode=itc_mode,
                irsplr_mode=irsplr_mode,
                ohtax0_mode=ohtax0_mode,
                mnsutb_mode=mnsutb_mode,
                mework_mode=mework_mode,
                mosu00_mode=mosu00_mode,
                fcc_mode=fcc_mode,
                ferc_mode=ferc_mode,
                nlrb_mode=nlrb_mode,
            )

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
                itc_count, itc_duration = self.process_batch(main_df, full_df, file_path, update_progress, "itc", dar_mode, wc_mode, itc_mode=True)
                if self.set_status:
                    self.set_status("ITC Batch Processed")
                if itc_count > 0:
                    total_mins = int(itc_duration // 60)
                    total_secs = int(itc_duration % 60)
                    logging.info("[ITC PROCESSING SUMMARY] ITC: %d LNIs successfully routed in %dm %ds", itc_count, total_mins, total_secs)
                return counsel_df, main_df

            if fcc_mode:
                counsel_df = full_df.iloc[0:0].copy()
                main_df = full_df.copy()
                logging.info("FCC Count: %d", len(main_df))
                if self.set_status:
                    self.set_status("FCC Batch Started")
                fcc_count, fcc_duration = self.process_batch(
                    main_df, full_df, file_path, update_progress, "fcc", dar_mode, wc_mode, fcc_mode=True
                )
                if self.set_status:
                    self.set_status("FCC Batch Processed")
                if fcc_count > 0:
                    logging.info("[FCC PROCESSING SUMMARY] FCC: %d LNIs successfully routed in %dm %ds", fcc_count, int(fcc_duration // 60), int(fcc_duration % 60))
                return counsel_df, main_df

            if ferc_mode:
                counsel_df = full_df.iloc[0:0].copy()
                main_df = full_df.copy()
                logging.info("FERC Count: %d", len(main_df))
                if self.set_status:
                    self.set_status("FERC Batch Started")
                ferc_count, ferc_duration = self.process_batch(
                    main_df, full_df, file_path, update_progress, "ferc", dar_mode, wc_mode, ferc_mode=True
                )
                if self.set_status:
                    self.set_status("FERC Batch Processed")
                if ferc_count > 0:
                    logging.info("[FERC PROCESSING SUMMARY] FERC: %d LNIs successfully routed in %dm %ds", ferc_count, int(ferc_duration // 60), int(ferc_duration % 60))
                return counsel_df, main_df

            if nlrb_mode:
                counsel_df = full_df.iloc[0:0].copy()
                main_df = full_df.copy()
                logging.info("NLRB Count: %d", len(main_df))
                if self.set_status:
                    self.set_status("NLRB Batch Started")
                nlrb_count, nlrb_duration = self.process_batch(
                    main_df, full_df, file_path, update_progress, "nlrb", dar_mode, wc_mode, nlrb_mode=True
                )
                if self.set_status:
                    self.set_status("NLRB Batch Processed")
                if nlrb_count > 0:
                    logging.info("[NLRB PROCESSING SUMMARY] NLRB: %d LNIs successfully routed in %dm %ds", nlrb_count, int(nlrb_duration // 60), int(nlrb_duration % 60))
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

            if mework_mode:
                counsel_df = full_df.iloc[0:0].copy()
                main_df = full_df.copy()
                logging.info("MEWORK Count: %d", len(main_df))
                logging.info("=== Starting MEWORK Batch ===")
                if self.set_status:
                    self.set_status("MEWORK Batch Started")
                mework_count, mework_duration = self.process_batch(
                    main_df,
                    full_df,
                    file_path,
                    update_progress,
                    "mework",
                    dar_mode,
                    wc_mode,
                    mework_mode=True,
                )
                if self.set_status:
                    self.set_status("MEWORK Batch Processed")
                if mework_count > 0:
                    total_mins = int(mework_duration // 60)
                    total_secs = int(mework_duration % 60)
                    logging.info(
                        "[MEWORK PROCESSING SUMMARY] MEWORK: %d LNIs successfully routed in %dm %ds",
                        mework_count,
                        total_mins,
                        total_secs,
                    )
                return counsel_df, main_df

            if mosu00_mode:
                logging.info("=== Starting MOSU00 Counsel Batch ===")
                if self.set_status:
                    self.set_status("Counsel Batch Started")
                counsel_count, counsel_duration = self.process_batch(
                    counsel_df,
                    full_df,
                    file_path,
                    update_progress,
                    "counsel",
                    dar_mode,
                    wc_mode,
                    mosu00_mode=True,
                )

                main_df, deferred_main_rows = defer_main_rows_with_failed_counsel(
                    main_df,
                    full_df,
                    dar_mode=dar_mode,
                    wc_mode=wc_mode,
                )
                if deferred_main_rows:
                    logging.warning(
                        "Deferred %d MOSU00 main opinion row(s) because required counsel did not finish cleanly.",
                        len(deferred_main_rows),
                    )

                if self.set_status:
                    self.set_status("Counsel Batch Processed")

                try:
                    while len(self.driver.window_handles) > 1:
                        self.driver.switch_to.window(self.driver.window_handles[-1])
                        self.driver.close()
                        self.driver.switch_to.window(self.driver.window_handles[0])
                    logging.info("Cleaned up all leftover popup windows before MOSU00 main/table batch.")
                except Exception:
                    logging.warning("Failed to clean up extra windows before MOSU00 main/table batch.")

                logging.info("=== Starting MOSU00 Main/Table Batch ===")
                if self.set_status:
                    self.set_status("MOSU00 Batch Started")
                mosu00_count, mosu00_duration = self.process_batch(
                    main_df,
                    full_df,
                    file_path,
                    update_progress,
                    "mosu00",
                    dar_mode,
                    wc_mode,
                    mosu00_mode=True,
                )
                if self.set_status:
                    self.set_status("MOSU00 Batch Processed")

                total_count = counsel_count + mosu00_count
                total_time = counsel_duration + mosu00_duration
                if total_count > 0:
                    overall_avg = total_time / total_count
                    overall_est_per_hour = int(3600 / overall_avg) if overall_avg else 0
                    logging.info("[MOSU00 PROCESSING SUMMARY] TOTAL: %d LNIs successfully routed in %dm %ds", total_count, int(total_time // 60), int(total_time % 60))
                    logging.info("    - Counsel: %d LNIs in %dm %ds", counsel_count, int(counsel_duration // 60), int(counsel_duration % 60))
                    logging.info("    - Main/Table: %d LNIs in %dm %ds", mosu00_count, int(mosu00_duration // 60), int(mosu00_duration % 60))
                    logging.info("    - Overall Avg: %.1fs/LNI -> Est. %d LNIs/hour", overall_avg, overall_est_per_hour)
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

    def configure_irt_duplicate_verification(
        self,
        *,
        mspb_mode=False,
        itc_mode=False,
        irsplr_mode=False,
        ohtax0_mode=False,
        mnsutb_mode=False,
        mework_mode=False,
        mosu00_mode=False,
        fcc_mode=False,
        ferc_mode=False,
        nlrb_mode=False,
    ):
        """Set duplicate-content verification policy for the active router mode.

        SADM and DARA only clear IRT's duplicate UI and continue as new.  This
        avoids investigating the expected counsel/main-opinion alerts.  The
        specialized routers retain their content-verification safeguards.
        """
        self._irt_duplicate_verification_enabled = any((
            mspb_mode,
            itc_mode,
            irsplr_mode,
            ohtax0_mode,
            mnsutb_mode,
            mework_mode,
            mosu00_mode,
            fcc_mode,
            ferc_mode,
            nlrb_mode,
        ))
        self._irsplr_duplicate_pdf_validation = bool(irsplr_mode)
        self._irsplr_browser_first = bool(irsplr_mode)
        self._itc_duplicate_verification = bool(itc_mode)
        self._nlrb_form_recovery = bool(nlrb_mode)
        policy = "content verification enabled" if self._irt_duplicate_verification_enabled else "process-as-new only"
        logging.info("IRT duplicate policy for this run: %s", policy)
        return self._irt_duplicate_verification_enabled

    def should_archive_duplicate(self, archive_as_duplicate=None):
        if archive_as_duplicate is None:
            return bool(getattr(self, "_archive_duplicate_mode", False))
        return bool(archive_as_duplicate)

    def _visible_duplicate_candidate_lnis(self):
        """Return the original LNIs listed in IRT's visible duplicate dialog."""
        pattern = re.compile(r"\b[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-\d{5}-\d{2}\b")
        candidates = []
        try:
            dialogs = self.driver.find_elements(
                By.XPATH,
                "//div[contains(@class, 'ui-dialog') or @role='dialog']",
            )
            for dialog in dialogs:
                if not dialog.is_displayed():
                    continue
                dialog_text = dialog.text or ""
                if "duplicate" not in dialog_text.lower() and not dialog.find_elements(By.ID, "processDuplicate"):
                    continue
                for lni in pattern.findall(dialog_text.upper()):
                    if lni not in candidates:
                        candidates.append(lni)
        except Exception as e:
            logging.warning("Could not read LNI candidates from IRT duplicate dialog: %s", e)
        return candidates

    def _fetch_irt_pdf_in_current_browser(self, href, *, allow_non_pdf=False):
        """Fetch an IRT document through the authenticated browser session."""
        absolute_url = urljoin(self.driver.current_url, href)
        try:
            result = self.driver.execute_async_script(
                """
                const url = arguments[0];
                const done = arguments[arguments.length - 1];
                fetch(url, {credentials: 'same-origin'})
                  .then(async response => {
                    const bytes = new Uint8Array(await response.arrayBuffer());
                    let binary = '';
                    const size = 0x8000;
                    for (let offset = 0; offset < bytes.length; offset += size) {
                      binary += String.fromCharCode(...bytes.subarray(offset, offset + size));
                    }
                    done({ok: response.ok, status: response.status, body: btoa(binary)});
                  })
                  .catch(error => done({ok: false, error: String(error)}));
                """,
                absolute_url,
            )
            if result and result.get("ok") and result.get("body"):
                content = base64.b64decode(result["body"])
                if content and (allow_non_pdf or self.is_pdf_bytes(content)):
                    return content
            logging.warning(
                "IRT document fetch did not return a PDF (status=%s) for %s.",
                (result or {}).get("status"),
                absolute_url,
            )
        except Exception as e:
            logging.warning("Could not fetch IRT document through the active browser: %s", e)
        return None

    def _result_document_href(self):
        """Find the File Name document link for the currently searched LNI."""
        selectors = (
            "#searchTable a[href*='openDocumentInBrowser']",
            "#searchTable a[href*='OpenDocumentInBrowser']",
            "#searchTable a[href$='.pdf']",
            "a[href*='openDocumentInBrowser']",
            "a[href*='OpenDocumentInBrowser']",
        )
        for selector in selectors:
            try:
                for link in self.driver.find_elements(By.CSS_SELECTOR, selector):
                    href = link.get_attribute("href")
                    if href:
                        return href
            except Exception:
                continue
        return None

    def _document_profile_for_irt_lni(self, lni):
        """Search an LNI in the main IRT tab and build its PDF/OCR profile."""
        normalized_lni = str(lni or "").strip().upper()
        if not normalized_lni:
            return None
        verify_pdf = bool(getattr(self, "_irsplr_duplicate_pdf_validation", False))
        browser_first = verify_pdf and bool(getattr(self, "_irsplr_browser_first", False))
        if normalized_lni in self._duplicate_profile_cache:
            cached = self._duplicate_profile_cache[normalized_lni]
            if not verify_pdf or (getattr(cached, "is_verified_pdf", False) and (
                not browser_first or getattr(cached, "is_browser_verified", False)
            )):
                return cached

        form_tab = self.driver.current_window_handle
        main_tab = getattr(self, "_main_tab", None)
        if not main_tab or main_tab not in self.driver.window_handles:
            logging.warning("Cannot verify IRT duplicate %s because the Search Inventory tab is unavailable.", normalized_lni)
            return None
        try:
            self.driver.switch_to.window(main_tab)
            if not self.search_lni(normalized_lni):
                return None
            href = self._result_document_href()
            if not href:
                logging.warning("No document link was found while verifying duplicate LNI %s.", normalized_lni)
                return None
            if browser_first:
                try:
                    self.inspect_irsplr_duplicate_in_browser(href)
                except IRSPLRCorruptDocument as exc:
                    # Never download/OCR a failed existing source to decide
                    # whether it can disqualify a valid replacement.
                    return IRTDocumentProfile(normalized_lni, "", "", is_verified_corrupt=True, validation_reason=str(exc))
            pdf_bytes = self._fetch_irt_pdf_in_current_browser(href, allow_non_pdf=True) if verify_pdf else self._fetch_irt_pdf_in_current_browser(href)
            if not pdf_bytes:
                return None
            profile = build_document_profile(normalized_lni, pdf_bytes, verify_pdf=True) if verify_pdf else build_document_profile(normalized_lni, pdf_bytes)
            if browser_first:
                profile = replace(profile, is_browser_verified=True)
            if not profile.is_verified_corrupt:
                self._duplicate_profile_cache[normalized_lni] = profile
            logging.info("Captured IRT document content for duplicate comparison: %s", normalized_lni)
            return profile
        except Exception as e:
            self._raise_if_invalid_session_error(e, "capturing an IRT duplicate candidate")
            logging.warning("Could not capture IRT duplicate candidate %s: %s", normalized_lni, e)
            return None
        finally:
            if form_tab in self.driver.window_handles:
                self.driver.switch_to.window(form_tab)

    def verify_irt_duplicate_overlay(self):
        """Confirm whether an IRT duplicate candidate is the same document.

        This is deliberately invoked only after IRT itself raises a duplicate
        alert. PLR validates each source before comparing content. A confirmed
        corrupt original cannot cause a valid replacement to be archived.
        """
        verify_pdf = bool(getattr(self, "_irsplr_duplicate_pdf_validation", False))
        verify_itc = bool(getattr(self, "_itc_duplicate_verification", False))

        def require_review(reason):
            if verify_pdf:
                self._irsplr_duplicate_review_reason = "DUPLICATE COMPARISON - " + reason
                logging.warning("IRSPLR %s", self._irsplr_duplicate_review_reason)
            if verify_itc:
                self._itc_duplicate_review_reason = "DUPLICATE COMPARISON - " + reason
                logging.warning("ITC %s", self._itc_duplicate_review_reason)
            return None

        current_lni = str(getattr(self, "_active_duplicate_lni", "") or "").strip().upper()
        candidate_lnis = self._visible_duplicate_candidate_lnis()
        if (verify_pdf or verify_itc) and current_lni and not candidate_lnis:
            try:
                def candidates_after_alerts(_driver):
                    self.accept_pending_alerts(initial_timeout=0.1, followup_timeout=0.2, max_alerts=5)
                    return self._visible_duplicate_candidate_lnis()
                candidate_lnis = WebDriverWait(self.driver, 10).until(candidates_after_alerts)
            except TimeoutException:
                pass
        if not current_lni or not candidate_lnis:
            logging.warning("IRT duplicate dialog has no usable current/candidate LNI; treating it as unconfirmed.")
            return require_review("the current or existing candidate LNI could not be confirmed; check the duplicate dialog")

        current_profile = self._document_profile_for_irt_lni(current_lni)
        if not current_profile:
            logging.warning("Could not read current IRT document %s for duplicate comparison.", current_lni)
            return require_review("the incoming PDF could not be validated; supply a readable source PDF")
        if current_profile.is_verified_corrupt:
            if getattr(self, "_active_irsplr_corrupt_exclusion", False):
                return None  # The incoming row is already being excluded, never normally routed.
            return require_review("the incoming source is corrupt; it cannot be routed as a valid replacement")
        if verify_pdf and not current_profile.is_verified_pdf:
            return require_review("the incoming source has no verified PDF integrity result")

        unresolved_lnis = []
        inspected_candidates = 0
        for candidate_lni in candidate_lnis:
            if candidate_lni == current_lni:
                continue
            inspected_candidates += 1
            candidate_profile = self._document_profile_for_irt_lni(candidate_lni)
            if not candidate_profile:
                unresolved_lnis.append(candidate_lni)
                continue
            if candidate_profile.is_verified_corrupt:
                logging.info(
                    "Existing duplicate candidate %s is verified corrupt (%s); it cannot disqualify valid incoming LNI %s. Continuing checks against any other candidates.",
                    candidate_lni, candidate_profile.validation_reason, current_lni,
                )
                continue
            if verify_pdf and not candidate_profile.is_verified_pdf:
                unresolved_lnis.append(candidate_lni)
                continue
            match = compare_document_profiles(current_profile, candidate_profile)
            logging.info(
                "IRT duplicate comparison %s vs %s: %s (%.3f)",
                current_lni,
                candidate_lni,
                match.method,
                match.similarity,
            )
            if match.is_match:
                return match
            if (verify_pdf or verify_itc) and match.method in {"text unavailable", "insufficient extracted text"}:
                unresolved_lnis.append(candidate_lni)
        if (verify_pdf or verify_itc) and (unresolved_lnis or not inspected_candidates):
            return require_review(
                "existing candidate(s) could not be validated/compared: " + ", ".join(unresolved_lnis or candidate_lnis)
                + "; unavailable/OCR failures are not proof of corruption"
            )
        return None

    def duplicate_status_label(self):
        match = getattr(self, "_verified_duplicate_match", None)
        return f"DUPLICATE OF {match.original_lni}" if match else ""

    def save_verified_duplicate(self, row_index):
        """Finish the minimal Archive workflow after IRT accepted a true duplicate."""
        match = getattr(self, "_verified_duplicate_match", None)
        if not match:
            return "ERROR: DUPLICATE VERIFICATION MISSING"
        try:
            route = self.wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="route"]')))
            selected_route = self.get_selected_dropdown_text(route)
            if not self.dropdown_text_matches(selected_route, "Archive"):
                logging.error("IRT did not set Archive after confirming duplicate %s; selected route=%r", match.original_lni, selected_route)
                return "ERROR: DUPLICATE ARCHIVE ROUTE NOT SET"
            ready_result = self.click_ready_checkbox_and_check_overlay(False)
            if ready_result == "READY_NOT_CLICKABLE":
                return "ALREADY PROCESSED"
            save_status = self.handle_routing_and_save(False, row_index, skip_route_and_ready=True)
            if save_status == "DONE":
                return self.duplicate_status_label()
            return save_status
        except Exception as e:
            logging.error("Could not save verified duplicate %s: %s", match.original_lni, e)
            return "ERROR: DUPLICATE SAVE FAILED"

    def handle_duplicate_overlay(self, archive_as_duplicate=None):
        """Choose Archive only after comparing IRT's current and candidate PDFs."""
        if getattr(self, "_irsplr_duplicate_pdf_validation", False) or getattr(self, "_itc_duplicate_verification", False):
            self.accept_pending_alerts(initial_timeout=0.5, followup_timeout=1, max_alerts=5)
        if getattr(self, "_active_irsplr_corrupt_exclusion", False):
            verified_match = None
            logging.info("Incoming PLR has a verified corrupt-file exclusion; duplicate UI cannot turn it into normal routing.")
        elif getattr(self, "_irt_duplicate_verification_enabled", True):
            verified_match = self.verify_irt_duplicate_overlay()
        else:
            verified_match = None
            logging.info(
                "IRT duplicate content verification is disabled for this SADM/DARA run; processing the alert as a new document."
            )
        if getattr(self, "_irsplr_duplicate_review_reason", ""):
            return False
        if getattr(self, "_itc_duplicate_review_reason", ""):
            return False
        archive_as_duplicate = verified_match is not None
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
                if verified_match:
                    if not self.append_comments([f"Dup of {verified_match.original_lni}"], "verified duplicate"):
                        logging.error("Archive duplicate was selected but its required comment could not be added.")
                        return False
                    self._verified_duplicate_match = verified_match
                    logging.info("Confirmed and archived duplicate of %s via %s.", verified_match.original_lni, verified_match.method)
                else:
                    logging.info("IRT duplicate was not confirmed by document content; continuing as a new document.")
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
                    return True

            except TimeoutException:
                logging.info("No alert found when checking for duplicate popup.")

            # Handle overlay if present
            if not self.handle_duplicate_overlay(archive_as_duplicate=archive_as_duplicate):
                logging.info("No duplicate overlay popup detected after alert.")
                return False
            return True

        except Exception as e:
            logging.error(f"Failed to handle Duplicate LNI popup: {e}")
            # Try to accept any remaining alert as a fallback
            try:
                alert = self.driver.switch_to.alert
                alert.accept()
                logging.info("Accepted fallback alert after duplicate handling error.")
            except:
                pass
            return False

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
        if getattr(self, "_itc_field_recovery_active", False):
            return self.select_itc_dropdown_with_recovery(xpath, selection, field_name)
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

    def wait_for_itc_editable_control(self, xpath, timeout=10):
        """Ignore hidden duplicate IDs and re-find controls after IRT replaces them."""
        def usable(driver):
            for field in driver.find_elements(By.XPATH, xpath):
                if field.is_displayed() and field.is_enabled() and field.get_attribute("readonly") not in ("true", "readonly"):
                    return field
            return False
        return WebDriverWait(self.driver, timeout).until(usable)

    def select_itc_dropdown_with_recovery(self, xpath, selection, field_name):
        for attempt in range(1, 4):
            try:
                self.handle_any_alert(timeout=0.5)
                if getattr(self, "_verified_duplicate_match", None):
                    return True
                field = self.wait_for_itc_editable_control(xpath)
                if self.dropdown_text_matches(self.get_selected_dropdown_text(field), selection) or self.dropdown_text_matches(field.get_attribute("value"), selection):
                    return True
                dropdown = Select(field)
                try:
                    dropdown.select_by_visible_text(selection)
                except NoSuchElementException:
                    dropdown.select_by_value(selection)
                # Selenium's native option click fires change itself. A second
                # synthetic change can generate another duplicate warning.
                self.handle_any_alert(timeout=1)
                if getattr(self, "_verified_duplicate_match", None):
                    return True
                fresh = self.wait_for_itc_editable_control(xpath)
                if self.dropdown_text_matches(self.get_selected_dropdown_text(fresh), selection) or self.dropdown_text_matches(fresh.get_attribute("value"), selection):
                    logging.info("%s selected and verified: %s", field_name, selection)
                    return True
                raise IRTFormRecoveryError(f"{field_name} did not retain {selection!r}")
            except UnexpectedAlertPresentException as exc:
                self.handle_any_alert(timeout=1, initial_alert_text=getattr(exc, "alert_text", None))
            except IRTFormRecoveryError as exc:
                if getattr(self, "_itc_field_failure_reason", ""):
                    raise
                logging.warning("%s verification attempt %d/3 failed: %s", field_name, attempt, exc)
            except Exception as exc:
                self._raise_if_invalid_session_error(exc, f"selecting ITC {field_name}")
                logging.warning("Could not select ITC %s on attempt %d/3: %s", field_name, attempt, exc)
        logging.error("Could not select and verify ITC %s: %s", field_name, selection)
        return False

    def verify_itc_values_before_save(self, row, metadata):
        """A resolved popup must not turn lost/reset form values into a saved DONE."""
        if getattr(self, "_itc_field_failure_reason", ""):
            return False
        try:
            saved = self.read_ready_locked_form()
            docket_key = lambda value: re.sub(r"\s+", "", self.normalize_irt_text(value)).upper()
            expected_route = "Archive" if (getattr(metadata, "is_excluded", False) or getattr(metadata, "is_true_duplicate", False)) else "Outside Conversion"
            checks = {
                "Docket Number": docket_key(saved.get("docket")) == docket_key(metadata.docket_number),
                "Decision Date": self._saved_date_key(saved.get("decision_date")) == self._saved_date_key(metadata.decision_date),
                "Source Detail": self.dropdown_text_matches(saved.get("source_detail"), resolve_source_detail(metadata.source_detail)),
                "Route": self.dropdown_text_matches(saved.get("route"), expected_route),
                "Ready to Process": saved.get("ready") is True,
            }
            comments = self.normalize_irt_text(saved.get("comments") or "")
            for expected in (metadata.comments_text, row.get("Comments", "")):
                if str(expected or "").strip().lower() in {"", "nan", "none"}:
                    continue
                checks["Comments"] = checks.get("Comments", True) and all(
                    re.search(r"(?<!\w)" + re.escape(part.strip()) + r"(?!\w)", comments, re.I)
                    for part in self.normalize_irt_text(expected).split(";") if part.strip()
                )
            failed = [label for label, valid in checks.items() if not valid]
            if failed:
                logging.error("ITC values not confirmed before Save: %s", ", ".join(failed))
                return False
            return True
        except Exception as exc:
            self._raise_if_invalid_session_error(exc, "verifying ITC fields before Save")
            logging.error("Could not confirm ITC form values before Save: %s", exc)
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

    @staticmethod
    def normalize_mapping_decision_date(value):
        """Normalize Mapping Data decision dates without inventing a fallback."""
        if value is None or str(value).strip().lower() in {"", "nan", "nat", "none"}:
            return None
        if isinstance(value, (datetime.date, datetime.datetime)):
            return value.strftime("%m-%d-%Y")
        text = str(value).strip()
        date_key = CaseLawRouter._saved_date_key(text)
        if date_key:
            return datetime.datetime.strptime(date_key, "%Y-%m-%d").strftime("%m-%d-%Y")
        return text

    def find_main_opinion_date_for_counsel(self, counsel_docket, counsel_file_name, dar_mode=False, wc_mode=False, full_df=None):
        """Find the matched main opinion's mapping/filename date for a counsel document."""
        try:
            dataframe = full_df if full_df is not None else getattr(self, "full_df", None)
            if dataframe is not None:
                for _, row in dataframe.iterrows():
                    main_file_name = str(row.get("FileName", "")).strip()
                    if not is_counsel(main_file_name, dar_mode, wc_mode):
                        main_docket = CaseLawRouter.format_docket_number(None, main_file_name, dar_mode, wc_mode)
                        if main_docket and main_docket == counsel_docket:
                            mapped_date = self.normalize_mapping_decision_date(row.get("Decision Date"))
                            if mapped_date:
                                logging.info(
                                    "Found Main Opinion mapping decision date %s for counsel docket %s",
                                    mapped_date,
                                    counsel_docket,
                                )
                                return mapped_date
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

        # IRT can reset Related while dismissing a duplicate dialog.  Do not
        # attempt counsel attachment until the replacement controls are live.
        if not self.ensure_related_lni_input_ready():
            logging.error("Related checkbox or Related LNI field was not ready after duplicate handling.")
            if row_index is not None:
                status_updates_buffer[row_index] = "RELATED LNI FIELD LOCKED"
            return "RELATED LNI FIELD LOCKED"

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
            # The caller owns IRT-tab cleanup.  Closing it here and then
            # continuing the caller's form checks creates an invalid browser
            # session/no-such-window cascade.
            return current_status

        # Check if both Comments and Route are not interactable
        try:
            comments_field = self.wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="comments"]')))
            route_element = self.wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="route"]')))

            if not comments_field.is_enabled() and not route_element.is_enabled():
                logging.error("Both Comments and Route dropdown are non-interactable. Skipping Main Opinion.")
                status_updates_buffer[row_index] = "Non-interactable IRT Form"
                return "Non-interactable IRT Form"

        except Exception as e:
            logging.error(f"Error checking Comments/Route interactability: {e}")
            status_updates_buffer[row_index] = "Non-interactable IRT Form"
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
                for attempt in range(1, 3):
                    try:
                        if not self.clear_and_fill_input('//*[@id="relateLNIs"]', lni):
                            if row_index is not None:
                                status_updates_buffer[row_index] = "RELATED LNI FIELD LOCKED"
                            logging.warning(f"Related LNI input was not interactable for {lni}.")
                            return False

                        self.click_add_related_lni_button(lni)

                        # Wait up to 5 minutes for the LNI to appear in the list box.
                        def lni_in_listbox(driver):
                            related_lni_box = driver.find_element(By.XPATH, '//*[@id="relatedLni"]')
                            updated_lnis = [x.strip() for x in related_lni_box.text.split('\n') if x.strip()]
                            return lni in updated_lnis

                        self.long_wait.until(lni_in_listbox)
                        logging.info(f"Related Counsel LNI {lni} added successfully.")
                        attached_any = True
                        success = True
                        break
                    except Exception as e:
                        if "already exists" in str(e).lower():
                            logging.warning(f"Related Counsel LNI {lni} already attached. Skipping.")
                            logging.info(f"{lni} already exists according to alert. Skipping further attempts.")
                            success = True
                            break

                        is_timeout = isinstance(e, TimeoutException) or "timeout" in str(e).lower()
                        logging.warning(
                            "Failed to add Related Counsel LNI %s on attempt %d/2: %s",
                            lni, attempt, e,
                        )
                        if is_timeout:
                            docket_number = CaseLawRouter.format_docket_number(None, row["FileName"], dar_mode, wc_mode) if "FileName" in row else "?"
                            msg = f"Oops! Related Counsel LNI {lni} for Docket Number {docket_number} did not attach after 5 minutes. Skipping this Main Opinion. Retry again later."
                            logging.warning(msg)
                            if self.show_error:
                                self.show_error(msg)
                            if row_index is not None:
                                status_updates_buffer[row_index] = "RELATED LNI TIMEOUT"
                            return False
                        if attempt == 1:
                            time.sleep(0.75)
                        elif row_index is not None:
                            status_updates_buffer[row_index] = "RELATED LNI ATTACH FAILED"
                if not success:
                    logging.error(f"Failed to attach LNI {lni} after two click attempts.")
                    return False

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
            logging.exception(f"Error handling related LNIs for docket {main_docket if 'main_docket' in locals() else '?'}: {e}")
            if row_index is not None:
                status_updates_buffer[row_index] = "RELATED LNI ERROR"
            return False  # Return False to indicate failure
        return True  # Return True if at least one LNI was attached

    def click_add_related_lni_button(self, lni):
        """Click Add Related using browser-safe fallbacks and retain the failure reason."""
        button = WebDriverWait(self.driver, 10).until(
            EC.presence_of_element_located((By.XPATH, '//*[@id="AddRelated"]'))
        )
        self.driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center', inline: 'center'});", button
        )
        if not button.is_enabled():
            raise RuntimeError(f"Add Related button was disabled for {lni}")

        failures = []
        for method_name, click_method in (
            ("native", lambda: button.click()),
            ("action", lambda: ActionChains(self.driver).move_to_element(button).pause(0.15).click().perform()),
            ("javascript", lambda: self.driver.execute_script("arguments[0].click();", button)),
        ):
            try:
                click_method()
                logging.info("Clicked Add Related for %s using %s click.", lni, method_name)
                return
            except Exception as exc:
                failures.append(f"{method_name}: {exc}")

        raise RuntimeError(f"Could not click Add Related for {lni} ({'; '.join(failures)})")

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

