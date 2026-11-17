import io
import unittest

from docx import Document

from core.ferc_extractor import (
    FERC_COURT_CODE,
    is_ferc_row,
    parse_ferc_document_text,
    parse_ferc_docx_bytes,
)


class FERCExtractorTests(unittest.TestCase):
    def parse(self, body):
        metadata = parse_ferc_document_text(body)
        self.assertIsNotNone(metadata)
        return metadata

    def test_certification_is_opinion_with_secondary_docket_and_citation_comment(self):
        metadata = self.parse("""
            196 FERC ¶ 63,010
            UNITED STATES OF AMERICA
            FEDERAL ENERGY REGULATORY COMMISSION
            Docket Nos. ER26-1137-000
            ER26-1137-001
            CERTIFICATION OF UNCONTESTED OFFER OF SETTLEMENT
            (Issued September 8, 2026)
        """)
        self.assertEqual(FERC_COURT_CODE, metadata.court)
        self.assertEqual("ER26-1137-000", metadata.docket_number)
        self.assertEqual(("ER26-1137-001",), metadata.other_numbers)
        self.assertEqual("09-08-2026", metadata.decision_date)
        self.assertEqual("Opinion", metadata.source_detail)
        self.assertEqual("196 FERC ¶ 63,010; ER26-1137-001", metadata.comments_text)

    def test_genuine_order_is_order(self):
        metadata = self.parse("""
            196 FERC ¶ 61,089
            FEDERAL ENERGY REGULATORY COMMISSION
            Eastern Gas Transmission and Storage, Inc. Docket No. RP26-939-000
            ORDER ACCEPTING AND SUSPENDING TARIFF RECORDS, SUBJECT TO REFUND
            (Issued July 31, 2026)
        """)
        self.assertEqual("Order", metadata.source_detail)

    def test_order_focused_heading_with_a_prefix_is_order(self):
        metadata = self.parse("""
            196 FERC ¶ 61,089
            FEDERAL ENERGY REGULATORY COMMISSION
            Docket No. ER26-999-000
            INITIAL ORDER GRANTING RELIEF
            (Issued July 31, 2026)
        """)
        self.assertEqual("Order", metadata.source_detail)

    def test_opinion_with_order_in_title_is_opinion(self):
        metadata = self.parse("""
            195 FERC ¶ 61,167
            FEDERAL ENERGY REGULATORY COMMISSION
            Docket Nos. ER21-915-000
            EL22-6-001
            OPINION NO. 595
            ORDER ON INITIAL DECISION
            (Issued June 2, 2026)
        """)
        self.assertEqual("OPINION NO. 595", metadata.title_hint)
        self.assertEqual("Opinion", metadata.source_detail)

    def test_notice_heading_is_opinion_not_a_later_body_order_reference(self):
        metadata = self.parse("""
            197 FERC ¶ 62,037
            UNITED STATES OF AMERICA
            FEDERAL ENERGY REGULATORY COMMISSION
            H.A. Wagner LLC
            Docket Nos. ER26-2739-003
            ER26-2740-003
            NOTICE OF DENIAL OF REHEARING BY OPERATION OF LAW AND
            PROVIDING FOR FURTHER CONSIDERATION
            (October 19, 2026)
            The order filed in this proceeding will be addressed in a future order.
        """)
        self.assertEqual(
            "NOTICE OF DENIAL OF REHEARING BY OPERATION OF LAW AND",
            metadata.title_hint,
        )
        self.assertEqual("Opinion", metadata.source_detail)

    def test_errata_is_stopped_for_review(self):
        metadata = self.parse("""
            196 FERC ¶ 61,135
            FEDERAL ENERGY REGULATORY COMMISSION
            Appalachian Power Company Project No. 2514-209
            ERRATA NOTICE
            (August 14, 2026)
        """)
        self.assertEqual("2514-209", metadata.docket_number)
        self.assertEqual("08-14-2026", metadata.decision_date)
        self.assertEqual("Corrections", metadata.source_detail)
        self.assertEqual("ERRATA FOR REVIEW", metadata.review_status)
        self.assertTrue(metadata.requires_review)

    def test_plural_project_numbers_use_first_as_primary_and_keep_the_rest(self):
        metadata = self.parse("""
            197 FERC ¶ 62,030
            UNITED STATES OF AMERICA
            FEDERAL ENERGY REGULATORY COMMISSION
            FirstLight CT Housatonic, LLC Project Nos. 2576-219 and 2576-221
            ORDER MODIFYING AND APPROVING NON-PROJECT USE OF PROJECT
            (Issued October 14, 2026)
        """)
        self.assertEqual("2576-219", metadata.docket_number)
        self.assertEqual(("2576-221",), metadata.other_numbers)
        self.assertEqual("197 FERC ¶ 62,030; 2576-221", metadata.comments_text)
        self.assertFalse(metadata.requires_review)

    def test_body_footnote_numbers_do_not_become_other_dockets(self):
        metadata = self.parse("""
            196 FERC ¶ 63,008
            FEDERAL ENERGY REGULATORY COMMISSION
            Consolidated Edison Company of New York, Inc. Docket Nos. ER26-1206-000
            ER26-1206-003
            CERTIFICATION OF UNCONTESTED OFFER OF SETTLEMENT
            (Issued August 26, 2026)
            1 The filing consisted of a Transmittal Letter at 1-2.
        """)
        self.assertEqual(("ER26-1206-003",), metadata.other_numbers)

    def test_incomplete_header_requires_review(self):
        metadata = self.parse("""
            FEDERAL ENERGY REGULATORY COMMISSION
            ORDER APPROVING ABANDONMENT
            (Issued February 9, 2026)
        """)
        self.assertEqual("NEEDS REVIEW", metadata.review_status)

    def test_docx_uses_the_same_ferc_metadata_rules_as_pdf(self):
        document = Document()
        document.add_paragraph("196 FERC ¶ 63,010")
        document.add_paragraph("UNITED STATES OF AMERICA")
        document.add_paragraph("FEDERAL ENERGY REGULATORY COMMISSION")
        document.add_paragraph("Docket Nos. ER26-1137-000")
        document.add_paragraph("ER26-1137-001")
        document.add_paragraph("CERTIFICATION OF UNCONTESTED OFFER OF SETTLEMENT")
        document.add_paragraph("(Issued September 8, 2026)")
        payload = io.BytesIO()
        document.save(payload)

        metadata = parse_ferc_docx_bytes(payload.getvalue(), "FERC-settlement.docx")

        self.assertIsNotNone(metadata)
        self.assertEqual("ER26-1137-000", metadata.docket_number)
        self.assertEqual(("ER26-1137-001",), metadata.other_numbers)
        self.assertEqual("09-08-2026", metadata.decision_date)
        self.assertEqual("Opinion", metadata.source_detail)
        self.assertEqual("196 FERC ¶ 63,010; ER26-1137-001", metadata.comments_text)

    def test_docx_reads_first_page_dockets_from_the_header_and_caption_table(self):
        document = Document()
        document.sections[0].header.paragraphs[0].text = "Docket Nos. RM93-11-004 and RM20-14-005"
        document.add_paragraph("197 FERC ¶ 61,035")
        document.add_paragraph("UNITED STATES OF AMERICA")
        document.add_paragraph("FEDERAL ENERGY REGULATORY COMMISSION")
        caption = document.add_table(rows=1, cols=2)
        caption.cell(0, 0).text = "Revisions to Oil Pipeline Regulations"
        caption.cell(0, 1).text = "Docket Nos. RM93-11-004 and RM20-14-005"
        document.add_paragraph("ORDER ON CLARIFICATION AND MOTION FOR STAY")
        document.add_paragraph("(Issued October 15, 2026)")
        payload = io.BytesIO()
        document.save(payload)

        metadata = parse_ferc_docx_bytes(payload.getvalue(), "LDC_SMD_RM93-11-004_E2E.docx")

        self.assertIsNotNone(metadata)
        self.assertEqual("RM93-11-004", metadata.docket_number)
        self.assertEqual(("RM20-14-005",), metadata.other_numbers)
        self.assertEqual("10-15-2026", metadata.decision_date)
        self.assertEqual("Order", metadata.source_detail)
        self.assertEqual("197 FERC ¶ 61,035; RM20-14-005", metadata.comments_text)
        self.assertFalse(metadata.requires_review)

    def test_row_scope(self):
        self.assertTrue(is_ferc_row({"CourtCode": "FDFERC00"}))
        self.assertFalse(is_ferc_row({"CourtCode": "FDFCC000"}))

    def test_letter_uses_header_date_docket_and_citation_only(self):
        metadata = self.parse("""
            197 FERC ¶ 61,095
            FEDERAL ENERGY REGULATORY COMMISSION
            WASHINGTON, DC 20426
            November 5, 2026
            In Reply Refer To:
            Tri-State Generation and Transmission Association, Inc.
            Docket No. ER26-1929-002
            Willkie Farr & Gallagher LLP
            1875 K Street, NW
            Washington, DC 20006
            Attention: Fredrick Wilson
            Dear Mr. Wilson:
            On September 9, 2026, Tri-State submitted revisions.
            The Commission's order issued on August 14, 2026 applies.
            In Docket No. ER25-3316-000, Tri-State proposed a tariff.
            196 FERC ¶ 61,127 (2026).
        """)
        self.assertEqual("Letter", metadata.source_detail)
        self.assertEqual("Dear Mr. Wilson:", metadata.title_hint)
        self.assertEqual("ER26-1929-002", metadata.docket_number)
        self.assertEqual((), metadata.other_numbers)
        self.assertEqual("11-05-2026", metadata.decision_date)
        self.assertEqual("197 FERC ¶ 61,095", metadata.comments_text)
        self.assertFalse(metadata.requires_review)

    def test_letter_accepts_issued_date_prefix_variants(self):
        for date_line in (
            "Issued:  November 6, 2026",
            "Issued:November 6, 2026",
            "Issued : November 6, 2026",
            "Issued November 6, 2026",
            "Issued on November 6, 2026",
            "November 6, 2026",
        ):
            with self.subTest(date_line=date_line):
                metadata = self.parse(f"""
                    197 FERC ¶ 62,072
                    FEDERAL ENERGY REGULATORY COMMISSION
                    WASHINGTON, DC 20426
                    OFFICE OF ENERGY MARKET REGULATION
                    In Reply Refer To:
                    US Borax Inc.
                    Docket Nos. EL26-97-000
                    QF82-202-002
                    {date_line}
                    Damien R. Lyster
                    Kirkland & Ellis LLP
                    Reference: Request for Waiver of Efficiency Standards
                    Dear Mr. Lyster:
                    On August 10, 2026, you submitted a petition.
                    Issued: August 14, 2026
                    Docket No. QF82-202-000
                """)
                self.assertEqual("11-06-2026", metadata.decision_date)
                self.assertEqual("Letter", metadata.source_detail)
                self.assertEqual("EL26-97-000", metadata.docket_number)
                self.assertEqual(("QF82-202-002",), metadata.other_numbers)
                self.assertEqual("197 FERC ¶ 62,072; QF82-202-002", metadata.comments_text)
                self.assertFalse(metadata.requires_review)

    def test_letter_invalid_issued_date_does_not_use_body_date(self):
        metadata = self.parse("""
            197 FERC ¶ 62,072
            FEDERAL ENERGY REGULATORY COMMISSION
            Docket No. EL26-97-000
            Issued: November 31, 2026
            Dear Mr. Lyster:
            Issued: November 6, 2026
        """)
        self.assertEqual("", metadata.decision_date)
        self.assertEqual("NEEDS REVIEW", metadata.review_status)
        self.assertTrue(metadata.requires_review)

    def test_letter_preserves_multiple_header_dockets_and_ignores_body_heading(self):
        metadata = self.parse("""
            197 FERC ¶ 61,095
            November 5, 2026
            Docket Nos. ER26-1929-002 and ER26-1929-003
            Dear Counsel,
            ORDER REFERENCED IN YOUR REQUEST
            Issued August 14, 2026
        """)
        self.assertEqual("Letter", metadata.source_detail)
        self.assertEqual(("ER26-1929-003",), metadata.other_numbers)
        self.assertEqual("11-05-2026", metadata.decision_date)

    def test_letter_missing_header_fields_still_requires_review(self):
        metadata = self.parse("""
            November 5, 2026
            Dear Mr. Wilson:
            This references Docket No. ER26-1929-002 and 197 FERC ¶ 61,095.
        """)
        self.assertEqual("Letter", metadata.source_detail)
        self.assertEqual("", metadata.docket_number)
        self.assertEqual("", metadata.comments_text)
        self.assertTrue(metadata.requires_review)

    def test_letter_date_is_nearest_top_citation(self):
        metadata = self.parse("""
            197 FERC ¶ 61,095
            FEDERAL ENERGY REGULATORY COMMISSION
            November 5, 2026
            Docket No. ER26-1929-002
            In Reply Refer To:
            September 9, 2026
            Dear Mr. Wilson:
            Issued August 14, 2026
        """)
        self.assertEqual("Letter", metadata.source_detail)
        self.assertEqual("11-05-2026", metadata.decision_date)

    def test_formal_order_with_body_salutation_remains_order(self):
        metadata = self.parse("""
            197 FERC ¶ 61,095
            Docket No. ER26-1929-002
            ORDER ACCEPTING FILING
            (Issued November 5, 2026)
            Dear Counsel:
            Quoted correspondence follows.
        """)
        self.assertEqual("Order", metadata.source_detail)
        self.assertFalse(metadata.requires_review)


if __name__ == "__main__":
    unittest.main()
