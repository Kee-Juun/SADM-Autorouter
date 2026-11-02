import unittest

from core.critical_error_notifier import _build_success_email_body
from core.rerun_status import summarize_statuses_for_rows
import pandas as pd


class ManualReviewReportingTests(unittest.TestCase):
    def test_success_email_names_manual_review_documents(self):
        theme = {
            "hello": "Hello,",
            "opener": "{app_name} completed.",
            "scoreboard": "Results:",
            "attachments": "Attachments included.",
            "closer": "Done.",
        }
        review_summary = {
            "manual_review_count": 1,
            "manual_review_rows": [{
                "File Name": "LDC_SMD_P-2576-219_E2E.pdf",
                "LNI": "6KRV-X203-S9X6-C2W3-00000-00",
                "Status": "NEEDS REVIEW",
            }],
        }

        body = _build_success_email_body(
            "ferc",
            {"main_success": 5},
            "C:/reports/run",
            theme,
            run_status_summary=review_summary,
        )

        self.assertIn("Manual review required:", body)
        self.assertIn("Documents skipped safely: 1", body)
        self.assertIn("LDC_SMD_P-2576-219_E2E.pdf", body)
        self.assertIn("6KRV-X203-S9X6-C2W3-00000-00", body)

    def test_detailed_manual_review_reason_is_reported(self):
        df = pd.DataFrame([{
            "LNI": "6NLR-B000-TEST-0000-00000-00",
            "FileName": "unreadable-nlrb.pdf",
        }])
        summary = summarize_statuses_for_rows(
            df,
            {0: "MANUAL REVIEW REQUIRED — MISSING DECISION DATE"},
        )

        self.assertEqual(summary["manual_review_count"], 1)
        self.assertEqual(
            summary["manual_review_rows"][0]["Status"],
            "MANUAL REVIEW REQUIRED — MISSING DECISION DATE",
        )


if __name__ == "__main__":
    unittest.main()
