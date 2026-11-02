import ast
import logging
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pandas as pd

from core.irsplr_extractor import is_irsplr_row
from core.ohtax0_extractor import parse_ohtax0_document_text
from core.rerun_status import finalize_rerun_ready_statuses
from core.smducar_config import error_log_entries, mspb_metadata_buffer, status_updates_buffer
from core.smducar_router import CaseLawRouter
from core.smducar_workflow import _run_document_router_phase


def load_ui_method(name):
    """Exercise real UI methods without its module's logging/startup effects."""
    source_path = Path(__file__).parents[1] / "frontend" / "smducar_pyqt.py"
    module = ast.parse(source_path.read_text(encoding="utf-8"))
    gui = next(node for node in module.body if isinstance(node, ast.ClassDef) and node.name == "SMDUSAPGui")
    method = next(node for node in gui.body if isinstance(node, ast.FunctionDef) and node.name == name)
    namespace = {"logging": logging}
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(source_path), "exec"), namespace)
    return namespace[name]


class RouterModeSelectionTests(unittest.TestCase):
    def setUp(self):
        self.clear_buffers()

    def tearDown(self):
        self.clear_buffers()

    @staticmethod
    def clear_buffers():
        status_updates_buffer.clear()
        mspb_metadata_buffer.clear()
        error_log_entries.clear()

    @staticmethod
    def rows(count=1):
        return pd.DataFrame([
            {"CourtCode": "STOHTAX0", "FileName": f"LDC_BC_2026-{392 + i}_OrderOrDecision_21-Oct-202608_12AM.pdf",
             "LNI": f"6KT7-KGF3-S477-M2F{letter}-00000-00", "Status": "NEEDS RERUN - INTERRUPTED"}
            for i, letter in enumerate("TRS"[:count])
        ])

    @staticmethod
    def router():
        router = CaseLawRouter.__new__(CaseLawRouter)
        router.driver = Mock()
        router.safe_alert_accept = Mock()
        router.configure_irt_duplicate_verification = Mock()
        router.search_lni = Mock(return_value=True)
        router.check_result_available = Mock(return_value=True)
        router.click_matching_result = Mock()
        router.handle_lni_search = Mock(return_value=True)
        router.mark_itc_duplicate_status = Mock(side_effect=lambda index, row, lni, metadata: metadata)
        router.mark_mework_duplicate_status = Mock(side_effect=lambda index, row, lni, metadata: metadata)
        router._should_refresh_retry_form_status = Mock(return_value=False)
        metadata = SimpleNamespace(court="STOHTAX0", docket_number="2026-392", decision_date="10-21-2026",
                                   source_detail="Opinion", has_text_content=True)
        for mode in ("mspb", "itc", "irsplr", "ohtax0", "mnsutb", "mework", "fcc", "ferc", "nlrb", "mosu00"):
            setattr(router, f"extract_{mode}_metadata_from_search_result", Mock(return_value=metadata))

        def complete(row, full_df, index, file_path, **kwargs):
            status_updates_buffer[index] = "DONE"
            return "DONE"

        router.open_and_process_form = Mock(side_effect=complete)
        return router

    def test_filename_inspection_never_overrides_ohtax0_codex_selection(self):
        """Filename inspection must not reconfigure a Codex-selected mode."""
        gui = SimpleNamespace(config={"mode": "ohtax0", "dar_mode": False},
                              _set_router_mode_config=Mock(), router_mode_signal=Mock())
        load_ui_method("auto_detect_mode_from_filenames")(gui, self.rows(3))
        self.assertEqual(gui.config["mode"], "ohtax0")
        gui._set_router_mode_config.assert_not_called()
        gui.router_mode_signal.emit.assert_not_called()

    def test_ohtax0_selection_blocks_irsplr_filename_fallback(self):
        """LDC_BC-style OHTAX0 filenames must never take the IRSPLR path."""
        router = self.router()
        df = self.rows(3)
        self.assertTrue(is_irsplr_row(df.iloc[0]))
        metadata = parse_ohtax0_document_text(
            "OHIO BOARD OF TAX APPEALS\nCASE NO(S). 2026-392\nDECISION AND ORDER\n"
            "APPEARANCES:\nEntered Wednesday, October 21, 2026\n" + "Board ruling. " * 40
        )
        router.extract_ohtax0_metadata_from_search_result.return_value = metadata

        count, _ = router.process_batch(df, df, "unused.xlsx", None, "ohtax0", ohtax0_mode=True)

        self.assertEqual(count, 3)
        self.assertEqual(router.extract_ohtax0_metadata_from_search_result.call_count, 3)
        router.extract_irsplr_metadata_from_search_result.assert_not_called()
        for call in router.open_and_process_form.call_args_list:
            self.assertIs(call.kwargs["ohtax0_metadata"], metadata)
            self.assertIsNone(call.kwargs["irsplr_metadata"])
        self.assertEqual({entry["Metadata Type"] for entry in mspb_metadata_buffer.values()}, {"OHTAX0"})
        self.assertEqual(set(status_updates_buffer.values()), {"DONE"})
        self.assertFalse(error_log_entries)

    def test_all_specialist_batch_entry_points_reach_their_selected_parser(self):
        for mode in ("mspb", "itc", "irsplr", "ohtax0", "mnsutb", "mework", "fcc", "ferc", "nlrb"):
            with self.subTest(mode=mode):
                self.clear_buffers()
                router = self.router()
                df = self.rows()
                count, _ = router.process_batch(df, df, "unused.xlsx", None, mode, **{f"{mode}_mode": True})
                self.assertEqual(count, 1)
                getattr(router, f"extract_{mode}_metadata_from_search_result").assert_called_once()
                self.assertFalse(error_log_entries)

    def test_legacy_itc_batch_call_does_not_require_new_flag(self):
        router = self.router()
        df = self.rows()
        count, _ = router.process_batch(df, df, "unused.xlsx", None, "itc")
        self.assertEqual(count, 1)
        router.extract_itc_metadata_from_search_result.assert_called_once()
        router.extract_irsplr_metadata_from_search_result.assert_not_called()

    def test_smd_dar_and_mosu00_entry_points_still_work(self):
        for mode, filename, batch, kwargs, metadata_key in (
            ("smd", "smd_26-123_CA6_10_21_2026.pdf", "main", {}, None),
            ("dar", "DAR_26-123.pdf", "main", {"dar_mode": True}, None),
            ("mosu00", "LDC_SMD_Minutesof10212026.html", "mosu00", {"mosu00_mode": True}, "mosu00_metadata"),
        ):
            with self.subTest(mode=mode):
                self.clear_buffers()
                router = self.router()
                df = self.rows()
                df.loc[0, "FileName"] = filename
                df.loc[0, "CourtCode"] = "MOSU00" if mode == "mosu00" else "CA6"
                count, _ = router.process_batch(df, df, "unused.xlsx", None, batch, **kwargs)
                self.assertEqual(count, 1)
                self.assertFalse(error_log_entries)
                if metadata_key:
                    self.assertIsNotNone(router.open_and_process_form.call_args.kwargs[metadata_key])
                else:
                    router.handle_lni_search.assert_called_once()
                    router.configure_irt_duplicate_verification.assert_called_once_with()

    def test_extraction_exception_is_recorded_and_next_row_can_continue(self):
        router = self.router()
        df = self.rows(2)
        router.extract_ohtax0_metadata_from_search_result.side_effect = [RuntimeError("extraction failed"),
                                                                       SimpleNamespace(has_text_content=True)]
        with self.assertLogs(level="ERROR"):
            count, _ = router.process_batch(df, df, "unused.xlsx", None, "ohtax0", ohtax0_mode=True)
        self.assertEqual(count, 1)
        self.assertEqual(status_updates_buffer, {0: "ERROR", 1: "DONE"})
        self.assertEqual(error_log_entries[0]["Error Message"], "extraction failed")
        self.assertEqual(mspb_metadata_buffer[0]["Metadata Type"], "OHTAX0")

    def test_metadata_diagnostic_failure_does_not_hide_primary_error_or_stop_batch(self):
        router = self.router()
        df = self.rows(2)
        real_record = router.record_ohtax0_metadata

        def record(index, *args, **kwargs):
            if kwargs.get("metadata_status") == "Error":
                raise RuntimeError("diagnostic failed")
            return real_record(index, *args, **kwargs)

        router.record_ohtax0_metadata = record
        router.extract_ohtax0_metadata_from_search_result.side_effect = [RuntimeError("primary failed"),
                                                                       SimpleNamespace(has_text_content=True)]
        with self.assertLogs(level="WARNING"):
            count, _ = router.process_batch(df, df, "unused.xlsx", None, "ohtax0", ohtax0_mode=True)
        self.assertEqual(count, 1)
        self.assertEqual(error_log_entries[0]["Error Message"], "primary failed")
        self.assertEqual(status_updates_buffer, {0: "ERROR", 1: "DONE"})

    def test_parallel_crash_records_processing_rows_and_preserves_completed_rows(self):
        df = self.rows(3)
        router = Mock()
        status_updates_buffer.update({0: "PROCESSING", 1: "DONE"})
        router.process_batch.side_effect = RuntimeError("batch crashed")
        with tempfile.TemporaryDirectory() as task_dir, ExitStack() as stack:
            stack.enter_context(patch("core.smducar_workflow.Path.home", return_value=Path(task_dir)))
            for name in ("_build_chrome_options", "_create_chrome_driver", "_navigate_with_retries",
                         "_write_router_split_workbook"):
                stack.enter_context(patch(f"core.smducar_workflow.{name}"))
            stack.enter_context(patch("core.smducar_workflow._open_search_inventory_with_recovery", return_value=True))
            with self.assertLogs(level="ERROR"):
                result = _run_document_router_phase(
                    1, "ohtax0", df, df, "unused.xlsx", {}, "driver", "url", Mock(return_value=router),
                    None, None, None, False, False, "OHTAX0", ohtax0_mode=True,
                )
        self.assertEqual(result, (0, 0))
        self.assertEqual(status_updates_buffer, {0: "ERROR", 1: "DONE", 2: "ERROR"})
        self.assertEqual({entry["Row"] for entry in error_log_entries}, {2, 4})
        self.assertTrue(router.process_batch.call_args.kwargs["ohtax0_mode"])

    def test_summary_reports_rerun_even_without_error_entries(self):
        df = self.rows(3)
        status_updates_buffer.update({idx: "PROCESSING" for idx in df.index})
        summary = finalize_rerun_ready_statuses(df=df, mode="ohtax0")
        gui = SimpleNamespace(config={"mode": "ohtax0"})
        message = load_ui_method("get_success_message")(gui, "User", 0, 0, 0, 0, review_summary=summary)
        self.assertIn("Run could not complete", message)
        self.assertIn("3 document(s) still need a rerun", message)
        self.assertNotIn("No unfinished rows", message)
        self.assertNotIn("No new routing needed", message)

    def test_partial_completion_summary_reports_remaining_work(self):
        gui = SimpleNamespace(config={"mode": "ohtax0"})
        message = load_ui_method("get_success_message")(
            gui, "User", 0, 1, 0, 0, review_summary={"needs_rerun_count": 2}
        )
        self.assertIn("Successfully auto-routed:", message)
        self.assertIn("OHTAX0: 1", message)
        self.assertIn("2 document(s) still need a rerun", message)
        self.assertNotIn("Fresh routing complete", message)

    def test_review_only_summary_does_not_claim_there_is_no_unfinished_work(self):
        gui = SimpleNamespace(config={"mode": "smd"})
        message = load_ui_method("get_success_message")(
            gui, "User", 0, 0, 0, 0,
            review_summary={"manual_review_count": 1, "manual_review_rows": [{
                "File Name": "smd_26-7087_CADC_Counsel.csv", "LNI": "6KTN-J843-SGX3-C3R4-00000-00",
                "Status": "MANUAL REVIEW REQUIRED - READY TO PROCESS LOCKED: Route mismatch",
            }]},
        )
        self.assertIn("manual review is required", message)
        self.assertIn("Route mismatch", message)
        self.assertNotIn("No unfinished rows found", message)
        self.assertNotIn("No new routing needed", message)


if __name__ == "__main__":
    unittest.main()
