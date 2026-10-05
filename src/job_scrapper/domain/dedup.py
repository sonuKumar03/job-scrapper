"""Domain contracts for the Deduplication and Entity Resolution Engine."""

from typing import Any, Protocol, runtime_checkable
from job_scrapper.domain.models import JobPosting


@runtime_checkable
class DeduplicationEngine(Protocol):
    """Abstract protocol for multi-layer job deduplication and attribute enrichment."""

    def normalize_company(self, name: str) -> str:
        """Strip legal entity suffixes, punctuation, and whitespace."""
        ...

    def normalize_title(self, title: str) -> str:
        """Strip location/remote brackets and expand common abbreviations."""
        ...

    def compute_canonical_signature(self, job: JobPosting) -> str:
        """Compute deterministic canonical signature: norm_co|norm_title|location_prefix."""
        ...

    def compute_simhash(self, text: str) -> int:
        """Compute a 64-bit SimHash over text word 3-grams for near-duplicate matching."""
        ...

    def is_duplicate(self, existing: JobPosting, incoming: JobPosting) -> bool:
        """Return whether two recent cross-source postings have matching content."""
        ...

    def are_near_duplicates(self, hash1: int, hash2: int, max_distance: int = 3) -> bool:
        """Return True if Hamming distance between two 64-bit SimHashes is <= max_distance."""
        ...

    def enrich_attributes(
        self, canonical: dict[str, Any], duplicate: dict[str, Any]
    ) -> tuple[dict[str, Any], bool]:
        """Merge missing non-null values and union list attributes from duplicate into canonical.

        Returns:
            Tuple of (merged_attributes, was_enriched_boolean).
        """
        ...
