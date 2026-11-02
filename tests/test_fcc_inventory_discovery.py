import unittest

from tools.fcc_inventory_discovery import (
    FccInventoryRecord,
    map_result_columns,
    normalise_irt_date,
    required_report_columns_present,
)


class FccInventoryDiscoveryTests(unittest.TestCase):
    def test_maps_irt_result_headers_with_common_variations(self):
        headers = [
            "Document LNI",
            "Decided Date",
            "Date Received",
            "Route",
            "Source Details",
            "File name",
        ]
        self.assertEqual(
            map_result_columns(headers),
            {"lni": 0, "decision_date": 1, "received_date": 2, "route": 3, "source_detail": 4, "file_name": 5},
        )
        self.assertTrue(required_report_columns_present(headers))

    def test_maps_the_verified_irt_search_table_headers(self):
        headers = [
            "LNI", "File name", "Court code", "Court name", "Docket No.",
            "Decided Date", "Received Date", "File Size", "File Type", "Is Child",
            "Is Parent", "Child Count", "Parent Info", "Content Provider Id", "Route", "Source Detail",
        ]
        mapped = map_result_columns(headers)
        self.assertEqual(mapped["file_name"], 1)
        self.assertEqual(mapped["decision_date"], 5)
        self.assertEqual(mapped["received_date"], 6)
        self.assertEqual(mapped["route"], 14)
        self.assertEqual(mapped["source_detail"], 15)

    def test_requires_every_requested_report_field(self):
        self.assertFalse(required_report_columns_present(["LNI", "Decision Date", "Route"]))

    def test_report_row_retains_requested_metadata(self):
        record = FccInventoryRecord(
            "6ABC-1234", "01-02-2026", "01-03-2026", "FDFCC00", "Opinion",
            filename="LDC_SMD_TEST_E2E.pdf", docket_number="DA 26-1",
        )
        self.assertEqual(
            record.as_report_row()[:7],
            ["6ABC-1234", "LDC_SMD_TEST_E2E.pdf", "DA 26-1", "01-02-2026", "01-03-2026", "FDFCC00", "Opinion"],
        )

    def test_normalises_slash_dates_to_irt_format(self):
        self.assertEqual(normalise_irt_date("01/01/2026"), "01-01-2026")
        self.assertEqual(normalise_irt_date("10-01-2026"), "10-01-2026")


if __name__ == "__main__":
    unittest.main()
