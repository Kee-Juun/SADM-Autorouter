import ast
import importlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

from core import startup_progress


class StartupProgressTests(unittest.TestCase):
    def setUp(self):
        self.closed = patch.object(startup_progress, "_closed", False)
        self.closed.start()
        self.connection = MagicMock()
        self.socket_patch = patch("core.startup_progress.socket.create_connection", return_value=self.connection)
        self.connect = self.socket_patch.start()
        self.environment = patch.dict("os.environ", {"SADM_STARTUP_ENDPOINT": "12345:test-token"})
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        self.socket_patch.stop()
        self.closed.stop()

    def sent(self):
        data = self.connection.__enter__.return_value.sendall.call_args.args[0]
        return json.loads(data)

    def test_reports_actual_stage_using_authenticated_local_connection(self):
        startup_progress.report_startup("Loading Fonts")
        self.connect.assert_called_once_with(("127.0.0.1", 12345), timeout=0.2)
        self.assertEqual(self.sent(), {"event": "stage", "message": "Loading Fonts", "token": "test-token"})

    def test_transmits_estimated_progress_but_reserves_completion_for_ready(self):
        startup_progress.report_startup("Loading Fonts", 70)
        self.assertEqual(self.sent()["progress"], 70)
        startup_progress.report_startup("Opening Your Workspace", 100)
        self.assertEqual(self.sent()["progress"], 99)

    def test_invalid_estimates_do_not_break_startup_or_emit_invalid_json_numbers(self):
        for value in (True, "50", -1, 101, float('nan'), float('inf')):
            with self.subTest(value=value):
                startup_progress.report_startup("Loading Fonts", value)
                self.assertNotIn("progress", self.sent())

    def test_close_is_idempotent_and_late_updates_do_not_reopen_splash(self):
        startup_progress.close_startup()
        startup_progress.close_startup()
        startup_progress.report_startup("Too late")
        self.connect.assert_called_once()
        self.assertEqual(self.sent()["event"], "ready")

    def test_direct_engine_runs_and_invalid_endpoints_remain_usable(self):
        for endpoint in ("", "invalid", "invalid:port"):
            with self.subTest(endpoint=endpoint), patch.dict("os.environ", {"SADM_STARTUP_ENDPOINT": endpoint}), \
                    patch.object(startup_progress, "_closed", False):
                startup_progress.report_startup("Loading Libraries")
                startup_progress.close_startup()
        self.connect.assert_not_called()

    def test_disconnected_loading_window_does_not_prevent_app_start(self):
        self.connect.side_effect = ConnectionError("disconnected")
        startup_progress.report_startup("Loading Libraries")
        startup_progress.close_startup()

    def test_status_message_cannot_split_the_ipc_command(self):
        startup_progress.report_startup("Loading\r\nLibraries")
        self.assertEqual(self.sent()["message"], "Loading\r\nLibraries")
        data = self.connection.__enter__.return_value.sendall.call_args.args[0]
        self.assertEqual(data.count(b"\n"), 1)

    def test_failure_cannot_be_followed_by_a_false_ready_message(self):
        startup_progress.fail_startup("UI failed")
        startup_progress.close_startup()
        self.connect.assert_called_once()
        self.assertEqual(self.sent()["event"], "error")


class EntrypointStartupTests(unittest.TestCase):
    def test_entrypoint_does_not_eagerly_import_gui_or_routing_libraries(self):
        tree = ast.parse((Path(__file__).parents[1] / "main.py").read_text(encoding="utf-8"))
        names = []
        for node in tree.body:
            if isinstance(node, ast.ImportFrom):
                names.append(node.module)
            elif isinstance(node, ast.Import):
                names.extend(alias.name for alias in node.names)
        self.assertFalse(any(name.startswith(("PyQt5", "frontend")) for name in names))
        self.assertNotIn("core.critical_error_notifier", names)

    def test_initialization_failure_always_closes_loading_window(self):
        entrypoint = importlib.import_module("main")
        with patch.object(entrypoint, "_run_application", side_effect=RuntimeError("UI failed")), \
                patch.object(entrypoint, "close_startup") as close, \
                patch.object(entrypoint, "fail_startup") as fail:
            with self.assertRaisesRegex(RuntimeError, "UI failed"):
                entrypoint.main()
            close.assert_called_once()
            fail.assert_called_once_with("UI failed")

    def test_normal_exit_keeps_app_exit_code_and_closes_loading_window(self):
        entrypoint = importlib.import_module("main")
        with patch.object(entrypoint, "_run_application", return_value=7), \
                patch.object(entrypoint, "close_startup") as close:
            self.assertEqual(entrypoint.main(), 7)
            close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
