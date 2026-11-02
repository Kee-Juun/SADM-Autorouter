import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd

from core.smducar_config import error_log_entries, itc_content_fingerprint_buffer, mspb_metadata_buffer, status_updates_buffer
from core.smducar_workflow import (
    _itc_pre_save_recovery_rows,
    _recover_itc_pre_save_failures,
    _run_parallel_document_workflow,
    run_automation_workflow,
)


FORM_FAILURE = "ERROR: IRT FORM NOT EDITABLE AFTER 3 ATTEMPTS"
MODIFY_FAILURE = "ERROR: MODIFY BUTTON NOT FOUND AFTER 3 ATTEMPTS"
MODULE = "core.smducar_workflow."


class ITCFreshBrowserRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.clear_buffers()
        self.df = pd.DataFrame([
            {"CourtCode": "FDITC000", "FileName": f"itc000_337-{1500+i}_20261029.pdf",
             "LNI": f"6KW3-NVD3-SDC5-63Y{i}-00000-00", "Status": ""}
            for i in range(5)
        ])

    def tearDown(self):
        self.clear_buffers()

    @staticmethod
    def clear_buffers():
        status_updates_buffer.clear()
        error_log_entries.clear()
        mspb_metadata_buffer.clear()
        itc_content_fingerprint_buffer.clear()

    def recover(self, df=None, **kwargs):
        return _recover_itc_pre_save_failures(
            self.df if df is None else df, self.df, "unused.xlsx", kwargs.pop("config", {}),
            "driver", "url", kwargs.pop("workers", 6), **kwargs,
        )

    def test_only_this_runs_specific_pre_save_itc_failures_are_selected(self):
        status_updates_buffer.update({0: "DONE", 1: FORM_FAILURE, 2: "ERROR: SAVE UNCONFIRMED",
                                      3: "MANUAL REVIEW REQUIRED - ITC candidate unreadable", 4: MODIFY_FAILURE})
        self.assertEqual(list(_itc_pre_save_recovery_rows(self.df).index), [1, 4])
        non_itc = self.df.copy()
        non_itc["CourtCode"] = "STOHTAX0"
        non_itc["FileName"] = "ohtax_order.pdf"
        self.assertTrue(_itc_pre_save_recovery_rows(non_itc).empty)

    def test_old_or_generic_failures_are_not_eligible_without_a_current_pre_save_failure(self):
        self.df["Status"] = FORM_FAILURE
        self.assertTrue(_itc_pre_save_recovery_rows(self.df).empty)
        for status in ("ERROR", "NEEDS RERUN - FAILED", "ERROR: ITC FORM VALUES UNCONFIRMED",
                       "ERROR: DUPLICATE SAVE FAILED", "ALREADY PROCESSED", "DUPLICATE OF OLD"):
            status_updates_buffer[0] = status
            self.assertTrue(_itc_pre_save_recovery_rows(self.df).empty, status)

    def test_empty_scope_or_recovery_config_does_not_start_another_pass(self):
        with patch(MODULE+"_run_parallel_document_phase") as phase:
            self.assertEqual(self.recover(), (0, 0))
            status_updates_buffer[0] = FORM_FAILURE
            self.assertEqual(self.recover(config={"_itc_fresh_recovery": True}), (0, 0))
        phase.assert_not_called()

    def test_recovery_retries_only_failed_rows_at_most_two_workers_and_preserves_other_errors(self):
        status_updates_buffer.update({0: "DONE", 1: FORM_FAILURE, 2: "ERROR: SAVE UNCONFIRMED",
                                      3: "MANUAL REVIEW REQUIRED - ITC candidate unreadable", 4: MODIFY_FAILURE})
        for index in (1, 2, 4):
            error_log_entries.append({"Row": index+2, "LNI": self.df.loc[index,"LNI"], "Status": status_updates_buffer[index]})
        original_errors = list(error_log_entries)
        config = {"parallel_router_instances": 6}

        def phase(*args, **kwargs):
            self.assertEqual(args[0], "itc")
            self.assertEqual(list(args[1].index), [1, 4])
            self.assertEqual(args[7], 2)
            self.assertIsNone(args[8])  # do not reset main progress to 0/2
            self.assertTrue(args[4]["_itc_fresh_recovery"])
            self.assertEqual(error_log_entries, original_errors)
            status_updates_buffer.update({1: "DONE", 4: "DONE"})
            return 2, 20

        with patch(MODULE+"_run_parallel_document_phase", side_effect=phase) as run:
            self.assertEqual(self.recover(config=config), (2, 20))
        run.assert_called_once()
        self.assertNotIn("_itc_fresh_recovery", config)
        self.assertEqual(error_log_entries, [original_errors[1]])
        self.assertEqual(status_updates_buffer[0], "DONE")
        self.assertEqual(status_updates_buffer[2], "ERROR: SAVE UNCONFIRMED")
        self.assertTrue(status_updates_buffer[3].startswith("MANUAL REVIEW REQUIRED"))

    def test_repeated_failure_is_not_looped_or_removed_from_error_report(self):
        status_updates_buffer[0] = FORM_FAILURE
        error_log_entries.append({"Row": 2, "LNI": self.df.loc[0,"LNI"], "Status": FORM_FAILURE})
        with patch(MODULE+"_run_parallel_document_phase", return_value=(0, 12)) as phase:
            self.assertEqual(self.recover(), (0, 12))
        phase.assert_called_once()
        self.assertEqual(status_updates_buffer[0], FORM_FAILURE)
        self.assertEqual(len(error_log_entries), 1)

    def test_intentional_review_outcome_is_preserved_after_technical_recovery(self):
        status_updates_buffer[0] = FORM_FAILURE
        error_log_entries.append({"Row": 2, "LNI": self.df.loc[0,"LNI"], "Status": FORM_FAILURE})
        review = "MANUAL REVIEW REQUIRED - READY TO PROCESS LOCKED: Route mismatch"
        def phase(*args, **kwargs):
            status_updates_buffer[0] = review
            return 0, 3
        with patch(MODULE+"_run_parallel_document_phase", side_effect=phase):
            self.recover(workers=1)
        self.assertEqual(status_updates_buffer[0], review)
        self.assertFalse(error_log_entries)

    def test_controller_exception_preserves_the_initial_outcome_and_finishes_bounded_recovery(self):
        status_updates_buffer[0] = FORM_FAILURE
        with patch(MODULE+"_run_parallel_document_phase", side_effect=RuntimeError("worker setup failed")) as phase:
            with self.assertLogs(level="ERROR"):
                self.assertEqual(self.recover(), (0, 0))
        phase.assert_called_once()
        self.assertEqual(status_updates_buffer[0], FORM_FAILURE)

    def test_recovery_phase_creates_fresh_browsers_and_preserves_initial_split_workbooks(self):
        scope = self.df.iloc[:3].copy()
        status_updates_buffer.update({idx:FORM_FAILURE for idx in scope.index})
        drivers = [Mock(), Mock()]

        def make_router(driver, **kwargs):
            router = Mock()
            def process(chunk, *args, **kwargs):
                status_updates_buffer.update({idx:"DONE" for idx in chunk.index})
                return len(chunk), 5
            router.process_batch.side_effect = process
            return router

        with ExitStack() as stack:
            stack.enter_context(patch(MODULE+"Path.home", return_value=Path("C:/mock-itc-home")))
            stack.enter_context(patch(MODULE+"Path.mkdir"))
            build = stack.enter_context(patch(MODULE+"_build_chrome_options"))
            create = stack.enter_context(patch(MODULE+"_create_chrome_driver", side_effect=drivers))
            stack.enter_context(patch(MODULE+"_navigate_with_retries"))
            stack.enter_context(patch(MODULE+"_open_search_inventory_with_recovery", return_value=True))
            stack.enter_context(patch(MODULE+"_write_router_split_workbook"))
            self.assertEqual(self.recover(scope, create_router=make_router), (3, 10))
        self.assertEqual(create.call_count, 2)
        for driver in drivers:
            driver.quit.assert_called_once()
        for call in build.call_args_list:
            self.assertIn("ITC Recovery", call.args[1].parts)

    def reporting_mocks(self, stack):
        for name in ("flush_status_updates", "notify_for_critical_statuses", "notify_successful_run", "notify_critical_error",
                     "_write_error_report_if_needed", "start_critical_error_run"):
            stack.enter_context(patch(MODULE+name))
        stack.enter_context(patch(MODULE+"get_full_username", return_value="Test User"))
        stack.enter_context(patch(MODULE+"_resolve_chromedriver_path", return_value="driver"))

    def test_parallel_workflow_recovers_before_final_summary_and_reporting(self):
        scope = self.df.iloc[:3].copy()
        calls = []
        def phase(*args, **kwargs):
            calls.append(args[4].get("_itc_fresh_recovery", False))
            if not calls[-1]:
                status_updates_buffer.update({0:"DONE",1:FORM_FAILURE,2:MODIFY_FAILURE})
                return 1, 10
            status_updates_buffer.update({1:"DONE",2:"DONE"})
            return 2, 20
        success = Mock()
        with ExitStack() as stack:
            self.reporting_mocks(stack)
            run = stack.enter_context(patch(MODULE+"_run_parallel_document_phase", side_effect=phase))
            _run_parallel_document_workflow(df=scope, df_filtered=scope, latest_excel="unused.xlsx",
                                            config={"parallel_router_instances":6}, itc_mode=True,
                                            show_success=success, set_status=Mock())
        self.assertEqual(calls, [False, True])
        self.assertEqual(run.call_args_list[1].args[7], 2)
        self.assertEqual(success.call_args.args[2], 3)  # main_success
        self.assertEqual(success.call_args.args[-1]["needs_rerun_count"], 0)

    def test_single_workflow_quits_original_browser_before_fresh_recovery(self):
        scope = self.df.iloc[:2].copy()
        original_driver = Mock()
        router = Mock()
        def initial(*args, **kwargs):
            status_updates_buffer.update({0:"DONE",1:FORM_FAILURE})
            return scope.iloc[0:0], scope
        router.process_rows.side_effect = initial
        def recovered(*args, **kwargs):
            original_driver.quit.assert_called_once()
            self.assertEqual(args[6], 1)
            status_updates_buffer[1] = "DONE"
            return 1, 5
        success = Mock()
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            self.reporting_mocks(stack)
            stack.enter_context(patch(MODULE+"Path.home", return_value=Path(directory)))
            stack.enter_context(patch(MODULE+"load_config", return_value={"headless":True}))
            stack.enter_context(patch(MODULE+"Options"))
            stack.enter_context(patch(MODULE+"ChromeService"))
            stack.enter_context(patch(MODULE+"ChromeWebDriver", return_value=original_driver))
            stack.enter_context(patch(MODULE+"_navigate_with_retries"))
            stack.enter_context(patch(MODULE+"_open_search_inventory_with_recovery", return_value=True))
            recovery = stack.enter_context(patch(MODULE+"_recover_itc_pre_save_failures", side_effect=recovered))
            run_automation_workflow(df=scope, latest_excel="unused.xlsx", itc_mode=True,
                                    create_router=Mock(return_value=router), show_success=success, set_status=Mock())
        recovery.assert_called_once()
        self.assertEqual(success.call_args.args[2], 2)
        self.assertEqual(success.call_args.args[-1]["needs_rerun_count"], 0)


if __name__ == "__main__":
    unittest.main()
