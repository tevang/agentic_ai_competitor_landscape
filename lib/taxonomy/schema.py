"""Controlled taxonomy schema for drug-discovery and development steps."""

from typing import Any


PHASE_TO_CANONICAL = {
    "Early Drug Discovery": "Discovery",
    "Pre-clinical Development": "Preclinical",
    "Clinical Development": "Clinical",
    "Regulatory Review & Approval": "Regulatory",
    "Post-market & Lifecycle": "Commercial/Lifecycle",
}

STEP_TO_TAXONOMY: dict[str, dict[str, Any]] = {
    "Target identification": {
        "primary_phase": "Discovery",
        "primary_subcategory": "target identification",
        "phase_labels": ["Discovery"],
        "subcategory_labels": ["target identification", "target prioritization", "disease biology"],
        "rationale": "Target selection and prioritisation belongs in discovery.",
    },
    "Target validation": {
        "primary_phase": "Discovery",
        "primary_subcategory": "target validation",
        "phase_labels": ["Discovery"],
        "subcategory_labels": ["target validation", "mechanism validation", "translational validation"],
        "rationale": "Biological validation of a proposed target belongs in discovery.",
    },
    "Assay development": {
        "primary_phase": "Discovery",
        "primary_subcategory": "assay development",
        "phase_labels": ["Discovery"],
        "subcategory_labels": ["assay development", "screening assay design", "assay automation"],
        "rationale": "Assay creation and optimisation is a discovery-screening capability.",
    },
    "Hit identification": {
        "primary_phase": "Discovery",
        "primary_subcategory": "hit discovery",
        "phase_labels": ["Discovery"],
        "subcategory_labels": ["hit discovery", "high-throughput screening", "virtual screening"],
        "rationale": "Initial active discovery is a discovery-stage activity.",
    },
    "Hit-to-Lead": {
        "primary_phase": "Discovery",
        "primary_subcategory": "hit-to-lead",
        "phase_labels": ["Discovery"],
        "subcategory_labels": ["hit-to-lead", "triage", "series prioritization"],
        "rationale": "Hit triage and optimisation remains in discovery.",
    },
    "Lead identification": {
        "primary_phase": "Discovery",
        "primary_subcategory": "lead identification",
        "phase_labels": ["Discovery"],
        "subcategory_labels": ["lead identification", "SAR", "backup series evaluation"],
        "rationale": "Lead selection belongs in discovery.",
    },
    "Lead optimization": {
        "primary_phase": "Discovery",
        "primary_subcategory": "lead optimization",
        "phase_labels": ["Discovery"],
        "subcategory_labels": ["lead optimization", "medicinal chemistry", "multi-parameter optimization"],
        "rationale": "Iterative chemistry optimisation is a core discovery activity.",
    },
    "Candidate selection & pre-formulation": {
        "primary_phase": "Discovery",
        "primary_subcategory": "candidate selection",
        "phase_labels": ["Discovery", "Preclinical"],
        "subcategory_labels": ["candidate selection", "pre-formulation", "developability"],
        "rationale": "This bridges late discovery and preclinical preparation.",
    },
    "Pharmacology & ADME": {
        "primary_phase": "Preclinical",
        "primary_subcategory": "ADMET",
        "phase_labels": ["Preclinical"],
        "subcategory_labels": ["ADMET", "pharmacology", "PK/PD"],
        "rationale": "ADME and pharmacology are preclinical translational capabilities.",
    },
    "Toxicology": {
        "primary_phase": "Preclinical",
        "primary_subcategory": "toxicology",
        "phase_labels": ["Preclinical"],
        "subcategory_labels": ["toxicology", "safety pharmacology", "genotoxicity"],
        "rationale": "Toxicology is a preclinical safety capability.",
    },
    "Proof-of-concept & efficacy": {
        "primary_phase": "Preclinical",
        "primary_subcategory": "proof of concept",
        "phase_labels": ["Preclinical"],
        "subcategory_labels": ["proof of concept", "efficacy models", "translational biomarkers"],
        "rationale": "Preclinical efficacy and disease-model work belongs in preclinical development.",
    },
    "Phase 0 (microdosing)": {
        "primary_phase": "Preclinical",
        "primary_subcategory": "microdosing",
        "phase_labels": ["Preclinical", "Clinical"],
        "subcategory_labels": ["microdosing", "exploratory IND", "early clinical pharmacology"],
        "rationale": "Phase 0 bridges preclinical de-risking and early clinical development.",
    },
    "Formulation & delivery optimisation": {
        "primary_phase": "Preclinical",
        "primary_subcategory": "formulation and delivery",
        "phase_labels": ["Preclinical"],
        "subcategory_labels": ["formulation and delivery", "bioavailability optimisation", "drug delivery"],
        "rationale": "Formulation and route optimisation is primarily preclinical.",
    },
    "IND preparation": {
        "primary_phase": "Regulatory",
        "primary_subcategory": "IND-enabling",
        "phase_labels": ["Preclinical", "Regulatory"],
        "subcategory_labels": ["IND-enabling", "medical writing", "dossier assembly"],
        "rationale": "IND preparation is best normalized under regulatory dossier preparation.",
    },
    "Study design & initiation": {
        "primary_phase": "Clinical",
        "primary_subcategory": "trial design",
        "phase_labels": ["Clinical"],
        "subcategory_labels": ["trial design", "site startup", "protocol design"],
        "rationale": "Protocol design and trial initiation belong in clinical development.",
    },
    "Phase I": {
        "primary_phase": "Clinical",
        "primary_subcategory": "phase I",
        "phase_labels": ["Clinical"],
        "subcategory_labels": ["phase I", "dose escalation", "first-in-human"],
        "rationale": "Phase I is a clinical-development capability.",
    },
    "Phase II": {
        "primary_phase": "Clinical",
        "primary_subcategory": "phase II",
        "phase_labels": ["Clinical"],
        "subcategory_labels": ["phase II", "dose ranging", "proof of concept"],
        "rationale": "Phase II is a clinical-development capability.",
    },
    "Phase III": {
        "primary_phase": "Clinical",
        "primary_subcategory": "phase III",
        "phase_labels": ["Clinical"],
        "subcategory_labels": ["phase III", "pivotal trials", "multicentre operations"],
        "rationale": "Phase III is a clinical-development capability.",
    },
    "Phase IV": {
        "primary_phase": "Commercial/Lifecycle",
        "primary_subcategory": "phase IV",
        "phase_labels": ["Clinical", "Commercial/Lifecycle", "Pharmacovigilance"],
        "subcategory_labels": ["phase IV", "post-marketing surveillance", "real-world evidence"],
        "rationale": "Phase IV spans late clinical, post-market evidence generation, and safety monitoring.",
    },
    "NDA/BLA submission": {
        "primary_phase": "Regulatory",
        "primary_subcategory": "dossier assembly",
        "phase_labels": ["Regulatory"],
        "subcategory_labels": ["dossier assembly", "submission publishing", "medical writing"],
        "rationale": "Submission preparation belongs in regulatory affairs.",
    },
    "FDA review & decision": {
        "primary_phase": "Regulatory",
        "primary_subcategory": "regulatory review support",
        "phase_labels": ["Regulatory"],
        "subcategory_labels": ["regulatory review support", "label negotiation", "inspection readiness"],
        "rationale": "Review support and agency responses belong in regulatory affairs.",
    },
    "Reasons for failure": {
        "primary_phase": "Regulatory",
        "primary_subcategory": "failure analysis",
        "phase_labels": ["Discovery", "Preclinical", "Clinical", "Regulatory"],
        "subcategory_labels": ["failure analysis", "attrition analysis", "risk review"],
        "rationale": "Failure analysis is cross-cutting but most useful as a regulatory-normalized risk category.",
    },
    "Generics/ANDA": {
        "primary_phase": "Regulatory",
        "primary_subcategory": "generic submission",
        "phase_labels": ["Regulatory"],
        "subcategory_labels": ["generic submission", "ANDA", "bioequivalence"],
        "rationale": "ANDA work is a regulatory submission capability.",
    },
    "Pharmacovigilance": {
        "primary_phase": "Pharmacovigilance",
        "primary_subcategory": "signal detection",
        "phase_labels": ["Pharmacovigilance"],
        "subcategory_labels": [
            "case intake",
            "case processing",
            "MedDRA coding",
            "signal detection",
            "signal management",
            "benefit-risk assessment",
            "RMP/PSMF",
            "QPPV",
            "SUSAR reporting",
            "E2B(R3)",
            "EudraVigilance",
            "label monitoring",
            "literature surveillance",
        ],
        "rationale": "This is the dedicated pharmacovigilance bucket.",
    },
    "Additional indications & formulations": {
        "primary_phase": "Commercial/Lifecycle",
        "primary_subcategory": "lifecycle management",
        "phase_labels": ["Commercial/Lifecycle"],
        "subcategory_labels": ["lifecycle management", "new indications", "line extensions"],
        "rationale": "Line extensions and additional indications belong in lifecycle management.",
    },
    "Manufacturing scale-up & quality": {
        "primary_phase": "Manufacturing",
        "primary_subcategory": "scale-up",
        "phase_labels": ["Manufacturing"],
        "subcategory_labels": ["scale-up", "tech transfer", "CMC", "quality management"],
        "rationale": "Scale-up and quality operations belong in manufacturing.",
    },
}


def get_step_taxonomy_payload(phase_name: str, step_name: str) -> dict[str, Any]:
    """Return the controlled taxonomy payload for a given pipeline step."""

    if step_name in STEP_TO_TAXONOMY:
        return dict(STEP_TO_TAXONOMY[step_name])

    canonical_phase = PHASE_TO_CANONICAL.get(phase_name, phase_name)
    return {
        "primary_phase": canonical_phase,
        "primary_subcategory": step_name.strip().lower(),
        "phase_labels": [canonical_phase],
        "subcategory_labels": [step_name.strip().lower()],
        "rationale": "Fallback controlled mapping derived from the phase and step names.",
    }


def format_taxonomy_target_for_step(phase_name: str, step_name: str) -> str:
    """Return a readable taxonomy target string for prompt injection."""

    payload = get_step_taxonomy_payload(phase_name, step_name)
    phase_labels = ", ".join(payload["phase_labels"])
    subcategory_labels = ", ".join(payload["subcategory_labels"])
    return (
        f"Primary phase bucket: {payload['primary_phase']}\n"
        f"Primary subcategory: {payload['primary_subcategory']}\n"
        f"Allowed phase labels: {phase_labels}\n"
        f"Allowed subcategories: {subcategory_labels}"
    )