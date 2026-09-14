import unittest

import pandas as pd

from core.mework_extractor import MEWORKMetadata
from core.rerun_status import mode_scope_df
from core.smducar_config import mework_content_fingerprint_buffer, status_updates_buffer
from core.smducar_router import CaseLawRouter
from core.smducar_workflow import (
    _count_results_for_rows,
    _get_mode_router_label,
    _select_parallel_document_rows,
)


class MEWORKWorkflowTests(unittest.TestCase):
    def setUp(self):
        mework_content_fingerprint_buffer.clear()
        status_updates_buffer.clear()

    def tearDown(self):
        mework_content_fingerprint_buffer.clear()
        status_updates_buffer.clear()

    @staticmethod
    def row(lni, court="STMEWORK", status=""):
        return {
            "LNI": lni,
            "CourtCode": court,
            "FileName": f"MEWORK_{lni}.pdf",
            "Status": status,
        }

    @staticmethod
    def metadata(*, fingerprint="same-text", excluded=False):
        return MEWORKMetadata(
            court="STMEWORK",
            docket_number="23021622B",
            decision_date="02-28-2025",
            source_detail="Excluded" if excluded else "Opinion",
            content_fingerprint=fingerprint,
            has_text_content=True,
            is_excluded=excluded,
            exclusion_reason="Consent Decree" if excluded else "",
        )

    def test_mode_scope_keeps_only_stmework_rows(self):
        df = pd.DataFrame([
            self.row("A"),
            self.row("B", court="FDITC000"),
        ])
        scoped = mode_scope_df(df, "mework")
        self.assertEqual(list(scoped["LNI"]), ["A"])

    def test_parallel_selection_treats_mework_as_single_document_mode(self):
        df = pd.DataFrame([self.row("A"), self.row("B")])
        selected = _select_parallel_document_rows(df, df, 0, mework_mode=True)
        self.assertEqual(list(selected["LNI"]), ["A", "B"])
        self.assertEqual(_get_mode_router_label(mework_mode=True), "MEWORK")

    def test_mework_results_are_counted_as_documents_not_counsel(self):
        df = pd.DataFrame([self.row("A")])
        status_updates_buffer[0] = "DONE"
        counts = _count_results_for_rows(
            df,
            False,
            False,
            False,
            mework_mode=True,
            current_run_only=True,
        )
        self.assertEqual(counts, (0, 1, 0, 0, 0, 0))

    def test_duplicate_requires_matching_content_fingerprint(self):
        router = CaseLawRouter.__new__(CaseLawRouter)
        first = router.mark_mework_duplicate_status(0, self.row("A"), "A", self.metadata())
        second = router.mark_mework_duplicate_status(1, self.row("B"), "B", self.metadata())
        different = router.mark_mework_duplicate_status(
            2,
            self.row("C"),
            "C",
            self.metadata(fingerprint="different-text"),
        )
        self.assertFalse(first.is_true_duplicate)
        self.assertTrue(second.is_true_duplicate)
        self.assertEqual(second.duplicate_of_lni, "A")
        self.assertFalse(different.is_true_duplicate)

    def test_exclusion_wins_and_is_not_registered_as_duplicate(self):
        router = CaseLawRouter.__new__(CaseLawRouter)
        excluded = self.metadata(excluded=True)
        first = router.mark_mework_duplicate_status(0, self.row("A"), "A", excluded)
        second = router.mark_mework_duplicate_status(1, self.row("B"), "B", excluded)
        self.assertFalse(first.is_true_duplicate)
        self.assertFalse(second.is_true_duplicate)
        self.assertEqual(mework_content_fingerprint_buffer, {})


if __name__ == "__main__":
    unittest.main()
