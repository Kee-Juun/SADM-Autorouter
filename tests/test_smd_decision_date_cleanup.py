import copy
import datetime
import json
import shutil
import subprocess
import unittest
from unittest.mock import Mock, patch

import pandas as pd
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.keys import Keys

from core.critical_error_notifier import _build_success_email_body
from core.rerun_status import (
    STATUS_DATE_UPDATE_UNCONFIRMED,
    STATUS_DECISION_DATE_UPDATED,
    finalize_rerun_ready_statuses,
    is_completed_status,
    should_recheck_smd_decision_date,
    summarize_statuses_for_rows,
)
from core.smducar_config import error_log_entries, status_updates_buffer
from core.smducar_router import CaseLawRouter
from core.smducar_workflow import (
    _completed_status_mask,
    _count_results_for_rows,
    _select_parallel_document_rows,
)


class SMDDecisionDateCleanupTests(unittest.TestCase):
    ROW = {
        "LNI": "6KV9-9YS3-S8KG-939F-00000-00", "CourtCode": "FDUSAPDC",
        "FileName": "LDC_SMD_26-1169_E2E_PCQ.pdf", "Decision Date": "10/23/2026", "Status": "DONE",
    }

    def setUp(self):
        status_updates_buffer.clear()
        error_log_entries.clear()
        self.router = CaseLawRouter.__new__(CaseLawRouter)
        self.router.driver = Mock(current_window_handle="form", window_handles=["inventory", "form"])
        self.router._opened_tab = "form"
        self.router._main_tab = "inventory"
        self.state = {
            "ready": True, "decision_date": "10-25-2026", "docket": "26-1169",
            "record_lni": self.ROW["LNI"], "blocking_dialog": False,
            "protected_fields": {
                "docketNumber": "26-1169", "numberOfPages": "8", "caseName": "Original Case Name",
                "sourceDetails": "Order", "route": "Outside Conversion", "comments": "Original notes",
                "relatedLni": ["existing-counsel-lni"], "tableCases": ["existing-table-case"],
                "readyToProcess": True, "vendorCode": "Original Vendor", "workflow": "Original Workflow",
            },
        }
        self.persisted = copy.deepcopy(self.state)
        self.router.read_smd_date_cleanup_snapshot = Mock(side_effect=lambda: copy.deepcopy(self.state))
        self.router._accept_smd_date_cleanup_alerts = Mock(return_value=[])
        self.router._cleanup_tabs = Mock()
        self.modify = Mock()
        self.save = Mock()
        for button in (self.modify, self.save):
            button.is_displayed.return_value = True
            button.is_enabled.return_value = True
        self.field = Mock()
        self.field.is_enabled.return_value = True
        self.field.is_displayed.return_value = True
        self.field.get_attribute.side_effect = lambda key: None if key == "readonly" else self.state["decision_date"]
        self.field.clear.side_effect = lambda: self.state.update(decision_date="")

        def type_value(value):
            if value != Keys.TAB:
                self.state["decision_date"] += value

        self.field.send_keys.side_effect = type_value
        self.save.click.side_effect = lambda: setattr(self, "persisted", copy.deepcopy(self.state))
        self.router.driver.find_element.side_effect = lambda by, value: {
            "modify": self.modify, "decisionDate": self.field, "add": self.save,
        }[value]

        def reopen(lni):
            self.assertEqual(lni, self.ROW["LNI"])
            self.state = copy.deepcopy(self.persisted)
            self.router._opened_tab = "verified-form"
            return True

        self.router.handle_lni_search = Mock(side_effect=reopen)
        self.router.prepare_common_fields = Mock()
        self.router.fill_irt_form = Mock(return_value="DONE")
        self.router.submit_irt_form = Mock()
        self.router.handle_routing_and_save = Mock()
        self.router.click_ready_checkbox_and_check_overlay = Mock()
        self.router.handle_duplicate_overlay = Mock()
        self.router.attempt_open_modify = Mock(return_value=True)

    def tearDown(self):
        status_updates_buffer.clear()
        error_log_entries.clear()

    def waits(self, driver, timeout):
        def until(condition):
            result = condition(driver)
            if not result:
                raise TimeoutException()
            return result
        return Mock(until=until)

    def update(self, row=None):
        before = copy.deepcopy(self.state)
        with patch("core.smducar_router.WebDriverWait", side_effect=self.waits):
            return self.router.update_smd_processed_decision_date(row or self.ROW, 0, before)

    def assert_no_routing(self):
        for method in (
            self.router.fill_irt_form, self.router.prepare_common_fields, self.router.handle_routing_and_save,
            self.router.click_ready_checkbox_and_check_overlay, self.router.handle_duplicate_overlay,
            self.router.submit_irt_form,
        ):
            method.assert_not_called()

    def test_date_only_save_reopens_and_verifies_all_other_values(self):
        original = copy.deepcopy(self.state["protected_fields"])
        self.assertEqual(self.update(), STATUS_DECISION_DATE_UPDATED)
        self.assertEqual(self.persisted["decision_date"], "10-23-2026")
        self.assertEqual(self.persisted["protected_fields"], original)
        self.modify.click.assert_called_once()
        self.field.clear.assert_called_once()
        self.field.send_keys.assert_any_call("10-23-2026")
        self.save.click.assert_called_once()
        self.router.handle_lni_search.assert_called_once_with(self.ROW["LNI"])
        self.assertEqual(status_updates_buffer[0], STATUS_DECISION_DATE_UPDATED)
        self.assert_no_routing()

    def test_counsel_cleanup_uses_its_explicit_sheet_date(self):
        row = {**self.ROW, "FileName": "LDC_SMD_26-1169counsel_E2E.htm"}
        self.state["protected_fields"]["route"] = "Archive"
        self.assertEqual(self.update(row), STATUS_DECISION_DATE_UPDATED)
        self.assertEqual(self.persisted["protected_fields"]["route"], "Archive")
        self.assert_no_routing()

    def test_equivalent_dates_are_skipped_without_modify_typing_or_save(self):
        for requested in ("10/25/2026", "2026-10-25", datetime.date(2026, 10, 25)):
            with self.subTest(requested=requested):
                self.assertEqual(self.update({**self.ROW, "Decision Date": requested}), "ALREADY PROCESSED")
        self.modify.click.assert_not_called()
        self.field.clear.assert_not_called()
        self.save.click.assert_not_called()

    def test_invalid_or_missing_date_never_uses_received_or_filename_fallback(self):
        for value in (None, "", "bad date", "02/30/2026"):
            with self.subTest(value=value):
                self.assertTrue(self.update({**self.ROW, "Decision Date": value}).startswith("MANUAL REVIEW REQUIRED"))
        self.modify.click.assert_not_called()
        self.field.clear.assert_not_called()
        self.save.click.assert_not_called()

    def test_locked_field_is_not_force_enabled(self):
        self.field.is_enabled.return_value = False
        self.assertIn("remains locked", self.update())
        self.field.clear.assert_not_called()
        self.save.click.assert_not_called()
        self.router.driver.execute_script.assert_not_called()

    def test_readonly_field_is_not_changed(self):
        self.field.get_attribute.return_value = "true"
        self.field.get_attribute.side_effect = None
        self.assertIn("remains locked", self.update())
        self.field.clear.assert_not_called()
        self.save.click.assert_not_called()

    def test_wrong_docket_wrong_lni_or_unprocessed_record_are_not_changed(self):
        original = copy.deepcopy(self.state)
        for overrides in ({"docket": "26-5168"}, {"record_lni": "other-lni"}, {"record_lni": None}, {"ready": False}, {"blocking_dialog": True}):
            with self.subTest(overrides=overrides):
                self.state = {**copy.deepcopy(original), **overrides}
                self.assertTrue(self.update().startswith("MANUAL REVIEW REQUIRED"))
        self.modify.click.assert_not_called()
        self.save.click.assert_not_called()

    def test_other_field_change_after_modify_prevents_save(self):
        self.modify.click.side_effect = lambda: self.state["protected_fields"].update(route="Archive")
        self.assertIn("another form value", self.update())
        self.field.clear.assert_not_called()
        self.save.click.assert_not_called()

    def test_date_event_changing_other_values_prevents_save(self):
        self.field.send_keys.side_effect = lambda value: self.state["protected_fields"].update(comments="Unexpected change")
        self.assertIn("another form value", self.update())
        self.save.click.assert_not_called()

    def test_duplicate_dialog_does_not_enter_routing_workflow(self):
        self.router._accept_smd_date_cleanup_alerts.return_value = ["This is a duplicate document"]
        self.assertIn("duplicate notice", self.update())
        self.field.clear.assert_not_called()
        self.save.click.assert_not_called()
        self.assert_no_routing()

    def test_ready_lock_notice_may_still_allow_native_date_correction(self):
        self.router._accept_smd_date_cleanup_alerts.side_effect = [["Cannot modify ready to process = [on]"], [], []]
        self.assertEqual(self.update(), STATUS_DECISION_DATE_UPDATED)

    def test_changed_input_without_server_persistence_is_not_success(self):
        self.save.click.side_effect = None  # Server retains the original date.
        self.assertEqual(self.update(), STATUS_DATE_UPDATE_UNCONFIRMED)
        self.assertNotEqual(status_updates_buffer[0], STATUS_DECISION_DATE_UPDATED)
        self.save.click.assert_called_once()

    def test_save_rejection_or_click_exception_is_never_already_processed(self):
        self.router._accept_smd_date_cleanup_alerts.side_effect = [[], [], ["Invalid decision date"]]
        self.assertEqual(self.update(), STATUS_DATE_UPDATE_UNCONFIRMED)
        self.save.click.assert_called_once()

    def test_cannot_reopen_saved_record_is_unconfirmed(self):
        self.router.handle_lni_search.side_effect = None
        self.router.handle_lni_search.return_value = False
        self.assertEqual(self.update(), STATUS_DATE_UPDATE_UNCONFIRMED)

    def test_prior_unconfirmed_save_is_not_silently_relabelled_successful(self):
        self.state["decision_date"] = "10-23-2026"
        result = self.update({**self.ROW, "Status": STATUS_DATE_UPDATE_UNCONFIRMED})
        self.assertIn("previously unconfirmed Save", result)
        self.modify.click.assert_not_called()
        self.save.click.assert_not_called()

    def test_save_click_exception_is_unconfirmed_and_not_retried(self):
        self.save.click.side_effect = RuntimeError("connection lost after click")
        self.assertEqual(self.update(), STATUS_DATE_UPDATE_UNCONFIRMED)
        self.save.click.assert_called_once()

    def test_other_server_values_changing_after_save_is_reported(self):
        def save_with_unexpected_change():
            self.persisted = copy.deepcopy(self.state)
            self.persisted["protected_fields"]["route"] = "Archive"
        self.save.click.side_effect = save_with_unexpected_change
        self.assertEqual(self.update(), STATUS_DATE_UPDATE_UNCONFIRMED)

    def test_completed_row_uses_cleanup_instead_of_normal_form_fill(self):
        df = pd.DataFrame([self.ROW])
        with patch("core.smducar_router.WebDriverWait", side_effect=self.waits):
            status = self.router.open_and_process_form(df.loc[0], df, 0, "unused.xlsx")
        self.assertEqual(status, STATUS_DECISION_DATE_UPDATED)
        self.router.attempt_open_modify.assert_not_called()
        self.assert_no_routing()

    def test_fresh_sheet_also_detects_an_already_processed_irt_record(self):
        row = {**self.ROW, "Status": ""}
        df = pd.DataFrame([row])
        with patch("core.smducar_router.WebDriverWait", side_effect=self.waits):
            self.assertEqual(self.router.open_and_process_form(row, df, 0, "unused.xlsx"), STATUS_DECISION_DATE_UPDATED)
        self.assert_no_routing()

    def reveal_processed_state_after_modify(self):
        self.state["ready"] = False
        self.state["protected_fields"]["readyToProcess"] = False

        def modify(**kwargs):
            self.modify.click()
            self.state["ready"] = True
            self.state["protected_fields"]["readyToProcess"] = True
            self.router._modify_blocked_ready = True
            return False

        self.router.attempt_open_modify.side_effect = modify
        self.router.verify_ready_locked_form = Mock(side_effect=AssertionError("must use date cleanup, not mismatch-only verification"))

    def test_date_cleanup_also_starts_when_modify_first_reveals_ready_lock(self):
        self.reveal_processed_state_after_modify()
        row = {**self.ROW, "Status": ""}
        with patch("core.smducar_router.WebDriverWait", side_effect=self.waits):
            result = self.router.open_and_process_form(row, pd.DataFrame([row]), 0, "unused.xlsx")
        self.assertEqual(result, STATUS_DECISION_DATE_UPDATED)
        self.modify.click.assert_called_once()
        self.save.click.assert_called_once()
        self.assert_no_routing()

    def test_completed_sheet_row_can_reveal_ready_only_after_modify(self):
        self.reveal_processed_state_after_modify()
        df = pd.DataFrame([self.ROW])
        with patch("core.smducar_router.WebDriverWait", side_effect=self.waits):
            self.assertEqual(self.router.open_and_process_form(self.ROW, df, 0, "unused.xlsx"), STATUS_DECISION_DATE_UPDATED)
        self.modify.click.assert_called_once()
        self.assert_no_routing()

    def test_exact_counsel_date_mismatch_from_0312_run_is_cleanup_eligible(self):
        self.ROW = {
            **self.ROW, "LNI": "6KV9-9YS3-S8KG-939Y-00000-00",
            "FileName": "LDC_SMD_26-1169counsel_E2E.htm", "Decision Date": pd.Timestamp("2026-10-23"),
            "Status": "MANUAL REVIEW REQUIRED - READY TO PROCESS LOCKED: DECISION DATE EXPECTED 10-23-2026, FOUND 10-25-2026",
        }
        self.state["record_lni"] = self.ROW["LNI"]
        self.state["protected_fields"]["route"] = "Archive"
        self.state["protected_fields"]["comments"] = "6KV9-9YS3-S8KG-939F-00000-00"
        self.reveal_processed_state_after_modify()
        df = pd.DataFrame([self.ROW])
        self.assertFalse(_completed_status_mask(df, smd_date_cleanup=True).iloc[0])
        with patch("core.smducar_router.WebDriverWait", side_effect=self.waits):
            result = self.router.open_and_process_form(self.ROW, df, 0, "unused.xlsx")
        self.assertEqual(result, STATUS_DECISION_DATE_UPDATED)
        self.assertEqual(self.persisted["decision_date"], "10-23-2026")
        self.assertEqual(self.persisted["protected_fields"]["route"], "Archive")
        self.assertEqual(self.persisted["protected_fields"]["comments"], "6KV9-9YS3-S8KG-939F-00000-00")
        self.modify.click.assert_called_once()
        self.save.click.assert_called_once()
        self.assert_no_routing()

    def test_non_date_change_after_late_ready_detection_still_prevents_save(self):
        self.reveal_processed_state_after_modify()
        modify = self.router.attempt_open_modify.side_effect

        def modify_with_changed_route(**kwargs):
            result = modify()
            self.state["protected_fields"]["route"] = "Archive"
            return result

        self.router.attempt_open_modify.side_effect = modify_with_changed_route
        row = {**self.ROW, "Status": ""}
        with patch("core.smducar_router.WebDriverWait", side_effect=self.waits):
            self.assertIn("another form value", self.router.open_and_process_form(row, pd.DataFrame([row]), 0, "unused.xlsx"))
        self.field.clear.assert_not_called()
        self.save.click.assert_not_called()

    def test_completed_row_never_falls_back_to_full_routing_when_still_not_ready(self):
        self.state["ready"] = False
        df = pd.DataFrame([self.ROW])
        self.assertTrue(self.router.open_and_process_form(self.ROW, df, 0, "unused.xlsx").startswith("MANUAL REVIEW REQUIRED"))
        self.assert_no_routing()

    def test_delayed_form_load_is_awaited_before_date_cleanup(self):
        reads = [0]

        def delayed_snapshot():
            reads[0] += 1
            return None if reads[0] == 1 else copy.deepcopy(self.state)

        self.router.read_smd_date_cleanup_snapshot.side_effect = delayed_snapshot
        df = pd.DataFrame([self.ROW])
        with patch("core.smducar_router.WebDriverWait", side_effect=self.waits):
            self.assertEqual(self.router.open_and_process_form(self.ROW, df, 0, "unused.xlsx"), STATUS_DECISION_DATE_UPDATED)
        self.assert_no_routing()

    def test_new_unprocessed_record_retains_normal_processing(self):
        row = {**self.ROW, "Status": ""}
        self.state["ready"] = False
        self.assertEqual(self.router.open_and_process_form(row, pd.DataFrame([row]), 0, "unused.xlsx"), "DONE")
        self.router.fill_irt_form.assert_called_once()
        self.modify.click.assert_not_called()

    def test_dara_does_not_enter_smd_cleanup(self):
        self.assertEqual(self.router.open_and_process_form(self.ROW, pd.DataFrame([self.ROW]), 0, "unused.xlsx", dar_mode=True), "DONE")
        self.router.fill_irt_form.assert_called_once()
        self.modify.click.assert_not_called()

    def test_completed_batch_row_reaches_date_cleanup_without_rerouting(self):
        row = pd.Series(self.ROW)
        df = pd.DataFrame([row])
        self.router.safe_alert_accept = Mock()
        self.router.configure_irt_duplicate_verification = Mock()
        self.router.validate_row = Mock(return_value=self.ROW["LNI"])
        self.router._should_refresh_retry_form_status = Mock(return_value=False)
        with patch("core.smducar_router.WebDriverWait", side_effect=self.waits):
            count, _ = self.router.process_batch(df, df, "unused.xlsx", None, "main")
        self.assertEqual(count, 0)
        self.assertEqual(status_updates_buffer[0], STATUS_DECISION_DATE_UPDATED)
        self.assert_no_routing()

    def test_readback_uses_the_real_tab_cleanup_without_losing_inventory(self):
        self.router._cleanup_tabs = CaseLawRouter._cleanup_tabs.__get__(self.router)
        self.router.driver.switch_to.window.side_effect = lambda tab: setattr(self.router.driver, "current_window_handle", tab)
        self.router.driver.close.side_effect = lambda: self.router.driver.window_handles.remove(self.router.driver.current_window_handle)

        def reopen(lni):
            self.assertEqual(self.router.driver.current_window_handle, "inventory")
            self.state = copy.deepcopy(self.persisted)
            self.router.driver.window_handles.append("verified-form")
            self.router.driver.current_window_handle = "verified-form"
            self.router._opened_tab = "verified-form"
            self.router._main_tab = "inventory"
            return True

        self.router.handle_lni_search.side_effect = reopen
        df = pd.DataFrame([self.ROW])
        with patch("core.smducar_router.WebDriverWait", side_effect=self.waits):
            self.assertEqual(self.router.open_and_process_form(self.ROW, df, 0, "unused.xlsx"), STATUS_DECISION_DATE_UPDATED)
        self.assertEqual(self.router.driver.window_handles, ["inventory"])
        self.assertEqual(self.router.driver.current_window_handle, "inventory")
        self.assert_no_routing()

    def test_dara_completed_batch_remains_skipped(self):
        df = pd.DataFrame([self.ROW])
        self.router.safe_alert_accept = Mock()
        self.router.configure_irt_duplicate_verification = Mock()
        self.router.validate_row = Mock(return_value=self.ROW["LNI"])
        count, _ = self.router.process_batch(df, df, "unused.xlsx", None, "main", dar_mode=True)
        self.assertEqual(count, 0)
        self.router.validate_row.assert_not_called()
        self.modify.click.assert_not_called()
        self.save.click.assert_not_called()


class SMDDateCleanupSelectionTests(unittest.TestCase):
    def tearDown(self):
        status_updates_buffer.clear()
        error_log_entries.clear()

    def test_completed_date_requests_are_eligible_only_in_smd_mode(self):
        df = pd.DataFrame([
            {**SMDDecisionDateCleanupTests.ROW, "Status": status}
            for status in ("DONE", "ALREADY PROCESSED", STATUS_DECISION_DATE_UPDATED, "MANUAL REVIEW REQUIRED - docket mismatch")
        ])
        self.assertEqual(list(_completed_status_mask(df)), [True] * 4)
        self.assertEqual(list(_completed_status_mask(df, smd_date_cleanup=True)), [False, False, False, True])
        self.assertFalse(should_recheck_smd_decision_date(df.loc[0]))

    def test_blank_date_completed_rows_remain_skipped(self):
        for value in (None, "", float("nan"), pd.NaT):
            with self.subTest(value=value):
                self.assertFalse(should_recheck_smd_decision_date({**SMDDecisionDateCleanupTests.ROW, "Decision Date": value}, smd_mode=True))

    def test_cleanup_does_not_schedule_counsel_dependencies(self):
        df = pd.DataFrame([
            SMDDecisionDateCleanupTests.ROW,
            {**SMDDecisionDateCleanupTests.ROW, "FileName": "LDC_SMD_26-1169counsel_E2E.htm", "LNI": "counsel-lni", "Status": "", "Decision Date": None},
        ])
        self.assertEqual(list(_select_parallel_document_rows(df, df, 1).index), [0])
        self.assertEqual(list(_select_parallel_document_rows(df, df, 0, dar_mode=True).index), [1])

    def test_date_updates_are_completed_and_reported_without_new_routing(self):
        df = pd.DataFrame([SMDDecisionDateCleanupTests.ROW])
        status_updates_buffer[0] = STATUS_DECISION_DATE_UPDATED
        self.assertTrue(is_completed_status(STATUS_DECISION_DATE_UPDATED))
        summary = finalize_rerun_ready_statuses(df=df)
        self.assertEqual(summary["decision_date_updated_count"], 1)
        self.assertEqual(summary["done_count"], 0)
        self.assertEqual(summary["needs_rerun_count"], 0)
        self.assertEqual(_count_results_for_rows(df, False, False, False, current_run_only=True), (0, 0, 0, 1, 0, 0))
        theme = {"hello": "Hello", "opener": "{app_name}", "scoreboard": "Results", "attachments": "Reports", "closer": "Done"}
        body = _build_success_email_body("smd", {"main_already": 1}, "reports", theme, run_status_summary=summary)
        self.assertIn("Decision dates updated (no new routing): 1", body)
        self.assertIn("Total routed: 0", body)

    def test_other_router_rows_are_not_date_cleanup_candidates(self):
        for court in ("FDIRSPLR", "FDPLR000", "FDCCA001", "FDFCC000", "FDFERC00", "FDNLRB00", "FDMSPB00", "STOHTAX0", "STMEWORK", "MOSU00"):
            with self.subTest(court=court):
                row = {**SMDDecisionDateCleanupTests.ROW, "CourtCode": court}
                self.assertFalse(should_recheck_smd_decision_date(row, smd_mode=True))

    def test_ambiguous_save_stays_rerun_eligible(self):
        df = pd.DataFrame([{**SMDDecisionDateCleanupTests.ROW, "Status": STATUS_DATE_UPDATE_UNCONFIRMED}])
        self.assertFalse(_completed_status_mask(df, smd_date_cleanup=True).iloc[0])
        self.assertTrue(should_recheck_smd_decision_date(df.loc[0], smd_mode=True))
        summary = summarize_statuses_for_rows(df)
        self.assertEqual(summary["needs_rerun_count"], 1)


@unittest.skipUnless(shutil.which("node"), "Node is required to exercise the DOM snapshot script")
class SMDDateCleanupSnapshotTests(unittest.TestCase):
    def test_snapshot_protects_business_values_but_not_date_or_transport_tokens(self):
        router = CaseLawRouter.__new__(CaseLawRouter)
        router.driver = Mock()
        router.read_smd_date_cleanup_snapshot()
        script = router.driver.execute_script.call_args.args[0]
        runner = r"""
            const assert = require('node:assert/strict');
            const script = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
            const field = (id, value, type='text') => ({id, name:id, value, type, tagName:'INPUT', checked:false});
            const controls = [field('documentLNI','6KV9-9YS3-S8KG-939F-00000-00','hidden'),
                field('readyToProcess','on','checkbox'), field('decisionDate','10-25-2026'),
                field('docketNumber','26-1169'), field('comments','Original note'),
                field('command','view','hidden'), field('documentHistory','Original audit')];
            controls[1].checked = true;
            const labels = [];
            global.document = {
                getElementById: id => controls.find(control => control.id === id),
                querySelectorAll: selector => selector === 'input, select, textarea' ? controls
                    : selector === 'label, td, th' ? labels : []
            };
            const snapshot = new Function(script);
            const before = snapshot();
            assert.equal(before.record_lni, controls[0].value);
            assert.equal(before.ready, true);
            controls[2].value = '10-23-2026';
            controls[5].value = 'update';
            controls[6].value = 'New audit entry';
            assert.deepEqual(snapshot().protected_fields, before.protected_fields);
            assert.equal(snapshot().decision_date, '10-23-2026');
            controls[4].value = 'Unexpected comment';
            assert.notDeepEqual(snapshot().protected_fields, before.protected_fields);
            controls[0].value = '';
            labels.push({textContent:'Document LNI:', nextElementSibling:{textContent:'6KV9-9YS3-S8KG-939F-00000-00'}});
            assert.equal(snapshot().record_lni, '6KV9-9YS3-S8KG-939F-00000-00');
            console.log('DOM snapshot checks passed');
        """
        result = subprocess.run([shutil.which("node"), "-e", runner], input=json.dumps(script), capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
