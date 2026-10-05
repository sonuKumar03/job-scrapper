"""Deduplication hashing utility."""

import hashlib


def compute_content_hash(company_name: str, title: str, description_text: str) -> str:
    """Compute deterministic SHA-256 fingerprint for a job posting.

    Normalizes company, title, and initial portion of description to lowercase
    to catch cross-posted jobs with minor formatting differences.
    """
    signature = f"{company_name.strip().lower()}|{title.strip().lower()}|{description_text[:250].strip().lower()}"
    return hashlib.sha256(signature.encode("utf-8")).hexdigest()
