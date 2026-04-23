"""Input/output helpers for loading the pipeline ontology from disk."""

import csv
from pathlib import Path

from lib.models import PipelineStep


REQUIRED_PIPELINE_COLUMNS = {"Phase", "Sub-phase / Step", "Key activities"}


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