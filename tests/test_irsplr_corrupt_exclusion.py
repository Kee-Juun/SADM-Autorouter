import itertools
import unittest
from io import BytesIO
from unittest.mock import Mock, patch

import pandas as pd
from pypdf import PdfWriter

from core.irsplr_extractor import (
    IRSPLRCorruptDocument,
    IRSPLRDocumentReviewRequired,
    build_irsplr_corrupt_exclusion_metadata,
    validate_irsplr_pdf_bytes,
)
from core.smducar_config import error_log_entries, mspb_metadata_buffer, status_updates_buffer
from core.rerun_status import should_recheck_irsplr_comment_review
from core.smducar_router import CaseLawRouter
from core.smducar_workflow import _completed_status_mask


class IRSPLRCorruptExclusionTests(unittest.TestCase):
    ROW = {"FileName": "mc.202642012_20261016.pdf", "CourtCode": "FDPLR000", "LNI": "6KTW-5733-RRMW-12HM-00000-00", "Status": ""}

    def setUp(self):
        self.clear_buffers()
        self.router = CaseLawRouter.__new__(CaseLawRouter)
        self.router.driver = Mock(current_window_handle="irt", window_handles=["search", "irt"])
        self.router.prepare_common_fields = Mock()
        self.router.handle_any_alert = Mock()
        self.router.wait_for_existing_field_text = Mock(return_value="Existing case name")
        self.router.select_source_detail = Mock(return_value=True)
        self.router.click_ready_checkbox_and_check_overlay = Mock(return_value=False)
        self.router.handle_routing_and_save = Mock(return_value="DONE")
        self.metadata = build_irsplr_corrupt_exclusion_metadata("FDPLR000", "Verified bitmap in place of PDF")
        self.comments = "Existing reviewer note"
        self.comments_field = Mock()
        self.comments_field.is_enabled.return_value = True
        self.comments_field.get_attribute.side_effect = lambda name: self.comments if name == "value" else None
        self.comments_field.clear.side_effect = lambda: setattr(self, "comments", "")
        self.comments_field.send_keys.side_effect = lambda value: setattr(self, "comments", value)
        self.route_field = Mock()
        self.route_field.is_enabled.return_value = True
        fields = itertools.cycle([Mock(), self.comments_field, self.route_field, self.route_field])
        self.router.wait = Mock()
        self.router.wait.until.side_effect = lambda *args: next(fields)
        self.configured = {"ready": True, "source_detail": "Excluded", "route": "Archive"}
        self.router.read_ready_locked_form = Mock(side_effect=lambda: {**self.configured, "comments": self.comments})

    def tearDown(self):
        self.clear_buffers()

    @staticmethod
    def clear_buffers():
        status_updates_buffer.clear()
        mspb_metadata_buffer.clear()
        error_log_entries.clear()

    def fill(self):
        def wait(driver, timeout):
            return Mock(until=Mock(return_value=self.comments_field if timeout == 10 else self.route_field))

        with patch("core.smducar_router.WebDriverWait", side_effect=wait), patch("core.smducar_router.Select") as select:
            result = self.router.fill_irsplr_irt_form(self.ROW, 0, self.metadata)
        return result, select

    def test_verified_corrupt_metadata_authorizes_only_the_requested_exclusion(self):
        self.assertTrue(self.metadata.is_verified_corrupt)
        self.assertTrue(self.metadata.is_excluded)
        self.assertFalse(self.metadata.has_text_content)
        self.assertFalse(self.metadata.is_text_fallback)
        self.assertEqual(self.metadata.source_detail, "Excluded")
        self.assertEqual(self.metadata.comments_text, "Exclude - Corrupt File")
        self.assertEqual(self.metadata.docket_number, "")
        self.assertEqual(self.metadata.decision_date, "")
        self.assertEqual(build_irsplr_corrupt_exclusion_metadata("FDIRSPLR").court, "")

    def test_confirmed_replacement_image_formats_use_the_typed_corrupt_outcome(self):
        for payload in (b"BM\xd2\x1d\x1c", b"\x89PNG\r\n", b"\xff\xd8\xffimage"):
            with self.subTest(payload=payload), self.assertRaises(IRSPLRCorruptDocument):
                validate_irsplr_pdf_bytes(payload)

    def test_empty_download_and_server_error_page_are_not_verified_corruption(self):
        for payload in (b"", b"<html>Login required or server error</html>", b"%PDF-1.7\ntruncated", b'{"error":"service unavailable"}'):
            with self.subTest(payload=payload), self.assertRaises(IRSPLRDocumentReviewRequired) as raised:
                validate_irsplr_pdf_bytes(payload)
            self.assertNotIsInstance(raised.exception, IRSPLRCorruptDocument)

    def test_password_protection_is_not_verified_corruption(self):
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        writer.encrypt("secret")
        stream = BytesIO()
        writer.write(stream)
        with self.assertRaises(IRSPLRDocumentReviewRequired) as raised:
            validate_irsplr_pdf_bytes(stream.getvalue())
        self.assertNotIsInstance(raised.exception, IRSPLRCorruptDocument)

    def test_exclusion_sets_source_and_archive_and_appends_exact_comment(self):
        result, select = self.fill()
        self.assertEqual(result, "DONE")
        self.router.select_source_detail.assert_called_once_with("Excluded")
        select.return_value.select_by_visible_text.assert_called_once_with("Archive")
        self.assertEqual(self.comments, "Existing reviewer note; Exclude - Corrupt File")
        self.router.prepare_common_fields.assert_not_called()
        self.router.handle_routing_and_save.assert_called_once_with(False, 0, skip_route_and_ready=True)

    def test_repeated_comment_update_is_idempotent(self):
        self.assertEqual(self.fill()[0], "DONE")
        self.assertEqual(self.fill()[0], "DONE")
        self.assertEqual(self.comments.count("Exclude - Corrupt File"), 1)
        self.comments_field.clear.assert_called_once()

    def test_excluded_source_can_use_an_already_locked_archive_route(self):
        self.route_field.is_enabled.return_value = False
        self.router.get_selected_dropdown_text = Mock(return_value="Archive")
        result, select = self.fill()
        self.assertEqual(result, "DONE")
        select.assert_not_called()
        self.assertIn("Exclude - Corrupt File", self.comments)

    def test_wrong_source_or_route_prevents_save(self):
        for field, value in (("source_detail", "Letter"), ("route", "Outside Conversion"), ("ready", False)):
            with self.subTest(field=field):
                self.configured = {"ready": True, "source_detail": "Excluded", "route": "Archive", field: value}
                result, _ = self.fill()
                self.assertEqual(result, "ERROR: CORRUPT FILE EXCLUSION NOT CONFIRMED")
                self.router.handle_routing_and_save.assert_not_called()

    def test_comment_lost_after_ready_duplicate_overlay_prevents_save(self):
        self.router.click_ready_checkbox_and_check_overlay.side_effect = lambda *args: setattr(self, "comments", "")
        result, _ = self.fill()
        self.assertEqual(result, "ERROR: CORRUPT FILE EXCLUSION NOT CONFIRMED")
        self.router.handle_routing_and_save.assert_not_called()

    def test_unavailable_ready_is_not_mistaken_for_a_saved_exclusion(self):
        self.router.click_ready_checkbox_and_check_overlay.return_value = "READY_NOT_CLICKABLE"
        self.assertEqual(self.fill()[0], "NON-INTERACTABLE IRT FORM")
        self.router.handle_routing_and_save.assert_not_called()

    def test_ambiguous_save_failure_is_not_mistaken_for_already_processed(self):
        self.router.handle_routing_and_save.return_value = "ALREADY PROCESSED"
        self.assertEqual(self.fill()[0], "ERROR: CORRUPT FILE EXCLUSION SAVE UNCONFIRMED")

    def test_ready_locked_excluded_archive_does_not_require_retroactive_comment(self):
        for comments in ("", "Existing reviewer note", "Excluded for some other reason", "Exclude - Corrupt File"):
            with self.subTest(comments=comments):
                self.comments = comments
                result = self.router.verify_ready_locked_form(self.ROW, pd.DataFrame([self.ROW]), metadata=self.metadata)
                self.assertEqual(result, "ALREADY PROCESSED")
                self.assertEqual(self.comments, comments)
                self.comments_field.clear.assert_not_called()
                self.router.handle_routing_and_save.assert_not_called()

    def test_ready_locked_route_source_and_ready_mismatches_still_require_review(self):
        for field, value in (("source_detail", "Letter"), ("route", "Outside Conversion"), ("ready", False)):
            with self.subTest(field=field):
                self.configured = {"ready": True, "source_detail": "Excluded", "route": "Archive", field: value}
                result = self.router.verify_ready_locked_form(self.ROW, pd.DataFrame([self.ROW]), metadata=self.metadata)
                self.assertTrue(result.startswith("MANUAL REVIEW REQUIRED"))

    def test_explicit_user_comment_requirements_are_not_silently_ignored(self):
        row = {**self.ROW, "Comments": "Additional required reviewer note"}
        result = self.router.verify_ready_locked_form(row, pd.DataFrame([row]), metadata=self.metadata)
        self.assertIn("required Comments text missing", result)

    def test_locked_excluded_record_is_skipped_without_fill_ready_or_save(self):
        def locked(**kwargs):
            self.router._modify_blocked_ready = True
            return False

        self.router.attempt_open_modify = Mock(side_effect=locked)
        self.router.fill_irt_form = Mock()
        self.router.submit_irt_form = Mock()
        self.router._cleanup_tabs = Mock()
        result = self.router.open_and_process_form(self.ROW, pd.DataFrame([self.ROW]), 0, "unused.xlsx", irsplr_metadata=self.metadata)
        self.assertEqual(result, "ALREADY PROCESSED")
        self.assertEqual(status_updates_buffer[0], "ALREADY PROCESSED")
        self.router.fill_irt_form.assert_not_called()
        self.router.click_ready_checkbox_and_check_overlay.assert_not_called()
        self.router.handle_routing_and_save.assert_not_called()
        self.router.submit_irt_form.assert_not_called()
        self.assertEqual(self.comments, "Existing reviewer note")

    def test_old_plr_comment_only_review_is_reverified_instead_of_permanently_skipped(self):
        old = "MANUAL REVIEW REQUIRED - READY TO PROCESS LOCKED: REQUIRED COMMENTS TEXT MISSING"
        row = {**self.ROW, "Status": old}
        df = pd.DataFrame([row])
        self.assertFalse(_completed_status_mask(df).iloc[0])
        status_updates_buffer[0] = old
        self.router.safe_alert_accept = Mock()
        self.router.validate_row = Mock(side_effect=lambda row, *args: row["LNI"])
        self.router.search_lni = Mock(return_value=True)
        self.router.check_result_available = Mock(return_value=True)
        self.router.click_matching_result = Mock()
        self.router.extract_irsplr_metadata_from_search_result = Mock(side_effect=IRSPLRCorruptDocument("Verified PDF load failed"))

        def locked(**kwargs):
            self.router._modify_blocked_ready = True
            return False

        self.router.attempt_open_modify = Mock(side_effect=locked)
        self.router.fill_irt_form = Mock()
        self.router.submit_irt_form = Mock()
        self.router._cleanup_tabs = Mock()
        count, _ = self.router.process_batch(df, df, "unused.xlsx", None, "irsplr", irsplr_mode=True)
        self.assertEqual(count, 0)  # Existing record, not a newly routed document.
        self.router.search_lni.assert_called_once_with(row["LNI"])
        self.assertEqual(status_updates_buffer[0], "ALREADY PROCESSED")
        self.router.fill_irt_form.assert_not_called()
        self.router.handle_routing_and_save.assert_not_called()
        self.comments_field.clear.assert_not_called()

    def test_comment_review_recheck_is_scoped_to_plr_with_no_other_review_issues(self):
        old = "MANUAL REVIEW REQUIRED - READY TO PROCESS LOCKED: REQUIRED COMMENTS TEXT MISSING"
        rows = pd.DataFrame([
            {**self.ROW, "Status": old},
            {**self.ROW, "CourtCode": "FDUSAPDC", "Status": old},
            {**self.ROW, "CourtCode": "FDFERC00", "Status": old},
            {**self.ROW, "Status": old + "; ROUTE EXPECTED ARCHIVE, FOUND OUTSIDE CONVERSION"},
            {**self.ROW, "Comments": "Explicit required note", "Status": old},
            {**self.ROW, "Status": "MANUAL REVIEW REQUIRED - OTHER ISSUE"},
            {**self.ROW, "Status": "DONE"},
            {**self.ROW, "Status": "ALREADY PROCESSED"},
        ])
        self.assertEqual(list(rows.apply(should_recheck_irsplr_comment_review, axis=1)), [True, False, False, False, False, False, False, False])
        self.assertEqual(list(_completed_status_mask(rows)), [False, True, True, True, True, True, True, True])

    def test_verified_corrupt_exclusion_is_allowed_into_modify_without_pdf_metadata(self):
        self.router.attempt_open_modify = Mock(return_value=True)
        self.router.fill_irt_form = Mock(return_value="DONE")
        self.router.submit_irt_form = Mock()
        self.router._cleanup_tabs = Mock()
        result = self.router.open_and_process_form(self.ROW, pd.DataFrame([self.ROW]), 0, "unused.xlsx", irsplr_metadata=self.metadata)
        self.assertEqual(result, "DONE")
        self.router.attempt_open_modify.assert_called_once()
        self.assertIs(self.router.fill_irt_form.call_args.kwargs["irsplr_metadata"], self.metadata)

    def test_batch_turns_verified_failure_into_exclusion_metadata_then_continues(self):
        self.router.safe_alert_accept = Mock()
        self.router.validate_row = Mock(side_effect=lambda row, *args: row["LNI"])
        self.router.search_lni = Mock(return_value=True)
        self.router.check_result_available = Mock(return_value=True)
        self.router.click_matching_result = Mock()
        self.router._should_refresh_retry_form_status = Mock(return_value=False)
        self.router.extract_irsplr_metadata_from_search_result = Mock(side_effect=IRSPLRCorruptDocument("Verified PDF load failed"))

        def save(row, df, index, *args, **kwargs):
            metadata = kwargs["irsplr_metadata"]
            self.assertTrue(metadata.is_verified_corrupt)
            self.assertEqual(metadata.source_detail, "Excluded")
            self.assertEqual(metadata.comments_text, "Exclude - Corrupt File")
            status_updates_buffer[index] = "DONE"
            return "DONE"

        self.router.open_and_process_form = Mock(side_effect=save)
        df = pd.DataFrame([self.ROW, {**self.ROW, "LNI": "6KTW-5733-RRMW-12HN-00000-00"}])
        count, _ = self.router.process_batch(df, df, "unused.xlsx", None, "irsplr", irsplr_mode=True)
        self.assertEqual(count, 2)
        self.assertEqual(self.router.open_and_process_form.call_count, 2)
        self.assertEqual(mspb_metadata_buffer[0]["Route"], "Archive")
        self.assertEqual(mspb_metadata_buffer[0]["Extracted Source Detail"], "Excluded")
        self.assertEqual(mspb_metadata_buffer[0]["Prepared Comments"], "Exclude - Corrupt File")
        self.assertTrue(mspb_metadata_buffer[0]["Metadata Status"].startswith("Verified Corrupt File"))


if __name__ == "__main__":
    unittest.main()
