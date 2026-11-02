import unittest
from unittest.mock import MagicMock, patch

from openpyxl import Workbook, load_workbook

from core.smducar_excel import flush_status_updates
from core.smducar_router import CaseLawRouter


class _DocumentLink:
    def __init__(self, href, text):
        self.href = href
        self.text = text

    def get_attribute(self, name):
        if name == "href":
            return self.href
        if name == "textContent":
            return self.text
        return ""


class FilenameDocumentationTests(unittest.TestCase):
    def test_link_filename_is_captured_for_an_lni_only_row(self):
        router = CaseLawRouter.__new__(CaseLawRouter)
        row = {"LNI": "6KS2-XJ83-S90T-D35S", "FileName": float("nan")}

        captured = router.capture_file_name_from_link(
            row,
            _DocumentLink("/document.aspx?fileName=04-RM-390302_Order.pdf", "04-RM-390302_Order.pdf"),
        )

        self.assertEqual("04-RM-390302_Order.pdf", captured)
        self.assertEqual(captured, row["FileName"])

    def test_resolved_filename_is_written_to_mapping_and_metadata_sheets(self):
        wb = Workbook()
        ws = wb.active
        ws.title = "Mapping Data"
        ws.append([
            "Require Cardinal Process", "Court Code", "File Name", "LNI", "Tier",
            "Received Date", "Time Left", "Recycled Counsel LNI", "Source Detail",
            "Comments", "Decision Date", "Status",
        ])
        ws.append(["", "FDNLRB00", "", "6KS2-XJ83-S90T-D35S", "", "", "", "", "", "", "", ""])
        wb.save = MagicMock()

        with patch("core.smducar_excel.load_workbook", return_value=wb):
            flush_status_updates(
                "mapping.xlsx",
                {0: "DONE"},
                {
                    0: {
                        "Metadata Type": "NLRB",
                        "LNI": "6KS2-XJ83-S90T-D35S",
                        "File Name": "04-RM-390302_Order.pdf",
                        "Metadata Status": "Extracted",
                    }
                },
            )

        self.assertEqual("04-RM-390302_Order.pdf", wb["Mapping Data"]["C2"].value)
        self.assertEqual("04-RM-390302_Order.pdf", wb["PDF Metadata"]["C2"].value)


if __name__ == "__main__":
    unittest.main()
