"""Text-normalization, JSON-recovery, and context-building helpers."""

import hashlib
import re
from typing import Any

from rapidfuzz import fuzz

from lib.models import Candidate, EvidenceDoc


def canonical_name(name: str) -> str:
    """Normalize a company name into a canonical key for cache lookups."""

    name = re.sub(r"[^a-zA-Z0-9]+", " ", name.lower()).strip()
    return re.sub(r"\s+", " ", name)


def sha1_hash(text: str) -> str:
    """Return a SHA-1 hash for deterministic evidence-store document IDs."""

    return hashlib.sha1(text.encode("utf-8")).hexdigest()


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
        else:
            title = item.get("title", "")
            url = item.get("url", "")
            text = item.get("text", "") or item.get("snippet", "")

        block = f"TITLE: {title}\nURL: {url}\nTEXT: {clean_text(text)[:chars_per_item]}"
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