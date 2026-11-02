import unittest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from selenium.common.exceptions import InvalidSessionIdException, NoSuchWindowException, WebDriverException

from core.irsplr_extractor import IRSPLRCorruptDocument, IRSPLRDocumentReviewRequired, IRSPLRMetadata
from core.smducar_config import mspb_metadata_buffer
from core.smducar_router import CaseLawRouter, RouterSessionLostError


class IRSPLRDownloadHandoffTests(unittest.TestCase):
    ROW = {"FileName": "mc.202642004_20261016.pdf", "CourtCode": "FDPLR000", "LNI": "6KTW-5733-RRMW-12K2-00000-00"}

    def setUp(self):
        self.router = CaseLawRouter.__new__(CaseLawRouter)
        self.driver = self.router.driver = Mock()
        self.driver.current_window_handle = "search"
        self.driver.current_url = "https://example.test/inventory/search"
        self.driver.window_handles = ["search"]
        self.driver.switch_to.window.side_effect = self.switch_window
        self.driver.close.side_effect = self.close_window
        self.closed = []
        self.handoff_error = NoSuchWindowException("no such window: target window already closed")
        self.remove_pdf_on_error = True
        self.driver.execute_script.side_effect = self.execute_script
        self.router._get_element_href = Mock(return_value="https://example.test/document.pdf")
        self.router.get_filename_from_document_href = Mock(return_value=self.ROW["FileName"])
        self.router.snapshot_irsplr_downloads = Mock(return_value={})
        self.router.find_completed_irsplr_download = Mock(return_value=None)
        self.router.enable_chrome_downloads = Mock()
        self.router.enable_browser_network_capture = Mock()
        self.router.irsplr_download_dir = "unused"
        self.router.wait_for_open_tab_load_state = Mock()
        self.metadata = IRSPLRMetadata("FDPLR000", "202642004", "07-20-2026", "Letter", has_text_content=True)
        self.router.wait_for_irsplr_downloaded_metadata = Mock(return_value=self.metadata)
        self.router.get_opened_pdf_bytes_from_browser_network = Mock()
        self.router.copy_open_pdf_tab_text = Mock()
        self.router.read_open_pdf_tab_text = Mock()
        self.router.read_open_pdf_accessibility_text = Mock()

    def switch_window(self, handle):
        if handle not in self.driver.window_handles:
            raise NoSuchWindowException("no such window")
        self.driver.current_window_handle = handle

    def close_window(self):
        handle = self.driver.current_window_handle
        self.closed.append(handle)
        self.driver.window_handles.remove(handle)

    def execute_script(self, script, *args):
        if "window.open" in script:
            self.driver.window_handles.append("pdf")
            return
        if self.remove_pdf_on_error and "pdf" in self.driver.window_handles:
            self.driver.window_handles.remove("pdf")
        raise self.handoff_error

    def open_source(self):
        return self.router.open_irsplr_link_and_extract_metadata(Mock(), self.ROW)

    def test_closed_pdf_tab_returns_to_inventory_and_reads_completed_download(self):
        def downloaded(*args, **kwargs):
            self.assertEqual(self.driver.current_window_handle, "search")
            self.assertGreaterEqual(kwargs["timeout"], 30)
            return self.metadata

        self.router.wait_for_irsplr_downloaded_metadata.side_effect = downloaded
        self.assertEqual(self.open_source(), self.metadata)
        self.assertEqual(self.driver.current_window_handle, "search")
        self.assertEqual(self.driver.window_handles, ["search"])
        self.assertEqual(self.closed, [])
        self.router.wait_for_irsplr_downloaded_metadata.assert_called_once()
        self.router.get_opened_pdf_bytes_from_browser_network.assert_not_called()
        self.router.copy_open_pdf_tab_text.assert_not_called()

    def test_generic_webdriver_closed_window_message_is_also_recoverable(self):
        self.handoff_error = WebDriverException("no such window: target window already closed")
        self.assertEqual(self.open_source(), self.metadata)
        self.assertIn("search", self.driver.window_handles)

    def test_pdf_closing_during_accessibility_check_is_recoverable(self):
        def script(source, *args):
            if "window.open" in source:
                self.driver.window_handles.append("pdf")
            return ""

        def cdp(*args):
            self.driver.window_handles.remove("pdf")
            raise NoSuchWindowException("web view not found: target window already closed")

        self.driver.execute_script.side_effect = script
        self.driver.execute_cdp_cmd.side_effect = cdp
        self.assertEqual(self.open_source(), self.metadata)
        self.assertEqual(self.driver.current_window_handle, "search")
        self.assertEqual(self.closed, [])

    def test_pdf_closing_during_switch_to_viewer_is_recoverable(self):
        def switch(handle):
            if handle == "pdf":
                self.driver.window_handles.remove("pdf")
                raise NoSuchWindowException("target window already closed")
            self.switch_window(handle)

        self.driver.switch_to.window.side_effect = switch
        self.assertEqual(self.open_source(), self.metadata)
        self.router.wait_for_irsplr_downloaded_metadata.assert_called_once()

    def test_incomplete_download_is_review_not_corruption_or_session_loss(self):
        self.router.wait_for_irsplr_downloaded_metadata.return_value = None
        with self.assertRaises(IRSPLRDocumentReviewRequired) as raised:
            self.open_source()
        self.assertNotIsInstance(raised.exception, IRSPLRCorruptDocument)
        self.assertIn("search", self.driver.window_handles)
        self.assertEqual(self.closed, [])

    def test_download_verified_corrupt_after_handoff_retains_exclusion_outcome(self):
        self.router.wait_for_irsplr_downloaded_metadata.side_effect = IRSPLRCorruptDocument("Verified bitmap download")
        with self.assertRaises(IRSPLRCorruptDocument):
            self.open_source()
        self.assertIn("search", self.driver.window_handles)

    def test_cleanup_never_closes_inventory_when_pdf_handle_still_exists(self):
        self.remove_pdf_on_error = False
        self.assertEqual(self.open_source(), self.metadata)
        self.assertEqual(self.closed, ["pdf"])
        self.assertEqual(self.driver.window_handles, ["search"])
        self.assertEqual(self.driver.current_window_handle, "search")

    def test_real_invalid_browser_session_still_aborts_instead_of_waiting(self):
        self.handoff_error = InvalidSessionIdException("invalid session id")
        with self.assertRaises(RouterSessionLostError):
            self.open_source()
        self.router.wait_for_irsplr_downloaded_metadata.assert_not_called()

    def test_no_surviving_inventory_window_is_not_treated_as_a_download_success(self):
        def close_all(script, *args):
            if "window.open" in script:
                self.driver.window_handles.append("pdf")
                return
            self.driver.window_handles.clear()
            raise NoSuchWindowException("no such window")

        self.driver.execute_script.side_effect = close_all
        with self.assertRaises(RouterSessionLostError):
            self.open_source()
        self.router.wait_for_irsplr_downloaded_metadata.assert_not_called()

    def test_delayed_download_completes_after_viewer_closes(self):
        with tempfile.TemporaryDirectory(prefix="irsplr-handoff-") as folder:
            self.router.irsplr_download_dir = Path(folder)
            partial = Path(folder, self.ROW["FileName"] + ".crdownload")
            completed = Path(folder, self.ROW["FileName"])
            partial.write_bytes(b"download still in progress")
            self.router.find_completed_irsplr_download = CaseLawRouter.find_completed_irsplr_download.__get__(self.router)
            self.router.wait_for_irsplr_downloaded_metadata = CaseLawRouter.wait_for_irsplr_downloaded_metadata.__get__(self.router)
            self.router._irsplr_unreadable_pdf_signatures = set()
            clock = [100.0]

            def sleep(seconds):
                clock[0] += seconds
                if clock[0] >= 102 and partial.exists():
                    partial.rename(completed)

            with patch("core.smducar_router.time.time", side_effect=lambda: clock[0]), \
                    patch("core.smducar_router.time.sleep", side_effect=sleep), \
                    patch("core.smducar_router.parse_irsplr_pdf_bytes", return_value=self.metadata) as parse:
                self.assertEqual(self.open_source(), self.metadata)
            self.assertGreaterEqual(clock[0], 102)
            self.assertEqual(self.driver.current_window_handle, "search")
            self.assertEqual(self.closed, [])
            parse.assert_called_once()

    def test_attempted_metadata_does_not_claim_an_outside_conversion_route(self):
        mspb_metadata_buffer.clear()
        self.addCleanup(mspb_metadata_buffer.clear)
        self.router.record_irsplr_metadata(0, self.ROW, self.ROW["LNI"], metadata_status="Attempted")
        self.assertEqual(mspb_metadata_buffer[0]["Route"], "Not Routed")


class IRSPLRDownloadSelectionTests(unittest.TestCase):
    NAME = "mc.202642004_20261016.pdf"

    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix="irsplr-download-selection-")
        self.addCleanup(folder.cleanup)
        self.directory = Path(folder.name)
        self.router = CaseLawRouter.__new__(CaseLawRouter)
        self.router.irsplr_download_dir = self.directory

    def find(self, snapshot=None):
        return self.router.find_completed_irsplr_download(snapshot or {}, self.NAME)

    def test_partial_downloads_are_never_returned_as_completed_sources(self):
        for name in (self.NAME + ".crdownload", self.NAME + " (1).crdownload"):
            (self.directory / name).write_bytes(b"partial bytes")
        self.assertIsNone(self.find())

    def test_stale_partial_does_not_block_a_new_completed_retry(self):
        (self.directory / (self.NAME + ".crdownload")).write_bytes(b"abandoned earlier download")
        before = self.router.snapshot_irsplr_downloads()
        completed = self.directory / self.NAME
        completed.write_bytes(b"new completed download")
        self.assertEqual(self.find(before), completed)

    def test_still_active_matching_partial_blocks_its_incomplete_target(self):
        (self.directory / self.NAME).write_bytes(b"new download")
        (self.directory / (self.NAME + ".crdownload")).write_bytes(b"still writing")
        self.assertIsNone(self.find())

    def test_different_duplicate_partial_does_not_block_a_completed_filename(self):
        completed = self.directory / self.NAME
        completed.write_bytes(b"completed source")
        (self.directory / (self.NAME + " (1).crdownload")).write_bytes(b"separate retry still in progress")
        self.assertEqual(self.find(), completed)

    def test_both_chrome_duplicate_filename_conventions_are_supported(self):
        for suffix, name in (("before", "mc.202642004_20261016 (1).pdf"), ("after", self.NAME + " (1)")):
            with self.subTest(name=name):
                directory = self.directory / suffix
                directory.mkdir()
                self.router.irsplr_download_dir = directory
                completed = directory / name
                completed.write_bytes(b"completed duplicate-name download")
                self.assertEqual(self.find(), completed)

    def test_old_completed_or_wrong_document_is_not_reused(self):
        (self.directory / self.NAME).write_bytes(b"old source from a prior run")
        before = self.router.snapshot_irsplr_downloads()
        (self.directory / "unrelated.pdf").write_bytes(b"a different document")
        self.assertIsNone(self.find(before))


if __name__ == "__main__":
    unittest.main()
