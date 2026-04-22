import pandas as pd
import textwrap
from lib.models import PipelineStep, CompanyProfile
from lib.llm_utils import LLM

PAIN_WEIGHTS = {
    "Target identification": 2.0,
    "Target validation": 2.2,
    "Assay development": 2.0,
    "Hit identification": 1.8,
    "Hit-to-Lead": 2.0,
    "Lead identification": 2.0,
    "Lead optimization": 2.0,
    "Candidate selection & pre-formulation": 2.8,
    "Pharmacology & ADME": 2.6,
    "Toxicology": 3.4,
    "Proof-of-concept & efficacy": 2.8,
    "Phase 0 (microdosing)": 2.2,
    "Formulation & delivery optimisation": 3.2,
    "IND preparation": 3.5,
    "Study design & initiation": 2.6,
    "Phase I": 2.4,
    "Phase II": 2.6,
    "Phase III": 2.8,
    "Phase IV": 2.7,
    "NDA/BLA submission": 3.3,
    "FDA review & decision": 3.2,
    "Reasons for failure": 3.0,
    "Generics/ANDA": 2.4,
    "Pharmacovigilance": 3.3,
    "Additional indications & formulations": 2.8,
    "Manufacturing scale-up & quality": 3.5,
}

REGULATORY_TAILWIND = {
    "Toxicology": 1.4,
    "Formulation & delivery optimisation": 0.8,
    "IND preparation": 1.6,
    "NDA/BLA submission": 1.4,
    "FDA review & decision": 1.2,
    "Pharmacovigilance": 1.4,
    "Manufacturing scale-up & quality": 1.2,
}


def build_matrix_df(records_df: pd.DataFrame) -> pd.DataFrame:
    """
    Builds a pivot table showing which companies are in which pipeline steps.
    """
    if records_df.empty:
        return pd.DataFrame(columns=["phase", "step", "competitors"])

    matrix = (
        records_df.groupby(["phase", "step"])["company"]
        .apply(lambda s: "; ".join(sorted(set(s))))
        .reset_index()
        .rename(columns={"company": "competitors"})
    )
    return matrix.sort_values(["phase", "step"])


def build_profile_df(profile_cache: dict[str, CompanyProfile]) -> pd.DataFrame:
    """
    Converts a cache of company profiles into a pandas DataFrame.
    """
    rows = []
    for profile in profile_cache.values():
        rows.append(
            {
                "company": profile.name,
                "type": profile.vertical_or_horizontal,
                "funding": profile.funding,
                "employees": profile.employees,
                "founded": profile.founded,
                "headquarters": profile.headquarters,
                "presence": "; ".join(profile.presence),
                "specialization": profile.specialization,
                "agentic_posture": profile.explicit_agentic_posture,
                "confidence": round(profile.confidence, 2),
            }
        )
    if not rows:
        return pd.DataFrame(columns=["company", "type", "funding", "employees", "founded", "headquarters", "presence", "specialization", "agentic_posture", "confidence"])
    return pd.DataFrame(rows).sort_values("company")


def compute_gap_scores(records_df: pd.DataFrame, steps: list[PipelineStep]) -> pd.DataFrame:
    """
    Computes saturation and whitespace scores for each step in the pipeline.
    """
    rows = []
    for step in steps:
        subset = records_df[
            (records_df["phase"] == step.phase) &
            (records_df["step"] == step.step)
        ] if not records_df.empty else pd.DataFrame()

        competitor_count = int(subset["company"].nunique()) if not subset.empty else 0
        explicit_count = int((subset["agentic_posture"] == "explicit").sum()) if not subset.empty else 0
        vertical_count = int((subset["vertical_or_horizontal"] == "vertical").sum()) if not subset.empty else 0
        avg_conf = float(subset["confidence"].mean()) if not subset.empty else 0.0

        saturation_score = competitor_count + 0.5 * explicit_count + 0.35 * vertical_count
        whitespace_score = (
            PAIN_WEIGHTS.get(step.step, 2.5)
            + REGULATORY_TAILWIND.get(step.step, 0.0)
            + max(0.0, 4.5 - saturation_score)
        )

        rows.append(
            {
                "phase": step.phase,
                "step": step.step,
                "competitor_count": competitor_count,
                "explicit_agentic_count": explicit_count,
                "vertical_count": vertical_count,
                "avg_confidence": round(avg_conf, 2),
                "saturation_score": round(saturation_score, 2),
                "whitespace_score": round(whitespace_score, 2),
            }
        )

    gap_df = pd.DataFrame(rows)
    return gap_df.sort_values(["whitespace_score", "competitor_count"], ascending=[False, True])


def generate_gap_memo(
    llm: LLM,
    matrix_df: pd.DataFrame,
    profile_df: pd.DataFrame,
    gap_df: pd.DataFrame,
) -> str:
    """
    Generates a strategic memo based on the collected competitor data and gap analysis.
    """
    matrix_text = matrix_df.head(20).to_markdown(index=False) if not matrix_df.empty else "No matrix yet."
    profile_text = profile_df.head(20).to_markdown(index=False) if not profile_df.empty else "No profiles yet."
    gap_text = gap_df.head(12).to_markdown(index=False) if not gap_df.empty else "No gaps yet."

    prompt = f"""
You are a strategy analyst.

Write a concise market-gap memo for an investor/operator evaluating a startup building AI agents for biotech R&D.

Use this data:

COVERAGE MATRIX
{matrix_text}

COMPANY PROFILES
{profile_text}

GAP SCORES
{gap_text}

Output:
- 5 key findings
- which parts of the pipeline look saturated
- which parts look less crowded
- 3 product hypotheses for a new entrant
- one paragraph on what to ask the startup in diligence

Keep it sharp and practical.
"""
    return llm.ask(prompt)


def generate_slide_outline(
    llm: LLM,
    matrix_df: pd.DataFrame,
    profile_df: pd.DataFrame,
    gap_df: pd.DataFrame,
) -> str:
    """
    Generates a slide deck outline for presenting the competitor landscape findings.
    """
    matrix_text = matrix_df.head(20).to_markdown(index=False) if not matrix_df.empty else "No matrix yet."
    profile_text = profile_df.head(20).to_markdown(index=False) if not profile_df.empty else "No profiles yet."
    gap_text = gap_df.head(10).to_markdown(index=False) if not gap_df.empty else "No gaps yet."

    prompt = f"""
Create a 10-slide presentation outline for a competitive landscape review of agentic AI in drug discovery and development.

Use:
COVERAGE MATRIX
{matrix_text}

COMPANY PROFILES
{profile_text}

GAP SCORES
{gap_text}

For each slide, provide:
- slide title
- 3 to 5 bullets

Make it suitable for presenting to a startup founder or hiring manager.
"""
    return llm.ask(prompt)
