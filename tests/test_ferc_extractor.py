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


if __name__ == "__main__":
    unittest.main()
