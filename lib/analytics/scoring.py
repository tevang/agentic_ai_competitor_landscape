"""Tabular analytics and gap-scoring functions for the pipeline coverage map."""

import pandas as pd

from lib.config import AppConfig
from lib.models import CompanyProfile, PipelineStep


def build_matrix_df(records_df: pd.DataFrame) -> pd.DataFrame:
    """Build a step-level matrix mapping each pipeline step to its verified competitors."""

    if records_df.empty:
        return pd.DataFrame(columns=["phase", "step", "competitors"])

    company_column = "competitor_label" if "competitor_label" in records_df.columns else "company"

    matrix_df = (
        records_df.groupby(["phase", "step"])[company_column]
        .apply(lambda series: "; ".join(sorted(set(str(value) for value in series if str(value).strip()))))
        .reset_index()
        .rename(columns={company_column: "competitors"})
    )
    return matrix_df.sort_values(["phase", "step"])


def build_profile_df(profile_cache: dict[str, CompanyProfile]) -> pd.DataFrame:
    """Convert the in-memory company-profile cache into a dataframe."""

    rows: list[dict[str, str | float]] = []
    seen_company_keys: set[str] = set()

    for profile in profile_cache.values():
        company_key = profile.name.strip().lower()
        if company_key in seen_company_keys:
            continue
        seen_company_keys.add(company_key)

        rows.append(
            {
                "company": profile.name,
                "products_or_solutions": "; ".join(profile.products_or_solutions),
                "type": profile.vertical_or_horizontal,
                "funding": profile.funding,
                "funding_rounds": profile.funding_rounds,
                "employees": profile.employees,
                "founded": profile.founded,
                "headquarters": profile.headquarters,
                "presence": "; ".join(profile.presence),
                "website": profile.website,
                "specialization": profile.specialization,
                "agentic_posture": profile.explicit_agentic_posture,
                "confidence": round(profile.confidence, 2),
                "logo_path": profile.logo_path,
                "taxonomy_primary_phase": profile.taxonomy_primary_phase,
                "taxonomy_primary_subcategory": profile.taxonomy_primary_subcategory,
                "taxonomy_phase_labels": "; ".join(profile.taxonomy_phase_labels),
                "taxonomy_subcategory_labels": "; ".join(profile.taxonomy_subcategory_labels),
            }
        )

    if not rows:
        return pd.DataFrame(
            columns=[
                "company",
                "products_or_solutions",
                "type",
                "funding",
                "funding_rounds",
                "employees",
                "founded",
                "headquarters",
                "presence",
                "website",
                "specialization",
                "agentic_posture",
                "confidence",
                "logo_path",
                "taxonomy_primary_phase",
                "taxonomy_primary_subcategory",
                "taxonomy_phase_labels",
                "taxonomy_subcategory_labels",
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

        competitor_basis = "company"
        competitor_count = int(subset[competitor_basis].nunique()) if not subset.empty else 0
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