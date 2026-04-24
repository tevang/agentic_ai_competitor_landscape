"""Presentation agent that turns structured outputs into memo and slide-outline narratives."""

import pandas as pd

from lib.config import AppConfig
from lib.llm import LLM


class PresentationAgent:
    """Generate narrative outputs from the structured competitor-analysis tables."""

    def __init__(self, llm: LLM, config: AppConfig) -> None:
        """Store the dependencies required for final narrative generation."""

        self.llm = llm
        self.config = config

    def generate_gap_memo(
        self,
        matrix_df: pd.DataFrame,
        profile_df: pd.DataFrame,
        gap_df: pd.DataFrame,
        fact_analysis: str,
        critical_review: str,
    ) -> str:
        """Generate a balanced market-gap memo from structured tables and analyst debate."""

        matrix_text = self._table_preview(
            matrix_df,
            self.config.reporting.matrix_head_rows,
            empty_message="No matrix yet.",
        )
        profile_text = self._table_preview(
            profile_df,
            self.config.reporting.profile_head_rows,
            empty_message="No profiles yet.",
        )
        gap_text = self._table_preview(
            gap_df,
            self.config.reporting.gap_head_rows,
            empty_message="No gaps yet.",
        )

        prompt = f"""
You are a synthesis presenter.

Combine a fact-driven analyst view with a critical devil's-advocate review into one investor-grade market-gap memo.
Preserve objectivity, quantify uncertainty where possible, and prefer hard claims over hype.

FACT-DRIVEN ANALYST VIEW:
{fact_analysis}

CRITICAL AGENT REVIEW:
{critical_review}

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

Keep it sharp, balanced, and practical.
"""
        return self.llm.ask(prompt)

    def generate_slide_outline(
        self,
        matrix_df: pd.DataFrame,
        profile_df: pd.DataFrame,
        gap_df: pd.DataFrame,
        fact_analysis: str,
        critical_review: str,
    ) -> str:
        """Generate a slide-by-slide presentation outline for the analysis."""

        matrix_text = self._table_preview(
            matrix_df,
            self.config.reporting.matrix_head_rows,
            empty_message="No matrix yet.",
        )
        profile_text = self._table_preview(
            profile_df,
            self.config.reporting.profile_head_rows,
            empty_message="No profiles yet.",
        )
        gap_text = self._table_preview(
            gap_df,
            self.config.reporting.slide_gap_head_rows,
            empty_message="No gaps yet.",
        )

        prompt = f"""
Create a {self.config.reporting.slide_count}-slide presentation outline for a competitive landscape review of agentic AI in drug discovery and development.

FACT-DRIVEN ANALYST VIEW:
{fact_analysis}

CRITICAL AGENT REVIEW:
{critical_review}

COVERAGE MATRIX
{matrix_text}

COMPANY PROFILES
{profile_text}

GAP SCORES
{gap_text}

For each slide, provide:
- slide title
- 3 to 5 bullets

Make it suitable for presenting to a startup founder, investor, or hiring manager.
"""
        return self.llm.ask(prompt)

    def _table_preview(self, dataframe: pd.DataFrame, rows: int, empty_message: str) -> str:
        """Convert a dataframe preview into markdown, or return a fallback message when empty."""

        if dataframe.empty:
            return empty_message
        return dataframe.head(rows).to_markdown(index=False)