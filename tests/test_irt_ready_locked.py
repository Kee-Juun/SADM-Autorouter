import datetime
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pandas as pd
from selenium.common.exceptions import TimeoutException

from core.rerun_status import defer_main_rows_with_failed_counsel, finalize_rerun_ready_statuses
from core.smducar_config import error_log_entries, status_updates_buffer
from core.smducar_router import CaseLawRouter
from core.smducar_workflow import _count_results_for_rows


class IRTReadyLockedTests(unittest.TestCase):
    MAIN = "6KTN-J843-SGX3-C3NB-00000-00"
    COUNSEL = "6KTN-J843-SGX3-C3R4-00000-00"

    def setUp(self):
        status_updates_buffer.clear()
        error_log_entries.clear()
        self.df = pd.DataFrame([
            {"FileName": "smd_26-7087_CADC_10_22_2026_0_151396853.pdf", "LNI": self.MAIN,
             "CourtCode": "FDUSAPDC", "SourceDetail": "Order", "Decision Date": datetime.date(2026, 10, 22), "Status": ""},
            {"FileName": "smd_26-7087_CADC_Counsel.csv", "LNI": self.COUNSEL,
             "CourtCode": "FDUSAPDC", "SourceDetail": "", "Decision Date": datetime.date(2026, 10, 22), "Status": ""},
        ])
        self.router = CaseLawRouter.__new__(CaseLawRouter)
        self.router.driver = Mock(current_window_handle="irt", window_handles=["search", "irt"])
        self.router.driver.find_elements.return_value = []
        self.router.check_session_validity = Mock(return_value=True)
        self.router.fill_irt_form = Mock()
        self.router.submit_irt_form = Mock()
        self.router._cleanup_tabs = Mock()
        self.router.refresh_search_inventory_for_retry = Mock(return_value=True)
        self.router.handle_lni_search = Mock(return_value=True)
        # These tests cover saved-field verification. Alert/DOM transition
        # timing is exercised through the real settler in its own suite.
        self.router.settle_irt_modify_transition = Mock(
            side_effect=lambda **kwargs: "READY_LOCKED" if isinstance(self.router.driver.execute_script.return_value, dict)
            and self.router.driver.execute_script.return_value.get("ready") is True else "NOT_READY"
        )
        self.router._main_tab = "search"
        self.router._opened_tab = "irt"

    def tearDown(self):
        status_updates_buffer.clear()
        error_log_entries.clear()

    def saved(self, counsel=True, **overrides):
        result = {
            "ready": True,
            "route": "Archive" if counsel else "Outside Conversion",
            "source_detail": "Counsel Information" if counsel else "Order",
            "docket": "26-7087", "decision_date": "10/22/2026",
            "comments": self.MAIN if counsel else "", "related_lnis": "" if counsel else self.COUNSEL,
        }
        result.update(overrides)
        return result

    def alert_waits(self, alert_text="The document cannot be modified (ready to process = [on])"):
        self.button = Mock()
        self.alert = Mock(text=alert_text)
        return [Mock(until=Mock(return_value=self.button)), Mock(until=Mock(return_value=self.alert))]

    def verify(self, *, counsel=True, **saved_overrides):
        self.router.driver.execute_script.return_value = self.saved(counsel, **saved_overrides)
        return self.router.verify_ready_locked_form(self.df.loc[1 if counsel else 0], self.df)

    def test_locked_counsel_with_correct_fields_is_already_processed_without_retry_or_save(self):
        self.router.driver.execute_script.return_value = self.saved()
        with patch("core.smducar_router.WebDriverWait", side_effect=self.alert_waits()), \
                patch("core.smducar_router.time.sleep") as sleep:
            status = self.router.open_and_process_form(self.df.loc[1], self.df, 1, "unused.xlsx")
        self.assertEqual(status, "ALREADY PROCESSED")
        self.assertEqual(status_updates_buffer[1], "ALREADY PROCESSED")
        self.button.click.assert_called_once()
        self.alert.accept.assert_called_once()
        self.router.fill_irt_form.assert_not_called()
        self.router.submit_irt_form.assert_not_called()
        self.router.refresh_search_inventory_for_retry.assert_not_called()
        self.router.handle_lni_search.assert_not_called()
        self.router._cleanup_tabs.assert_called_once_with("irt", "search")
        sleep.assert_not_called()

    def test_locked_main_requires_saved_related_counsel(self):
        self.assertEqual(self.verify(counsel=False), "ALREADY PROCESSED")
        status = self.verify(counsel=False, related_lnis="6KTN-J843-SGX3-C3P2-00000-00")
        self.assertTrue(status.startswith("MANUAL REVIEW REQUIRED"))
        self.assertIn("missing related counsel LNI", status)
        self.assertIn(self.COUNSEL, status)

    def test_counsel_requires_matching_main_lni_in_comments(self):
        status = self.verify(comments="unrelated comment")
        self.assertIn("missing main opinion LNI in Comments", status)
        self.assertIn(self.MAIN, status)

    def test_saved_route_docket_date_source_and_ready_must_match(self):
        for change, reason in (
            ({"route": "Inventory"}, "Route expected Outside Conversion"),
            ({"docket": "26-7088"}, "Docket expected 26-7087"),
            ({"decision_date": "10/23/2026"}, "Decision Date expected"),
            ({"source_detail": "Opinion"}, "Source Detail expected Order"),
            ({"ready": False}, "Ready to Process state could not be confirmed"),
        ):
            with self.subTest(change=change):
                status = self.verify(counsel=False, **change)
                self.assertTrue(status.startswith("MANUAL REVIEW REQUIRED"))
                self.assertIn(reason, status)

    def test_mismatched_locked_record_is_not_edited_or_saved_or_retried(self):
        self.router.driver.execute_script.return_value = self.saved(route="Outside Conversion")
        with patch("core.smducar_router.WebDriverWait", side_effect=self.alert_waits()):
            status = self.router.open_and_process_form(self.df.loc[1], self.df, 1, "unused.xlsx")
        self.assertTrue(status.startswith("MANUAL REVIEW REQUIRED"))
        self.assertNotIn("MODIFY BUTTON NOT FOUND", status)
        self.router.fill_irt_form.assert_not_called()
        self.router.submit_irt_form.assert_not_called()
        self.router.refresh_search_inventory_for_retry.assert_not_called()
        self.router._cleanup_tabs.assert_called_once()

    def test_counsel_date_verification_uses_the_main_opinion_date(self):
        self.df.loc[1, "Decision Date"] = datetime.date(2026, 10, 23)
        self.assertEqual(self.verify(), "ALREADY PROCESSED")

    def test_dash_and_date_display_variations_are_equivalent(self):
        self.assertEqual(self.verify(docket="26\u20147087", decision_date="2026-10-22"), "ALREADY PROCESSED")

    def test_required_user_comments_must_also_exist(self):
        self.df.loc[1, "Comments"] = "Retain original attachment"
        self.assertIn("required Comments text missing", self.verify())
        self.assertEqual(self.verify(comments=self.MAIN + "; Retain original attachment"), "ALREADY PROCESSED")

    def test_unreadable_saved_state_never_becomes_already_processed(self):
        self.router.driver.execute_script.return_value = None
        status = self.router.verify_ready_locked_form(self.df.loc[1], self.df)
        self.assertTrue(status.startswith("MANUAL REVIEW REQUIRED"))
        self.assertIn("saved routing details unavailable", status)

    def test_missing_expected_date_cannot_be_verified_from_the_saved_date_itself(self):
        self.df["Decision Date"] = None
        status = self.verify()
        self.assertIn("expected decision date unavailable", status)

    def test_specialist_metadata_uses_its_own_fields_without_counsel_requirements(self):
        metadata = SimpleNamespace(docket_number="2026-392", decision_date="10-21-2026", source_detail="Opinion")
        self.router.driver.execute_script.return_value = self.saved(
            counsel=False, docket="2026-392", decision_date="10/21/2026", source_detail="Opinion", related_lnis="",
        )
        self.assertEqual(self.router.verify_ready_locked_form(self.df.loc[0], self.df, metadata=metadata), "ALREADY PROCESSED")

    def test_dara_locked_counsel_uses_the_same_verified_archive_path(self):
        self.df.loc[0, "FileName"] = "DAR_26-7087_10222026.pdf"
        self.df.loc[1, "FileName"] = "DAR_26-7087_Counsel.csv"
        self.router.driver.execute_script.return_value = self.saved()
        self.assertEqual(self.router.verify_ready_locked_form(self.df.loc[1], self.df, dar_mode=True), "ALREADY PROCESSED")

    def test_ready_state_flag_is_reset_before_the_next_record(self):
        self.router._modify_blocked_ready = True
        self.router.settle_irt_modify_transition = Mock(return_value="EDITABLE")
        waits = [Mock(until=Mock(return_value=Mock())), Mock(until=Mock(side_effect=TimeoutException()))]
        with patch("core.smducar_router.WebDriverWait", side_effect=waits):
            self.assertTrue(self.router.attempt_open_modify(max_attempts=1))
        self.assertFalse(self.router._modify_blocked_ready)

    def test_ready_alert_after_dsar_is_also_a_terminal_modify_rejection(self):
        self.router.driver.execute_script.return_value = self.saved()
        waits = self.alert_waits("DSAR duplicate notice")
        waits.append(Mock(until=Mock(return_value=Mock(text="The document cannot be modified (ready to process = [on])"))))
        with patch("core.smducar_router.WebDriverWait", side_effect=waits), patch("core.smducar_router.time.sleep"):
            self.assertFalse(self.router.attempt_open_modify(max_attempts=3))
        self.assertTrue(self.router._modify_blocked_ready)
        self.button.click.assert_called_once()

    def test_genuinely_missing_modify_still_uses_the_existing_refresh_retries(self):
        self.router.attempt_open_modify = Mock(return_value=False)
        status = self.router.open_and_process_form(self.df.loc[1], self.df, 1, "unused.xlsx")
        self.assertEqual(status, "ERROR: MODIFY BUTTON NOT FOUND AFTER 3 ATTEMPTS")
        self.assertEqual(self.router.attempt_open_modify.call_count, 3)
        self.assertEqual(self.router.refresh_search_inventory_for_retry.call_count, 2)

    def test_counsel_needing_review_does_not_release_its_main_opinion(self):
        status_updates_buffer[1] = "MANUAL REVIEW REQUIRED - READY TO PROCESS LOCKED: Route mismatch"
        main, deferred = defer_main_rows_with_failed_counsel(self.df.loc[[0]], self.df)
        self.assertTrue(main.empty)
        self.assertEqual(len(deferred), 1)
        self.assertEqual(status_updates_buffer[0], "NEEDS RERUN - COUNSEL FAILED")
        summary = finalize_rerun_ready_statuses(df=self.df)
        self.assertEqual(summary["manual_review_count"], 1)
        self.assertEqual(summary["needs_rerun_count"], 1)

    def test_verified_already_processed_counsel_releases_its_main_opinion(self):
        status_updates_buffer[1] = "ALREADY PROCESSED"
        main, deferred = defer_main_rows_with_failed_counsel(self.df.loc[[0]], self.df)
        self.assertEqual(list(main.index), [0])
        self.assertFalse(deferred)

    def test_batch_reports_verified_record_as_already_processed_and_not_newly_saved(self):
        self.router.safe_alert_accept = Mock()
        self.router.configure_irt_duplicate_verification = Mock()
        self.router._should_refresh_retry_form_status = Mock(return_value=False)
        self.router.driver.execute_script.return_value = self.saved()
        with patch("core.smducar_router.WebDriverWait", side_effect=self.alert_waits()):
            count, _ = self.router.process_batch(self.df.loc[[1]], self.df, "unused.xlsx", None, "counsel")
        self.assertEqual(count, 0)
        self.assertEqual(status_updates_buffer[1], "ALREADY PROCESSED")
        self.assertFalse(error_log_entries)
        counts = _count_results_for_rows(self.df, False, False, False, current_run_only=True)
        self.assertEqual(counts, (0, 0, 1, 0, 0, 0))


if __name__ == "__main__":
    unittest.main()
