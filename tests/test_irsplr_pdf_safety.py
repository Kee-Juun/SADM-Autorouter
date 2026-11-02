import unittest
import json
import shutil
import subprocess
from io import BytesIO
from unittest.mock import Mock, call, patch

import pandas as pd
from pypdf import PdfWriter
from selenium.common.exceptions import TimeoutException

from core.irsplr_extractor import (
    IRSPLRCorruptDocument,
    IRSPLRDocumentReviewRequired,
    IRSPLRMetadata,
    build_irsplr_unreadable_fallback_metadata,
    parse_irsplr_pdf_bytes,
    validate_irsplr_pdf_bytes,
)
from core.rerun_status import is_manual_review_status, rerun_status_for, summarize_statuses_for_rows
from core.smducar_config import error_log_entries, mspb_metadata_buffer, status_updates_buffer
from core.smducar_router import CaseLawRouter


def valid_pdf_bytes():
    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.write(output)
    return output.getvalue()


class IRSPLRPdfValidationTests(unittest.TestCase):
    def test_bitmap_mislabeled_as_pdf_is_rejected_before_ocr(self):
        with patch("core.irsplr_extractor.extract_text_from_pdf_bytes") as extract:
            with self.assertRaisesRegex(IRSPLRCorruptDocument, "not a PDF"):
                parse_irsplr_pdf_bytes(b"BM\xd2\x1d\x1c" + b"bitmap bytes", filename_hint="mc.202642012_20261016.pdf")
        extract.assert_not_called()

    def test_html_error_or_empty_download_is_not_sent_to_ocr(self):
        for payload in (b"", b"<html>Failed to load PDF document.</html>", b"\x89PNG\r\n", b"\xff\xd8\xffimage"):
            with self.subTest(payload=payload), patch("core.irsplr_extractor.extract_text_from_pdf_bytes") as extract:
                with self.assertRaises(IRSPLRDocumentReviewRequired):
                    parse_irsplr_pdf_bytes(payload)
                extract.assert_not_called()

    def test_truncated_pdf_is_rejected_before_tolerant_text_extraction(self):
        payload = valid_pdf_bytes().rsplit(b"%%EOF", 1)[0]
        with patch("core.irsplr_extractor.extract_text_from_pdf_bytes") as extract:
            with self.assertRaisesRegex(IRSPLRDocumentReviewRequired, "TRUNCATED"):
                parse_irsplr_pdf_bytes(payload)
        extract.assert_not_called()

    def test_fake_header_and_eof_do_not_pass_structural_validation(self):
        with self.assertRaisesRegex(IRSPLRDocumentReviewRequired, "structural validation"):
            validate_irsplr_pdf_bytes(b"%PDF-1.7\ngarbage\n%%EOF\n")

    def test_valid_image_only_pdf_can_still_use_ocr(self):
        with patch("core.irsplr_extractor.extract_text_from_pdf_bytes", side_effect=["", "ocr text"]) as extract, \
                patch("core.irsplr_extractor.parse_irsplr_document_text", side_effect=[None, "parsed"]):
            payload = valid_pdf_bytes()
            self.assertEqual(parse_irsplr_pdf_bytes(payload), "parsed")
        self.assertEqual(extract.call_args_list, [call(payload, use_ocr_fallback=False), call(payload, force_ocr=True)])

    def test_valid_pdf_with_no_metadata_is_not_itself_labeled_corrupt(self):
        with patch("core.irsplr_extractor.extract_text_from_pdf_bytes", return_value=""):
            self.assertIsNone(parse_irsplr_pdf_bytes(valid_pdf_bytes()))

    def test_zero_page_or_password_protected_pdf_is_not_processed_as_normal(self):
        for protected in (False, True):
            with self.subTest(protected=protected):
                output = BytesIO()
                writer = PdfWriter()
                if protected:
                    writer.add_blank_page(width=612, height=792)
                    writer.encrypt("secret")
                writer.write(output)
                with self.assertRaises(IRSPLRDocumentReviewRequired):
                    validate_irsplr_pdf_bytes(output.getvalue())


class IRSPLRRoutingSafetyTests(unittest.TestCase):
    ROW = {"FileName": "mc.202642012_20261016.pdf", "CourtCode": "FDPLR000", "LNI": "6KTW-5733-RRMW-12HM-00000-00", "Status": ""}

    def setUp(self):
        status_updates_buffer.clear()
        mspb_metadata_buffer.clear()
        error_log_entries.clear()
        self.router = CaseLawRouter.__new__(CaseLawRouter)
        self.router.driver = Mock(current_window_handle="search", window_handles=["search"])
        self.router.driver.execute_cdp_cmd.return_value = {"nodes": []}
        self.router._irsplr_unreadable_pdf_signatures = set()
        self.router.prepare_common_fields = Mock()
        self.router.handle_routing_and_save = Mock()
        self.router.attempt_open_modify = Mock()
        self.router._cleanup_tabs = Mock()
        self.metadata = IRSPLRMetadata("FDPLR000", "202642012", "07-10-2026", "Letter", has_text_content=True)

    def tearDown(self):
        status_updates_buffer.clear()
        mspb_metadata_buffer.clear()
        error_log_entries.clear()

    def test_visible_viewer_error_is_detected(self):
        self.router.driver.execute_script.return_value = "Failed to load PDF document."
        self.assertEqual(self.router.read_irsplr_pdf_viewer_error(), "Failed to load PDF document.")

    def test_dom_script_finds_shadow_error_but_ignores_hidden_dialog(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node is needed to execute the PDF viewer DOM checker")
        self.router.driver.execute_script.return_value = ""
        self.router.read_irsplr_pdf_viewer_error()
        script = self.router.driver.execute_script.call_args.args[0]
        harness = """
            const scan = new Function('document', 'getComputedStyle', SCRIPT);
            function check(hidden, text, tag = 'VIEWER-ERROR-DIALOG') {
                const document = {querySelectorAll: () => [host]};
                const host = {
                    innerText: '', hidden, tagName: tag, getClientRects: () => [{}],
                    getAttribute: () => null, getRootNode: () => document,
                };
                const shadow = {host, querySelectorAll: () => [message]};
                const message = {
                    innerText: text, hidden: false, getClientRects: () => [{}],
                    getAttribute: () => null, getRootNode: () => shadow,
                };
                host.shadowRoot = shadow;
                return scan(document, () => ({display: 'block', visibility: 'visible', opacity: '1'}));
            }
            process.stdout.write(JSON.stringify([
                check(false, 'Failed to load PDF document.'),
                check(true, 'Failed to load PDF document.'),
                check(false, 'PDF loaded normally'),
                check(false, 'Failed to load PDF document.pdf', 'VIEWER-TOOLBAR'),
            ]));
        """.replace("SCRIPT", json.dumps(script))
        result = subprocess.run([node, "-e", harness], capture_output=True, text=True, timeout=10, check=True)
        self.assertEqual(json.loads(result.stdout), ["Failed to load PDF document.", "", "", ""])

    def test_accessible_error_text_in_dialog_children_is_detected(self):
        self.router.driver.execute_script.return_value = ""
        self.router.driver.execute_cdp_cmd.return_value = {"nodes": [
            {"nodeId": "1", "role": {"value": "dialog"}, "name": {"value": "Error"}, "childIds": ["2"]},
            {"nodeId": "2", "role": {"value": "StaticText"}, "name": {"value": "Failed to load PDF document."}},
        ]}
        self.assertEqual(self.router.read_irsplr_pdf_viewer_error(), "Failed to load PDF document.")

    def test_hidden_error_and_ordinary_document_text_are_not_viewer_errors(self):
        self.router.driver.execute_script.return_value = ""
        self.router.driver.execute_cdp_cmd.return_value = {"nodes": [
            {"nodeId": "1", "ignored": True, "role": {"value": "dialog"}, "name": {"value": "Failed to load PDF document."}},
            {"nodeId": "2", "role": {"value": "StaticText"}, "name": {"value": "The taxpayer reported Failed to load PDF document."}},
        ]}
        self.assertEqual(self.router.read_irsplr_pdf_viewer_error(), "")

    def test_error_in_cross_origin_viewer_frame_is_detected(self):
        self.router.driver.execute_script.return_value = ""

        def cdp(method, params):
            if method == "Page.getFrameTree":
                return {"frameTree": {"frame": {"id": "outer"}, "childFrames": [{"frame": {"id": "pdf"}}]}}
            if params.get("frameId") == "pdf":
                return {"nodes": [{"nodeId": "1", "role": {"value": "alertdialog"}, "name": {"value": "Failed to load PDF document."}}]}
            return {"nodes": []}

        self.router.driver.execute_cdp_cmd.side_effect = cdp
        self.assertEqual(self.router.read_irsplr_pdf_viewer_error(), "Failed to load PDF document.")

    def configure_pdf_reader(self):
        self.router.wait_for_open_tab_load_state = Mock()
        self.router.wait_for_irsplr_downloaded_metadata = Mock(return_value=None)
        self.router.read_irsplr_pdf_viewer_error = Mock(return_value="")
        self.router.get_opened_pdf_bytes_from_browser_network = Mock(return_value=None)
        self.router.read_open_pdf_accessibility_text = Mock()
        self.router.copy_open_pdf_tab_text = Mock()
        self.router.read_open_pdf_tab_text = Mock()
        self.router.log_mspb_pdf_tab_diagnostics = Mock()

    def test_viewer_error_with_valid_download_is_review_not_corruption(self):
        self.configure_pdf_reader()
        self.router.read_irsplr_pdf_viewer_error.return_value = "Failed to load PDF document."
        self.router.wait_for_irsplr_downloaded_metadata.return_value = self.metadata
        with self.assertRaisesRegex(IRSPLRDocumentReviewRequired, "PDF VALIDATED") as raised:
            self.router.wait_for_irsplr_metadata_from_open_tab(timeout=1)
        self.assertNotIsInstance(raised.exception, IRSPLRCorruptDocument)
        self.router.wait_for_irsplr_downloaded_metadata.assert_called_once()
        self.router.prepare_common_fields.assert_not_called()

    def test_failed_download_does_not_use_stale_clipboard_or_inventory_text(self):
        self.configure_pdf_reader()
        clock = [100.0]

        def sleep(seconds):
            clock[0] += seconds

        with patch("core.smducar_router.time.time", side_effect=lambda: clock[0]), patch("core.smducar_router.time.sleep", side_effect=sleep):
            self.assertIsNone(self.router.wait_for_irsplr_metadata_from_open_tab(timeout=1))
        self.router.read_open_pdf_accessibility_text.assert_not_called()
        self.router.copy_open_pdf_tab_text.assert_not_called()
        self.router.read_open_pdf_tab_text.assert_not_called()

    def test_corrupt_download_exception_is_not_swallowed(self):
        path = Mock(name="bad.pdf")
        path.name = "bad.pdf"
        path.read_bytes.return_value = b"BM\xd2\x1d\x1c"
        self.router.find_completed_irsplr_download = Mock(return_value=path)
        with self.assertRaisesRegex(IRSPLRCorruptDocument, "not a PDF"):
            self.router.wait_for_irsplr_downloaded_metadata({}, "bad.pdf", timeout=1)

    def test_network_pdf_validation_failure_is_not_used_as_metadata(self):
        self.configure_pdf_reader()
        self.router.get_opened_pdf_bytes_from_browser_network.return_value = b"%PDF-1.7\ntruncated"
        with self.assertRaisesRegex(IRSPLRDocumentReviewRequired, "TRUNCATED"):
            self.router.wait_for_irsplr_metadata_from_open_tab(timeout=1)
        self.router.copy_open_pdf_tab_text.assert_not_called()

    def test_failed_extraction_is_propagated_to_the_row_review_handler(self):
        self.router.find_mspb_file_name_link = Mock(return_value=Mock())
        self.router.open_irsplr_link_and_extract_metadata = Mock(side_effect=IRSPLRDocumentReviewRequired("LOAD FAILED"))
        with self.assertRaises(IRSPLRDocumentReviewRequired):
            self.router.extract_irsplr_metadata_from_search_result(self.ROW, 0)

    def configure_link(self):
        self.router.driver.current_url = "https://example.test/inventory/search"
        self.router._get_element_href = Mock(return_value="https://example.test/document.pdf")
        self.router.get_filename_from_document_href = Mock(return_value=self.ROW["FileName"])
        self.router.snapshot_irsplr_downloads = Mock(return_value={})
        self.router.enable_chrome_downloads = Mock()
        self.router.enable_browser_network_capture = Mock()
        self.router.irsplr_download_dir = "unused"

    def test_opened_viewer_failure_closes_pdf_tab_and_propagates_review(self):
        self.configure_link()
        self.configure_pdf_reader()
        self.router.read_irsplr_pdf_viewer_error.return_value = "Failed to load PDF document."
        self.router.wait_for_irsplr_downloaded_metadata.return_value = self.metadata
        self.router.driver.execute_script.side_effect = lambda *args: self.router.driver.window_handles.append("pdf")
        with patch("core.smducar_router.WebDriverWait"), self.assertRaises(IRSPLRDocumentReviewRequired):
            self.router.open_irsplr_link_and_extract_metadata(Mock(), self.ROW)
        self.router.wait_for_irsplr_downloaded_metadata.assert_called_once()
        self.router.driver.close.assert_called_once()
        self.router.driver.switch_to.window.assert_called_with("search")

    def test_download_only_document_does_not_scrape_search_page(self):
        self.configure_link()
        self.router.wait_for_irsplr_downloaded_metadata = Mock(return_value=self.metadata)
        self.router.wait_for_irsplr_metadata_from_open_tab = Mock()
        with patch("core.smducar_router.WebDriverWait"):
            result = self.router.open_irsplr_link_and_extract_metadata(Mock(), self.ROW)
        self.assertEqual(result, self.metadata)
        self.router.wait_for_irsplr_metadata_from_open_tab.assert_not_called()

    def test_non_downloadable_source_requires_review_instead_of_fallback(self):
        self.configure_link()
        self.router.wait_for_irsplr_downloaded_metadata = Mock(return_value=None)
        self.router.wait_for_irsplr_metadata_from_open_tab = Mock()
        with patch("core.smducar_router.WebDriverWait"), self.assertRaisesRegex(IRSPLRDocumentReviewRequired, "UNAVAILABLE"):
            self.router.open_irsplr_link_and_extract_metadata(Mock(), self.ROW)
        self.router.wait_for_irsplr_metadata_from_open_tab.assert_not_called()

    def test_legacy_unreadable_fallback_never_enters_modify_or_claims_already_processed(self):
        metadata = build_irsplr_unreadable_fallback_metadata(self.ROW["FileName"], "FDPLR000")
        result = self.router.open_and_process_form(self.ROW, pd.DataFrame([self.ROW]), 0, "unused.xlsx", irsplr_metadata=metadata)
        self.assertTrue(is_manual_review_status(result))
        self.router.attempt_open_modify.assert_not_called()
        self.router.handle_routing_and_save.assert_not_called()
        self.assertEqual(mspb_metadata_buffer[0]["Route"], "Not Routed")

    def test_direct_fill_with_unverified_metadata_leaves_form_untouched(self):
        for metadata in (None, build_irsplr_unreadable_fallback_metadata(self.ROW["FileName"])):
            with self.subTest(metadata=metadata):
                result = self.router.fill_irsplr_irt_form(self.ROW, 0, metadata)
                self.assertTrue(is_manual_review_status(result))
                self.router.prepare_common_fields.assert_not_called()
                self.router.handle_routing_and_save.assert_not_called()

    def configure_batch(self):
        self.router.safe_alert_accept = Mock()
        self.router.validate_row = Mock(side_effect=lambda row, *args: row["LNI"])
        self.router.search_lni = Mock(return_value=True)
        self.router.check_result_available = Mock(return_value=True)
        self.router.click_matching_result = Mock()
        self.router._should_refresh_retry_form_status = Mock(return_value=False)

        def save(row, df, index, *args, **kwargs):
            status_updates_buffer[index] = "DONE"
            return "DONE"

        self.router.open_and_process_form = Mock(side_effect=save)

    def test_unverified_source_problem_is_reviewed_and_next_valid_document_still_routes(self):
        self.configure_batch()
        df = pd.DataFrame([self.ROW, {**self.ROW, "LNI": "6KTW-5733-RRMW-12HN-00000-00"}])
        self.router.extract_irsplr_metadata_from_search_result = Mock(side_effect=[IRSPLRDocumentReviewRequired("UNAVAILABLE - corruption not verified"), self.metadata])
        progress = Mock()
        count, _ = self.router.process_batch(df, df, "unused.xlsx", progress, "irsplr", irsplr_mode=True)
        self.assertEqual(count, 1)
        self.assertTrue(is_manual_review_status(status_updates_buffer[0]))
        self.assertEqual(status_updates_buffer[1], "DONE")
        self.router.click_matching_result.assert_called_once()
        self.router.open_and_process_form.assert_called_once()
        self.assertEqual(self.router.open_and_process_form.call_args.args[2], 1)
        self.assertEqual(mspb_metadata_buffer[0]["Route"], "Not Routed")
        self.assertEqual(rerun_status_for(status_updates_buffer[0]), status_updates_buffer[0].upper())
        self.assertEqual(summarize_statuses_for_rows(df)["manual_review_count"], 1)
        progress.assert_called_with("irsplr", 2, 2)

    def test_missing_metadata_does_not_open_form_via_filename_fallback(self):
        self.configure_batch()
        df = pd.DataFrame([self.ROW])
        self.router.extract_irsplr_metadata_from_search_result = Mock(return_value=None)
        count, _ = self.router.process_batch(df, df, "unused.xlsx", None, "irsplr", irsplr_mode=True)
        self.assertEqual(count, 0)
        self.assertTrue(is_manual_review_status(status_updates_buffer[0]))
        self.router.click_matching_result.assert_not_called()
        self.router.open_and_process_form.assert_not_called()


if __name__ == "__main__":
    unittest.main()
