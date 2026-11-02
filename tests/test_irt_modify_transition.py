import unittest
from contextlib import ExitStack
from unittest.mock import Mock, PropertyMock, patch

import pandas as pd
from selenium.common.exceptions import NoAlertPresentException, TimeoutException, UnexpectedAlertPresentException

from core.rerun_status import finalize_rerun_ready_statuses, is_completed_status, is_manual_review_status
from core.smducar_config import status_updates_buffer
from core.smducar_router import CaseLawRouter
from core.smducar_workflow import _completed_status_mask


class Clock:
    def __init__(self):
        self.now = 0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class IRTModifyTransitionTests(unittest.TestCase):
    def setUp(self):
        status_updates_buffer.clear()
        self.router = CaseLawRouter.__new__(CaseLawRouter)
        self.router.driver = Mock()
        self.router.driver.find_elements.return_value = []
        self.router.check_session_validity = Mock(return_value=True)
        self.router.handle_duplicate_overlay = Mock(return_value=True)
        self.router.verify_irt_duplicate_overlay = Mock()
        self.router._irt_duplicate_verification_enabled = False
        self.router._accept_modify_transition_alerts = Mock(return_value=[])
        self.snapshot = {"docket": "26-7087", "route": "Inventory Route", "ready": False,
                         "route_enabled": True, "comments_enabled": True, "ready_enabled": True}
        self.router.read_ready_locked_form = Mock(side_effect=lambda: dict(self.snapshot))
        self.stack = ExitStack()
        self.clock = Clock()
        self.stack.enter_context(patch("core.smducar_router.time.monotonic", side_effect=self.clock.monotonic))
        self.stack.enter_context(patch("core.smducar_router.time.sleep", side_effect=self.clock.sleep))

    def tearDown(self):
        self.stack.close()
        status_updates_buffer.clear()

    def click_modify_with_alert(self, text):
        button = Mock()
        alert = Mock(text=text)
        waits = [Mock(until=Mock(return_value=button)), Mock(until=Mock(return_value=alert))]
        with patch("core.smducar_router.WebDriverWait", side_effect=waits):
            result = self.router.attempt_open_modify(max_attempts=1)
        alert.accept.assert_called_once()
        self.assertFalse(self.router._modify_blocked_ready)
        return result

    def schedule_duplicate_overlay(self, delay=3, modify_button=None):
        state = {"cleared": False, "early_reads": 0}
        radio = Mock()
        radio.is_displayed.side_effect = lambda: self.clock.now >= delay and not state["cleared"]
        self.router.driver.find_elements.side_effect = lambda by, field: (
            [radio] if field == "processDuplicate" else [modify_button] if field == "modify" and modify_button else []
        )

        def clear():
            self.assertGreaterEqual(self.clock.now, delay)
            state["cleared"] = True
            return True

        def read_form():
            if not state["cleared"]:
                state["early_reads"] += 1
            return dict(self.snapshot)

        self.router.handle_duplicate_overlay.side_effect = clear
        self.router.read_ready_locked_form.side_effect = read_form
        return state

    def test_duplicate_warning_without_overlay_never_proceeds_despite_editable_fields(self):
        self.assertFalse(self.click_modify_with_alert("This is a duplicate document"))
        self.assertGreaterEqual(self.clock.now, 30)
        self.assertTrue(self.router._modify_transition_incomplete)
        self.assertFalse(self.router._last_transition_duplicate_cleared)
        self.router.handle_duplicate_overlay.assert_not_called()
        self.router.read_ready_locked_form.assert_not_called()
        self.router.verify_irt_duplicate_overlay.assert_not_called()

    def test_duplicate_warning_waits_for_delayed_overlay_even_when_form_looks_editable(self):
        state = self.schedule_duplicate_overlay(delay=3)
        self.assertTrue(self.click_modify_with_alert("This is a duplicate document"))
        self.assertGreaterEqual(self.clock.now, 3.4)
        self.router.handle_duplicate_overlay.assert_called_once()
        self.assertTrue(self.router._last_transition_duplicate_cleared)
        self.assertEqual(state["early_reads"], 0)

    def test_overlay_wait_is_separate_from_the_short_form_settling_timeout(self):
        state = self.schedule_duplicate_overlay(delay=12)
        self.assertEqual(self.router.settle_irt_modify_transition(initial_alerts=["This is a duplicate document"]), "EDITABLE")
        self.assertGreaterEqual(self.clock.now, 12.4)
        self.assertEqual(state["early_reads"], 0)

    def test_itc_mid_form_alert_waits_for_delayed_overlay_before_using_controls(self):
        self.router._itc_field_recovery_active = True
        self.router.accept_pending_alerts = Mock(return_value=(True, True))
        state = self.schedule_duplicate_overlay(delay=5)
        self.assertTrue(self.router.handle_any_alert())
        self.assertGreaterEqual(self.clock.now, 5.4)
        self.assertEqual(state["early_reads"], 0)
        self.router.handle_duplicate_overlay.assert_called_once()

    def test_delayed_overlay_finishes_process_as_new_and_continue_before_form_reads(self):
        state = self.schedule_duplicate_overlay(delay=3)
        events = []
        self.router.handle_duplicate_overlay = lambda: CaseLawRouter.handle_duplicate_overlay(self.router)
        self.router.accept_pending_alerts = Mock(return_value=(False, False))
        self.router.click_duplicate_process_radio = Mock(side_effect=lambda **kwargs: events.append("process-as-new"))
        self.router.click_duplicate_archive_radio = Mock()
        self.router.click_duplicate_continue_button = Mock(side_effect=lambda **kwargs: events.append("continue"))

        def clear(**kwargs):
            events.append("overlay-cleared")
            state["cleared"] = True

        self.router.wait_for_duplicate_overlay_to_clear = Mock(side_effect=clear)
        self.assertTrue(self.click_modify_with_alert("This is a duplicate document"))
        self.assertEqual(events, ["process-as-new", "continue", "overlay-cleared"])
        self.assertEqual(state["early_reads"], 0)
        self.router.verify_irt_duplicate_overlay.assert_not_called()
        self.router.click_duplicate_archive_radio.assert_not_called()

    def test_missing_overlay_cannot_be_misclassified_as_a_ready_locked_record(self):
        self.snapshot.update(ready=True, route="Archive", route_enabled=False, comments_enabled=False)
        self.assertFalse(self.click_modify_with_alert("This is a duplicate document"))
        self.assertFalse(self.router._modify_blocked_ready)
        self.router.read_ready_locked_form.assert_not_called()

    def test_warning_interrupting_modify_click_still_waits_for_required_overlay(self):
        state = self.schedule_duplicate_overlay(delay=3)
        button = Mock()
        button.click.side_effect = UnexpectedAlertPresentException(alert_text="This is a duplicate document")
        with patch("core.smducar_router.WebDriverWait", return_value=Mock(until=Mock(return_value=button))):
            self.assertTrue(self.router.attempt_open_modify(max_attempts=1))
        self.router.handle_duplicate_overlay.assert_called_once()
        self.assertEqual(state["early_reads"], 0)

    def test_missing_overlay_exhausts_safe_reopens_without_filling_or_saving(self):
        row = {"FileName": "smd_26-7087_CADC_10_22_2026_0_151396853.pdf", "LNI": "6KTN-J843-SGX3-C3NB-00000-00", "Decision Date": "10-22-2026"}
        self.router._cleanup_tabs = Mock()
        self.router.refresh_search_inventory_for_retry = Mock(return_value=True)
        self.router.handle_lni_search = Mock(return_value=True)
        self.router.fill_irt_form = Mock()
        self.router.submit_irt_form = Mock()
        button = Mock()
        alert = Mock(text="This is a duplicate document")

        def wait(driver, timeout):
            return Mock(until=Mock(return_value=button if timeout == 120 else alert))

        with patch("core.smducar_router.WebDriverWait", side_effect=wait):
            result = self.router.open_and_process_form(row, pd.DataFrame([row]), 0, "unused.xlsx")
        self.assertEqual(result, "ERROR: IRT FORM NOT EDITABLE AFTER 3 ATTEMPTS")
        self.assertEqual(button.click.call_count, 3)
        self.assertEqual(self.router.refresh_search_inventory_for_retry.call_count, 2)
        self.router.fill_irt_form.assert_not_called()
        self.router.submit_irt_form.assert_not_called()
        self.router.read_ready_locked_form.assert_not_called()

    def test_duplicate_overlay_is_cleared_before_the_form_is_used(self):
        visible = [True]
        radio = Mock()
        radio.is_displayed.side_effect = lambda: visible[0]
        self.router.driver.find_elements.side_effect = lambda by, field: [radio] if field == "processDuplicate" else []

        def clear():
            visible[0] = False
            self.snapshot.update(route_enabled=True, comments_enabled=True)
            return True

        self.snapshot.update(route_enabled=False, comments_enabled=False)
        self.router.handle_duplicate_overlay.side_effect = clear
        self.assertTrue(self.click_modify_with_alert("This is a duplicate document"))
        self.router.handle_duplicate_overlay.assert_called_once()

    def test_ready_rejection_then_delayed_duplicate_with_unchecked_ready_recovers(self):
        self.snapshot.update(route_enabled=False, comments_enabled=False)
        alerts = iter([[], [], ["This is a duplicate document"]])
        self.router._accept_modify_transition_alerts.side_effect = lambda: next(alerts, [])
        retry_button = Mock()
        retry_button.click.side_effect = lambda: self.snapshot.update(route_enabled=True, comments_enabled=True)
        # One unchecked/disabled snapshot precedes the delayed native alert.
        self.schedule_duplicate_overlay(delay=3, modify_button=retry_button)
        read_after_overlay = self.router.read_ready_locked_form.side_effect
        self.router.read_ready_locked_form.side_effect = lambda: dict(self.snapshot) if self.clock.now == 0 else read_after_overlay()
        self.assertTrue(self.click_modify_with_alert("The document cannot be modified (ready to process = [on])"))
        retry_button.click.assert_called_once()

    def test_delayed_duplicate_after_first_alert_wait_timed_out_is_handled(self):
        alerts = iter([[], ["This is a duplicate document"]])
        self.router._accept_modify_transition_alerts.side_effect = lambda: next(alerts, [])
        self.schedule_duplicate_overlay(delay=3)
        waits = [Mock(until=Mock(return_value=Mock())), Mock(until=Mock(side_effect=TimeoutException()))]
        with patch("core.smducar_router.WebDriverWait", side_effect=waits):
            self.assertTrue(self.router.attempt_open_modify(max_attempts=1))
        self.assertFalse(self.router._modify_blocked_ready)

    def test_existing_duplicate_notice_is_cleared_before_modify_lookup(self):
        notices = iter([["This is a duplicate document"]])
        self.router._accept_modify_transition_alerts.side_effect = lambda: next(notices, [])
        self.schedule_duplicate_overlay(delay=3)
        with patch("core.smducar_router.WebDriverWait") as waits:
            self.assertTrue(self.router.attempt_open_modify(max_attempts=1))
        waits.assert_not_called()

    def test_existing_warning_with_missing_overlay_never_clicks_modify_again(self):
        notices = iter([["This is a duplicate document"]])
        self.router._accept_modify_transition_alerts.side_effect = lambda: next(notices, [])
        with patch("core.smducar_router.WebDriverWait") as waits:
            self.assertFalse(self.router.attempt_open_modify(max_attempts=1))
        waits.assert_not_called()
        self.router.read_ready_locked_form.assert_not_called()
        self.assertTrue(self.router._modify_transition_incomplete)

    def test_native_alert_drain_accepts_each_notice_and_stops_when_clear(self):
        first = Mock(text="This is a duplicate document")
        second = Mock(text="DSAR duplicate")
        with patch.object(type(self.router.driver.switch_to), "alert", new_callable=PropertyMock, create=True) as alert:
            alert.side_effect = [first, second, NoAlertPresentException()]
            texts = CaseLawRouter._accept_modify_transition_alerts(self.router)
        self.assertEqual(texts, ["This is a duplicate document", "DSAR duplicate"])
        first.accept.assert_called_once()
        second.accept.assert_called_once()

    def test_alert_arriving_between_dom_inspections_is_recovered(self):
        self.schedule_duplicate_overlay(delay=3)
        read_after_overlay = self.router.read_ready_locked_form.side_effect
        reads = iter([UnexpectedAlertPresentException("This is a duplicate document")])

        def interrupted_read():
            first = next(reads, None)
            if first:
                raise first
            return read_after_overlay()

        self.router.read_ready_locked_form.side_effect = interrupted_read
        alerts = iter([[], ["This is a duplicate document"]])
        self.router._accept_modify_transition_alerts.side_effect = lambda: next(alerts, [])
        self.assertEqual(self.router.settle_irt_modify_transition(), "EDITABLE")
        self.assertTrue(self.router._last_transition_duplicate_cleared)

    def test_duplicate_dismissed_by_chrome_still_requires_the_following_overlay(self):
        self.schedule_duplicate_overlay(delay=3)
        read_after_overlay = self.router.read_ready_locked_form.side_effect
        reads = iter([UnexpectedAlertPresentException(alert_text="This is a duplicate document")])

        def interrupted_read():
            first = next(reads, None)
            if first:
                raise first
            return read_after_overlay()

        self.router.read_ready_locked_form.side_effect = interrupted_read
        self.assertEqual(self.router.settle_irt_modify_transition(), "EDITABLE")
        self.router.handle_duplicate_overlay.assert_called_once()

    def test_confirmed_checked_ready_still_uses_saved_record_verification(self):
        self.snapshot.update(ready=True, route="Archive", route_enabled=False, comments_enabled=False)
        self.assertEqual(self.router.settle_irt_modify_transition(), "READY_LOCKED")

    def test_missing_fields_do_not_prove_a_ready_lock(self):
        self.router.read_ready_locked_form.return_value = None
        self.router.read_ready_locked_form.side_effect = None
        state = self.router.settle_irt_modify_transition(
            initial_alerts=["The document cannot be modified (ready to process = [on])"], timeout=1,
        )
        self.assertEqual(state, "NOT_READY")

    def test_disabled_unchecked_ready_does_not_prove_prior_processing(self):
        self.snapshot.update(route_enabled=False, comments_enabled=False, ready_enabled=False)
        self.assertEqual(self.router.settle_irt_modify_transition(timeout=1), "NOT_READY")

    def test_overlay_failure_never_proceeds_into_the_form(self):
        radio = Mock()
        radio.is_displayed.return_value = True
        self.router.driver.find_elements.return_value = [radio]
        self.router.handle_duplicate_overlay.return_value = False
        self.assertEqual(self.router.settle_irt_modify_transition(), "NOT_READY")

    def test_ready_checkbox_blocked_by_duplicate_requests_normal_form_refill(self):
        button = Mock()
        self.router.handle_any_alert = Mock()
        notices = iter([["This is a duplicate document"]])
        self.router._accept_modify_transition_alerts.side_effect = lambda: next(notices, [])
        self.schedule_duplicate_overlay(delay=3)
        waits = [
            Mock(until=Mock(side_effect=TimeoutException())),
            Mock(until=Mock(return_value=button)),
            Mock(until=Mock(side_effect=TimeoutException())),
            Mock(until=Mock(side_effect=TimeoutException())),
        ]
        with patch("core.smducar_router.WebDriverWait", side_effect=waits):
            result = self.router.click_ready_checkbox_and_check_overlay(False)
        self.assertEqual(result, "DUPLICATE_FORM_RETRY")
        button.click.assert_not_called()

    def test_duplicate_recovery_refills_normal_fields_before_one_save(self):
        row = {"FileName": "smd_26-7087_CADC_Counsel.csv", "LNI": "6KTN-J843-SGX3-C3R4-00000-00", "Decision Date": "10-22-2026"}
        self.router.prepare_common_fields = Mock()
        self.router.find_main_opinion_date_for_counsel = Mock(return_value="10-22-2026")
        self.router.handle_any_alert = Mock()
        self.router.handle_counsel_fields = Mock()
        self.router.wait = Mock()
        self.router.click_ready_checkbox_and_check_overlay = Mock(side_effect=["DUPLICATE_FORM_RETRY", False])
        self.router.handle_routing_and_save = Mock(return_value="DONE")
        with patch("core.smducar_router.WebDriverWait"), patch("core.smducar_router.Select"):
            result = self.router.fill_irt_form(row, pd.DataFrame([row]), 0, "unused.xlsx")
        self.assertEqual(result, "DONE")
        self.assertEqual(self.router.prepare_common_fields.call_count, 2)
        self.assertEqual(self.router.handle_counsel_fields.call_count, 2)
        self.router.handle_routing_and_save.assert_called_once_with(True, 0, skip_route_and_ready=True)

    def test_unavailable_ready_on_fresh_form_is_not_reported_as_already_processed(self):
        row = {"FileName": "smd_26-7087_CADC_Counsel.csv", "LNI": "6KTN-J843-SGX3-C3R4-00000-00", "Decision Date": "10-22-2026"}
        self.router.prepare_common_fields = Mock()
        self.router.find_main_opinion_date_for_counsel = Mock(return_value="10-22-2026")
        self.router.handle_any_alert = Mock()
        self.router.handle_counsel_fields = Mock()
        self.router.wait = Mock()
        self.router.click_ready_checkbox_and_check_overlay = Mock(return_value="READY_NOT_CLICKABLE")
        self.router.handle_routing_and_save = Mock()
        with patch("core.smducar_router.WebDriverWait"), patch("core.smducar_router.Select"):
            result = self.router.fill_irt_form(row, pd.DataFrame([row]), 0, "unused.xlsx")
        self.assertEqual(result, "NON-INTERACTABLE IRT FORM")
        self.assertNotEqual(status_updates_buffer[0], "ALREADY PROCESSED")
        self.router.handle_routing_and_save.assert_not_called()

    def test_main_pdf_duplicate_recovery_restores_counsel_links_and_outside_conversion(self):
        row = {"FileName": "smd_26-7087_CADC_10_22_2026_0_151396853.pdf", "LNI": "6KTN-J843-SGX3-C3NB-00000-00", "Decision Date": "10-22-2026"}
        df = pd.DataFrame([row])
        self.router.prepare_common_fields = Mock()
        self.router.handle_any_alert = Mock()
        self.router.handle_main_opinion_fields = Mock(return_value=None)
        self.router.wait = Mock()
        self.router.click_ready_checkbox_and_check_overlay = Mock(side_effect=["DUPLICATE_FORM_RETRY", False])
        self.router.handle_routing_and_save = Mock(return_value="DONE")
        with patch("core.smducar_router.WebDriverWait"), patch("core.smducar_router.Select") as select:
            result = self.router.fill_irt_form(row, df, 0, "unused.xlsx")
        self.assertEqual(result, "DONE")
        self.assertEqual(self.router.handle_main_opinion_fields.call_count, 2)
        self.router.handle_main_opinion_fields.assert_called_with(row, df, 0, "unused.xlsx", False, False)
        select.return_value.select_by_visible_text.assert_called_with("Outside Conversion")
        self.router.handle_routing_and_save.assert_called_once_with(False, 0, skip_route_and_ready=True)

    def test_duplicate_recovery_is_bounded_and_never_saves_an_unready_form(self):
        row = {"FileName": "smd_26-7087_CADC_Counsel.csv", "LNI": "6KTN-J843-SGX3-C3R4-00000-00", "Decision Date": "10-22-2026"}
        self.router.prepare_common_fields = Mock()
        self.router.find_main_opinion_date_for_counsel = Mock(return_value="10-22-2026")
        self.router.handle_any_alert = Mock()
        self.router.handle_counsel_fields = Mock()
        self.router.wait = Mock()
        self.router.click_ready_checkbox_and_check_overlay = Mock(return_value="DUPLICATE_FORM_RETRY")
        self.router.handle_routing_and_save = Mock()
        with patch("core.smducar_router.WebDriverWait"), patch("core.smducar_router.Select"):
            result = self.router.fill_irt_form(row, pd.DataFrame([row]), 0, "unused.xlsx", dar_mode=True)
        self.assertEqual(result, "ERROR: DUPLICATE FORM RECOVERY FAILED")
        self.assertEqual(self.router.prepare_common_fields.call_count, 2)
        self.router.handle_counsel_fields.assert_called_with(row, True, False)
        self.router.handle_routing_and_save.assert_not_called()

    def test_duplicate_cleared_while_route_is_blocked_refills_fields_before_save(self):
        row = {"FileName": "smd_26-7087_CADC_Counsel.csv", "LNI": "6KTN-J843-SGX3-C3R4-00000-00", "Decision Date": "10-22-2026"}
        self.router.prepare_common_fields = Mock()
        self.router.find_main_opinion_date_for_counsel = Mock(return_value="10-22-2026")
        self.router.handle_any_alert = Mock()
        self.router.handle_counsel_fields = Mock()
        comments, route = Mock(), Mock()
        comments.is_enabled.return_value = True
        route.is_enabled.side_effect = [False, True]
        self.router.wait = Mock()
        self.router.wait.until.side_effect = [comments, route, comments, route]
        self.schedule_duplicate_overlay(delay=3)
        notices = iter([["This is a duplicate document"]])
        self.router._accept_modify_transition_alerts.side_effect = lambda: next(notices, [])
        self.router.click_ready_checkbox_and_check_overlay = Mock(return_value=False)
        self.router.handle_routing_and_save = Mock(return_value="DONE")
        with patch("core.smducar_router.WebDriverWait"), patch("core.smducar_router.Select"):
            result = self.router.fill_irt_form(row, pd.DataFrame([row]), 0, "unused.xlsx")
        self.assertEqual(result, "DONE")
        self.assertEqual(self.router.handle_counsel_fields.call_count, 2)
        self.router.handle_routing_and_save.assert_called_once()

    def test_old_unconfirmed_ready_review_is_eligible_for_rerun(self):
        old = "MANUAL REVIEW REQUIRED - READY TO PROCESS LOCKED: SAVED READY TO PROCESS STATE COULD NOT BE CONFIRMED; ROUTE EXPECTED ARCHIVE, FOUND BLANK/UNAVAILABLE"
        real = "MANUAL REVIEW REQUIRED - READY TO PROCESS LOCKED: ROUTE EXPECTED ARCHIVE, FOUND OUTSIDE CONVERSION"
        df = pd.DataFrame([{"LNI": "A", "Status": old}, {"LNI": "B", "Status": real}, {"LNI": "C", "Status": "DONE"}])
        self.assertFalse(is_completed_status(old))
        self.assertFalse(is_manual_review_status(old))
        self.assertEqual(list(_completed_status_mask(df)), [False, True, True])
        self.assertEqual(finalize_rerun_ready_statuses(df=df)["needs_rerun_count"], 1)
        self.assertEqual(status_updates_buffer[1], real)


if __name__ == "__main__":
    unittest.main()
