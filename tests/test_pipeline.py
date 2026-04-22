from main import PIPELINE_CSV, compute_gap_scores, parse_pipeline
import pandas as pd


def test_parse_pipeline_count():
    steps = parse_pipeline(PIPELINE_CSV)
    assert len(steps) == 26


def test_gap_scores_shape():
    steps = parse_pipeline(PIPELINE_CSV)[:3]
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
    gap_df = compute_gap_scores(records, steps)
    assert set(gap_df.columns) >= {
        "phase",
        "step",
        "competitor_count",
        "saturation_score",
        "whitespace_score",
    }
    assert len(gap_df) == 3