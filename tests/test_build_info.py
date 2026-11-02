import ast
import datetime
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

from core.build_info import BUILD_TIMEZONE, build_version_footer, get_build_info, write_build_manifest
from core import critical_error_notifier as notifier


class BuildInfoTests(unittest.TestCase):
    BUILT_AT = datetime.datetime(2026, 10, 29, 15, 20, 31, 123456, tzinfo=BUILD_TIMEZONE)

    def test_frozen_version_comes_from_packaging_date_not_run_or_copy_date(self):
        with tempfile.TemporaryDirectory() as build, tempfile.TemporaryDirectory() as copied:
            manifest = write_build_manifest(build, built_at=self.BUILT_AT)
            shutil.copyfile(manifest, Path(copied) / manifest.name)
            with patch.object(sys, "frozen", True, create=True), patch.object(sys, "_MEIPASS", copied, create=True):
                info = get_build_info()
        self.assertEqual(info["version"], "10.29.2026")
        self.assertEqual(info["runtime"], "exe")
        self.assertEqual(info["built_at"], self.BUILT_AT.isoformat())
        self.assertTrue(build_version_footer(info).endswith("SADM Autorouter version 10.29.2026"))

    def test_two_builds_on_same_day_keep_distinct_timestamps(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = write_build_manifest(directory, built_at=self.BUILT_AT)
            before = json.loads(manifest.read_text())
            write_build_manifest(directory, built_at=self.BUILT_AT + datetime.timedelta(minutes=1))
            after = json.loads(manifest.read_text())
        self.assertEqual(before["build_date"], after["build_date"])
        self.assertNotEqual(before["built_at"], after["built_at"])

    def test_build_date_uses_asia_shanghai_day(self):
        when = datetime.datetime(2026, 10, 28, 18, 30, tzinfo=datetime.timezone.utc)
        with tempfile.TemporaryDirectory() as directory:
            payload = json.loads(write_build_manifest(directory, built_at=when).read_text())
        self.assertEqual(payload["build_date"], "2026-10-29")
        self.assertTrue(payload["built_at"].endswith("+08:00"))

    def test_python_does_not_invent_an_exe_build_date(self):
        with patch.object(sys, "frozen", False, create=True):
            info = get_build_info()
        self.assertEqual(info["runtime"], "python")
        self.assertIn("Python source", info["version"])
        self.assertIsNone(info["built_at"])

    def test_missing_invalid_or_inconsistent_manifest_does_not_claim_todays_date(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(sys, "frozen", True, create=True), \
                patch.object(sys, "_MEIPASS", directory, create=True):
            for payload in (None, "{bad json", '{"build_date":"2026-10-29","built_at":"2026-10-28T12:00:00+08:00"}'):
                if payload is not None:
                    (Path(directory) / "build_info.json").write_text(payload)
                self.assertIn("unknown", get_build_info()["version"])

    def test_spec_packages_the_generated_manifest_at_bundle_root(self):
        spec = Path(__file__).parents[1] / "smducar_pyqt.spec"
        tree = ast.parse(spec.read_text(encoding="utf-8"))
        assignments = [node for node in tree.body if isinstance(node, ast.Assign)
                       and any(isinstance(target, ast.Name) and target.id in {"build_manifest", "datas"} for target in node.targets)]
        self.assertEqual(len(assignments), 2)
        with tempfile.TemporaryDirectory() as directory:
            namespace = {"Path": Path, "workpath": directory, "write_build_manifest": write_build_manifest}
            exec(compile(ast.Module(body=assignments, type_ignores=[]), str(spec), "exec"), namespace)
            path, destination = namespace["datas"][0]
            self.assertTrue(Path(path).is_file())
            self.assertEqual(Path(path).name, "build_info.json")
            self.assertEqual(destination, ".")


class VersionedReportTests(unittest.TestCase):
    INFO = {"version": "10.29.2026", "build_date": "2026-10-29", "built_at": "2026-10-29T15:20:31.123456+08:00", "runtime": "exe"}

    def tearDown(self):
        notifier._active_run.clear()

    def test_success_and_critical_reports_keep_build_identity_in_email_summary_and_json(self):
        for critical in (False, True):
            with self.subTest(critical=critical), tempfile.TemporaryDirectory() as directory, \
                    patch.object(notifier, "_build_report_folder", return_value=Path(directory)), \
                    patch.object(notifier, "_get_current_log_file", return_value=None), \
                    patch.object(notifier, "_copy_attachment", return_value=None), \
                    patch.object(notifier, "_write_error_entries_workbook"), \
                    patch.object(notifier, "get_build_info", return_value=self.INFO), \
                    patch.object(notifier, "_send_outlook_email") as send:
                notifier.start_critical_error_run(mode="itc", config={})
                summary = {"done_count": 65, "needs_rerun_count": 5}
                if critical:
                    notifier.notify_critical_error("ITC form failed", mode="itc", run_status_summary=summary, config={})
                    stem = "Critical Error"
                    text_name = "Critical Error Summary.txt"
                else:
                    notifier.notify_successful_run(mode="itc", result_counts={"main_success": 65}, run_status_summary=summary, config={})
                    stem = "Run Summary"
                    text_name = "Run Summary.txt"
                body = send.call_args.args[1]
                self.assertTrue(body.endswith("SADM Autorouter version 10.29.2026"))
                self.assertIn(self.INFO["built_at"], body)
                self.assertIn("SADM Autorouter version 10.29.2026", (Path(directory) / text_name).read_text(encoding="utf-8"))
                payload = json.loads((Path(directory) / (stem + " Payload.json")).read_text(encoding="utf-8"))
                self.assertEqual(payload["build_info"], self.INFO)


if __name__ == "__main__":
    unittest.main()
