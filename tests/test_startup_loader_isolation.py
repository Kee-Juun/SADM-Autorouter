"""Run Qt6 tests in their own process so they cannot mix with Qt5 test suites."""
import os
from pathlib import Path
import subprocess
import sys
import unittest


class StartupLoaderIsolationTests(unittest.TestCase):
    def test_slow_process_creation_cannot_block_first_paint_or_controls(self):
        root = Path(__file__).resolve().parents[1]
        env = dict(os.environ)
        for key in ("QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH", "QML2_IMPORT_PATH"):
            env.pop(key, None)
        result = subprocess.run(
            [sys.executable, str(root / "tools/verify_startup_launch.py"), "--offscreen"],
            cwd=root, env=env, capture_output=True, text=True, timeout=40,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("slow process creation keeps animation/minimize responsive", result.stdout)

    def test_separate_qt6_loader_and_qt5_engine_handoff(self):
        root = Path(__file__).resolve().parents[1]
        env = dict(os.environ)
        for key in ("QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH", "QML2_IMPORT_PATH"):
            env.pop(key, None)
        result = subprocess.run(
            [sys.executable, str(root / "tools/verify_startup_loader.py"), "--offscreen"],
            cwd=root, env=env, capture_output=True, text=True, timeout=40,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("actual separate Qt5 UI handoff", result.stdout)


if __name__ == "__main__":
    unittest.main()
