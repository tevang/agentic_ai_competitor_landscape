"""Tabular analytics and gap-scoring functions for the pipeline coverage map."""

import pandas as pd

from lib.config import AppConfig
from lib.models import CompanyProfile, PipelineStep


def build_matrix_df(records_df: pd.DataFrame) -> pd.DataFrame:
    """Build a step-level matrix mapping each pipeline step to its verified competitors."""

    if records_df.empty:
        return pd.DataFrame(columns=["phase", "step", "competitors"])

    matrix_df = (
        records_df.groupby(["phase", "step"])["company"]
        .apply(lambda series: "; ".join(sorted(set(series))))
        .reset_index()
        .rename(columns={"company": "competitors"})
    )
    return matrix_df.sort_values(["phase", "step"])


def build_profile_df(profile_cache: dict[str, CompanyProfile]) -> pd.DataFrame:
    """Convert the in-memory company-profile cache into a dataframe."""

    rows: list[dict[str, str | float]] = []
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
        return pd.DataFrame(
            columns=[
                "company",
                "type",
                "funding",
                "employees",
                "founded",
                "headquarters",
                "presence",
                "specialization",
                "agentic_posture",
                "confidence",
            ]
        )

    return pd.DataFrame(rows).sort_values("company")


def compute_gap_scores(records_df: pd.DataFrame, steps: list[PipelineStep], config: AppConfig) -> pd.DataFrame:
    """Compute saturation and whitespace scores for each pipeline step."""

    rows: list[dict[str, str | float | int]] = []
    scoring = config.scoring

    for step in steps:
        subset = (
            records_df[
                (records_df["phase"] == step.phase)
                & (records_df["step"] == step.step)
            ]
            if not records_df.empty
            else pd.DataFrame()
        )

        competitor_count = int(subset["company"].nunique()) if not subset.empty else 0
        explicit_count = int((subset["agentic_posture"] == "explicit").sum()) if not subset.empty else 0
        vertical_count = int((subset["vertical_or_horizontal"] == "vertical").sum()) if not subset.empty else 0
        avg_confidence = float(subset["confidence"].mean()) if not subset.empty else 0.0

        saturation_score = (
            competitor_count
            + scoring.explicit_agentic_weight * explicit_count
            + scoring.vertical_weight * vertical_count
        )
        whitespace_score = (
            scoring.pain_weights.get(step.step, scoring.default_pain_weight)
            + scoring.regulatory_tailwind.get(step.step, 0.0)
            + max(0.0, scoring.whitespace_baseline - saturation_score)
        )

        rows.append(
            {
                "phase": step.phase,
                "step": step.step,
                "competitor_count": competitor_count,
                "explicit_agentic_count": explicit_count,
                "vertical_count": vertical_count,
                "avg_confidence": round(avg_confidence, 2),
                "saturation_score": round(saturation_score, 2),
                "whitespace_score": round(whitespace_score, 2),
            }
        )

    gap_df = pd.DataFrame(rows)
    return gap_df.sort_values(["whitespace_score", "competitor_count"], ascending=[False, True])