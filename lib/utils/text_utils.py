"""Text-normalization, JSON-recovery, URL helpers, and context-building utilities."""

import hashlib
import re
from typing import Any, Iterable
from urllib.parse import urlparse

from rapidfuzz import fuzz

from lib.models import Candidate, EvidenceDoc


def canonical_name(name: str) -> str:
    """Normalize a company name into a canonical key for cache lookups."""

    name = re.sub(r"[^a-zA-Z0-9]+", " ", name.lower()).strip()
    return re.sub(r"\s+", " ", name)


def sha1_hash(text: str) -> str:
    """Return a SHA-1 hash for deterministic document IDs."""

    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def build_step_signature(phase: str, step: str, activities: str) -> str:
    """Build a deterministic signature for a pipeline step including its activity text."""

    return sha1_hash(f"{phase}|{step}|{clean_text(activities)}")


def clean_text(text: str | None) -> str:
    """Collapse whitespace and safely normalize optional text into a single line."""

    if not text:
        return ""
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_json_blob(text: str) -> str:
    """Recover a JSON payload from a model response, including fenced markdown blocks."""

    fenced_json_blocks = re.findall(r"```json(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced_json_blocks:
        return fenced_json_blocks[0].strip()

    fenced_blocks = re.findall(r"```(.*?)```", text, flags=re.DOTALL)
    for block in fenced_blocks:
        block = block.strip()
        if block.startswith("{") or block.startswith("["):
            return block

    start_candidates = [index for index in (text.find("{"), text.find("[")) if index != -1]
    if not start_candidates:
        raise ValueError(f"No JSON found in model output:\n{text[:1000]}")

    start = min(start_candidates)
    end = max(text.rfind("}"), text.rfind("]"))
    if end == -1:
        raise ValueError(f"No JSON terminator found in model output:\n{text[:1000]}")

    return text[start : end + 1].strip()


def evidence_to_context(items: list[Any], limit: int, chars_per_item: int) -> str:
    """Convert evidence documents into a compact text context block for prompt injection."""

    blocks: list[str] = []
    for item in items[:limit]:
        if isinstance(item, EvidenceDoc):
            title = item.title
            url = item.url
            text = item.text or item.snippet
            source_type = item.source_type
        else:
            title = item.get("title", "")
            url = item.get("url", "")
            text = item.get("text", "") or item.get("snippet", "")
            source_type = item.get("source_type", "")

        block = (
            f"TITLE: {title}\n"
            f"URL: {url}\n"
            f"SOURCE_TYPE: {source_type}\n"
            f"TEXT: {clean_text(text)[:chars_per_item]}"
        )
        blocks.append(block)

    return "\n\n---\n\n".join(blocks)


def fuzzy_dedupe_candidates(candidates: list[Candidate], threshold: int) -> list[Candidate]:
    """Deduplicate candidate companies using fuzzy token-set matching on company names."""

    kept: list[Candidate] = []
    for candidate in sorted(candidates, key=lambda item: item.confidence, reverse=True):
        duplicate_found = False
        for existing in kept:
            score = fuzz.token_set_ratio(candidate.name, existing.name)
            if score >= threshold:
                duplicate_found = True
                break
        if not duplicate_found:
            kept.append(candidate)

    return kept


def domain_from_url(url: str) -> str:
    """Extract a bare domain name from a URL or hostname-like string."""

    if not url:
        return ""
    parsed = urlparse(url if "://" in url else f"https://{url}")
    domain = (parsed.netloc or parsed.path or "").strip().lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def unique_preserve_order(items: Iterable[str]) -> list[str]:
    """Deduplicate a sequence of strings while preserving the original order."""

    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        value = (item or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def parse_delimited_list(text: str) -> list[str]:
    """Parse a semicolon- or pipe-delimited text field into a clean list of strings."""

    if not text:
        return []
    parts = re.split(r"[;|]", text)
    return [part.strip() for part in parts if part.strip()]


def slugify_filename(text: str) -> str:
    """Convert a free-form string into a filesystem-friendly slug."""

    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return slug or "unknown"


def chunked(items: list[Any], size: int) -> list[list[Any]]:
    """Split a list into fixed-size chunks."""

    if size <= 0:
        return [items]
    return [items[index : index + size] for index in range(0, len(items), size)]


def rank_evidence_docs_for_extraction(docs: list[EvidenceDoc]) -> list[EvidenceDoc]:
    """Rank evidence for extraction while preserving useful search-result snippets."""

    indexed_docs = list(enumerate(docs))

    def score(item: tuple[int, EvidenceDoc]) -> tuple[float, float, int, int]:
        index, doc = item
        text = doc.text or doc.snippet or ""
        has_full_text = 1.0 if doc.text else 0.0
        quality_score = float(doc.quality_score or 0.0)
        text_length = min(len(text), 4000)
        return (has_full_text, quality_score, text_length, -index)

    return [doc for _, doc in sorted(indexed_docs, key=score, reverse=True)]