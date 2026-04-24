"""Fact-driven analyst agent that generates objective evidence-led findings."""

import pandas as pd

from lib.config import AppConfig
from lib.llm import LLM


class FactDrivenAnalystAgent:
    """Produce evidence-led interpretations from the structured tables without hype."""

    def __init__(self, llm: LLM, config: AppConfig) -> None:
        """Store the dependencies required for objective analysis."""

        self.llm = llm
        self.config = config

    def analyze(
        self,
        matrix_df: pd.DataFrame,
        profile_df: pd.DataFrame,
        gap_df: pd.DataFrame,
    ) -> str:
        """Write a strictly evidence-led analytical summary from the current run outputs."""

        matrix_text = self._table_preview(matrix_df, self.config.reporting.matrix_head_rows, "No matrix yet.")
        profile_text = self._table_preview(profile_df, self.config.reporting.profile_head_rows, "No profiles yet.")
        gap_text = self._table_preview(gap_df, self.config.reporting.gap_head_rows, "No gaps yet.")

        prompt = f"""
You are the Fact-Driven Analyst Agent.

Your job is to produce a sober, evidence-led interpretation of the current competitor-landscape data.
Rules:
- Use only what can be supported by the tables below.
- Avoid hype, speculation, or strategic storytelling.
- Note uncertainty when the data is sparse.

COVERAGE MATRIX
{matrix_text}

COMPANY PROFILES
{profile_text}

GAP SCORES
{gap_text}

Write:
- a concise analytical summary
- the most supported saturation observations
- the most supported whitespace observations
- explicit uncertainty notes
"""
        return self.llm.ask(prompt)

    def _table_preview(self, dataframe: pd.DataFrame, rows: int, empty_message: str) -> str:
        """Convert a dataframe preview into markdown, or return a fallback message when empty."""

        if dataframe.empty:
            return empty_message
        return dataframe.head(rows).to_markdown(index=False)