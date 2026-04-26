"""Generic query construction from pipeline-row text and controlled taxonomy labels."""

import re

from lib.models import PipelineStep
from lib.taxonomy.schema import get_step_taxonomy_payload
from lib.utils.text_utils import clean_text, unique_preserve_order


GENERIC_TERM_STOPLIST = {
    "using",
    "including",
    "through",
    "using genomics",
    "and",
    "or",
    "with",
    "the",
    "from",
    "into",
    "for",
    "data",
    "systems",
    "software",
    "platform",
    "workflow",
    "workflows",
}


def build_step_search_terms(step: PipelineStep, max_terms: int = 18) -> list[str]:
    """Build reusable search terms from the pipeline row and taxonomy without hardcoding rosters."""

    payload = get_step_taxonomy_payload(step.phase, step.step)
    raw_terms: list[str] = [
        step.step,
        payload.get("primary_subcategory", ""),
    ]
    raw_terms.extend(payload.get("subcategory_labels", []))
    raw_terms.extend(_extract_acronyms_and_standards(step.activities))
    raw_terms.extend(_extract_activity_phrases(step.activities))

    normalized_terms = []
    for term in raw_terms:
        normalized = _normalize_term(term)
        if _is_useful_term(normalized):
            normalized_terms.append(normalized)

    return unique_preserve_order(normalized_terms)[:max_terms]


def build_discovery_queries(
    step: PipelineStep,
    max_queries: int = 10,
    max_terms: int = 18,
) -> list[str]:
    """Create generic vendor/platform discovery queries for any pipeline step."""

    terms = build_step_search_terms(step, max_terms=max_terms)
    step_name = _quote(step.step)

    queries = [
        f'{step_name} "AI" "software" "pharma"',
        f'{step_name} "automation" "platform" "life sciences"',
        f'{step_name} "agentic AI" "pharma"',
        f'{step_name} "AI agent" "life sciences"',
        f'{step_name} "machine learning" "company"',
        f'{step_name} "vendor" "drug development"',
        f'{step_name} "solution" "biopharma"',
        f'{step_name} "product page" "AI"',
    ]

    for term in terms:
        quoted_term = _quote(term)
        queries.extend(
            [
                f'{quoted_term} {step_name} "AI"',
                f'{quoted_term} "automation" "pharma" "software"',
                f'{quoted_term} "vendor" "life sciences"',
                f'{quoted_term} "platform" "biopharma"',
            ]
        )

    return unique_preserve_order(queries)[:max_queries]


def _extract_acronyms_and_standards(text: str) -> list[str]:
    """Extract acronyms, regulatory standards, and camel/mixed-case domain terms."""

    clean = clean_text(text)
    pattern = r"\b[A-Z][A-Za-z0-9]*(?:\([A-Za-z0-9]+\))?(?:/[A-Z][A-Za-z0-9]*(?:\([A-Za-z0-9]+\))?)*\b"
    candidates = re.findall(pattern, clean)
    terms: list[str] = []

    for candidate in candidates:
        if (
            candidate.isupper()
            or re.search(r"[A-Z]{2,}", candidate)
            or re.search(r"\d", candidate)
            or candidate in {"MedDRA", "EudraVigilance", "FAERS"}
        ):
            terms.append(candidate)

    return terms


def _extract_activity_phrases(text: str) -> list[str]:
    """Extract short operational phrases from the activity description."""

    clean = clean_text(text)
    clauses = re.split(r"[;,.:]", clean)
    phrases: list[str] = []

    for clause in clauses:
        clause = re.sub(
            r"^(identify|prioritise|prioritize|validate|design|run|conduct|assemble|prepare|support|collect|analyse|analyze|implement|manage|monitor|improve)\s+",
            "",
            clause.strip(),
            flags=re.IGNORECASE,
        )
        clause = re.sub(
            r"^(using|through|including|such as|via|with|and)\s+",
            "",
            clause.strip(),
            flags=re.IGNORECASE,
        )
        words = clause.split()

        if 2 <= len(words) <= 8:
            phrases.append(clause)
            continue

        if len(words) > 8:
            for ngram_size in (2, 3, 4):
                for index in range(0, max(0, len(words) - ngram_size + 1)):
                    ngram = " ".join(words[index : index + ngram_size])
                    if _looks_operational(ngram):
                        phrases.append(ngram)

    return phrases


def _looks_operational(text: str) -> bool:
    """Return whether a short phrase looks like a workflow, deliverable, or standard."""

    lowered = text.lower()
    triggers = [
        "case",
        "processing",
        "signal",
        "report",
        "reporting",
        "submission",
        "coding",
        "monitoring",
        "assessment",
        "management",
        "detection",
        "triage",
        "intake",
        "surveillance",
        "design",
        "validation",
        "screening",
        "optimization",
        "optimisation",
        "manufacturing",
        "quality",
        "formulation",
        "toxicology",
        "pharmacology",
        "protocol",
        "dossier",
        "evidence",
        "biomarker",
        "clinical",
        "regulatory",
        "literature",
    ]
    return any(trigger in lowered for trigger in triggers)


def _normalize_term(term: str) -> str:
    """Normalize a candidate search term while preserving regulatory capitalization."""

    term = clean_text(term)
    term = re.sub(r"\s*/\s*", "/", term)
    term = re.sub(r"\s+", " ", term)
    return term.strip(" -–—:;,.()")


def _is_useful_term(term: str) -> bool:
    """Filter out very short or generic terms."""

    if not term or len(term) < 3:
        return False
    if term.lower() in GENERIC_TERM_STOPLIST:
        return False
    if len(term.split()) > 8:
        return False
    return True


def _quote(term: str) -> str:
    """Quote a term for search."""

    escaped = term.replace('"', "")
    return f'"{escaped}"'