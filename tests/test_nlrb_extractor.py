import unittest

from core.nlrb_extractor import NLRB_COURT_CODE, is_nlrb_row, parse_nlrb_document_text
from core.smducar_router import CaseLawRouter


class NLRBExtractorTests(unittest.TestCase):
    def test_board_decision_uses_caption_docket_and_other_caption_dockets(self):
        metadata = parse_nlrb_document_text(
            """
            375 NLRB No. 57
            S.R. Key Plumbing and Mechanical, LLC. Case 10-CA-291436
            September 30, 2026
            DECISION AND ORDER
            """
        )
        self.assertEqual(NLRB_COURT_CODE, metadata.court)
        self.assertEqual("10-CA-291436", metadata.docket_number)
        self.assertEqual("09-30-2026", metadata.decision_date)
        self.assertEqual("OP", metadata.source_detail)
        self.assertFalse(metadata.requires_review)

    def test_order_uses_or_even_when_its_body_mentions_decision_and_order(self):
        metadata = parse_nlrb_document_text(
            """
            UNITED STATES OF AMERICA
            Case 03-RC-336208
            ORDER REMANDING
            The Regional Director's Decision and Order is discussed below.
            Dated, Washington, D.C., February 9, 2026.
            """
        )
        self.assertEqual("03-RC-336208", metadata.docket_number)
        self.assertEqual("02-09-2026", metadata.decision_date)
        self.assertEqual("OR", metadata.source_detail)

    def test_published_decision_prefers_its_caption_date_over_attached_alj_date(self):
        metadata = parse_nlrb_document_text(
            """
            375 NLRB No. 57
            Case 10-CA-291436
            September 30, 2026
            DECISION AND ORDER
            The attached decision says: Dated, Washington, D.C., November 17, 2023.
            """
        )
        self.assertEqual("09-30-2026", metadata.decision_date)

    def test_uses_first_caption_docket_and_saves_other_caption_dockets_as_comments(self):
        metadata = parse_nlrb_document_text(
            """
            Cases 13-CA-305908, 13-CA-318212, 14-CA-312412
            ORDER
            Dated, Washington, D.C., March 25, 2026.
            """
        )
        self.assertEqual("13-CA-305908", metadata.docket_number)
        self.assertEqual(("13-CA-318212", "14-CA-312412"), metadata.other_numbers)
        self.assertEqual("13-CA-318212; 14-CA-312412", metadata.comments_text)

    def test_transfer_order_reads_caption_dockets_after_the_order_heading(self):
        metadata = parse_nlrb_document_text(
            """
            UNITED STATES OF AMERICA
            BEFORE THE NATIONAL LABOR RELATIONS BOARD
            ORDER TRANSFERRING PROCEEDING TO THE NATIONAL LABOR RELATIONS BOARD
            Dated, Washington, D.C., September 30, 2026.
            Cases 05-CA-318025 and 05-CA-324434
            """
        )
        self.assertEqual("05-CA-318025", metadata.docket_number)
        self.assertEqual(("05-CA-324434",), metadata.other_numbers)
        self.assertEqual("09-30-2026", metadata.decision_date)
        self.assertEqual("OR", metadata.source_detail)

    def test_spaced_month_in_board_caption_is_normalized(self):
        metadata = parse_nlrb_document_text(
            """
            375 NLRB No. 49
            Starbucks Corporation. Case 18-CA-298181
            S eptember 30, 2026
            DECISION AND ORDER
            Dated, Washington, D.C., October 17, 2023.
            """
        )
        self.assertEqual("09-30-2026", metadata.decision_date)

    def test_exhibit_is_explicitly_sent_to_manual_review(self):
        metadata = parse_nlrb_document_text("Case 07-CA-328161\nEXHIBIT A\nOctober 6, 2026")
        self.assertTrue(metadata.requires_review)
        self.assertEqual("MANUAL REVIEW REQUIRED — EXHIBIT / ATTACHMENT", metadata.review_status)

    def test_missing_values_name_the_required_user_inputs(self):
        metadata = parse_nlrb_document_text("UNITED STATES OF AMERICA\nDECISION")
        self.assertTrue(metadata.requires_review)
        self.assertIn("DOCKET NUMBER", metadata.review_status)
        self.assertIn("DECISION DATE", metadata.review_status)

    def test_unreadable_content_is_review_safe(self):
        metadata = parse_nlrb_document_text("")
        self.assertTrue(metadata.requires_review)
        self.assertEqual("MANUAL REVIEW REQUIRED — DOCUMENT CONTENT UNREADABLE", metadata.review_status)

    def test_court_row_detection(self):
        self.assertTrue(is_nlrb_row({"CourtCode": "FDNLRB00"}))
        self.assertFalse(is_nlrb_row({"CourtCode": "FDFERC00"}))

    def test_viewer_or_irt_page_text_is_not_accepted_as_nlrb_document_text(self):
        viewer_text = "NATIONAL LABOR RELATIONS BOARD\n" + ("Decision Date\n" * 80)
        self.assertFalse(CaseLawRouter.looks_like_nlrb_text(viewer_text))

    def test_structured_nlrb_document_text_is_accepted(self):
        document_text = (
            "UNITED STATES OF AMERICA\nBEFORE THE NATIONAL LABOR RELATIONS BOARD\n"
            "Case 04-RM-390302\nORDER\n" + ("Document body text.\n" * 30)
        )
        self.assertTrue(CaseLawRouter.looks_like_nlrb_text(document_text))


if __name__ == "__main__":
    unittest.main()
