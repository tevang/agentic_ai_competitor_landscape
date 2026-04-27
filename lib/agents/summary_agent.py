"""Summary agent for producing a clean competitor CSV from pipeline results or existing reports."""

from __future__ import annotations

import json
import re
from io import StringIO
from pathlib import Path
from typing import Any

import pandas as pd

from lib.config import AppConfig
from lib.llm import LLM
from lib.utils.text_utils import canonical_name, extract_json_blob


PRIORITY_REPORT_FILES = [
    "critical_review.md",
    "competitor_landscape_report.md",
    "gap_memo.md",
    "fact_driven_analysis.md",
    "presentation_outline.md",
]


class SummaryAgent:
    """Create a clean, CSV-ready competitor table from pipeline outputs and critical reviews."""

    def __init__(self, llm: LLM | None, config: AppConfig) -> None:
        """Store configuration and the optional LLM client."""

        self.llm = llm
        self.config = config

    def summarize_pipeline_results(
        self,
        matrix_df: pd.DataFrame,
        profile_df: pd.DataFrame,
        gap_df: pd.DataFrame,
        fact_analysis: str,
        critical_review: str,
        gap_memo: str,
        slide_outline: str,
        run_dir: Path,
    ) -> tuple[pd.DataFrame, str]:
        """Create and write the clean summary CSV after a normal pipeline run."""

        prompt = self._build_pipeline_prompt(
            matrix_df=matrix_df,
            profile_df=profile_df,
            gap_df=gap_df,
            fact_analysis=fact_analysis,
            critical_review=critical_review,
            gap_memo=gap_memo,
            slide_outline=slide_outline,
        )
        fallback_rows = self._rows_from_profile_df(profile_df)
        summary_df = self._generate_summary_dataframe(prompt=prompt, fallback_rows=fallback_rows)

        output_path = run_dir / self.config.summary.output_file_name
        self._write_csv(summary_df, output_path)
        return summary_df, str(output_path)

    def summarize_existing_report_dir(
        self,
        report_dir: Path,
        output_path: Path | None = None,
    ) -> tuple[pd.DataFrame, str]:
        """Create and write a clean summary CSV from an already-finished report directory."""

        if not report_dir.exists() or not report_dir.is_dir():
            raise FileNotFoundError(f"Report directory not found: {report_dir}")

        report_text = self._read_report_directory(report_dir)
        fallback_rows = self._rows_from_report_text(report_text)

        prompt = self._build_standalone_prompt(report_dir=report_dir, report_text=report_text)
        summary_df = self._generate_summary_dataframe(prompt=prompt, fallback_rows=fallback_rows)

        if output_path is None:
            if self.config.summary.output_dir:
                output_directory = Path(self.config.summary.output_dir)
                output_path = output_directory / self.config.summary.output_file_name
            else:
                output_path = report_dir / self.config.summary.output_file_name

        self._write_csv(summary_df, output_path)
        return summary_df, str(output_path)

    def _generate_summary_dataframe(
        self,
        prompt: str,
        fallback_rows: list[dict[str, str]],
    ) -> pd.DataFrame:
        """Use the LLM when enabled, otherwise fall back to deterministic profile-table extraction."""

        rows: list[dict[str, str]] = []

        if self.config.summary.use_llm and self.llm is not None:
            try:
                data = self.llm.ask_json(prompt)
                rows = data.get("rows", []) if isinstance(data, dict) else []
            except Exception as exc:
                if self.config.runtime.verbose:
                    print(f"  [warn] summary-agent LLM generation failed, using fallback rows: {exc}")

        if not rows:
            rows = fallback_rows

        df = self._coerce_dataframe(rows)
        return df.head(self.config.summary.max_rows)

    def _build_pipeline_prompt(
        self,
        matrix_df: pd.DataFrame,
        profile_df: pd.DataFrame,
        gap_df: pd.DataFrame,
        fact_analysis: str,
        critical_review: str,
        gap_memo: str,
        slide_outline: str,
    ) -> str:
        """Build the prompt for a full-pipeline summary pass."""

        matrix_text = self._table_text(matrix_df, "No matrix available.")
        profile_text = self._table_text(profile_df, "No profiles available.")
        gap_text = self._table_text(gap_df, "No gap scores available.")

        context = f"""
COVERAGE MATRIX
{matrix_text}

COMPANY PROFILES
{profile_text}

GAP SCORES
{gap_text}

FACT-DRIVEN ANALYST VIEW
{fact_analysis or "Not available."}

CRITICAL AGENT REVIEW
{critical_review or "Not available."}

GAP MEMO
{gap_memo or "Not available."}

PRESENTATION OUTLINE
{slide_outline or "Not available."}
"""
        return self._build_summary_prompt(context=context, source_description="current pipeline outputs")

    def _build_standalone_prompt(self, report_dir: Path, report_text: str) -> str:
        """Build the prompt for a standalone report-directory summary pass."""

        context = f"""
REPORT DIRECTORY:
{report_dir}

REPORT FILE CONTENT:
{report_text}
"""
        return self._build_summary_prompt(context=context, source_description="existing markdown reports")

    def _build_summary_prompt(self, context: str, source_description: str) -> str:
        """Build the shared summary-agent prompt."""

        truncated_context = self._truncate(context, self.config.summary.max_context_chars)
        output_columns = self.config.summary.output_columns
        include_missing = self.config.summary.include_critical_missing_companies

        return f"""
You are the Summary Agent for a biotech agentic-AI competitive intelligence pipeline.

Your task:
Create one clean CSV-ready table from {source_description}. The table must summarize competitor companies and products/solutions using only the columns listed below.

Required output columns, in this exact order:
{json.dumps(output_columns, indent=2)}

Important:
- The final CSV column is intentionally named "gentic_posture" because that is the requested schema. Populate it with the company's agentic posture value.
- Use the Company Profiles table as the primary source for existing rows.
- Use the Critical Agent Review, Gap Memo, and Presentation Outline to detect companies/products that the pipeline missed, under-specified, or misrepresented.
- If a critical review explicitly identifies a missing canonical company/product, include it when it is relevant to the analyzed phase/subphase and appears material to the landscape.
- Include missing companies/products with "unknown" for facts not present in the reports. Do not fabricate founding year, headquarters, funding, employee counts, or websites.
- If the report shows a generic company but the critical review says the product should be called out, preserve the product name in "products/solutions" rather than losing it.
- If a row is a non-commercial reference body, pure publisher, generic consultancy, or horizontal infrastructure provider, include it only if the reports support it as relevant to the competitive landscape. Otherwise omit it from the clean table.
- Prefer product vendors and productized PV/safety solutions over article publishers or implementation partners.
- Keep each company to one row when possible. Merge product names with semicolons.
- Use "unknown" for unavailable fields.
- Allowed type values: vertical, horizontal, services/BPO, SI/consultancy, reference/non-profit, unknown.
- Allowed gentic_posture values: explicit, adjacent, unclear, unknown.
- Do not include explanatory prose in the JSON.

include_critical_missing_companies:
{include_missing}

Source material:
{truncated_context}

Return JSON only:
{{
  "rows": [
    {{
      "company name": "Company Name",
      "products/solutions": "Product A; Product B",
      "type": "vertical|horizontal|services/BPO|SI/consultancy|reference/non-profit|unknown",
      "taxonomy_phase": "string",
      "taxonomy_subcategory": "string",
      "founded": "string",
      "headquarters": "string",
      "funding": "string",
      "funding_rounds": "string",
      "employees": "string",
      "website": "string",
      "specialization": "string",
      "gentic_posture": "explicit|adjacent|unclear|unknown"
    }}
  ]
}}
"""

    def _read_report_directory(self, report_dir: Path) -> str:
        """Read known report files from a run directory, prioritizing critical review and main report."""

        parts: list[str] = []
        seen_paths: set[Path] = set()

        for filename in PRIORITY_REPORT_FILES:
            path = report_dir / filename
            if not path.exists() or not path.is_file():
                continue
            seen_paths.add(path.resolve())
            parts.append(self._read_report_file(path))

        for path in sorted(report_dir.glob("*.md")):
            if path.resolve() in seen_paths:
                continue
            parts.append(self._read_report_file(path))

        if not parts:
            raise FileNotFoundError(f"No markdown report files found in: {report_dir}")

        return self._truncate("\n\n---\n\n".join(parts), self.config.summary.max_context_chars)

    def _read_report_file(self, path: Path) -> str:
        """Read one markdown file with a source heading."""

        text = path.read_text(encoding="utf-8", errors="ignore")
        return f"# SOURCE FILE: {path.name}\n\n{text}"

    def _rows_from_profile_df(self, profile_df: pd.DataFrame) -> list[dict[str, str]]:
        """Build deterministic fallback rows from an existing profile dataframe."""

        if profile_df is None or profile_df.empty:
            return []

        rows: list[dict[str, str]] = []
        for _, row in profile_df.iterrows():
            rows.append(
                {
                    "company name": self._value_from_row(row, ["company", "company name"]),
                    "products/solutions": self._value_from_row(row, ["products_or_solutions", "products/solutions"]),
                    "type": self._value_from_row(row, ["type", "vertical_or_horizontal"]),
                    "taxonomy_phase": self._value_from_row(row, ["taxonomy_primary_phase", "taxonomy_phase"]),
                    "taxonomy_subcategory": self._value_from_row(row, ["taxonomy_primary_subcategory", "taxonomy_subcategory"]),
                    "founded": self._value_from_row(row, ["founded"]),
                    "headquarters": self._value_from_row(row, ["headquarters"]),
                    "funding": self._value_from_row(row, ["funding"]),
                    "funding_rounds": self._value_from_row(row, ["funding_rounds"]),
                    "employees": self._value_from_row(row, ["employees"]),
                    "website": self._value_from_row(row, ["website"]),
                    "specialization": self._value_from_row(row, ["specialization"]),
                    "gentic_posture": self._value_from_row(row, ["gentic_posture", "agentic_posture"]),
                }
            )

        return rows

    def _rows_from_report_text(self, report_text: str) -> list[dict[str, str]]:
        """Build deterministic fallback rows by parsing company profile tables from markdown reports."""

        profile_table = self._extract_markdown_table_after_heading(report_text, "# COMPANY PROFILES")
        if profile_table.empty:
            profile_table = self._extract_markdown_table_after_heading(report_text, "# COMPANY MAP")

        if profile_table.empty:
            return []

        return self._rows_from_profile_df(profile_table)

    def _extract_markdown_table_after_heading(self, text: str, heading: str) -> pd.DataFrame:
        """Extract the first markdown table after a heading into a dataframe."""

        heading_index = text.find(heading)
        if heading_index == -1:
            return pd.DataFrame()

        following = text[heading_index + len(heading) :]
        table_lines: list[str] = []
        in_table = False

        for line in following.splitlines():
            stripped = line.strip()
            if stripped.startswith("|"):
                table_lines.append(stripped)
                in_table = True
                continue

            if in_table:
                break

        if len(table_lines) < 2:
            return pd.DataFrame()

        try:
            header = [self._clean_cell(cell) for cell in table_lines[0].strip("|").split("|")]
            rows: list[list[str]] = []
            for line in table_lines[2:]:
                cells = [self._clean_cell(cell) for cell in line.strip("|").split("|")]
                if len(cells) == len(header):
                    rows.append(cells)
            return pd.DataFrame(rows, columns=header)
        except Exception:
            return pd.DataFrame()

    def _coerce_dataframe(self, rows: list[dict[str, Any]]) -> pd.DataFrame:
        """Normalize LLM or fallback rows into the exact configured CSV schema."""

        normalized_rows: list[dict[str, str]] = []
        for item in rows:
            if not isinstance(item, dict):
                continue

            normalized = self._normalize_summary_row(item)
            if not normalized["company name"] or normalized["company name"] == "unknown":
                continue

            normalized_rows.append(normalized)

        deduped_rows = self._dedupe_summary_rows(normalized_rows)
        if not deduped_rows:
            return pd.DataFrame(columns=self.config.summary.output_columns)

        return pd.DataFrame(deduped_rows, columns=self.config.summary.output_columns)

    def _normalize_summary_row(self, row: dict[str, Any]) -> dict[str, str]:
        """Normalize one summary row into exact column names."""

        normalized = {
            "company name": self._first_value(row, ["company name", "company", "name"]),
            "products/solutions": self._first_value(
                row,
                ["products/solutions", "products_or_solutions", "product_or_solution", "products", "solutions"],
            ),
            "type": self._first_value(row, ["type", "vertical_or_horizontal", "vendor_type"]),
            "taxonomy_phase": self._first_value(row, ["taxonomy_phase", "taxonomy_primary_phase"]),
            "taxonomy_subcategory": self._first_value(row, ["taxonomy_subcategory", "taxonomy_primary_subcategory"]),
            "founded": self._first_value(row, ["founded"]),
            "headquarters": self._first_value(row, ["headquarters", "hq"]),
            "funding": self._first_value(row, ["funding"]),
            "funding_rounds": self._first_value(row, ["funding_rounds", "rounds"]),
            "employees": self._first_value(row, ["employees", "employee_count"]),
            "website": self._first_value(row, ["website", "url"]),
            "specialization": self._first_value(row, ["specialization", "description"]),
            "gentic_posture": self._first_value(row, ["gentic_posture", "agentic_posture", "explicit_agentic_posture"]),
        }

        for column in self.config.summary.output_columns:
            value = normalized.get(column, "")
            normalized[column] = self._clean_cell(value) or "unknown"

        normalized["type"] = self._normalize_type(normalized["type"])
        normalized["gentic_posture"] = self._normalize_posture(normalized["gentic_posture"])
        return normalized

    def _dedupe_summary_rows(self, rows: list[dict[str, str]]) -> list[dict[str, str]]:
        """Deduplicate summary rows by company and merge product names when possible."""

        by_company: dict[str, dict[str, str]] = {}

        for row in rows:
            key = canonical_name(row["company name"])
            if key not in by_company:
                by_company[key] = row
                continue

            existing = by_company[key]
            existing["products/solutions"] = self._merge_semicolon_values(
                existing.get("products/solutions", ""),
                row.get("products/solutions", ""),
            )

            for column in self.config.summary.output_columns:
                existing_value = existing.get(column, "unknown")
                new_value = row.get(column, "unknown")
                if self._is_unknown(existing_value) and not self._is_unknown(new_value):
                    existing[column] = new_value

        return list(by_company.values())

    def _merge_semicolon_values(self, first: str, second: str) -> str:
        """Merge semicolon-delimited text values while preserving order."""

        values: list[str] = []
        for value in [first, second]:
            if self._is_unknown(value):
                continue
            for part in re.split(r"[;|]", value):
                clean = part.strip()
                if clean and clean not in values:
                    values.append(clean)

        return "; ".join(values) if values else "unknown"

    def _write_csv(self, summary_df: pd.DataFrame, output_path: Path) -> None:
        """Write the summary dataframe as CSV."""

        output_path.parent.mkdir(parents=True, exist_ok=True)
        summary_df.to_csv(output_path, index=False, encoding="utf-8")

    def _table_text(self, dataframe: pd.DataFrame, empty_message: str) -> str:
        """Convert a dataframe to markdown or return an empty fallback."""

        if dataframe is None or dataframe.empty:
            return empty_message
        return dataframe.to_markdown(index=False)

    def _value_from_row(self, row: pd.Series, names: list[str]) -> str:
        """Return the first non-empty value from a dataframe row across possible columns."""

        lower_to_actual = {str(column).strip().lower(): column for column in row.index}
        for name in names:
            actual = lower_to_actual.get(name.strip().lower())
            if actual is None:
                continue
            value = row.get(actual, "")
            if value is not None and str(value).strip():
                return self._clean_cell(value)
        return "unknown"

    def _first_value(self, row: dict[str, Any], keys: list[str]) -> str:
        """Return the first non-empty value across possible dictionary keys."""

        lower_to_actual = {str(key).strip().lower(): key for key in row.keys()}
        for key in keys:
            actual = lower_to_actual.get(key.strip().lower())
            if actual is None:
                continue
            value = row.get(actual, "")
            if value is not None and str(value).strip():
                return str(value).strip()
        return "unknown"

    def _clean_cell(self, value: Any) -> str:
        """Clean a markdown or HTML table cell into CSV-safe plain text."""

        text = str(value or "").strip()
        if not text:
            return ""

        text = re.sub(r"<img[^>]*>", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\2", text)
        text = re.sub(r"<br\s*/?>", "; ", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = text.replace("&nbsp;", " ")
        text = text.strip("` ")
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _normalize_type(self, value: str) -> str:
        """Normalize vendor type values."""

        lowered = value.strip().lower()
        if lowered in {"vertical", "horizontal", "unknown"}:
            return lowered
        if "service" in lowered or "bpo" in lowered:
            return "services/BPO"
        if "consult" in lowered or "integrator" in lowered or lowered == "si":
            return "SI/consultancy"
        if "reference" in lowered or "non-profit" in lowered or "nonprofit" in lowered:
            return "reference/non-profit"
        return value if value else "unknown"

    def _normalize_posture(self, value: str) -> str:
        """Normalize agentic posture values."""

        lowered = value.strip().lower()
        if lowered in {"explicit", "adjacent", "unclear", "unknown"}:
            return lowered
        if "explicit" in lowered or "agentic" in lowered or "agent" in lowered:
            return "explicit"
        if "adjacent" in lowered or "ai" in lowered or "automation" in lowered or "ml" in lowered:
            return "adjacent"
        return "unknown"

    def _is_unknown(self, value: str) -> bool:
        """Return whether a text value is effectively unknown."""

        return not value or value.strip().lower() in {"unknown", "n/a", "na", "none", "-"}

    def _truncate(self, text: str, max_chars: int) -> str:
        """Truncate long report context safely."""

        if max_chars <= 0 or len(text) <= max_chars:
            return text
        return text[:max_chars] + "\n\n[TRUNCATED]\n"