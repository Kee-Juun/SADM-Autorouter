import unittest
from contextlib import ExitStack
from dataclasses import replace
from unittest.mock import Mock, patch

from selenium.common.exceptions import TimeoutException, UnexpectedAlertPresentException

from core.itc_extractor import ITCMetadata
from core.smducar_config import itc_content_fingerprint_buffer
from core.smducar_router import CaseLawRouter


READY_WARNING = "The document cannot be modified (ready to process = [on])"


class ITCModifyRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.router = CaseLawRouter.__new__(CaseLawRouter)
        self.router.driver = Mock()
        self.router._itc_duplicate_verification = True
        self.router._active_duplicate_lni = "6KW3-NVD3-SDC5-63YB-00000-00"
        self.router._accept_modify_transition_alerts = Mock(return_value=[])
        self.router.handle_duplicate_overlay = Mock(return_value=True)
        self.snapshot = {"docket": "337-TA-1527", "route": "Inventory Route", "ready": False,
                         "route_enabled": False, "comments_enabled": False, "ready_visible": True,
                         "ready_enabled": True, "blocking_dialog": False, "page_state": "complete"}
        self.router.read_ready_locked_form = Mock(side_effect=lambda: dict(self.snapshot))
        self.button = Mock()
        self.button.is_displayed.return_value = True
        self.button.is_enabled.return_value = True
        self.router.driver.find_elements.side_effect = lambda by, name: [self.button] if name == "modify" else []
        self.now = 0.0
        self.stack = ExitStack()
        self.stack.enter_context(patch("core.smducar_router.time.monotonic", side_effect=lambda: self.now))
        self.stack.enter_context(patch("core.smducar_router.time.sleep", side_effect=self.sleep))

    def sleep(self, seconds):
        self.now += seconds

    def tearDown(self):
        self.stack.close()

    def settle(self, **kwargs):
        return self.router.settle_irt_modify_transition(initial_alerts=[READY_WARNING], **kwargs)

    def test_ready_warning_with_unchecked_form_reenters_modify_and_waits_for_editable_controls(self):
        self.button.click.side_effect = lambda: self.snapshot.update(route_enabled=True, comments_enabled=True)
        self.assertEqual(self.settle(), "EDITABLE")
        self.button.click.assert_called_once()
        self.assertGreaterEqual(self.now, 1.4)
        self.router.driver.execute_script.assert_not_called()  # no forced checkbox/disabled-field changes

    def test_itc_waits_for_slow_form_beyond_previous_eight_second_deadline(self):
        def read():
            return dict(self.snapshot, route_enabled=self.now >= 12, comments_enabled=self.now >= 12)
        self.router.read_ready_locked_form.side_effect = read
        self.assertEqual(self.router.settle_irt_modify_transition(), "EDITABLE")
        self.assertGreaterEqual(self.now, 12.4)
        self.button.click.assert_not_called()

    def test_confirmed_checked_ready_never_retries_modify(self):
        self.snapshot["ready"] = True
        self.assertEqual(self.settle(), "READY_LOCKED")
        self.button.click.assert_not_called()

    def test_missing_hidden_or_dialog_blocked_ready_cannot_authorize_a_modify_retry(self):
        for change in ({"ready": None}, {"ready_visible": False}, {"blocking_dialog": True}):
            with self.subTest(change=change):
                before = dict(self.snapshot)
                self.snapshot.update(change)
                self.assertEqual(self.settle(timeout=2), "NOT_READY")
                self.button.click.assert_not_called()
                self.snapshot = before

    def test_repeated_ready_alerts_are_bounded_to_two_modify_retries(self):
        self.button.click.side_effect = UnexpectedAlertPresentException(alert_text=READY_WARNING)
        self.assertEqual(self.settle(), "NOT_READY")
        self.assertEqual(self.button.click.call_count, 2)
        self.assertGreaterEqual(self.now, 30)
        self.assertLess(self.now, 31)

    def test_disabled_same_form_retries_are_respected(self):
        self.assertEqual(self.settle(timeout=2, allow_modify_retry=False), "NOT_READY")
        self.button.click.assert_not_called()

    def test_non_itc_retains_existing_wait_and_does_not_gain_ready_warning_retries(self):
        self.router._itc_duplicate_verification = False
        self.assertEqual(self.settle(), "NOT_READY")
        self.assertGreaterEqual(self.now, 8)
        self.assertLess(self.now, 9)
        self.button.click.assert_not_called()

    def test_late_ready_warning_can_recover_the_same_form(self):
        self.router._accept_modify_transition_alerts.side_effect = lambda: [READY_WARNING] if 10 <= self.now < 10.2 else []
        self.button.click.side_effect = lambda: self.snapshot.update(route_enabled=True, comments_enabled=True)
        self.assertEqual(self.router.settle_irt_modify_transition(), "EDITABLE")
        self.assertGreaterEqual(self.now, 10)
        self.button.click.assert_called_once()

    def test_ready_becoming_checked_during_settling_is_verified_instead_of_reclicked(self):
        self.router.read_ready_locked_form.side_effect = lambda: dict(self.snapshot, ready=self.now >= 0.6)
        self.assertEqual(self.settle(), "READY_LOCKED")
        self.button.click.assert_not_called()

    def test_duplicate_after_ready_retry_still_requires_its_delayed_overlay_before_reading_fields(self):
        state = {"warned": False, "cleared": False, "early_reads": 0}
        radio = Mock()
        radio.is_displayed.side_effect = lambda: state["warned"] and self.now >= 5 and not state["cleared"]
        self.router.driver.find_elements.side_effect = lambda by, name: [radio] if name == "processDuplicate" else [self.button] if name == "modify" else []

        def click():
            state["warned"] = True
            raise UnexpectedAlertPresentException(alert_text="This is a duplicate document")

        def read():
            if state["warned"] and not state["cleared"]:
                state["early_reads"] += 1
            return dict(self.snapshot)

        def clear():
            state["cleared"] = True
            self.snapshot.update(route_enabled=True, comments_enabled=True)
            return True

        self.button.click.side_effect = click
        self.router.read_ready_locked_form.side_effect = read
        self.router.handle_duplicate_overlay.side_effect = clear
        self.assertEqual(self.settle(), "EDITABLE")
        self.assertEqual(state["early_reads"], 0)
        self.router.handle_duplicate_overlay.assert_called_once()
        self.assertGreaterEqual(self.now, 5.4)

    def test_missing_duplicate_overlay_after_retry_blocks_all_further_modify_clicks(self):
        self.button.click.side_effect = UnexpectedAlertPresentException(alert_text="This is a duplicate document")
        self.assertEqual(self.settle(), "NOT_READY")
        self.button.click.assert_called_once()
        self.router.handle_duplicate_overlay.assert_not_called()
        self.assertTrue(self.router._modify_transition_incomplete)

    def test_timeout_logs_the_actual_blocked_state_and_requested_lni(self):
        with self.assertLogs(level="WARNING") as logs:
            self.assertEqual(self.settle(timeout=2, allow_modify_retry=False), "NOT_READY")
        text = "\n".join(logs.output)
        for field in (self.router._active_duplicate_lni, "ready=False", "route_enabled=False",
                      "comments_enabled=False", "ready_warning=True", "timeout=2"):
            self.assertIn(field, text)

    def test_initial_modify_lookup_uses_visible_replacement_instead_of_hidden_first_button(self):
        hidden = Mock()
        hidden.is_displayed.return_value = False
        self.router.check_session_validity = Mock(return_value=True)
        self.router.driver.find_elements.side_effect = lambda by, name: [hidden,self.button] if name == "modify" else []
        self.button.click.side_effect = lambda: self.snapshot.update(route_enabled=True,comments_enabled=True)
        button_wait = Mock()
        button_wait.until.side_effect = lambda predicate: predicate(self.router.driver)
        alert_wait = Mock()
        alert_wait.until.side_effect = TimeoutException()
        with patch("core.smducar_router.WebDriverWait",side_effect=[button_wait,alert_wait]):
            self.assertTrue(self.router.attempt_open_modify(max_attempts=1))
        hidden.click.assert_not_called()
        self.button.click.assert_called_once()

    def test_missing_modify_button_logs_state_before_fresh_session_recovery(self):
        self.router.check_session_validity = Mock(return_value=True)
        with patch("core.smducar_router.WebDriverWait") as wait, self.assertLogs(level="WARNING") as logs:
            wait.return_value.until.side_effect = TimeoutException()
            self.assertFalse(self.router.attempt_open_modify(max_attempts=1))
        self.assertIn("phase=Modify button lookup/click", "\n".join(logs.output))
        self.assertIn("ready=False", "\n".join(logs.output))
        self.button.click.assert_not_called()


class ITCFingerprintRecoveryTests(unittest.TestCase):
    def setUp(self):
        itc_content_fingerprint_buffer.clear()
        self.router = CaseLawRouter.__new__(CaseLawRouter)
        self.metadata = ITCMetadata("FDITC000", "337-TA-1527", "10-29-2026", "Opinion", content_fingerprint="fingerprint")
        self.lni = "6KW3-NVD3-SDC5-63YB-00000-00"
        self.row = {"FileName": "itc000_337-1527_20261029.pdf"}

    def tearDown(self):
        itc_content_fingerprint_buffer.clear()

    def test_retry_of_same_lni_is_not_archived_as_a_duplicate_of_itself(self):
        first = self.router.mark_itc_duplicate_status(0, self.row, self.lni, self.metadata)
        retry = self.router.mark_itc_duplicate_status(0, self.row, self.lni.lower(), self.metadata)
        self.assertFalse(first.is_true_duplicate)
        self.assertFalse(retry.is_true_duplicate)
        self.assertEqual(itc_content_fingerprint_buffer["fingerprint"]["lni"], self.lni)

    def test_another_lni_with_same_document_still_gets_duplicate_handling(self):
        self.router.mark_itc_duplicate_status(0, self.row, self.lni, self.metadata)
        result = self.router.mark_itc_duplicate_status(1, self.row, "OTHER-LNI", self.metadata)
        self.assertTrue(result.is_true_duplicate)
        self.assertEqual(result.duplicate_of_lni, self.lni)

    def test_excluded_documents_keep_exclusion_priority_on_retry(self):
        excluded = replace(self.metadata, is_excluded=True)
        result = self.router.mark_itc_duplicate_status(0, self.row, self.lni, excluded)
        self.assertFalse(result.is_true_duplicate)
        self.assertFalse(itc_content_fingerprint_buffer)


if __name__ == "__main__":
    unittest.main()
