"""Browser evidence must precede every IRSPLR download/OCR decision."""

from contextlib import contextmanager
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from selenium.common.exceptions import NoSuchWindowException

from core.irsplr_browser_check import browser_pdf_state, confirm_browser_pdf
from core.irsplr_extractor import IRSPLRCorruptDocument, IRSPLRDocumentReviewRequired, IRSPLRMetadata
from core.irt_duplicate_verifier import IRTDocumentProfile
from core.smducar_router import CaseLawRouter
from core.smducar_workflow import _build_chrome_options
from tests.test_irsplr_ocr_integrity import blank_pdf


@contextmanager
def clock():
    now = [100.0]
    with patch("core.irsplr_browser_check.time.monotonic", side_effect=lambda: now[0]), \
            patch("core.irsplr_browser_check.time.sleep", side_effect=lambda seconds: now.__setitem__(0, now[0] + seconds)):
        yield now


class BrowserProofTests(unittest.TestCase):
    def setUp(self):
        self.driver = Mock()
        self.driver.execute_script.return_value = "loading"
        self.driver.execute_cdp_cmd.return_value = {}
        self.error = Mock(return_value="")
        self.headers = Mock(return_value={"ok": True, "status": 200, "content_type": "application/pdf"})

    def check(self, states, **kwargs):
        with clock(), patch("core.irsplr_browser_check.browser_pdf_state", side_effect=states):
            return confirm_browser_pdf(self.driver, self.error, self.headers, timeout=kwargs.get("timeout", 6))

    def test_loaded_pages_must_be_stable_before_pass(self):
        self.check(["loading", "loaded", "loaded", "loaded"])
        self.driver.refresh.assert_not_called()
        self.headers.assert_not_called()

    def test_transient_viewer_failure_recovers_after_one_reload(self):
        self.check(["failed"] * 5 + ["loading", "loaded", "loaded", "loaded"])
        self.driver.refresh.assert_called_once()
        self.headers.assert_not_called()

    def test_repeated_explicit_error_plus_pdf_access_confirms_failed_source(self):
        with self.assertRaisesRegex(IRSPLRCorruptDocument, "after one reload"):
            self.check(["failed"] * 10)
        self.driver.refresh.assert_called_once()
        self.headers.assert_called_once()

    def test_http_login_network_empty_or_unsupported_head_is_review(self):
        for headers in (
            {}, {"ok": False, "status": 403}, {"ok": False, "status": 405},
            {"ok": True, "status": 200, "content_type": "text/html"},
            {"ok": True, "status": 200, "content_type": "application/pdf", "content_length": "0"},
        ):
            with self.subTest(headers=headers):
                self.headers.return_value = headers
                with self.assertRaises(IRSPLRDocumentReviewRequired) as raised:
                    self.check(["failed"] * 10)
                self.assertNotIsInstance(raised.exception, IRSPLRCorruptDocument)

    def test_no_error_or_embed_alone_is_not_a_success_signal(self):
        with self.assertRaisesRegex(IRSPLRDocumentReviewRequired, "UNCONFIRMED"):
            self.check(["loading"] * 12)
        self.headers.assert_not_called()

    def test_password_is_review_without_waiting_or_declaring_corruption(self):
        with self.assertRaisesRegex(IRSPLRDocumentReviewRequired, "PASSWORD") as raised:
            self.check(["password"])
        self.assertNotIsInstance(raised.exception, IRSPLRCorruptDocument)
        self.driver.refresh.assert_not_called()

    def test_visible_failed_dialog_overrides_loaded_pages(self):
        self.error.return_value = "Failed to load PDF document."
        self.driver.execute_script.return_value = "loaded"
        self.assertEqual(browser_pdf_state(self.driver, self.error), "failed")
        self.driver.execute_script.assert_not_called()

    def test_cross_origin_pdf_pages_are_positive_evidence_for_a_scan(self):
        def cdp(method, params):
            if method == "Page.getFrameTree":
                return {"frameTree": {"childFrames": [{"frame": {"id": "pdf"}}]}}
            if params.get("frameId") == "pdf":
                return {"nodes": [{"role": {"value": "PdfRoot"}, "childIds": ["page1"]}]}
            return {"nodes": []}
        self.driver.execute_cdp_cmd.side_effect = cdp
        self.assertEqual(browser_pdf_state(self.driver, self.error), "loaded")

    def test_empty_or_ignored_pdf_root_is_not_success(self):
        for node in ({"childIds": []}, {"childIds": ["page1"], "ignored": True}):
            self.driver.execute_cdp_cmd.return_value = {"nodes": [{"role": {"value": "PdfRoot"}, **node}]}
            self.assertEqual(browser_pdf_state(self.driver, self.error), "loading")

    def test_closed_browser_shadow_frame_is_checked_and_restored(self):
        body, frame = Mock(), Mock()
        self.driver.find_elements.return_value = [body]
        body.shadow_root.find_elements.return_value = [frame]
        for state in ("loaded", "password", "failed", "loading"):
            with self.subTest(state=state), patch(
                "core.irsplr_browser_check._browser_pdf_state",
                side_effect=["loading", state],
            ):
                self.assertEqual(browser_pdf_state(self.driver, self.error), state)
                self.driver.switch_to.frame.assert_called_with(frame)
                self.driver.switch_to.parent_frame.assert_called()

    def test_viewer_exception_restores_parent_and_remains_unconfirmed(self):
        body = Mock()
        self.driver.find_elements.return_value = [body]
        body.shadow_root.find_elements.return_value = [Mock()]
        with patch("core.irsplr_browser_check._browser_pdf_state",
                   side_effect=["loading", RuntimeError("frame navigating")]):
            self.assertEqual(browser_pdf_state(self.driver, self.error), "loading")
        self.driver.switch_to.parent_frame.assert_called_once()


class IRSPLRBrowserIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.router = CaseLawRouter.__new__(CaseLawRouter)
        self.router._irsplr_browser_first = True
        self.router._irsplr_viewer_passed = False
        self.router.driver = Mock()
        self.router.driver.current_window_handle = "pdf"
        self.router.driver.current_url = "https://irt.test/document.pdf"
        self.router.driver.window_handles = ["inventory", "pdf"]
        self.router._irsplr_inventory_tab = "inventory"
        self.router.driver.switch_to.window.side_effect = lambda handle: setattr(self.router.driver, "current_window_handle", handle)
        self.router.validate_irsplr_browser_pdf = Mock()
        self.router.set_irsplr_browser_downloads = Mock()
        self.router.get_opened_pdf_bytes_from_browser_network = Mock(return_value=blank_pdf())
        self.router._store_browser_verified_irsplr_pdf = Mock()
        self.router.log_irsplr_metadata = Mock()
        self.router._fetch_irt_pdf_in_current_browser = Mock(return_value=blank_pdf())
        self.metadata = IRSPLRMetadata("FDPLR000", "202642012", "07-10-2026", "Letter", has_text_content=True)

    def test_browser_success_precedes_bytes_metadata_ocr_and_local_download(self):
        events = []
        self.router.validate_irsplr_browser_pdf.side_effect = lambda *a, **k: events.append("viewer")
        self.router.get_opened_pdf_bytes_from_browser_network.side_effect = lambda *a, **k: events.append("bytes") or blank_pdf()
        self.router._store_browser_verified_irsplr_pdf.side_effect = lambda *a: events.append("download")
        with patch("core.smducar_router.parse_irsplr_pdf_bytes", side_effect=lambda *a, **k: events.append("parse/OCR") or self.metadata):
            actual = self.router.wait_for_irsplr_metadata_from_open_tab("https://irt.test/document.pdf", expected_filename="ruling.pdf")
        self.assertEqual(actual, self.metadata)
        self.assertEqual(events, ["viewer", "bytes", "parse/OCR", "download"])
        self.assertTrue(self.router._irsplr_viewer_passed)

    def test_failed_or_unconfirmed_viewer_prevents_any_download_or_ocr(self):
        for error in (IRSPLRCorruptDocument("Failed to load PDF"), IRSPLRDocumentReviewRequired("Loading timed out")):
            self.router.validate_irsplr_browser_pdf.side_effect = error
            with patch("core.smducar_router.parse_irsplr_pdf_bytes") as parse, self.assertRaises(type(error)):
                self.router.wait_for_irsplr_metadata_from_open_tab("https://irt.test/document.pdf")
            parse.assert_not_called()
        self.router.get_opened_pdf_bytes_from_browser_network.assert_not_called()
        self.router._store_browser_verified_irsplr_pdf.assert_not_called()
        self.router.set_irsplr_browser_downloads.assert_not_called()
        self.router._fetch_irt_pdf_in_current_browser.assert_not_called()

    def test_scan_that_opens_but_ocr_fails_remains_review_not_corrupt(self):
        with patch("core.smducar_router.parse_irsplr_pdf_bytes", return_value=None), \
                self.assertRaisesRegex(IRSPLRDocumentReviewRequired, "native text/OCR") as raised:
            self.router.read_browser_verified_irsplr_metadata("https://irt.test/document.pdf", "scan.pdf", "FDPLR000")
        self.assertNotIsInstance(raised.exception, IRSPLRCorruptDocument)
        self.router._store_browser_verified_irsplr_pdf.assert_called_once()

    def test_authenticated_byte_fallback_only_after_browser_pass_and_restores_viewer(self):
        self.router.get_opened_pdf_bytes_from_browser_network.return_value = None
        def fetch(*args, **kwargs):
            self.assertTrue(self.router._irsplr_viewer_passed)
            self.assertEqual(self.router.driver.current_window_handle, "inventory")
            return blank_pdf()
        self.router._fetch_irt_pdf_in_current_browser.side_effect = fetch
        with patch("core.smducar_router.parse_irsplr_pdf_bytes", return_value=self.metadata):
            self.router.read_browser_verified_irsplr_metadata("https://irt.test/document.pdf", "scan.pdf", "FDPLR000")
        self.assertEqual(self.router.driver.current_window_handle, "pdf")

    def test_local_writer_is_guarded_and_preserves_existing_documents(self):
        del self.router._store_browser_verified_irsplr_pdf
        with tempfile.TemporaryDirectory() as directory:
            self.router.irsplr_download_dir = Path(directory)
            with self.assertRaisesRegex(IRSPLRDocumentReviewRequired, "blocked"):
                self.router._store_browser_verified_irsplr_pdf(b"new", "scan.pdf")
            self.assertEqual(list(Path(directory).iterdir()), [])
            self.router._irsplr_viewer_passed = True
            original = Path(directory) / "scan.pdf"
            original.write_bytes(b"original")
            saved = self.router._store_browser_verified_irsplr_pdf(b"new", "scan.pdf")
            self.assertEqual(original.read_bytes(), b"original")
            self.assertEqual(saved.name, "scan (1).pdf")
            self.assertEqual(saved.read_bytes(), b"new")

    def test_closed_viewer_before_proof_cannot_use_download_handoff(self):
        self.router.wait_for_irsplr_downloaded_metadata = Mock()
        with self.assertRaisesRegex(IRSPLRDocumentReviewRequired, "before Chrome loaded"):
            self.router.wait_for_irsplr_download_after_tab_close("inventory", {}, "scan.pdf", "FDPLR000")
        self.router.wait_for_irsplr_downloaded_metadata.assert_not_called()
        self.assertEqual(self.router.driver.current_window_handle, "inventory")

    def test_opener_disables_download_before_opening_and_always_restores_inventory(self):
        self.router.driver.current_window_handle = "inventory"
        self.router.driver.window_handles = ["inventory"]
        events = []
        self.router._get_element_href = Mock(return_value="https://irt.test/document.pdf")
        self.router.get_filename_from_document_href = Mock(return_value="ruling.pdf")
        self.router.snapshot_irsplr_downloads = Mock(return_value={})
        self.router.find_completed_irsplr_download = Mock(return_value=None)
        self.router.enable_browser_network_capture = Mock()
        self.router.set_irsplr_browser_downloads.side_effect = lambda **kw: events.append("deny" if not kw["allowed"] else "allow")
        def execute(*args):
            events.append("open")
            self.router.driver.window_handles.append("pdf")
        self.router.driver.execute_script.side_effect = execute
        self.router.wait_for_irsplr_metadata_from_open_tab = Mock(side_effect=IRSPLRCorruptDocument("Failed to load PDF"))
        self.router.driver.close.side_effect = lambda: self.router.driver.window_handles.remove(self.router.driver.current_window_handle)
        with self.assertRaises(IRSPLRCorruptDocument):
            self.router.open_irsplr_link_and_extract_metadata(Mock(), {"CourtCode": "FDPLR000"})
        self.assertEqual(events, ["deny", "open"])
        self.assertEqual(self.router.driver.window_handles, ["inventory"])
        self.assertEqual(self.router.driver.current_window_handle, "inventory")

    def test_pdf_header_request_uses_inventory_and_never_reads_a_body(self):
        self.router.driver.execute_async_script.return_value = {"ok": True, "status": 200, "content_type": "application/pdf"}
        result = self.router.irsplr_source_headers("https://irt.test/document.pdf")
        script = self.router.driver.execute_async_script.call_args.args[0]
        self.assertIn("method: 'HEAD'", script)
        self.assertNotIn("arrayBuffer", script)
        self.assertTrue(result["ok"])
        self.assertEqual(self.router.driver.current_window_handle, "pdf")

    def test_only_irsplr_switches_chrome_from_download_to_viewer(self):
        viewer = _build_chrome_options({}, Path("downloads"), browser_pdf_viewer=True)
        other = _build_chrome_options({}, Path("downloads"))
        self.assertFalse(viewer.experimental_options["prefs"]["plugins.always_open_pdf_externally"])
        self.assertTrue(other.experimental_options["prefs"]["plugins.always_open_pdf_externally"])
        self.router.configure_irt_duplicate_verification(irsplr_mode=True)
        self.assertTrue(self.router._irsplr_browser_first)
        self.router.configure_irt_duplicate_verification(ferc_mode=True)
        self.assertFalse(self.router._irsplr_browser_first)

    def test_candidate_probe_closes_only_its_own_tab_even_for_confirmed_failure(self):
        self.router.driver.current_window_handle = "inventory"
        self.router.driver.execute_script.side_effect = lambda *a: self.router.driver.window_handles.append("candidate")
        self.router.driver.close.side_effect = lambda: self.router.driver.window_handles.remove(self.router.driver.current_window_handle)
        self.router.validate_irsplr_browser_pdf.side_effect = IRSPLRCorruptDocument("Failed to load PDF")
        with self.assertRaises(IRSPLRCorruptDocument):
            self.router.inspect_irsplr_duplicate_in_browser("document.pdf")
        self.assertEqual(self.router.driver.window_handles, ["inventory", "pdf"])
        self.assertEqual(self.router.driver.current_window_handle, "inventory")

    def test_candidate_viewer_closure_is_not_a_dead_inventory_session(self):
        self.router.driver.current_window_handle = "inventory"
        self.router.driver.execute_script.side_effect = lambda *a: self.router.driver.window_handles.append("candidate")
        def close_during_check(*args):
            self.router.driver.window_handles.remove("candidate")
            raise NoSuchWindowException("no such window")
        self.router.validate_irsplr_browser_pdf.side_effect = close_during_check
        with self.assertRaisesRegex(IRSPLRDocumentReviewRequired, "candidate PDF viewer closed"):
            self.router.inspect_irsplr_duplicate_in_browser("document.pdf")
        self.assertEqual(self.router.driver.current_window_handle, "inventory")
        self.router.driver.close.assert_not_called()


class BrowserDuplicateProfileTests(unittest.TestCase):
    def setUp(self):
        self.router = CaseLawRouter.__new__(CaseLawRouter)
        self.router._irsplr_duplicate_pdf_validation = True
        self.router._irsplr_browser_first = True
        self.router._duplicate_profile_cache = {}
        self.router._main_tab = "inventory"
        self.router.driver = Mock(current_window_handle="form", window_handles=["inventory", "form"])
        self.router.search_lni = Mock(return_value=True)
        self.router._result_document_href = Mock(return_value="document.pdf")
        self.router.inspect_irsplr_duplicate_in_browser = Mock()
        self.router._fetch_irt_pdf_in_current_browser = Mock(return_value=blank_pdf())
        self.router._raise_if_invalid_session_error = Mock()

    def test_failed_existing_candidate_is_returned_as_corrupt_without_download_or_ocr(self):
        self.router.inspect_irsplr_duplicate_in_browser.side_effect = IRSPLRCorruptDocument("Failed to load PDF after reload")
        with patch("core.smducar_router.build_document_profile") as build:
            profile = self.router._document_profile_for_irt_lni("OLD")
        self.assertTrue(profile.is_verified_corrupt)
        build.assert_not_called()
        self.router._fetch_irt_pdf_in_current_browser.assert_not_called()
        self.assertEqual(self.router._duplicate_profile_cache, {})
        self.router.driver.switch_to.window.assert_called_with("form")

    def test_unavailable_existing_candidate_is_unresolved_not_corrupt(self):
        self.router.inspect_irsplr_duplicate_in_browser.side_effect = IRSPLRDocumentReviewRequired("HTTP 403")
        self.assertIsNone(self.router._document_profile_for_irt_lni("OLD"))
        self.router._fetch_irt_pdf_in_current_browser.assert_not_called()

    def test_old_unverified_cache_is_rechecked_then_only_browser_verified_profile_is_cached(self):
        self.router._duplicate_profile_cache["OLD"] = IRTDocumentProfile("OLD", "digest", "text", is_verified_pdf=True)
        with patch("core.smducar_router.build_document_profile", return_value=IRTDocumentProfile("OLD", "digest", "text", is_verified_pdf=True)):
            profile = self.router._document_profile_for_irt_lni("OLD")
        self.assertTrue(profile.is_browser_verified)
        self.router.inspect_irsplr_duplicate_in_browser.assert_called_once()
        self.assertIs(self.router._document_profile_for_irt_lni("OLD"), profile)
        self.router.inspect_irsplr_duplicate_in_browser.assert_called_once()


if __name__ == "__main__":
    unittest.main()
