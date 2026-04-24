"""Input/output helpers for loading the pipeline ontology and optional seed-company inputs."""

import csv
from pathlib import Path

from lib.models import PipelineStep, UserSeedCompany

REQUIRED_PIPELINE_COLUMNS = {"Phase", "Sub-phase / Step", "Key activities"}

SEED_COMPANY_COLUMN_ALIASES = {
    "company_name": ["company_name", "company", "name"],
    "classification": ["classification", "type", "vertical_or_horizontal"],
    "website": ["website", "url", "company_website"],
    "phase": ["phase"],
    "step": ["step", "sub-phase / step", "sub_phase / step", "subphase", "sub_phase"],
    "notes": ["notes", "note", "comments", "comment"],
    "funding": ["funding", "total_funding"],
    "funding_rounds": ["funding_rounds", "rounds", "number_of_rounds"],
    "employees": ["employees", "employee_count", "team_size"],
    "founded": ["founded", "founded_year", "year_founded"],
    "headquarters": ["headquarters", "hq", "hq_location"],
    "presence": ["presence", "geographical_presence", "locations", "offices"],
}


def load_pipeline_csv(path: str | Path) -> list[PipelineStep]:
    """Load the drug-development ontology from a CSV file stored under the data directory."""

    csv_path = Path(path)
    if not csv_path.exists():
        raise FileNotFoundError(f"Pipeline CSV not found: {csv_path}")

    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"CSV file has no header row: {csv_path}")

        missing_columns = REQUIRED_PIPELINE_COLUMNS.difference(reader.fieldnames)
        if missing_columns:
            missing = ", ".join(sorted(missing_columns))
            raise ValueError(f"CSV file is missing required column(s): {missing}")

        steps: list[PipelineStep] = []
        for row in reader:
            steps.append(
                PipelineStep(
                    phase=row["Phase"].strip(),
                    step=row["Sub-phase / Step"].strip(),
                    activities=row["Key activities"].strip(),
                )
            )

    return steps


def load_seed_companies_csv(
    path: str | Path | None,
    enabled: bool = True,
    required: bool = False,
) -> list[UserSeedCompany]:
    """Load optional user-supplied companies from a CSV file."""

    if not enabled or not path:
        return []

    csv_path = Path(path)
    if not csv_path.exists():
        if required:
            raise FileNotFoundError(f"Seed-company CSV not found: {csv_path}")
        return []

    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            if required:
                raise ValueError(f"Seed-company CSV has no header row: {csv_path}")
            return []

        companies: list[UserSeedCompany] = []
        for row in reader:
            normalized_row = {
                (key or "").strip().lower(): (value.strip() if isinstance(value, str) else "")
                for key, value in row.items()
            }
            company_name = _get_first_non_empty_value(normalized_row, SEED_COMPANY_COLUMN_ALIASES["company_name"])
            if not company_name:
                continue

            companies.append(
                UserSeedCompany(
                    company_name=company_name,
                    classification=_get_first_non_empty_value(normalized_row, SEED_COMPANY_COLUMN_ALIASES["classification"]),
                    website=_get_first_non_empty_value(normalized_row, SEED_COMPANY_COLUMN_ALIASES["website"]),
                    phase=_get_first_non_empty_value(normalized_row, SEED_COMPANY_COLUMN_ALIASES["phase"]),
                    step=_get_first_non_empty_value(normalized_row, SEED_COMPANY_COLUMN_ALIASES["step"]),
                    notes=_get_first_non_empty_value(normalized_row, SEED_COMPANY_COLUMN_ALIASES["notes"]),
                    funding=_get_first_non_empty_value(normalized_row, SEED_COMPANY_COLUMN_ALIASES["funding"]),
                    funding_rounds=_get_first_non_empty_value(normalized_row, SEED_COMPANY_COLUMN_ALIASES["funding_rounds"]),
                    employees=_get_first_non_empty_value(normalized_row, SEED_COMPANY_COLUMN_ALIASES["employees"]),
                    founded=_get_first_non_empty_value(normalized_row, SEED_COMPANY_COLUMN_ALIASES["founded"]),
                    headquarters=_get_first_non_empty_value(normalized_row, SEED_COMPANY_COLUMN_ALIASES["headquarters"]),
                    presence=_get_first_non_empty_value(normalized_row, SEED_COMPANY_COLUMN_ALIASES["presence"]),
                )
            )

    return companies


def _get_first_non_empty_value(row: dict[str, str], aliases: list[str]) -> str:
    """Return the first non-empty value among a list of possible column aliases."""

    for alias in aliases:
        value = row.get(alias.lower(), "")
        if value:
            return value.strip()
    return ""