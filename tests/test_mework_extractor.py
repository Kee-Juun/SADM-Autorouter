import unittest

from core.mework_extractor import (
    MEWORK_FINDINGS_SOURCE_DETAIL,
    classify_mework_exclusion,
    classify_mework_source_detail,
    extract_mework_date_from_filename,
    is_mework_row,
    parse_mework_document_text,
)
from core.irsplr_extractor import is_irsplr_row


class MEWORKExtractorTests(unittest.TestCase):
    def test_case_number_wins_and_distinct_wcb_numbers_become_comments(self):
        text = """
        STATE OF MAINE WORKERS' COMPENSATION BOARD
        Issuance Date: July 23, 2026
        RE: Joel Penwell v. Cote Corp.
        Case#: 24012495B
        WCB#: 24012495 (DOI: 4/12/2024); 24018256 (DOI: 05/09/2024)
        """ + ("Findings and decision text. " * 40)

        metadata = parse_mework_document_text(text, "Penwell_Joel07232026dec.pdf")

        self.assertEqual(metadata.docket_number, "24012495B")
        self.assertEqual(metadata.other_numbers, ("24012495", "24018256"))
        self.assertEqual(metadata.comments_text, "24012495; 24018256")

    def test_first_wcb_number_is_docket_when_case_number_is_absent(self):
        text = """
        STATE OF MAINE WORKERS' COMPENSATION BOARD
        Issuance Date: 7/27/2026
        RE: Ryan Thompson v. Hancock Lumber Company Inc.
        WCB: #23016454; 24-02-47-63 (DOI: 08/17/23; 12/04/2024)
        """ + ("Opinion body text. " * 50)

        metadata = parse_mework_document_text(text, "Thompson_Ryan07272026dec.pdf")

        self.assertEqual(metadata.docket_number, "23016454")
        self.assertEqual(metadata.comments_text, "24-02-47-63")

    def test_final_dated_value_precedes_issuance_and_mail_dates(self):
        text = """
        Issuance Date: 6/10/2024
        Mail Date: 6/12/2024
        Case#: 13-01-56-98C
        So Ordered.
        Dated: 06/11/2024
        """ + ("Decision body. " * 50)

        metadata = parse_mework_document_text(text, "Ariza_Roderick06112024decam2.pdf")
        self.assertEqual(metadata.decision_date, "06-11-2024")
        self.assertFalse(metadata.used_filename_date_fallback)

    def test_filename_date_is_only_used_after_document_dates_fail(self):
        text = "Case#: 23-016943B\nIssuance Date: handwritten\n" + ("Decision body. " * 50)
        metadata = parse_mework_document_text(text, "Plamondon_Tammy07162026dec.pdf")

        self.assertEqual(metadata.decision_date, "07-16-2026")
        self.assertTrue(metadata.used_filename_date_fallback)
        self.assertEqual(extract_mework_date_from_filename("Plamondon_Tammy07162026dec.pdf"), "07-16-2026")

    def test_appellate_division_decided_label_is_a_mework_decision_date(self):
        text = """
        STATE OF MAINE WORKERS' COMPENSATION BOARD APPELLATE DIVISION
        Case No. App. Div. 26-0002
        Decision No. 26-10
        Decided: October 8, 2026
        """ + ("Appellate decision analysis. " * 40)

        metadata = parse_mework_document_text(text, "26-10_Weiss-v-Maine-Soapstone-Co-_20261008.pdf")

        self.assertEqual(metadata.docket_number, "26-0002")
        self.assertEqual(metadata.decision_date, "10-08-2026")
        self.assertEqual(metadata.source_detail, "Opinion")
        self.assertFalse(metadata.used_filename_date_fallback)

    def test_mework_court_code_wins_when_filename_also_matches_irsplr(self):
        row = {
            "CourtCode": "STMEWORK",
            "FileName": "26-10_Weiss-v-Maine-Soapstone-Co-_20261008.pdf",
        }

        self.assertTrue(is_mework_row(row))
        self.assertTrue(is_irsplr_row(row))

    def test_standalone_decree_is_included_but_clerical_correction_remains_excluded(self):
        standard_text = """
        Issuance Date: 2/28/2025
        Case#: 23021622B
        DECISION
        The procedural history mentions an older consent decree and a correction for clerical error.
        """ + ("Standard opinion analysis. " * 40)
        decree_text = """
        Issuance Date: 06/11/2024
        Case#: 13-01-56-98C
        DECREE
        """ + ("Operative ruling text. " * 40)
        correction_text = """
        Issuance Date: 06/11/2024
        Case#: 13-01-56-98C
        DECREE AMENDED PURSUANT TO MOTION TO CORRECT CLERICAL ERROR
        """ + ("Operative ruling text. " * 40)

        standard = parse_mework_document_text(standard_text, "Alimandi_Gwen02282025dec.pdf")
        decree = parse_mework_document_text(decree_text, "Ariza_Roderick06112024decam2.pdf")
        correction = parse_mework_document_text(correction_text, "Ariza_Roderick06112024decam2.pdf")

        self.assertFalse(standard.is_excluded)
        self.assertEqual(standard.source_detail, "Opinion")
        self.assertFalse(decree.is_excluded)
        self.assertEqual(decree.source_detail, "Opinion")
        self.assertNotIn("Exclude -", decree.comments_text)
        self.assertTrue(correction.is_excluded)
        self.assertEqual(correction.source_detail, "Excluded")
        self.assertTrue(correction.comments_text.startswith("Exclude - Correction for Clerical Error"))

    def test_amended_consent_decree_remains_excluded(self):
        text = """
        Issuance Date: 06/11/2024
        Case#: 13-01-56-98C
        DECISION
        AMENDED CONSENT DECREE
        """ + ("Operative ruling text. " * 40)

        metadata = parse_mework_document_text(text)

        self.assertTrue(metadata.is_excluded)
        self.assertEqual(metadata.exclusion_reason, "Amended Consent Decree")
        self.assertEqual(metadata.source_detail, "Excluded")

    def test_findings_and_order_source_details_are_distinct(self):
        self.assertEqual(
            classify_mework_source_detail("Further Findings of Fact and Conclusions of Law"),
            MEWORK_FINDINGS_SOURCE_DETAIL,
        )
        self.assertEqual(classify_mework_source_detail("Order"), "Order")
        self.assertEqual(classify_mework_exclusion("Consent Decree"), "Consent Decree")

    def test_row_detection_uses_court_code_not_generic_filename(self):
        self.assertTrue(is_mework_row({"CourtCode": "STMEWORK", "FileName": "anything.pdf"}))
        self.assertFalse(is_mework_row({"CourtCode": "FDMSPB00", "FileName": "Smith_Jane01012026dec.pdf"}))

    def test_short_but_complete_document_is_readable_without_duplicate_fingerprint(self):
        metadata = parse_mework_document_text(
            "Case#: 23021622B\nIssuance Date: 2/28/2025\nDECISION"
        )
        self.assertTrue(metadata.has_text_content)
        self.assertEqual(metadata.content_fingerprint, "")


if __name__ == "__main__":
    unittest.main()
