import unittest
from pathlib import Path

from tools.ferc_inventory_discovery import COURT_CODE, FercInventoryDiscovery, default_output_paths


class FercInventoryDiscoveryTests(unittest.TestCase):
    def test_uses_the_requested_ferc_court_code(self):
        collector = FercInventoryDiscovery(
            object(),
            output_dir=Path("missing-ferc-output"),
            report_path=Path("missing-ferc-report.xlsx"),
        )
        self.assertEqual("FDFERC00", collector.court_code)

    def test_has_separate_ferc_discovery_outputs(self):
        downloads, report = default_output_paths()
        self.assertEqual("FERC PDF Downloads", downloads.name)
        self.assertEqual("FDFERC00_inventory_discovery.xlsx", report.name)


if __name__ == "__main__":
    unittest.main()
