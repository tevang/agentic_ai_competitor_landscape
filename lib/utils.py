import hashlib
import json
import re
import csv
import io
import yaml
from typing import Any
from rapidfuzz import fuzz
from lib.models import Candidate, PipelineStep

def load_config(path: str = "config.yml") -> dict:
    """
    Loads configuration from a YAML file.
    """
    with open(path, "r") as f:
        return yaml.safe_load(f)


def parse_pipeline_csv(csv_path: str) -> list[PipelineStep]:
    """
    Parses the drug development pipeline CSV from a file.
    """
    out = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            out.append(
                PipelineStep(
                    phase=row["Phase"].strip(),
                    step=row["Sub-phase / Step"].strip(),
                    activities=row["Key activities"].strip(),
                )
            )
    return out


def canonical_name(name: str) -> str:
    """
    Normalizes a company name for consistent lookups.
    """
    name = re.sub(r"[^a-zA-Z0-9]+", " ", name.lower()).strip()
    return re.sub(r"\s+", " ", name)


def sha1(text: str) -> str:
    """
    Generates a SHA1 hash of the given text.
    """
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def clean_text(text: str | None) -> str:
    """
    Cleans up text by removing extra whitespace and newlines.
    """
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def extract_json_blob(text: str) -> dict:
    """
    Extracts a JSON blob from a string, even if it's wrapped in markdown code blocks.
    """
    match = re.search(r"```json\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        blob = match.group(1).strip()
    else:
        blob = text.strip()
    try:
        return json.loads(blob)
    except Exception:
        # Fallback: try to find anything that looks like { ... }
        match = re.search(r"(\{.*\})", blob, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except Exception:
                return {}
        return {}


def evidence_to_context(items: list[Any], limit: int = 12, chars_per_item: int = 1000) -> str:
    """
    Converts a list of evidence documents into a text context for an LLM.
    """
    out = []
    for i, item in enumerate(items[:limit]):
        # item can be EvidenceDoc or dict from Chroma
        if hasattr(item, "text"):
            txt = item.text or item.snippet
            url = item.url
        else:
            txt = item.get("text", "") or item.get("snippet", "")
            url = item.get("url", "")
        
        clean_txt = clean_text(txt)[:chars_per_item]
        out.append(f"SOURCE [{i}]: {url}\nCONTENT: {clean_txt}")
    return "\n\n".join(out)


def fuzzy_dedupe_candidates(candidates: list[Candidate], threshold: int = 94) -> list[Candidate]:
    """
    Deduplicates a list of candidates using fuzzy name matching.
    """
    unique = []
    for c in candidates:
        is_new = True
        for u in unique:
            if fuzz.ratio(canonical_name(c.name), canonical_name(u.name)) > threshold:
                is_new = False
                break
        if is_new:
            unique.append(c)
    return unique
