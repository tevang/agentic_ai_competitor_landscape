"""Markdown report writer for the competitor-landscape workflow."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from lib.config import AppConfig


class ReportWriter:
    """Create aesthetically improved markdown reports and related output files."""

    def __init__(self, config: AppConfig) -> None:
        """Store the configuration required to create report directories and markdown files."""

        self.config = config

    def prepare_run_directory(self) -> dict[str, Any]:
        """Create a unique report directory for the current run and return its paths."""

        base_dir = Path(self.config.paths.reports_dir)
        base_dir.mkdir(parents=True, exist_ok=True)

        run_label = self.config.runtime.run_label or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        run_dir = self._ensure_unique_directory(base_dir / run_label)
        run_dir.mkdir(parents=True, exist_ok=True)

        logos_dir = run_dir / self.config.paths.logos_subdir
        logos_dir.mkdir(parents=True, exist_ok=True)

        return {
            "run_label": run_dir.name,
            "run_dir": run_dir,
            "logos_dir": logos_dir,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def write_reports(self, results: dict[str, Any], run_context: dict[str, Any]) -> dict[str, str]:
        """Write markdown reports to disk and return their file paths."""

        if not self.config.reporting.write_markdown_files:
            return {}

        run_dir = Path(run_context["run_dir"])
        report_paths = {
            "main_report": run_dir / self.config.reporting.report_file_name,
            "gap_memo": run_dir / self.config.reporting.gap_memo_file_name,
            "slide_outline": run_dir / self.config.reporting.slide_outline_file_name,
            "fact_analysis": run_dir / self.config.reporting.fact_analysis_file_name,
            "critical_review": run_dir / self.config.reporting.critical_review_file_name,
        }

        self._write_text(report_paths["main_report"], self._render_main_report(results, run_context))
        self._write_text(report_paths["gap_memo"], str(results["gap_memo"]))
        self._write_text(report_paths["slide_outline"], str(results["slide_outline"]))
        self._write_text(report_paths["fact_analysis"], str(results["fact_analysis"]))
        self._write_text(report_paths["critical_review"], str(results["critical_review"]))

        return {key: str(path) for key, path in report_paths.items()}

    def _render_main_report(self, results: dict[str, Any], run_context: dict[str, Any]) -> str:
        """Render the full markdown report with attractive sections and logo-aware profile tables."""

        matrix_df: pd.DataFrame = results["matrix_df"]
        profile_df: pd.DataFrame = results["profile_df"]
        gap_df: pd.DataFrame = results["gap_df"]
        records_df: pd.DataFrame = results["records_df"]

        sections = [
            "# Biotech AI Competitor Landscape Report",
            "",
            f"**Run label:** `{run_context['run_label']}`  ",
            f"**Generated:** `{run_context['generated_at']}`",
            "",
            "## Executive Snapshot",
            "",
            self._build_snapshot_table(results, records_df, profile_df),
            "",
            "## Fact-Driven Analyst View",
            "",
            str(results["fact_analysis"]).strip(),
            "",
            "## Critical Agent Review",
            "",
            str(results["critical_review"]).strip(),
            "",
            "## Synthesized Gap Memo",
            "",
            str(results["gap_memo"]).strip(),
            "",
            "---",
            "",
            "# COMPETITOR COVERAGE MATRIX",
            "",
            "> Verified pipeline-step coverage with competitor counts and grouped company names.",
            "",
            self._render_matrix_table(matrix_df),
            "",
        ]

        if self.config.reporting.include_logo_gallery:
            sections.extend(
                [
                    "## Logo Gallery",
                    "",
                    self._render_logo_gallery(profile_df),
                    "",
                ]
            )

        sections.extend(
            [
                "---",
                "",
                "# COMPANY PROFILES",
                "",
                "> Profile cards with compact company facts, official websites, and downloaded logos when available.",
                "",
                self._render_company_profiles_table(profile_df),
                "",
                "---",
                "",
                "# GAP SCORES",
                "",
                "> White-space and saturation indicators for the processed pipeline steps.",
                "",
                self._render_gap_scores_section(gap_df),
                "",
                "---",
                "",
                "## Presentation Outline",
                "",
                str(results["slide_outline"]).strip(),
                "",
            ]
        )

        return "\n".join(sections).strip() + "\n"

    def _build_snapshot_table(
        self,
        results: dict[str, Any],
        records_df: pd.DataFrame,
        profile_df: pd.DataFrame,
    ) -> str:
        """Build a compact markdown summary table for the top of the report."""

        steps_processed = len(results["run_steps"])
        verified_links = len(records_df.index) if not records_df.empty else 0
        unique_companies = int(profile_df["company"].nunique()) if not profile_df.empty else 0
        logos_downloaded = int((profile_df["logo_path"].astype(str) != "").sum()) if not profile_df.empty else 0

        summary_df = pd.DataFrame(
            [
                {"Metric": "Pipeline steps processed", "Value": steps_processed},
                {"Metric": "Verified step-company links", "Value": verified_links},
                {"Metric": "Unique companies profiled", "Value": unique_companies},
                {"Metric": "Downloaded logos", "Value": logos_downloaded},
            ]
        )
        return summary_df.to_markdown(index=False)

    def _render_matrix_table(self, matrix_df: pd.DataFrame) -> str:
        """Render the competitor coverage matrix with an added competitor-count column."""

        if matrix_df.empty:
            return "_No verified coverage records yet._"

        view = matrix_df.copy()
        view["competitor_count"] = view["competitors"].apply(
            lambda value: 0 if not value else len([item for item in str(value).split("; ") if item.strip()])
        )
        view = view[["phase", "step", "competitor_count", "competitors"]]
        return view.to_markdown(index=False)

    def _render_company_profiles_table(self, profile_df: pd.DataFrame) -> str:
        """Render the company profile table with inline logo previews and website links."""

        if profile_df.empty:
            return "_No company profiles yet._"

        view = profile_df.copy()
        view["logo"] = view["logo_path"].apply(self._logo_cell)
        view["website_link"] = view["website"].apply(self._website_cell)

        columns = [
            "logo",
            "company",
            "type",
            "founded",
            "headquarters",
            "funding",
            "funding_rounds",
            "employees",
            "website_link",
            "specialization",
            "agentic_posture",
        ]
        renamed = view[columns].rename(columns={"website_link": "website"})
        return renamed.to_markdown(index=False)

    def _render_gap_scores_section(self, gap_df: pd.DataFrame) -> str:
        """Render attractive markdown for the gap-score section with top highlights."""

        if gap_df.empty:
            return "_No gap scores yet._"

        whitespace_top = gap_df.head(5)
        crowded_top = gap_df.sort_values(["competitor_count", "saturation_score"], ascending=[False, False]).head(5)

        whitespace_lines = [
            f"- **{row.step}** ({row.phase}) — whitespace score `{row.whitespace_score}`"
            for row in whitespace_top.itertuples()
        ]
        crowded_lines = [
            f"- **{row.step}** ({row.phase}) — competitor count `{row.competitor_count}`, saturation `{row.saturation_score}`"
            for row in crowded_top.itertuples()
        ]

        section_parts = [
            "### Top White-Space Signals",
            "",
            "\n".join(whitespace_lines) if whitespace_lines else "_None_",
            "",
            "### Most Crowded Steps",
            "",
            "\n".join(crowded_lines) if crowded_lines else "_None_",
            "",
            "### Full Gap Table",
            "",
            gap_df.to_markdown(index=False),
        ]
        return "\n".join(section_parts)

    def _render_logo_gallery(self, profile_df: pd.DataFrame) -> str:
        """Render a compact logo gallery table for the main report."""

        if profile_df.empty:
            return "_No logos available._"

        gallery_rows = []
        for row in profile_df.itertuples():
            if not getattr(row, "logo_path", ""):
                continue
            gallery_rows.append(
                {
                    "logo": self._logo_cell(row.logo_path),
                    "company": row.company,
                }
            )

        if not gallery_rows:
            return "_No logos downloaded for this run._"

        gallery_df = pd.DataFrame(gallery_rows)
        return gallery_df.to_markdown(index=False)

    def _logo_cell(self, logo_path: str) -> str:
        """Render an HTML image cell for a logo file relative to the report directory."""

        if not logo_path:
            return ""
        relative_path = f"{self.config.paths.logos_subdir}/{Path(logo_path).name}"
        return f'<img src="{relative_path}" alt="logo" width="42" />'

    def _website_cell(self, website: str) -> str:
        """Render a markdown hyperlink for a company website."""

        if not website:
            return ""
        return f"[{website}]({website})"

    def _write_text(self, path: Path, text: str) -> None:
        """Write text content to disk using UTF-8 encoding."""

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _ensure_unique_directory(self, path: Path) -> Path:
        """Return a unique path by suffixing a counter if the directory already exists."""

        if not path.exists():
            return path

        counter = 1
        while True:
            candidate = Path(f"{path}_{counter:02d}")
            if not candidate.exists():
                return candidate
            counter += 1