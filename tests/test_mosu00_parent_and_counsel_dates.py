import datetime
import unittest

import pandas as pd

from core.mosu00_extractor import parse_mosu00_html_text
from core.smducar_router import CaseLawRouter


class MOSU00ParentAndCounselDateTests(unittest.TestCase):
    def test_parent_docket_is_not_sent_to_the_table_child_list(self):
        metadata = parse_mosu00_html_text(
            """
            <h1>Minutes of September 29, 2026</h1>
            <p>SC101636; SC101733; SC101784; SC101789</p>
            """,
            filename_hint="LDC_SMD_MinutesofSeptember29_2026_E2E.html",
        )

        self.assertIsNotNone(metadata)
        self.assertEqual(metadata.docket_number, "SC101636")
        self.assertEqual(metadata.child_dockets, ("SC101733", "SC101784", "SC101789"))
        self.assertNotIn(metadata.docket_number, metadata.child_dockets)

    def test_table_metadata_without_a_non_parent_docket_is_rejected(self):
        metadata = parse_mosu00_html_text(
            "Minutes of September 29, 2026\nSC101636",
            filename_hint="LDC_SMD_MinutesofSeptember29_2026_E2E.html",
        )

        self.assertIsNone(metadata)

    def test_counsel_uses_matched_main_mapping_decision_date(self):
        router = CaseLawRouter.__new__(CaseLawRouter)
        full_df = pd.DataFrame([
            {
                "FileName": "LDC_SMD_SC101636_E2E.pdf",
                "Decision Date": datetime.date(2026, 9, 29),
            },
            {
                "FileName": "LDC_SMD_SC101636counsel_E2E.pdf",
                "Decision Date": "09-30-2026",
            },
        ])

        decision_date = router.find_main_opinion_date_for_counsel(
            "SC101636",
            "LDC_SMD_SC101636counsel_E2E.pdf",
            full_df=full_df,
        )

        self.assertEqual(decision_date, "09-29-2026")


if __name__ == "__main__":
    unittest.main()
