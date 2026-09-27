"""Content-based confirmation for IRT duplicate-overlay candidates.

IRT's duplicate dialog is a useful lead, not proof.  This module deliberately
requires an exact PDF/text match or a near-identical, substantial text match
before a router archives a document.  Text extraction includes the existing
OCR fallback for scanned PDFs.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import hashlib
import re

from .mspb_extractor import extract_text_from_pdf_bytes


@dataclass(frozen=True)
class IRTDocumentProfile:
    lni: str
    pdf_sha256: str
    normalized_text: str


@dataclass(frozen=True)
class IRTDuplicateMatch:
    original_lni: str
    is_match: bool
    method: str
    similarity: float


def build_document_profile(lni: str, pdf_bytes: bytes) -> IRTDocumentProfile:
    """Create a comparable profile from the IRT-hosted document bytes."""
    text = extract_text_from_pdf_bytes(pdf_bytes, use_ocr_fallback=True)
    return IRTDocumentProfile(
        lni=str(lni or "").strip().upper(),
        pdf_sha256=hashlib.sha256(pdf_bytes).hexdigest(),
        normalized_text=normalize_document_text(text),
    )


def normalize_document_text(text: str) -> str:
    """Normalize layout-only differences without hiding substantive changes."""
    return re.sub(r"\s+", " ", str(text or "").upper()).strip()


def compare_document_profiles(
    current: IRTDocumentProfile,
    candidate: IRTDocumentProfile,
) -> IRTDuplicateMatch:
    """Confirm only exact or extremely close substantial document matches."""
    if current.pdf_sha256 == candidate.pdf_sha256:
        return IRTDuplicateMatch(candidate.lni, True, "identical PDF", 1.0)

    current_text = current.normalized_text
    candidate_text = candidate.normalized_text
    if not current_text or not candidate_text:
        return IRTDuplicateMatch(candidate.lni, False, "text unavailable", 0.0)
    if current_text == candidate_text:
        # OCR sees only the pages it can reliably render.  A short identical
        # header is therefore a lead, not enough evidence to archive.
        is_substantial = len(current_text) >= 800
        method = "identical extracted text" if is_substantial else "insufficient extracted text"
        return IRTDuplicateMatch(candidate.lni, is_substantial, method, 1.0)

    # OCR can introduce harmless character-level differences.  Avoid treating
    # a shared heading or brief similar text as a duplicate by requiring both
    # documents to be substantial and the complete normalized texts to match.
    similarity = SequenceMatcher(None, current_text, candidate_text, autojunk=False).ratio()
    minimum_length = min(len(current_text), len(candidate_text))
    is_match = minimum_length >= 800 and similarity >= 0.995
    method = "near-identical extracted text" if is_match else "different extracted text"
    return IRTDuplicateMatch(candidate.lni, is_match, method, similarity)
