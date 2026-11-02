from dataclasses import replace
import unittest
from unittest.mock import Mock, patch

from selenium.common.exceptions import ElementNotInteractableException, TimeoutException, UnexpectedAlertPresentException

from core.itc_extractor import ITCMetadata
from core.irt_duplicate_verifier import IRTDocumentProfile, IRTDuplicateMatch
from core.smducar_config import status_updates_buffer
from core.smducar_router import CaseLawRouter, IRTFormRecoveryError


class ITCFieldRecoveryTests(unittest.TestCase):
    def setUp(self):
        status_updates_buffer.clear()
        self.router = CaseLawRouter.__new__(CaseLawRouter)
        self.router.driver = Mock()
        self.router._itc_field_recovery_active = True
        self.router._itc_field_failure_reason = ""
        self.router.handle_any_alert = Mock(return_value=False)
        self.router._verified_duplicate_match = None

    def tearDown(self):
        status_updates_buffer.clear()

    @staticmethod
    def field(value="", visible=True):
        field = Mock()
        field.is_displayed.return_value = visible
        field.is_enabled.return_value = True
        field.get_attribute.side_effect = lambda name: value if name == "value" else ""
        return field

    def test_hidden_first_control_does_not_hide_visible_editable_replacement(self):
        hidden, visible = self.field(visible=False), self.field()
        self.router.driver.find_elements.return_value = [hidden, visible]
        self.assertIs(self.router.wait_for_itc_editable_control('//*[@id="comments"]'), visible)

    def test_dropdown_retries_and_verifies_fresh_control_after_interruption(self):
        first, fresh = self.field(), self.field("OR")
        self.router.wait_for_itc_editable_control = Mock(side_effect=[first, fresh, fresh])
        self.router.get_selected_dropdown_text = Mock(side_effect=["", "Order"])
        with patch("core.smducar_router.Select") as select:
            select.return_value.select_by_visible_text.side_effect = [UnexpectedAlertPresentException(alert_text="This is a duplicate document"), None]
            self.assertTrue(self.router.select_source_detail("Order"))
        self.assertTrue(any(call.kwargs.get("initial_alert_text") == "This is a duplicate document"
                            for call in self.router.handle_any_alert.call_args_list))
        # Successful existing selection avoids re-firing its native change.
        self.assertEqual(select.return_value.select_by_visible_text.call_count, 1)

    def test_unretained_dropdown_selection_never_reports_success(self):
        self.router.wait_for_itc_editable_control = Mock(return_value=self.field(""))
        self.router.get_selected_dropdown_text = Mock(return_value="")
        with patch("core.smducar_router.Select"):
            self.assertFalse(self.router.select_source_detail("Order"))

    def test_stale_or_non_interactable_control_is_reacquired(self):
        self.router.wait_for_itc_editable_control = Mock(return_value=self.field())
        self.router.get_selected_dropdown_text = Mock(side_effect=["", "", "Order"])
        with patch("core.smducar_router.Select") as select:
            select.return_value.select_by_visible_text.side_effect = [ElementNotInteractableException(), None]
            self.assertTrue(self.router.select_source_detail("Order"))
        self.assertEqual(select.return_value.select_by_visible_text.call_count, 2)
        self.router.driver.execute_script.assert_not_called()  # no second synthetic change event

    def test_comments_are_verified_on_fresh_field_after_alerts(self):
        before, after = self.field("Existing"), self.field("Existing; 39")
        self.router.wait_for_itc_editable_control = Mock(side_effect=[before, after])
        self.assertTrue(self.router.append_comments(["39"], "ITC"))
        before.send_keys.assert_any_call("Existing; 39")
        self.assertEqual(self.router.wait_for_itc_editable_control.call_count, 2)

    def test_lost_comments_do_not_report_success(self):
        self.router.wait_for_itc_editable_control = Mock(side_effect=[self.field(), self.field()])
        with self.assertRaisesRegex(IRTFormRecoveryError, "did not retain"):
            self.router.append_comments(["39"], "ITC")

    def test_order_number_is_not_mistaken_for_a_substring_of_another_number(self):
        before, after = self.field("139"), self.field("139; 39")
        self.router.wait_for_itc_editable_control = Mock(side_effect=[before, after])
        self.assertTrue(self.router.append_comments(["39"], "ITC"))
        before.send_keys.assert_any_call("139; 39")

    def test_every_mid_form_duplicate_requires_a_completed_overlay_and_editable_form(self):
        del self.router.handle_any_alert
        self.router.accept_pending_alerts = Mock(return_value=(True, True))
        self.router.settle_irt_modify_transition = Mock(return_value="EDITABLE")
        self.assertTrue(self.router.handle_any_alert())
        self.assertTrue(self.router.handle_any_alert())
        self.assertEqual(self.router.settle_irt_modify_transition.call_count, 2)

    def test_incomplete_duplicate_workflow_blocks_save_even_if_a_legacy_helper_catches_error(self):
        del self.router.handle_any_alert
        self.router.accept_pending_alerts = Mock(return_value=(True, True))
        self.router.settle_irt_modify_transition = Mock(return_value="NOT_READY")
        with self.assertRaises(IRTFormRecoveryError):
            self.router.handle_any_alert()
        self.assertEqual(self.router.handle_routing_and_save(False, 7), "ERROR: ITC DUPLICATE FORM RECOVERY FAILED")

    def test_true_duplicate_during_source_selection_does_not_resume_normal_field_filling(self):
        metadata = ITCMetadata("FDITCALJ", "337-TA-1477", "09-24-2026", "Order", comments_text="39")
        self.router.wait = Mock()
        self.router.wait_for_existing_field_text = Mock(return_value="RE")
        def selected(_value):
            self.router._verified_duplicate_match = IRTDuplicateMatch("OLD", True, "identical PDF", 1)
            return True
        self.router.select_source_detail = Mock(side_effect=selected)
        self.router.append_comments = Mock()
        self.assertTrue(self.router.handle_itc_fields({}, metadata))
        self.router.append_comments.assert_not_called()

    def test_ready_state_after_this_rows_ready_click_is_verified_later_not_mistaken_for_prior_processing(self):
        del self.router.handle_any_alert
        self.router._itc_ready_attempted = True
        self.router.accept_pending_alerts = Mock(return_value=(True, True))
        self.router.settle_irt_modify_transition = Mock(return_value="READY_LOCKED")
        self.assertTrue(self.router.handle_any_alert())
        self.assertEqual(self.router._itc_field_failure_reason, "")


class ITCDuplicateCandidateTests(unittest.TestCase):
    def setUp(self):
        self.router = CaseLawRouter.__new__(CaseLawRouter)
        self.router.driver = Mock()
        self.router.configure_irt_duplicate_verification(itc_mode=True)
        self.router._active_duplicate_lni = "NEW"
        self.router.accept_pending_alerts = Mock(return_value=(False, False))
        self.router._visible_duplicate_candidate_lnis = Mock(return_value=[])
        self.router._document_profile_for_irt_lni = Mock(side_effect=lambda lni: IRTDocumentProfile(lni, "same", "text"))

    def test_candidate_list_is_retried_after_draining_a_late_native_alert(self):
        self.router._visible_duplicate_candidate_lnis.side_effect = [[], ["OLD"]]
        result = self.router.verify_irt_duplicate_overlay()
        self.assertTrue(result.is_match)
        self.router.accept_pending_alerts.assert_called_once()

    def test_unreadable_candidate_or_missing_list_blocks_process_new_and_save(self):
        self.router._visible_duplicate_candidate_lnis.return_value = ["OLD"]
        self.router._document_profile_for_irt_lni.side_effect = lambda lni: IRTDocumentProfile(lni, "digest", "text") if lni == "NEW" else None
        self.router.click_duplicate_process_radio = Mock()
        self.router.click_duplicate_continue_button = Mock()
        self.assertFalse(self.router.handle_duplicate_overlay())
        self.router.click_duplicate_process_radio.assert_not_called()
        self.router.click_duplicate_continue_button.assert_not_called()
        self.assertTrue(self.router.handle_routing_and_save(False, 0).startswith("MANUAL REVIEW REQUIRED - ITC"))

    def test_missing_candidates_after_bounded_wait_remain_unresolved(self):
        with patch("core.smducar_router.WebDriverWait") as wait:
            wait.return_value.until.side_effect = TimeoutException()
            self.assertIsNone(self.router.verify_irt_duplicate_overlay())
        self.assertIn("candidate LNI could not be confirmed", self.router._itc_duplicate_review_reason)

    def tearDown(self):
        status_updates_buffer.clear()


class ITCBeforeSaveTests(unittest.TestCase):
    def setUp(self):
        self.router = CaseLawRouter.__new__(CaseLawRouter)
        self.router._itc_field_failure_reason = ""
        self.metadata = ITCMetadata("FDITCALJ", "337-TA-1477", "09-24-2026", "Order", comments_text="39")
        self.values = {"docket": "337-TA-1477", "decision_date": "09/24/2026", "source_detail": "Order",
                       "route": "Outside Conversion", "comments": "39", "ready": True}
        self.router.read_ready_locked_form = Mock(side_effect=lambda: dict(self.values))

    def test_matching_values_and_equivalent_date_formats_pass(self):
        self.assertTrue(self.router.verify_itc_values_before_save({}, self.metadata))

    def test_reset_or_wrong_form_fields_block_save(self):
        for key, bad in (("docket", "337-TA-1120"), ("decision_date", "06-08-2020"),
                         ("source_detail", "Opinion"), ("comments", "139"), ("route", "Inventory"), ("ready", False)):
            with self.subTest(key=key):
                original = self.values[key]
                self.values[key] = bad
                self.assertFalse(self.router.verify_itc_values_before_save({}, self.metadata))
                self.values[key] = original

    def test_verified_local_duplicates_keep_archive_route(self):
        self.values["route"] = "Archive"
        self.assertTrue(self.router.verify_itc_values_before_save({}, replace(self.metadata, is_true_duplicate=True)))

    def configure_form(self):
        self.router._archive_duplicate_mode = False
        self.router.driver = Mock()
        self.router.prepare_common_fields = Mock()
        self.router.handle_any_alert = Mock()
        self.router.is_locked_archive_excluded_form = Mock(return_value=False)
        self.router.is_route_locked_already_processed = Mock(return_value=False)
        self.router.handle_itc_fields = Mock(return_value=True)
        self.router.wait = Mock()
        self.router.wait.until.return_value.is_enabled.return_value = True
        self.router.select_dropdown_by_visible_text_or_value = Mock(return_value=True)
        self.router.click_ready_checkbox_and_check_overlay = Mock(return_value=False)
        self.router.handle_routing_and_save = Mock(return_value="DONE")

    def test_full_itc_flow_saves_only_confirmed_fields_and_restores_scoped_recovery(self):
        self.configure_form()
        self.assertEqual(self.router.fill_itc_irt_form({}, 0, self.metadata), "DONE")
        self.router.handle_routing_and_save.assert_called_once()
        self.assertFalse(self.router._itc_field_recovery_active)

    def test_full_itc_flow_does_not_save_reset_fields_or_assume_unavailable_ready_means_processed(self):
        for reset_date in (True, False):
            with self.subTest(reset_date=reset_date):
                self.configure_form()
                if reset_date:
                    self.values["decision_date"] = "06-08-2020"
                else:
                    self.router.click_ready_checkbox_and_check_overlay.return_value = "READY_NOT_CLICKABLE"
                self.assertTrue(self.router.fill_itc_irt_form({}, 0, self.metadata).startswith("ERROR: ITC"))
                self.router.handle_routing_and_save.assert_not_called()
                self.assertFalse(self.router._itc_field_recovery_active)

    def tearDown(self):
        status_updates_buffer.clear()


if __name__ == "__main__":
    unittest.main()
