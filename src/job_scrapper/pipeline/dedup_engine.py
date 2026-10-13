"""Standard implementation of the 3-Layer Deduplication & Entity Resolution Engine."""

import hashlib
import re
from datetime import timedelta
from typing import Any
from job_scrapper.domain.models import JobPosting

LEGAL_SUFFIXES = re.compile(
    r"\b(inc|incorporated|llc|ltd|limited|corp|corporation|technologies|technology|tech|gmbh|co|pvt|sa|bv)\b",
    re.IGNORECASE,
)
TITLE_NOISE = re.compile(
    r"(\[\s*(?:remote|hybrid|on[- ]?site)\s*\]|\(\s*(?:remote|hybrid|on[- ]?site)\s*\)|[-|]\s*(?:remote|hybrid|on[- ]?site)\b)",
    re.IGNORECASE,
)


class StandardDeduplicationEngine:
    """Production 3-layer deduplication engine (Normalization, 64-bit SimHash, and Attribute Enrichment)."""

    def normalize_company(self, name: str) -> str:
        if not name:
            return ""
        s = name.lower().strip()
        # Replace punctuation with spaces
        s = re.sub(r"[\.,\-_\(\)\/\\\'\"]", " ", s)
        # Strip legal entity designators
        s = LEGAL_SUFFIXES.sub("", s)
        # Collapse whitespace
        return re.sub(r"\s+", " ", s).strip()

    def normalize_title(self, title: str) -> str:
        if not title:
            return ""
        # Strip brackets, parentheses, and trailing remote tags
        s = TITLE_NOISE.sub("", title).lower().strip()
        s = re.sub(r"[()]", " ", s)
        s = re.sub(r"[\.,\-_\/\\\'\"]", " ", s)
        # Expand common job title contractions
        s = re.sub(r"\bsr\b", "senior", s)
        s = re.sub(r"\bjr\b", "junior", s)
        s = re.sub(r"\bdev\b", "developer", s)
        s = re.sub(r"\beng\b", "engineer", s)
        s = re.sub(r"\bsw\b", "software", s)
        return re.sub(r"\s+", " ", s).strip()

    def compute_canonical_signature(self, job: JobPosting) -> str:
        norm_co = self.normalize_company(job.company_name)
        norm_title = self.normalize_title(job.title)
        loc = str(job.attributes.get("location") or "remote").lower()
        norm_loc = re.sub(r"[^a-z0-9]+", " ", loc).strip()
        raw_key = f"{norm_co}|{norm_title}|{norm_loc}"
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    def is_duplicate(self, existing: JobPosting, incoming: JobPosting) -> bool:
        if (existing.source, existing.source_job_id) == (incoming.source, incoming.source_job_id):
            return True
        if existing.source == incoming.source:
            return False
        if self.compute_canonical_signature(existing) != self.compute_canonical_signature(incoming):
            return False
        if abs(existing.posted_at - incoming.posted_at) > timedelta(days=7):
            return False
        if existing.content_hash == incoming.content_hash:
            return True
        if min(len(re.findall(r"\b[a-z0-9]{2,}\b", existing.description_text.lower())),
               len(re.findall(r"\b[a-z0-9]{2,}\b", incoming.description_text.lower()))) < 50:
            return False
        return self.are_near_duplicates(
            self.compute_simhash(existing.description_text),
            self.compute_simhash(incoming.description_text),
        )

    def compute_simhash(self, text: str) -> int:
        """Compute a 64-bit SimHash over text word 3-grams."""
        if not text:
            return 0

        # Clean words
        words = re.findall(r"\b[a-z0-9]{2,}\b", text.lower())
        if len(words) < 3:
            shingles = words or ["empty"]
        else:
            shingles = [f"{words[i]}_{words[i+1]}_{words[i+2]}" for i in range(len(words) - 2)]

        v = [0] * 64
        for s in shingles:
            # 64-bit hash of token
            h = int(hashlib.md5(s.encode("utf-8")).hexdigest()[:16], 16)
            for i in range(64):
                if (h >> i) & 1:
                    v[i] += 1
                else:
                    v[i] -= 1

        fingerprint = 0
        for i in range(64):
            if v[i] > 0:
                fingerprint |= 1 << i

        # Convert to signed 64-bit integer to fit PostgreSQL BIGINT (-2^63 to 2^63-1)
        if fingerprint >= (1 << 63):
            fingerprint -= (1 << 64)

        return fingerprint

    def are_near_duplicates(self, hash1: int, hash2: int, max_distance: int = 3) -> bool:
        """Check whether two 64-bit SimHashes differ by at most three bits."""
        if hash1 == 0 or hash2 == 0:
            return False
        u1 = hash1 & 0xFFFFFFFFFFFFFFFF
        u2 = hash2 & 0xFFFFFFFFFFFFFFFF
        return (u1 ^ u2).bit_count() <= max_distance

    def enrich_attributes(
        self, canonical: dict[str, Any], duplicate: dict[str, Any]
    ) -> tuple[dict[str, Any], bool]:
        """Merge missing fields and union list attributes from duplicate into canonical."""
        merged = dict(canonical)
        changed = False

        for k, v in duplicate.items():
            # Availability describes one source posting, not the merged job entity.
            if k == "_attribute_evidence" or k in (
                'posting_status', 'posting_status_evidence', 'posting_status_checked_at',
            ):
                continue
            if v is None or v == "" or v == []:
                continue

            existing_val = merged.get(k)
            # If canonical is missing this field, backfill it
            if existing_val is None or existing_val == "" or existing_val == "unknown":
                merged[k] = v
                changed = True
            elif isinstance(existing_val, list) and isinstance(v, list):
                # ponytail: equality handles JSON objects; index values if label lists grow large.
                combined: list[Any] = []
                for item in existing_val + v:
                    if item not in combined:
                        combined.append(item)
                if combined != existing_val:
                    merged[k] = combined
                    changed = True

        evidence = dict(canonical.get("_attribute_evidence") or {})
        for field, incoming in (duplicate.get("_attribute_evidence") or {}).items():
            if (isinstance(incoming, dict) and incoming.get("normalized") == merged.get(field)
                    and (field not in evidence or canonical.get(field) != merged.get(field))):
                evidence[field] = incoming
        if evidence and evidence != canonical.get("_attribute_evidence"):
            merged["_attribute_evidence"] = evidence
            changed = True
        return merged, changed
