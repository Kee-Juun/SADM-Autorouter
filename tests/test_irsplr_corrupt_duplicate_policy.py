"""A bad original must not cause a valid replacement to be archived."""

from io import BytesIO
import re
import unittest
from unittest.mock import Mock, patch

import pandas as pd
from pypdf import PdfReader

from core.irsplr_extractor import IRSPLRCorruptDocument, IRSPLRDocumentReviewRequired, validate_irsplr_pdf_bytes
from core.irt_duplicate_verifier import IRTDocumentProfile, build_document_profile, compare_document_profiles
from core.rerun_status import should_recheck_irsplr_pdf_review
from core.smducar_router import CaseLawRouter
from core.smducar_workflow import _completed_status_mask
from tests.test_irsplr_ocr_integrity import blank_pdf


def nonstandard_trailer_pdf():
    payload = blank_pdf()
    reader = PdfReader(BytesIO(payload))
    root = reader.trailer.raw_get("/Root")
    previous = re.search(rb"startxref\s+(\d+)\s+%%EOF", payload).group(1).decode()
    tail = (
        f"\nxref\n0 0\ntrailer\n<< /Size {reader.trailer['/Size']} /Root {root.idnum} {root.generation} R /Prev {previous} >>\n"
        f"startxref\n{len(payload) + 1}\n%%EO\0\n"
    ).encode()
    return payload + tail


class PDFProfileSafetyTests(unittest.TestCase):
    def test_bitmap_named_pdf_is_corrupt_without_ocr(self):
        with patch("core.irt_duplicate_verifier.extract_text_from_pdf_bytes") as extract:
            profile = build_document_profile("OLD", b"BMbitmap", verify_pdf=True)
        self.assertTrue(profile.is_verified_corrupt)
        self.assertFalse(profile.is_verified_pdf)
        extract.assert_not_called()

    def test_corrupt_profile_is_never_a_duplicate_even_with_matching_hash_or_text(self):
        incoming = IRTDocumentProfile("NEW", "same", "A" * 1000, is_verified_pdf=True)
        old = IRTDocumentProfile("OLD", "same", "A" * 1000, is_verified_corrupt=True)
        self.assertFalse(compare_document_profiles(incoming, old).is_match)

    def test_html_or_unknown_download_is_not_classified_as_corrupt(self):
        for payload in (b"<html>Login</html>", b"Service unavailable"):
            with self.assertRaises(IRSPLRDocumentReviewRequired) as raised:
                build_document_profile("OLD", payload, verify_pdf=True)
            self.assertNotIsInstance(raised.exception, IRSPLRCorruptDocument)

    def test_scanned_pdf_remains_valid_when_text_is_empty(self):
        with patch("core.irt_duplicate_verifier.extract_text_from_pdf_bytes", return_value=""):
            profile = build_document_profile("NEW", blank_pdf(), verify_pdf=True)
        self.assertTrue(profile.is_verified_pdf)
        self.assertFalse(profile.is_verified_corrupt)

    def test_known_empty_incremental_trailer_is_accepted_after_independent_render(self):
        from core.irsplr_extractor import _validate_irsplr_nonstandard_trailer_rendering
        with patch("core.irsplr_extractor._validate_irsplr_nonstandard_trailer_rendering", wraps=_validate_irsplr_nonstandard_trailer_rendering) as render:
            payload = nonstandard_trailer_pdf()
            validate_irsplr_pdf_bytes(payload)
        render.assert_called_once_with(payload, 1)

    def test_nonstandard_trailer_cannot_bypass_failed_independent_render(self):
        with patch("fitz.open", side_effect=RuntimeError("renderer failed")), \
                self.assertRaises(IRSPLRDocumentReviewRequired) as raised:
            validate_irsplr_pdf_bytes(nonstandard_trailer_pdf())
        self.assertNotIsInstance(raised.exception, IRSPLRCorruptDocument)

    def test_partial_new_content_or_arbitrary_tail_still_requires_review(self):
        for payload in (
            blank_pdf() + b"\ntrailing data",
            nonstandard_trailer_pdf().replace(b"xref\n0 0", b"1 0 obj\n<<>>\nendobj\nxref\n0 0"),
            blank_pdf().rsplit(b"%%EOF", 1)[0],
        ):
            with self.assertRaises(IRSPLRDocumentReviewRequired) as raised:
                validate_irsplr_pdf_bytes(payload)
            self.assertNotIsInstance(raised.exception, IRSPLRCorruptDocument)

    def test_pdf_nul_whitespace_after_complete_eof_is_legal(self):
        validate_irsplr_pdf_bytes(blank_pdf() + b"\0\0\n")


class CorruptOriginalPolicyTests(unittest.TestCase):
    def setUp(self):
        self.router = CaseLawRouter.__new__(CaseLawRouter)
        self.router._irsplr_duplicate_pdf_validation = True
        self.router._irt_duplicate_verification_enabled = True
        self.router._irsplr_duplicate_review_reason = ""
        self.router._active_duplicate_lni = "NEW"
        self.router._visible_duplicate_candidate_lnis = Mock(return_value=["OLD"])
        self.new = IRTDocumentProfile("NEW", "new", "A" * 1000, is_verified_pdf=True, is_browser_verified=True)
        self.corrupt = IRTDocumentProfile("OLD", "", "", is_verified_corrupt=True, validation_reason="Failed to load PDF")
        self.profiles = {"NEW": self.new, "OLD": self.corrupt}
        self.router._document_profile_for_irt_lni = Mock(side_effect=lambda lni: self.profiles.get(lni))
        for name in ("accept_pending_alerts", "click_duplicate_process_radio", "click_duplicate_archive_radio",
                     "click_duplicate_continue_button", "wait_for_duplicate_overlay_to_clear", "append_comments"):
            setattr(self.router, name, Mock())

    def test_verified_corrupt_old_source_processes_valid_replacement_as_new(self):
        self.assertTrue(self.router.handle_duplicate_overlay())
        self.router.click_duplicate_process_radio.assert_called_once()
        self.router.click_duplicate_continue_button.assert_called_once()
        self.router.click_duplicate_archive_radio.assert_not_called()
        self.router.append_comments.assert_not_called()
        self.assertEqual(self.router._irsplr_duplicate_review_reason, "")

    def test_all_candidates_checked_before_ignoring_corrupt_old_source(self):
        self.router._visible_duplicate_candidate_lnis.return_value = ["OLD", "HEALTHY"]
        self.profiles["HEALTHY"] = IRTDocumentProfile("HEALTHY", "new", "A" * 1000, is_verified_pdf=True, is_browser_verified=True)
        self.assertTrue(self.router.handle_duplicate_overlay())
        self.router.click_duplicate_archive_radio.assert_called_once()
        self.router.click_duplicate_process_radio.assert_not_called()
        self.router.append_comments.assert_called_once_with(["Dup of HEALTHY"], "verified duplicate")

    def test_unavailable_original_blocks_process_new_and_save(self):
        self.profiles["OLD"] = None
        self.assertFalse(self.router.handle_duplicate_overlay())
        self.router.click_duplicate_process_radio.assert_not_called()
        self.router.click_duplicate_archive_radio.assert_not_called()
        self.router.click_duplicate_continue_button.assert_not_called()
        self.assertIn("could not be validated", self.router._irsplr_duplicate_review_reason)
        self.router._active_duplicate_row = {"LNI": "NEW"}
        self.router.flag_irsplr_document_review = Mock(return_value="MANUAL REVIEW REQUIRED")
        self.assertEqual(self.router.handle_routing_and_save(False, 3), "MANUAL REVIEW REQUIRED")
        self.router.flag_irsplr_document_review.assert_called_once()

    def test_one_corrupt_one_unavailable_original_is_still_unresolved(self):
        self.router._visible_duplicate_candidate_lnis.return_value = ["OLD", "UNAVAILABLE"]
        self.assertFalse(self.router.handle_duplicate_overlay())
        self.router.click_duplicate_process_radio.assert_not_called()

    def test_corrupt_incoming_cannot_be_normally_routed_as_a_replacement(self):
        self.profiles["NEW"] = self.corrupt
        self.assertFalse(self.router.handle_duplicate_overlay())
        self.router.click_duplicate_process_radio.assert_not_called()
        self.assertIn("incoming source is corrupt", self.router._irsplr_duplicate_review_reason)

    def test_existing_corrupt_exclusion_still_completes_its_own_exclusion_workflow(self):
        self.router._active_irsplr_corrupt_exclusion = True
        self.assertTrue(self.router.handle_duplicate_overlay())
        self.router._document_profile_for_irt_lni.assert_not_called()
        self.router.click_duplicate_process_radio.assert_called_once()
        self.router.click_duplicate_archive_radio.assert_not_called()


class OldPDFReviewEligibilityTests(unittest.TestCase):
    STATUS = ("MANUAL REVIEW REQUIRED - IRSPLR PDF: POSSIBLY TRUNCATED OR NONSTANDARD PDF - "
              "the final PDF end marker is missing or followed by unexpected data; corruption is not verified")

    def test_only_specific_generated_irsplr_eof_review_is_revalidated(self):
        rows = pd.DataFrame([
            {"CourtCode": "FDPLR000", "Status": self.STATUS},
            {"CourtCode": "FDPLR000", "Status": "MANUAL REVIEW REQUIRED - supply missing date"},
            {"CourtCode": "FDFERC00", "Status": self.STATUS},
            {"CourtCode": "FDPLR000", "Status": "DONE"},
        ])
        self.assertTrue(should_recheck_irsplr_pdf_review(rows.iloc[0]))
        self.assertEqual(_completed_status_mask(rows).tolist(), [False, True, True, True])


if __name__ == "__main__":
    unittest.main()
