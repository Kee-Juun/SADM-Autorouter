import unittest

import pandas as pd

from core.fcc_extractor import NO_NUMBER_IN_ORIGINAL, parse_fcc_document_text
from core.rerun_status import is_completed_status, rerun_status_for, summarize_statuses_for_rows


class FCCExtractorTests(unittest.TestCase):
    def parse(self, body):
        metadata = parse_fcc_document_text(body)
        self.assertIsNotNone(metadata)
        return metadata

    def test_report_and_order_is_opinion_with_release_header_docket(self):
        metadata = self.parse("""
            Federal Communications Commission
            DA 26-1039
            MB Docket No. 26-113
            REPORT AND ORDER
            Released: October 1, 2026
        """)
        self.assertEqual("FDFCC000", metadata.court)
        self.assertEqual("DA 26-1039", metadata.docket_number)
        self.assertEqual("10-01-2026", metadata.decision_date)
        self.assertEqual("Opinion", metadata.source_detail)
        self.assertIn("MB Docket No. 26-113", metadata.other_numbers)

    def test_order_focused_title_is_order(self):
        metadata = self.parse("""
            Federal Communications Commission
            FCC 26-12
            ORDER ON RECONSIDERATION
            Released: October 2, 2026
        """)
        self.assertEqual("Order", metadata.source_detail)

    def test_erratum_stops_before_irt(self):
        metadata = self.parse("""
            Federal Communications Commission
            DA 26-99
            ERRATUM
            Released: September 29, 2026
        """)
        self.assertTrue(metadata.requires_review)
        self.assertEqual("ERRATA FOR REVIEW", metadata.review_status)

    def test_attachment_stops_before_irt(self):
        metadata = self.parse("""
            Federal Communications Commission
            FCC 26-100
            ATTACHMENT A
            Released: September 29, 2026
        """)
        self.assertTrue(metadata.requires_review)
        self.assertEqual("ATTACHMENT FOR REVIEW", metadata.review_status)

    def test_petition_is_excluded_but_reconsideration_order_is_not(self):
        petition = self.parse("""
            Federal Communications Commission
            DA 26-44
            PETITION FOR RULEMAKING
            Released: September 1, 2026
        """)
        self.assertTrue(petition.is_excluded)
        self.assertEqual("Excluded", petition.source_detail)
        reconsideration = self.parse("""
            Federal Communications Commission
            FCC 26-45
            ORDER ON PETITION FOR RECONSIDERATION
            Released: September 2, 2026
        """)
        self.assertFalse(reconsideration.is_excluded)
        self.assertEqual("Order", reconsideration.source_detail)

    def test_daily_digest_and_missing_release_date(self):
        digest = self.parse("""
            FEDERAL COMMUNICATIONS COMMISSION DAILY DIGEST
            Volume 45, Issue 33
            Publish Date: October 4, 2026
        """)
        self.assertEqual("Volume 45, Issue 33", digest.docket_number)
        self.assertEqual("10-04-2026", digest.decision_date)
        missing = self.parse("""
            Federal Communications Commission
            NOTICE
        """)
        self.assertEqual(NO_NUMBER_IN_ORIGINAL, missing.docket_number)
        self.assertEqual("NEEDS REVIEW", missing.review_status)

    def test_report_number_is_the_primary_fallback_when_no_release_number_exists(self):
        metadata = self.parse("""
            REPORT NO. PN-2-261013-01 | PUBLISH DATE: 10/13/2026
            PUBLIC NOTICE
            Federal Communications Commission
        """)
        self.assertEqual("Report No. PN-2-261013-01", metadata.docket_number)
        self.assertEqual("10-13-2026", metadata.decision_date)
        self.assertEqual("Opinion", metadata.source_detail)

    def test_public_notice_header_column_order_still_reads_publish_date(self):
        metadata = self.parse("""
            | PUBLISH DATE: REPORT NO. PN-2-261013-01 10/13/2026
            PUBLIC NOTICE
        """)
        self.assertEqual("Report No. PN-2-261013-01", metadata.docket_number)
        self.assertEqual("10-13-2026", metadata.decision_date)

    def test_report_number_date_layouts_and_body_petition_reference(self):
        report = self.parse("""
            PUBLIC NOTICE
            Report No. SES-02826 Wednesday January 14, 2026
            RE: Applications Accepted for Filing
        """)
        self.assertEqual("Report No. SES-02826", report.docket_number)
        self.assertEqual("01-14-2026", report.decision_date)
        self.assertEqual("Opinion", report.source_detail)
        reversed_columns = self.parse("""
            20677Report Number:
            Date of Report: 09/09/2026
            PUBLIC NOTICE
        """)
        self.assertEqual("Report No. 20677", reversed_columns.docket_number)
        self.assertEqual("09-09-2026", reversed_columns.decision_date)
        body_reference = self.parse("""
            Report No. SAT-01966 Friday January 16, 2026
            RE: Applications Accepted for Filing
            The body refers to a petition only as background.
        """)
        self.assertFalse(body_reference.is_excluded)
        self.assertEqual("Opinion", body_reference.source_detail)

    def test_actual_letter_format_remains_letter(self):
        metadata = self.parse("""
            Report No. CWS-26-22 January 20, 2026
            Dear Licensee:
            This is an actual correspondence letter.
        """)
        self.assertEqual("Letter", metadata.source_detail)

    def test_manual_review_outcomes_are_not_converted_to_rerun_failures(self):
        for status in ("ERRATA FOR REVIEW", "ATTACHMENT FOR REVIEW", "NEEDS REVIEW"):
            self.assertTrue(is_completed_status(status))
            self.assertEqual(status, rerun_status_for(status))

    def test_manual_review_summary_includes_count_and_rows(self):
        df = pd.DataFrame([
            {"LNI": "review-lni", "FileName": "errata.pdf", "Status": "ERRATA FOR REVIEW"},
            {"LNI": "done-lni", "FileName": "done.pdf", "Status": "DONE"},
        ])
        summary = summarize_statuses_for_rows(df, status_map={0: "ERRATA FOR REVIEW", 1: "DONE"})
        self.assertEqual(1, summary["manual_review_count"])
        self.assertEqual("review-lni", summary["manual_review_rows"][0]["LNI"])
        self.assertEqual("ERRATA FOR REVIEW", summary["manual_review_rows"][0]["Status"])



if __name__ == "__main__":
    unittest.main()
