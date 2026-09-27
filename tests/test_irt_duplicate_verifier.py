import unittest

from core.irt_duplicate_verifier import (
    IRTDocumentProfile,
    compare_document_profiles,
    normalize_document_text,
)


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


if __name__ == "__main__":
    unittest.main()
