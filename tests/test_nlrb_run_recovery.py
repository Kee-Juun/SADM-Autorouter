"""Regressions from the October 31 NLRB run; no live IRT or email access."""
import threading
import unittest
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pandas as pd

from core.nlrb_extractor import parse_nlrb_document_text
from core.smducar_config import error_log_entries, mspb_metadata_buffer, status_updates_buffer
from core.smducar_router import CaseLawRouter
from core.smducar_workflow import (
    _recover_itc_pre_save_failures, _run_parallel_document_phase,
    _run_parallel_document_workflow, run_automation_workflow,
)
from test_itc_first_run_recovery import ITCModifyRecoveryTests as _ModifyCases
from test_router_mode_selection import load_ui_method

MODULE = "core.smducar_workflow."
FORM_FAILURE = "ERROR: IRT FORM NOT EDITABLE AFTER 3 ATTEMPTS"


class NLRBModifyRecoveryTests(_ModifyCases):
    """Exercise the existing shared recovery cases with NLRB policy active."""
    def setUp(self):
        super().setUp()
        self.router._itc_duplicate_verification = False
        self.router.configure_irt_duplicate_verification(nlrb_mode=True)
        self.snapshot["docket"] = "19-CA-352644"

    def test_non_itc_retains_existing_wait_and_does_not_gain_ready_warning_retries(self):
        self.router.configure_irt_duplicate_verification()
        super().test_non_itc_retains_existing_wait_and_does_not_gain_ready_warning_retries()


# unittest discovers imported TestCase classes, too; retain only the subclass.
del _ModifyCases


class NLRBDateAndHeadingTests(unittest.TestCase):
    def test_signature_year_joined_to_line_number_beats_historical_date(self):
        metadata = parse_nlrb_document_text(
            "JD-73-26\nCase 19-CA-352644\nDECISION\n"
            "On July 13, 2023, the employer met.\n"
            "ORDER5\nThe complaint is dismissed.\n"
            "Dated Washington, D.C. October 30, 202610\n"
            "Robert A. Ringler 15\nAdministrative Law Judge"
        )
        self.assertEqual(metadata.decision_date, "10-30-2026")
        self.assertEqual(metadata.source_detail, "OP")
        self.assertFalse(metadata.requires_review)

    def test_footnote_on_order_heading_still_routes_as_order(self):
        for heading in ("ORDER1", "ORDER¹", "ORDER 1"):
            with self.subTest(heading=heading):
                metadata = parse_nlrb_document_text(
                    f"Case 20-CA-370300\n{heading}\nThe motion is denied.\n"
                    "Dated, Washington, D.C., October 30, 2026."
                )
                self.assertEqual(metadata.source_detail, "OR")
                self.assertFalse(metadata.requires_review)

    def test_history_without_signature_date_requires_user_to_supply_date(self):
        metadata = parse_nlrb_document_text(
            "Case 19-CA-352644\nDECISION\nOn July 13, 2023, a meeting was held."
        )
        self.assertEqual(metadata.decision_date, "")
        self.assertIn("MISSING DECISION DATE", metadata.review_status)

    def test_invalid_signature_is_not_replaced_by_history_or_filename_date(self):
        metadata = parse_nlrb_document_text(
            "Case 19-CA-352644\nDECISION\nOn July 13, 2023, a meeting was held.\n"
            "Dated Washington, D.C. February 30, 202610",
            filename_hint="19-CA-352644_20261030.pdf",
        )
        self.assertEqual(metadata.decision_date, "")
        self.assertTrue(metadata.requires_review)

    def test_primary_signature_precedes_an_attached_older_decision(self):
        metadata = parse_nlrb_document_text(
            "Case 19-CA-352644\nDECISION\n"
            "Dated Washington, D.C. October 30, 2026\n"
            "Attached prior decision\nDated Washington, D.C. July 13, 2023"
        )
        self.assertEqual(metadata.decision_date, "10-30-2026")


class NLRBWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.clear_buffers()
        self.df = pd.DataFrame([
            {"LNI": f"6KW5-WG23-S2GH-V42{i}-00000-00", "CourtCode": "FDNLRB00",
             "FileName": f"LDC_BC_05-CA-{300000+i}.pdf", "Status": ""}
            for i in range(8)
        ])

    def tearDown(self):
        self.clear_buffers()

    @staticmethod
    def clear_buffers():
        status_updates_buffer.clear()
        mspb_metadata_buffer.clear()
        error_log_entries.clear()

    @staticmethod
    def reporting_mocks(stack):
        for name in ("flush_status_updates", "notify_for_critical_statuses", "notify_successful_run",
                     "notify_critical_error", "_write_error_report_if_needed", "start_critical_error_run"):
            stack.enter_context(patch(MODULE+name))
        stack.enter_context(patch(MODULE+"get_full_username", return_value="Test User"))
        stack.enter_context(patch(MODULE+"_resolve_chromedriver_path", return_value="driver"))

    def test_entry_point_honors_parallel_setting_and_excludes_other_courts_and_completed_rows(self):
        self.df.loc[0, "Status"] = "DONE"
        self.df.loc[1, "CourtCode"] = "FDFCC000"
        with ExitStack() as stack:
            self.reporting_mocks(stack)
            stack.enter_context(patch(MODULE+"load_config", return_value={
                "parallel_routers_enabled": True, "parallel_router_instances": 6}))
            parallel = stack.enter_context(patch(MODULE+"_run_parallel_document_workflow", return_value=(None, None)))
            browser = stack.enter_context(patch(MODULE+"ChromeWebDriver"))
            run_automation_workflow(df=self.df, latest_excel="unused.xlsx", nlrb_mode=True)
        parallel.assert_called_once()
        self.assertTrue(parallel.call_args.kwargs["nlrb_mode"])
        self.assertEqual(list(parallel.call_args.kwargs["df_filtered"].index), list(range(2, 8)))
        self.assertEqual(parallel.call_args.kwargs["config"]["parallel_router_instances"], 6)
        browser.assert_not_called()

    def test_six_workers_get_disjoint_rows_downloads_and_aggregated_progress(self):
        barrier = threading.Barrier(6, timeout=5)
        lock = threading.Lock()
        assignments = []
        routers = []
        drivers = []
        progress = Mock()

        def browser(*args):
            driver = Mock()
            with lock:
                drivers.append(driver)
            return driver

        def create_router(driver, **kwargs):
            router = Mock()
            def process(chunk, full, path, callback, batch, *args, **modes):
                self.assertEqual(batch, "nlrb")
                self.assertTrue(modes["nlrb_mode"])
                with lock:
                    assignments.append(list(chunk.index))
                barrier.wait()  # all six workers must actually coexist
                for count in range(len(chunk)+1):
                    callback(batch, count, len(chunk))
                return len(chunk), 1
            router.process_batch.side_effect = process
            with lock:
                routers.append(router)
            return router

        with ExitStack() as stack:
            stack.enter_context(patch(MODULE+"Path.home", return_value=Path("C:/mock-nlrb-home")))
            stack.enter_context(patch(MODULE+"Path.mkdir"))
            stack.enter_context(patch(MODULE+"_build_chrome_options"))
            stack.enter_context(patch(MODULE+"_create_chrome_driver", side_effect=browser))
            stack.enter_context(patch(MODULE+"_navigate_with_retries"))
            stack.enter_context(patch(MODULE+"_open_search_inventory_with_recovery", return_value=True))
            stack.enter_context(patch(MODULE+"_write_router_split_workbook"))
            count, _ = _run_parallel_document_phase(
                "nlrb", self.df, self.df, "unused.xlsx", {}, "driver", "url", 6,
                progress, create_router, None, None, False, False, "NLRB", nlrb_mode=True)
        self.assertEqual(count, 8)
        self.assertEqual(len(drivers), 6)
        self.assertEqual(sorted(i for chunk in assignments for i in chunk), list(range(8)))
        self.assertEqual(len({str(router.nlrb_download_dir) for router in routers}), 6)
        for driver in drivers:
            driver.quit.assert_called_once()
        for router in routers:
            self.assertTrue(router.configure_irt_duplicate_verification.call_args.kwargs["nlrb_mode"])
        values = [call.args[1] for call in progress.call_args_list]
        self.assertEqual(values, sorted(values))
        self.assertEqual(progress.call_args.args, ("nlrb", 8, 8))

    def test_pre_save_recovery_is_bounded_and_does_not_retry_review_or_uncertain_save(self):
        status_updates_buffer.update({0: FORM_FAILURE, 1: "MANUAL REVIEW REQUIRED - missing date",
                                      2: "ERROR: SAVE UNCONFIRMED", 3: "DONE"})
        def phase(*args, **kwargs):
            self.assertEqual(args[0], "nlrb")
            self.assertEqual(list(args[1].index), [0])
            self.assertEqual(args[7], 1)
            self.assertIsNone(args[8])
            self.assertTrue(args[4]["_nlrb_fresh_recovery"])
            self.assertTrue(kwargs["nlrb_mode"])
            status_updates_buffer[0] = "DONE"
            return 1, 5
        config = {}
        with patch(MODULE+"_run_parallel_document_phase", side_effect=phase) as run:
            _recover_itc_pre_save_failures(self.df, self.df, "unused.xlsx", config, "driver", "url", 6, nlrb_mode=True)
            status_updates_buffer[0] = FORM_FAILURE
            _recover_itc_pre_save_failures(self.df, self.df, "unused.xlsx", {"_nlrb_fresh_recovery": True}, "driver", "url", 6, nlrb_mode=True)
        run.assert_called_once()
        self.assertEqual(config, {})

    def test_parallel_workflow_recovers_before_reporting_and_uses_nlrb_summary(self):
        success = Mock()
        def phase(*args, **kwargs):
            self.assertEqual(args[0], "nlrb")
            self.assertTrue(kwargs["nlrb_mode"])
            if args[4].get("_nlrb_fresh_recovery"):
                status_updates_buffer[0] = "DONE"
                return 1, 1
            status_updates_buffer.update({idx: "DONE" for idx in self.df.index})
            status_updates_buffer[0] = FORM_FAILURE
            return 7, 7
        with ExitStack() as stack:
            self.reporting_mocks(stack)
            run = stack.enter_context(patch(MODULE+"_run_parallel_document_phase", side_effect=phase))
            _run_parallel_document_workflow(df=self.df, latest_excel="unused.xlsx", nlrb_mode=True,
                                            config={"parallel_router_instances": 6}, show_success=success)
        self.assertEqual(run.call_count, 2)
        self.assertEqual(run.call_args_list[0].args[7], 6)
        self.assertEqual(success.call_args.args[2], 8)
        self.assertEqual(success.call_args.args[-1]["needs_rerun_count"], 0)

    def test_progress_reaches_ui_for_success_skips_and_errors(self):
        router = CaseLawRouter.__new__(CaseLawRouter)
        router.driver = Mock()
        router.safe_alert_accept = Mock()
        router.validate_row = Mock(side_effect=lambda row, index, path: row["LNI"])
        router.search_lni = Mock(side_effect=[True, True, False])
        router.check_result_available = Mock(return_value=True)
        router.click_matching_result = Mock()
        metadata = parse_nlrb_document_text("Case 19-CA-352644\nDECISION\nDated October 30, 2026")
        router.extract_nlrb_metadata_from_search_result = Mock(side_effect=[
            metadata, replace(metadata, requires_review=True, review_status="MANUAL REVIEW REQUIRED - missing date")])
        router.record_nlrb_metadata = Mock()
        def complete(row, full, index, path, **kwargs):
            status_updates_buffer[index] = "DONE"
            return "DONE"
        router.open_and_process_form = Mock(side_effect=complete)
        router._should_refresh_retry_form_status = Mock(return_value=False)
        gui = SimpleNamespace(progress_label=Mock(), progress_bar=Mock())
        handler = load_ui_method("handle_progress_update")
        emitted = []
        def progress(batch, current, total):
            emitted.append((batch, current, total))
            handler(gui, batch, current, total)
        subset = self.df.iloc[:3]
        router.process_batch(subset, subset, "unused.xlsx", progress, "nlrb", nlrb_mode=True)
        self.assertEqual(emitted, [("nlrb", i, 3) for i in range(4)])
        self.assertEqual(gui.progress_bar.setValue.call_args.args, (100,))
        self.assertEqual(gui.progress_label.setText.call_args.args, ("NLRB Processed: 3/3",))
        self.assertEqual(router.open_and_process_form.call_count, 1)
        self.assertEqual(status_updates_buffer[2], "ERROR: LNI NOT FOUND")

    def test_nlrb_pre_save_validation_handles_nlrb_metadata_and_rejects_reset_date(self):
        router = CaseLawRouter.__new__(CaseLawRouter)
        metadata = parse_nlrb_document_text("Case 19-CA-352644\nDECISION\nDated October 30, 2026")
        snapshot = {"docket": "19-CA-352644", "decision_date": "10/30/2026", "source_detail": "Opinion",
                    "route": "Outside Conversion", "ready": True, "comments": ""}
        router.read_ready_locked_form = Mock(side_effect=lambda: snapshot)
        self.assertTrue(router.verify_itc_values_before_save({}, metadata))
        snapshot["decision_date"] = "07-13-2023"
        self.assertFalse(router.verify_itc_values_before_save({}, metadata))

    def test_nlrb_order_pre_save_validation_resolves_short_source_code(self):
        router = CaseLawRouter.__new__(CaseLawRouter)
        metadata = parse_nlrb_document_text("Case 20-CA-370300\nORDER1\nDated October 30, 2026")
        router.read_ready_locked_form = Mock(return_value={
            "docket": "20-CA-370300", "decision_date": "10-30-2026", "source_detail": "Order",
            "route": "Outside Conversion", "ready": True, "comments": ""})
        self.assertTrue(router.verify_itc_values_before_save({}, metadata))

    def test_nlrb_fill_activates_shared_recovery_and_never_saves_reset_fields(self):
        metadata = parse_nlrb_document_text("Case 19-CA-352644\nDECISION\nDated October 30, 2026")
        router = CaseLawRouter.__new__(CaseLawRouter)
        router.driver = Mock()
        router.wait = Mock()
        router._archive_duplicate_mode = False
        router.handle_any_alert = Mock()
        router.is_route_locked_already_processed = Mock(return_value=False)
        router.handle_itc_fields = Mock(return_value=True)
        router.click_ready_checkbox_and_check_overlay = Mock(return_value=False)
        router.select_dropdown_by_visible_text_or_value = Mock(return_value=True)
        router.handle_routing_and_save = Mock(return_value="DONE")
        def prepare(*args, **kwargs):
            self.assertTrue(router._itc_field_recovery_active)
            self.assertEqual(kwargs["decision_date"], "10-30-2026")
        router.prepare_common_fields = Mock(side_effect=prepare)
        router.verify_itc_values_before_save = Mock(return_value=False)
        outcome = router.fill_itc_irt_form({}, 0, metadata, context_label="NLRB")
        self.assertEqual(outcome, "ERROR: NLRB FORM VALUES UNCONFIRMED")
        router.handle_routing_and_save.assert_not_called()
        self.assertFalse(router._itc_field_recovery_active)
        router.verify_itc_values_before_save.return_value = True
        self.assertEqual(router.fill_itc_irt_form({}, 0, metadata, context_label="NLRB"), "DONE")
        router.handle_routing_and_save.assert_called_once()

    def test_single_router_mode_remains_single_and_recovers_before_reporting(self):
        original = Mock()
        router = Mock()
        def process(*args, **kwargs):
            self.assertTrue(kwargs["nlrb_mode"])
            status_updates_buffer.update({idx: "DONE" for idx in self.df.index})
            status_updates_buffer[0] = FORM_FAILURE
            return self.df.iloc[0:0], self.df
        router.process_rows.side_effect = process
        def recover(*args, **kwargs):
            original.quit.assert_called_once()
            self.assertEqual(args[6], 1)
            self.assertTrue(kwargs["nlrb_mode"])
            status_updates_buffer[0] = "DONE"
            return 1, 1
        success = Mock()
        with ExitStack() as stack:
            self.reporting_mocks(stack)
            for name in ("Path.mkdir", "Options", "ChromeService", "_navigate_with_retries"):
                stack.enter_context(patch(MODULE+name))
            stack.enter_context(patch(MODULE+"load_config", return_value={"parallel_routers_enabled": False, "headless": True}))
            stack.enter_context(patch(MODULE+"ChromeWebDriver", return_value=original))
            stack.enter_context(patch(MODULE+"_open_search_inventory_with_recovery", return_value=True))
            recovery = stack.enter_context(patch(MODULE+"_recover_itc_pre_save_failures", side_effect=recover))
            parallel = stack.enter_context(patch(MODULE+"_run_parallel_document_workflow"))
            run_automation_workflow(df=self.df, latest_excel="unused.xlsx", nlrb_mode=True,
                                    create_router=Mock(return_value=router), set_status=Mock(), show_success=success)
        recovery.assert_called_once()
        parallel.assert_not_called()
        self.assertEqual(success.call_args.args[2], 8)


if __name__ == "__main__":
    unittest.main()
