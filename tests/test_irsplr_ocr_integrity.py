"""A valid scan, an OCR failure, and a bad source file are different outcomes."""

import hashlib
import importlib.util
import unittest
from contextlib import contextmanager
from io import BytesIO
from unittest.mock import Mock, patch

from pypdf import PdfReader, PdfWriter

from core.irsplr_extractor import (
    IRSPLRCorruptDocument,
    IRSPLRDocumentReviewRequired,
    IRSPLRMetadata,
    parse_irsplr_pdf_bytes,
    validate_irsplr_pdf_bytes,
)
from core.smducar_router import CaseLawRouter


RULING_TEXT = """Internal Revenue Service
Department of the Treasury
Number: 202642012
Date: July 10, 2026
This private letter ruling responds to your request concerning the federal
income tax consequences of the proposed transaction described in your letter.
The conclusions in this letter are based on the information you supplied.
"""


def blank_pdf():
    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.write(output)
    return output.getvalue()


def scanned_pdf(*, partial_text_layer=False):
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (1275, 1650), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=28)
    draw.multiline_text((70, 80), RULING_TEXT, fill="black", font=font, spacing=15)
    output = BytesIO()
    image.save(output, format="PDF", resolution=150)
    payload = output.getvalue()
    if partial_text_layer:
        import fitz

        with fitz.open(stream=payload, filetype="pdf") as doc:
            doc[0].insert_text((30, 20), "SCANNED COPY")
            payload = doc.tobytes()
    return payload


@unittest.skipUnless(
    all(importlib.util.find_spec(name) for name in ("PIL", "fitz", "pytesseract")),
    "OCR renderer dependencies are required for scan integration tests",
)
class IRSPLRScanIntegrityTests(unittest.TestCase):
    def test_image_only_pdf_reaches_tesseract_through_the_actual_renderer(self):
        payload = scanned_pdf()
        self.assertFalse(PdfReader(BytesIO(payload)).pages[0].extract_text().strip())
        with patch("pytesseract.image_to_string", return_value=RULING_TEXT) as ocr:
            metadata = parse_irsplr_pdf_bytes(payload, filename_hint="202642012.pdf")
        self.assertEqual(metadata.docket_number, "202642012")
        self.assertEqual(metadata.decision_date, "07-10-2026")
        self.assertFalse(metadata.is_verified_corrupt)
        self.assertEqual(ocr.call_count, 1)
        self.assertGreater(ocr.call_args.args[0].width, 600)

    def test_partial_text_layer_does_not_suppress_ocr(self):
        payload = scanned_pdf(partial_text_layer=True)
        self.assertIn("SCANNED COPY", PdfReader(BytesIO(payload)).pages[0].extract_text())
        with patch("pytesseract.image_to_string", return_value=RULING_TEXT) as ocr:
            metadata = parse_irsplr_pdf_bytes(payload)
        self.assertEqual(metadata.docket_number, "202642012")
        ocr.assert_called_once()

    def test_empty_or_unintelligible_ocr_is_not_corruption(self):
        for text in ("", "unreadable scan", "x" * 150):
            with self.subTest(text=text), patch("pytesseract.image_to_string", return_value=text):
                self.assertIsNone(parse_irsplr_pdf_bytes(scanned_pdf()))

    def test_missing_tesseract_is_not_corruption(self):
        from pytesseract import TesseractNotFoundError

        with patch("pytesseract.image_to_string", side_effect=TesseractNotFoundError()), \
                patch("core.mspb_extractor._ocr_unavailable_logged", False):
            self.assertIsNone(parse_irsplr_pdf_bytes(scanned_pdf()))

    def test_explicitly_disabled_ocr_does_not_run(self):
        with patch("pytesseract.image_to_string") as ocr:
            self.assertIsNone(parse_irsplr_pdf_bytes(scanned_pdf(), use_ocr_fallback=False))
        ocr.assert_not_called()

    def test_complete_native_metadata_does_not_run_ocr(self):
        import fitz

        with fitz.open() as doc:
            doc.new_page().insert_textbox(fitz.Rect(30, 30, 570, 750), RULING_TEXT)
            payload = doc.tobytes()
        with patch("pytesseract.image_to_string") as ocr:
            self.assertEqual(parse_irsplr_pdf_bytes(payload).docket_number, "202642012")
        ocr.assert_not_called()


class IRSPLRInconclusiveValidationTests(unittest.TestCase):
    def assert_review_only(self, payload):
        with self.assertRaises(IRSPLRDocumentReviewRequired) as raised:
            validate_irsplr_pdf_bytes(payload)
        self.assertNotIsInstance(raised.exception, IRSPLRCorruptDocument)

    def test_unknown_server_responses_never_authorize_corrupt_exclusion(self):
        for payload in (b'{"error":"timeout"}', b"Service Unavailable", b"\xef\xbb\xbf<html>Login</html>"):
            with self.subTest(payload=payload):
                self.assert_review_only(payload)

    def test_recoverable_missing_eof_is_not_verified_corruption(self):
        self.assert_review_only(blank_pdf().rsplit(b"%%EOF", 1)[0])

    def test_trailing_source_data_is_reviewed_without_assuming_corruption(self):
        self.assert_review_only(blank_pdf() + b"\ntrailing source data\n")

    def test_parser_unsupported_feature_is_review_not_corruption(self):
        with patch("pypdf.PdfReader", side_effect=NotImplementedError("unsupported feature")):
            self.assert_review_only(blank_pdf())

    def test_malformed_pdf_is_blocked_without_guessing_it_is_ocr_only(self):
        with patch("core.irsplr_extractor.extract_text_from_pdf_bytes") as extract:
            with self.assertRaises(IRSPLRDocumentReviewRequired) as raised:
                parse_irsplr_pdf_bytes(b"%PDF-1.7\ngarbage\n%%EOF\n")
            self.assertNotIsInstance(raised.exception, IRSPLRCorruptDocument)
        extract.assert_not_called()


class IRSPLRViewerEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.router = CaseLawRouter.__new__(CaseLawRouter)
        self.router._irsplr_unreadable_pdf_signatures = set()
        self.router.wait_for_open_tab_load_state = Mock()
        self.router.wait_for_irsplr_downloaded_metadata = Mock(return_value=None)
        self.router.read_irsplr_pdf_viewer_error = Mock(return_value="Failed to load PDF document.")
        self.router.get_opened_pdf_bytes_from_browser_network = Mock(return_value=None)
        self.router.read_open_pdf_accessibility_text = Mock()
        self.router.copy_open_pdf_tab_text = Mock()
        self.router.read_open_pdf_tab_text = Mock()
        self.router.log_mspb_pdf_tab_diagnostics = Mock()
        self.metadata = IRSPLRMetadata("FDPLR000", "202642012", "07-10-2026", "Letter", has_text_content=True)

    @contextmanager
    def retrieval_clock(self):
        self.now = 100.0

        def sleep(seconds):
            self.now += seconds

        with patch("core.smducar_router.time.time", side_effect=lambda: self.now), \
                patch("core.smducar_router.time.sleep", side_effect=sleep):
            yield

    def test_persistent_failed_viewer_waits_entire_window_before_exclusion(self):
        with self.retrieval_clock(), self.assertRaises(IRSPLRCorruptDocument):
            self.router.wait_for_irsplr_metadata_from_open_tab(timeout=2)
        self.assertGreaterEqual(self.now, 102)
        self.assertGreaterEqual(self.router.read_irsplr_pdf_viewer_error.call_count, 2)
        self.router.copy_open_pdf_tab_text.assert_not_called()

    def test_temporary_error_can_recover_to_a_valid_download(self):
        self.router.read_irsplr_pdf_viewer_error.side_effect = ["Failed to load PDF document.", ""]
        self.router.wait_for_irsplr_downloaded_metadata.side_effect = [None, self.metadata]
        with self.retrieval_clock():
            self.assertEqual(self.router.wait_for_irsplr_metadata_from_open_tab(timeout=2), self.metadata)

    def test_valid_network_pdf_without_ocr_metadata_is_never_excluded_for_viewer_error(self):
        self.router.get_opened_pdf_bytes_from_browser_network.return_value = blank_pdf()
        with self.retrieval_clock(), patch("core.irsplr_extractor.extract_text_from_pdf_bytes", return_value=""), \
                self.assertRaisesRegex(IRSPLRDocumentReviewRequired, "PDF VALIDATED") as raised:
            self.router.wait_for_irsplr_metadata_from_open_tab(timeout=2)
        self.assertNotIsInstance(raised.exception, IRSPLRCorruptDocument)

    def test_cached_network_pdf_keeps_its_validated_status(self):
        payload = blank_pdf()
        self.router.get_opened_pdf_bytes_from_browser_network.return_value = payload
        self.router._irsplr_unreadable_pdf_signatures.add(("network", hashlib.sha1(payload).hexdigest()))
        with self.retrieval_clock(), self.assertRaisesRegex(IRSPLRDocumentReviewRequired, "PDF VALIDATED") as raised:
            self.router.wait_for_irsplr_metadata_from_open_tab(timeout=2)
        self.assertNotIsInstance(raised.exception, IRSPLRCorruptDocument)

    def test_downloaded_and_cached_unreadable_pdf_keep_validation_evidence(self):
        pdf_path = Mock()
        pdf_path.name = "test.pdf"
        pdf_path.read_bytes.return_value = blank_pdf()
        self.router.find_completed_irsplr_download = Mock(return_value=pdf_path)
        self.router.wait_for_irsplr_downloaded_metadata = CaseLawRouter.wait_for_irsplr_downloaded_metadata.__get__(self.router)
        for attempt in range(2):
            with self.subTest(attempt=attempt), self.retrieval_clock(), \
                    patch("core.irsplr_extractor.extract_text_from_pdf_bytes", return_value=""), \
                    self.assertRaisesRegex(IRSPLRDocumentReviewRequired, "PDF VALIDATED") as raised:
                self.router.wait_for_irsplr_metadata_from_open_tab(timeout=2)
            self.assertNotIsInstance(raised.exception, IRSPLRCorruptDocument)
        pdf_path.read_bytes.assert_called_once()

    def test_download_validation_evidence_does_not_leak_between_rows(self):
        self.router._irsplr_last_download_validated = True
        self.router.find_completed_irsplr_download = Mock(return_value=None)
        with self.retrieval_clock():
            self.assertIsNone(CaseLawRouter.wait_for_irsplr_downloaded_metadata(self.router, {}, timeout=1))
        self.assertFalse(self.router._irsplr_last_download_validated)


if __name__ == "__main__":
    unittest.main()
