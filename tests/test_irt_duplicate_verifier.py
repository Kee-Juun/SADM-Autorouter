import unittest
from unittest.mock import Mock

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


if __name__ == "__main__":
    unittest.main()
