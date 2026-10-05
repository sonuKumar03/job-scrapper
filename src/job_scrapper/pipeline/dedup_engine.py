"""Standard implementation of the 3-Layer Deduplication & Entity Resolution Engine."""

import hashlib
import re
from typing import Any
from job_scrapper.domain.models import JobPosting

LEGAL_SUFFIXES = re.compile(
    r"\b(inc|incorporated|llc|ltd|limited|corp|corporation|technologies|technology|tech|gmbh|co|pvt|sa|bv)\b",
    re.IGNORECASE,
)
TITLE_NOISE = re.compile(
    r"(\[.*?\]|\(.*?\)|-\s*remote|-\s*full\s*time|\|\s*remote|\|\s*hybrid|\|\s*onsite)",
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
        loc = (job.attributes.get("location") or "remote").lower()
        norm_loc = re.sub(r"[^a-z0-9]", "", loc)[:15]
        raw_key = f"{norm_co}|{norm_title}|{norm_loc}"
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

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

    def are_near_duplicates(self, hash1: int, hash2: int, max_distance: int = 7) -> bool:
        """Calculate bitwise Hamming distance between two 64-bit SimHashes (default <=7 bits for ~89%+ similarity)."""
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
            if v is None or v == "" or v == []:
                continue

            existing_val = merged.get(k)
            # If canonical is missing this field, backfill it
            if existing_val is None or existing_val == "" or existing_val == "unknown":
                merged[k] = v
                changed = True
            elif isinstance(existing_val, list) and isinstance(v, list):
                # Union lists (e.g. tech stack / tags)
                combined = list(dict.fromkeys(existing_val + v))
                if len(combined) > len(existing_val):
                    merged[k] = combined
                    changed = True

        return merged, changed
