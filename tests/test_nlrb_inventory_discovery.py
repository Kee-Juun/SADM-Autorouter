import unittest
from pathlib import Path

from tools.nlrb_inventory_discovery import (
    COURT_CODE,
    DEFAULT_DATE_FROM,
    DEFAULT_DATE_TO,
    NlrbInventoryDiscovery,
    default_output_paths,
)


class NlrbInventoryDiscoveryTests(unittest.TestCase):
    def test_uses_the_requested_nlrb_court_code(self):
        collector = NlrbInventoryDiscovery(
            object(),
            output_dir=Path("missing-nlrb-output"),
            report_path=Path("missing-nlrb-report.xlsx"),
        )
        self.assertEqual("FDNLRB00", collector.court_code)

    def test_has_separate_nlrb_discovery_outputs_and_requested_dates(self):
        downloads, report = default_output_paths()
        self.assertEqual("NLRB PDF Downloads", downloads.name)
        self.assertEqual("FDNLRB00_inventory_discovery.xlsx", report.name)
        self.assertEqual("01-01-2026", DEFAULT_DATE_FROM)
        self.assertEqual("10-15-2026", DEFAULT_DATE_TO)


if __name__ == "__main__":
    unittest.main()
