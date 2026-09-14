import unittest

from core.itc_extractor import (
    extract_itc_docket_from_filename,
    extract_itc_docket_numbers,
    normalize_itc_docket,
    parse_itc_document_text,
)
from core.smducar_utils import extract_itc_docket_number


class ITCMiscDocketTests(unittest.TestCase):
    def test_itc000_misc_document_is_included(self):
        text = """
        INTERNATIONAL TRADE COMMISSION
        Request for Comments Regarding Implementation of 19 U.S.C. 1338(g)
        AGENCY: The United States International Trade Commission
        ACTION: Request for comments in investigation No. MISC-053.
        SUMMARY: The Commission invites comments from interested persons.
        By order of the Commission.
        Issued: September 4, 2026
        """

        metadata = parse_itc_document_text(
            text,
            filename_hint="itc000_MISC-053_20260904.pdf",
            court_code_hint="FDITC000",
        )

        self.assertIsNotNone(metadata)
        self.assertEqual(metadata.docket_number, "MISC-053")
        self.assertEqual(metadata.decision_date, "09-04-2026")
        self.assertEqual(metadata.source_detail, "Opinion")
        self.assertFalse(metadata.is_excluded)
        self.assertEqual(metadata.exclusion_reason, "")

    def test_misc_filename_fallback_is_limited_to_itc000(self):
        self.assertEqual(
            extract_itc_docket_from_filename("itc000_MISC-053_20260904.pdf"),
            "MISC-053",
        )
        self.assertEqual(
            extract_itc_docket_number("itc000_MISC-053_20260904.pdf"),
            "MISC-053",
        )
        self.assertIsNone(extract_itc_docket_from_filename("itcalj_MISC-053_20260904.pdf"))
        self.assertIsNone(extract_itc_docket_number("itcalj_MISC-053_20260904.pdf"))

    def test_misc_normalization_handles_spacing_and_case(self):
        self.assertEqual(normalize_itc_docket(" misc - 053 "), "MISC-053")
        self.assertEqual(extract_itc_docket_numbers("Investigation No. misc - 053"), ["MISC-053"])

    def test_unstructured_misc_text_is_not_a_docket(self):
        self.assertIsNone(normalize_itc_docket("miscellaneous 053"))
        self.assertEqual(extract_itc_docket_numbers("Miscellaneous request number 053"), [])

    def test_existing_ta_docket_behavior_is_unchanged(self):
        self.assertEqual(
            extract_itc_docket_numbers("Investigation No. 337-TA-1484"),
            ["337-TA-1484"],
        )


if __name__ == "__main__":
    unittest.main()
