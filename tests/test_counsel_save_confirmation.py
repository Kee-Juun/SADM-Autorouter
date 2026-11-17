import unittest
from unittest.mock import Mock, patch

import pandas as pd
from selenium.common.exceptions import TimeoutException, UnexpectedAlertPresentException

from core.smducar_config import status_updates_buffer
from core.smducar_router import CaseLawRouter
from core.rerun_status import defer_main_rows_with_failed_counsel


class CounselSaveConfirmationTests(unittest.TestCase):
    def setUp(self):
        status_updates_buffer.clear()
        self.router = CaseLawRouter.__new__(CaseLawRouter)
        self.router.driver = Mock(current_window_handle="fresh-counsel")
        self.router._cleanup_tabs = Mock()
        self.router.handle_lni_search = Mock(return_value=True)
        self.saved = dict(ready=True, route="Archive", docket="23-3216",
                          decision_date="11-12-2026", source_detail="Counsel Information", comments="consolidated")
        self.router.read_ready_locked_form = Mock(return_value=self.saved.copy())
        self.router._counsel_save_expected = self.saved.copy()
        self.df = pd.DataFrame([
            dict(LNI="MAIN", FileName="smd_23-3217_CADC_11_12_2026_0_123.pdf", RecycledCounselLNI="COUNSEL", Status=""),
            dict(LNI="COUNSEL", FileName="smd_23-3216_CADC_Counsel.csv", Status="DONE"),
        ])

    def tearDown(self):
        status_updates_buffer.clear()

    def verify(self):
        def until(predicate):
            if not predicate(self.router.driver):
                raise TimeoutException("saved counsel did not match")
            return True
        with patch("core.smducar_router.WebDriverWait", return_value=Mock(until=until)):
            return self.router.verify_counsel_save(self.df.loc[1], 1, "old-form", "inventory")

    def test_only_fresh_matching_archive_ready_record_is_done(self):
        self.assertEqual(self.verify(), "DONE")
        self.router.handle_lni_search.assert_called_once_with("COUNSEL")
        self.router._cleanup_tabs.assert_any_call("old-form", "inventory")
        self.router._cleanup_tabs.assert_called_with("fresh-counsel", "inventory")

    def test_form_processing_verifies_counsel_before_publishing_done(self):
        self.router._main_tab = "inventory"
        self.router._opened_tab = "old-form"
        self.router.attempt_open_modify = Mock(return_value=True)
        self.router.submit_irt_form = Mock()
        row = self.df.loc[1].copy()
        row["Status"] = ""

        def filled(*args, **kwargs):
            self.assertNotEqual(status_updates_buffer.get(1), "DONE")
            self.router._counsel_save_expected = self.saved.copy()
            return "DONE"

        self.router.fill_irt_form = Mock(side_effect=filled)
        with patch("core.smducar_router.WebDriverWait") as wait:
            wait.return_value.until.side_effect = lambda predicate: predicate(self.router.driver) or (_ for _ in ()).throw(TimeoutException())
            self.assertEqual(self.router.open_and_process_form(row, self.df, 1, "unused.xlsx"), "DONE")
        self.assertEqual(status_updates_buffer[1], "DONE")
        self.router.handle_lni_search.assert_called_once_with("COUNSEL")
        self.router.submit_irt_form.assert_not_called()

    def test_unpersisted_or_wrong_values_block_consolidated_main(self):
        for key, value in (("ready", False), ("route", "Inventory"),
                           ("docket", "INITIALIZED"), ("decision_date", ""),
                           ("comments", ""), ("source_detail", "Order")):
            with self.subTest(key=key):
                status_updates_buffer.clear()
                self.router.read_ready_locked_form.return_value = {**self.saved, key: value}
                self.assertIn("UNCONFIRMED", self.verify())
                main, deferred = defer_main_rows_with_failed_counsel(self.df.loc[[0]], self.df)
                self.assertTrue(main.empty)
                self.assertEqual(deferred[0]["Blocking Counsel LNIs"], ["COUNSEL"])

    def test_reopen_failure_cannot_confirm_completion(self):
        self.router.handle_lni_search.return_value = False
        self.assertIn("UNCONFIRMED", self.verify())

    def test_failed_save_click_is_never_done_or_already_processed(self):
        self.router.click_element = Mock(return_value=False)
        status = self.router.handle_routing_and_save(True, 1, skip_route_and_ready=True)
        self.assertEqual(status, "NEEDS RERUN - SAVE UNCONFIRMED")
        self.assertEqual(status_updates_buffer[1], status)

    def test_save_exception_is_not_already_processed(self):
        self.router.click_element = Mock(side_effect=RuntimeError("click interrupted"))
        self.assertIn("UNCONFIRMED", self.router.handle_routing_and_save(True, 1, skip_route_and_ready=True))

    def test_negative_save_alert_is_not_success(self):
        self.router.click_element = Mock(return_value=True)
        self.router.driver.switch_to.alert.text = "Document cannot be saved"
        with patch("core.smducar_router.WebDriverWait"):
            self.assertEqual(self.router.handle_routing_and_save(True, 1, skip_route_and_ready=True), "ERROR: SAVE REJECTED")

    def test_irt_rejection_invalidates_old_done_counsel_and_stops_retry(self):
        status_updates_buffer[1] = "DONE"
        self.router.long_wait = Mock()
        self.router.long_wait.until.return_value = Mock(text="")
        self.router.clear_and_fill_input = Mock(return_value=True)
        self.router.click_add_related_lni_button = Mock(side_effect=UnexpectedAlertPresentException(
            "Following LNI's cannot be added as Related LNI : COUNSEL"))
        with patch("core.smducar_router.get_related_counsel_lnis", return_value=["COUNSEL"]):
            self.assertFalse(self.router.handle_related_ln_is(self.df.loc[0], self.df, row_index=0))
        self.assertIn("UNCONFIRMED", status_updates_buffer[1])
        self.assertEqual(status_updates_buffer[0], "NEEDS RERUN - COUNSEL FAILED")
        self.router.click_add_related_lni_button.assert_called_once()
        self.router.driver.switch_to.alert.accept.assert_called_once()


if __name__ == "__main__":
    unittest.main()
