import ast
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock


def load_progress_handler():
    """Load the UI callback without importing its logging-heavy Qt module."""
    source_path = Path(__file__).resolve().parents[1] / "frontend" / "smducar_pyqt.py"
    module = ast.parse(source_path.read_text(encoding="utf-8"))
    gui_class = next(
        node for node in module.body if isinstance(node, ast.ClassDef) and node.name == "SMDUSAPGui"
    )
    handler = next(
        node for node in gui_class.body
        if isinstance(node, ast.FunctionDef) and node.name == "handle_progress_update"
    )
    isolated_module = ast.Module(body=[handler], type_ignores=[])
    ast.fix_missing_locations(isolated_module)
    namespace = {}
    exec(compile(isolated_module, str(source_path), "exec"), namespace)
    return namespace["handle_progress_update"]


class ProgressUpdateTests(unittest.TestCase):
    def test_ferc_progress_calculates_percentage_before_setting_progress_bar(self):
        gui = SimpleNamespace(progress_label=Mock(), progress_bar=Mock())

        load_progress_handler()(gui, "ferc", 1, 2)

        gui.progress_label.setText.assert_called_once_with("FERC Processed: 1/2")
        gui.progress_bar.setValue.assert_called_once_with(50)

    def test_ferc_progress_handles_an_empty_batch(self):
        gui = SimpleNamespace(progress_label=Mock(), progress_bar=Mock())

        load_progress_handler()(gui, "ferc", 0, 0)

        gui.progress_bar.setValue.assert_called_once_with(0)


if __name__ == "__main__":
    unittest.main()
