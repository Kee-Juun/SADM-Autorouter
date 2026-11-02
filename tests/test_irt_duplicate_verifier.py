import unittest
from unittest.mock import Mock, patch

import pandas as pd
from selenium.common.exceptions import TimeoutException

from core.irt_duplicate_verifier import (
    IRTDocumentProfile,
    compare_document_profiles,
    normalize_document_text,
)
from core.smducar_router import CaseLawRouter


class IRTDuplicateVerifierTests(unittest.TestCase):
    def profile(self, lni, digest, text):
        return IRTDocumentProfile(lni, digest, normalize_document_text(text))

    def test_identical_pdf_is_confirmed(self):
        result = compare_document_profiles(
            self.profile("AAAA-1111-BBBB-2222-00000-00", "same", "first"),
            self.profile("CCCC-3333-DDDD-4444-00000-00", "same", "different"),
        )
        self.assertTrue(result.is_match)
        self.assertEqual(result.method, "identical PDF")

    def test_identical_extracted_text_is_confirmed(self):
        text = ("A decision with layout and findings. " * 40).strip()
        result = compare_document_profiles(
            self.profile("AAAA-1111-BBBB-2222-00000-00", "one", text),
            self.profile("CCCC-3333-DDDD-4444-00000-00", "two", text.upper().replace(" ", "  ")),
        )
        self.assertTrue(result.is_match)
        self.assertEqual(result.method, "identical extracted text")

    def test_short_identical_text_is_not_sufficient_evidence(self):
        result = compare_document_profiles(
            self.profile("AAAA-1111-BBBB-2222-00000-00", "one", "same brief header"),
            self.profile("CCCC-3333-DDDD-4444-00000-00", "two", "same brief header"),
        )
        self.assertFalse(result.is_match)

    def test_short_or_partly_similar_text_is_not_confirmed(self):
        result = compare_document_profiles(
            self.profile("AAAA-1111-BBBB-2222-00000-00", "one", "same heading and subject"),
            self.profile("CCCC-3333-DDDD-4444-00000-00", "two", "same heading and subject with changes"),
        )
        self.assertFalse(result.is_match)

    def test_near_identical_substantial_text_is_confirmed(self):
        first = "A" * 999 + "B"
        second = "A" * 999 + "C"
        result = compare_document_profiles(
            self.profile("AAAA-1111-BBBB-2222-00000-00", "one", first),
            self.profile("CCCC-3333-DDDD-4444-00000-00", "two", second),
        )
        self.assertTrue(result.is_match)
        self.assertGreaterEqual(result.similarity, 0.995)

    def test_sadm_and_dara_disable_content_verification(self):
        router = CaseLawRouter.__new__(CaseLawRouter)

        self.assertFalse(router.configure_irt_duplicate_verification())
        self.assertFalse(router.configure_irt_duplicate_verification())

    def test_specialized_router_modes_keep_content_verification(self):
        router = CaseLawRouter.__new__(CaseLawRouter)

        self.assertTrue(router.configure_irt_duplicate_verification(mspb_mode=True))
        self.assertTrue(router.configure_irt_duplicate_verification(itc_mode=True))
        self.assertTrue(router.configure_irt_duplicate_verification(mosu00_mode=True))
        self.assertTrue(router.configure_irt_duplicate_verification(ferc_mode=True))
        self.assertTrue(router.configure_irt_duplicate_verification(nlrb_mode=True))

    def test_sadm_duplicate_alert_processes_as_new_without_pdf_comparison(self):
        router = CaseLawRouter.__new__(CaseLawRouter)
        router._irt_duplicate_verification_enabled = False
        router.verify_irt_duplicate_overlay = Mock(side_effect=AssertionError("must not compare PDFs"))
        router.accept_pending_alerts = Mock(return_value=(False, False))
        router.click_duplicate_process_radio = Mock()
        router.click_duplicate_continue_button = Mock()
        router.wait_for_duplicate_overlay_to_clear = Mock()

        self.assertTrue(router.handle_duplicate_overlay())
        router.verify_irt_duplicate_overlay.assert_not_called()
        router.click_duplicate_process_radio.assert_called_once()
        router.click_duplicate_continue_button.assert_called_once()

    def test_direct_sadm_batch_initializes_the_process_as_new_policy(self):
        router = CaseLawRouter.__new__(CaseLawRouter)
        router.configure_irt_duplicate_verification = Mock()
        router.safe_alert_accept = Mock()

        router.process_batch(pd.DataFrame(), None, None, None, "main")

        router.configure_irt_duplicate_verification.assert_called_once_with()
        router.safe_alert_accept.assert_called_once()

    def test_dsar_alert_without_a_follow_up_leaves_modify_mode_ready(self):
        router = CaseLawRouter.__new__(CaseLawRouter)
        router.driver = Mock()
        router.check_session_validity = Mock(return_value=True)
        router.settle_irt_modify_transition = Mock(return_value="EDITABLE")

        modify_button = Mock()
        dsar_alert = Mock(text="The document has been marked as duplicate by DSAR")
        waits = [
            Mock(until=Mock(return_value=modify_button)),
            Mock(until=Mock(return_value=dsar_alert)),
            Mock(until=Mock(side_effect=TimeoutException())),
        ]

        with patch("core.smducar_router.WebDriverWait", side_effect=waits), patch(
            "core.smducar_router.time.sleep"
        ):
            self.assertTrue(router.attempt_open_modify(max_attempts=1))

        modify_button.click.assert_called_once()
        dsar_alert.accept.assert_called_once()


if __name__ == "__main__":
    unittest.main()
