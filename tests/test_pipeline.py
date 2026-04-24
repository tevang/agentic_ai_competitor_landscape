"""Basic tests for CSV loading and whitespace-scoring behavior."""

import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from lib.analytics.scoring import compute_gap_scores
from lib.config import (
    AppConfig,
    DedupeConfig,
    OpenAIConfig,
    PathsConfig,
    RagConfig,
    ReactConfig,
    ReportingConfig,
    RuntimeConfig,
    ScoringConfig,
    TavilyConfig,
)
from lib.utils.io_utils import load_pipeline_csv


SAMPLE_CSV = """Phase,Sub-phase / Step,Key activities
Early Drug Discovery,Target identification,"Use genomic analyses to identify a target."
Early Drug Discovery,Target validation,"Validate target relevance in disease."
Clinical Development,Phase I,"Assess safety and dose range."
"""


def build_test_config(tmp_path: Path) -> AppConfig:
    """Construct a minimal in-memory config object for unit testing."""

    return AppConfig(
        paths=PathsConfig(
            pipeline_csv=str(tmp_path / "pipeline.csv"),
            chroma_path=str(tmp_path / ".chroma"),
            chroma_collection_name="test_collection",
        ),
        runtime=RuntimeConfig(max_steps=3, max_candidates_per_step=10, verbose=False),
        openai=OpenAIConfig(),
        tavily=TavilyConfig(),
        rag=RagConfig(),
        react=ReactConfig(),
        dedupe=DedupeConfig(),
        reporting=ReportingConfig(),
        scoring=ScoringConfig(
            pain_weights={
                "Target identification": 2.0,
                "Target validation": 2.2,
                "Phase I": 2.4,
            },
            regulatory_tailwind={},
        ),
    )


def test_load_pipeline_csv_count(tmp_path: Path) -> None:
    """The CSV loader should parse the expected number of ontology rows."""

    csv_path = tmp_path / "pipeline.csv"
    csv_path.write_text(SAMPLE_CSV, encoding="utf-8")
    steps = load_pipeline_csv(csv_path)
    assert len(steps) == 3


def test_gap_scores_shape(tmp_path: Path) -> None:
    """The gap-score dataframe should contain one row per loaded pipeline step."""

    csv_path = tmp_path / "pipeline.csv"
    csv_path.write_text(SAMPLE_CSV, encoding="utf-8")
    config = build_test_config(tmp_path)
    steps = load_pipeline_csv(csv_path)

    records = pd.DataFrame(
        [
            {
                "phase": steps[0].phase,
                "step": steps[0].step,
                "company": "BenchSci",
                "agentic_posture": "adjacent",
                "vertical_or_horizontal": "vertical",
                "confidence": 0.8,
            },
            {
                "phase": steps[0].phase,
                "step": steps[0].step,
                "company": "Owkin",
                "agentic_posture": "explicit",
                "vertical_or_horizontal": "vertical",
                "confidence": 0.9,
            },
        ]
    )

    gap_df = compute_gap_scores(records, steps, config)
    assert set(gap_df.columns) >= {
        "phase",
        "step",
        "competitor_count",
        "saturation_score",
        "whitespace_score",
    }
    assert len(gap_df) == 3