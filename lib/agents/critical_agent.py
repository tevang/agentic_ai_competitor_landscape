"""Critical agent that plays devil's advocate against the fact-driven analyst."""

import pandas as pd

from lib.config import AppConfig
from lib.llm import LLM


class CriticalAgent:
    """Challenge assumptions, expose loopholes, and test the robustness of the current interpretation."""

    def __init__(self, llm: LLM, config: AppConfig) -> None:
        """Store the dependencies required for critical review."""

        self.llm = llm
        self.config = config

    def challenge(
        self,
        matrix_df: pd.DataFrame,
        profile_df: pd.DataFrame,
        gap_df: pd.DataFrame,
        fact_analysis: str,
    ) -> str:
        """Generate a devil's-advocate review that pressure-tests the current analysis."""

        matrix_text = self._table_preview(matrix_df, self.config.reporting.matrix_head_rows, "No matrix yet.")
        profile_text = self._table_preview(profile_df, self.config.reporting.profile_head_rows, "No profiles yet.")
        gap_text = self._table_preview(gap_df, self.config.reporting.gap_head_rows, "No gaps yet.")

        prompt = f"""
You are the Critical Agent.

Your job is to challenge the current interpretation aggressively but rationally.
Find logical loopholes, category errors, survivorship bias, data sparsity problems, and alternative explanations.

FACT-DRIVEN ANALYST VIEW:
{fact_analysis}

COVERAGE MATRIX
{matrix_text}

COMPANY PROFILES
{profile_text}

GAP SCORES
{gap_text}

Write:
- the strongest objections to the current analysis
- where the evidence base is too thin
- which conclusions are premature
- which extra checks would materially change confidence
"""
        return self.llm.ask(prompt)

    def _table_preview(self, dataframe: pd.DataFrame, rows: int, empty_message: str) -> str:
        """Convert a dataframe preview into markdown, or return a fallback message when empty."""

        if dataframe.empty:
            return empty_message
        return dataframe.head(rows).to_markdown(index=False)