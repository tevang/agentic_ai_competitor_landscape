# Agentic AI Biotech Competitor Landscape

This project researches AI companies across the biotech and drug-development workflow, then writes competitor tables, report markdown, and a clean summary CSV.

It is designed for two common workflows:

- Run a cheaper first-pass landscape scan to see which areas look interesting.
- Run a deeper analysis on selected phases or subphases after you know where to focus.

![Agent teams](docs/AI_agent_teams.png)

## What You Get

- A competitor coverage matrix by pipeline phase and subphase.
- Company profiles with products, websites, and evidence.
- Gap and whitespace scoring.
- Markdown reports in `reports/<run_id>/`.
- `competitor_summary.csv` when summary generation is enabled.

## Setup

Create the environment:

```shell
conda env create --file environment.yml
conda activate agentic_ai_competitor_landscape
```

Set your API keys:

```shell
export OPENAI_API_KEY="your-openai-key"
export TAVILY_API_KEY="your-tavily-key"
```

You can also place the keys in a local `.env` file because `main.py` loads environment variables with `python-dotenv`.

## Basic Configuration

The main settings live in `config.yml`.

### Available Pipeline Phases and Sub-phases

Below are the phases and sub-phases available for analysis, as defined in `data/Drug_Development_phase_segmentation_time_cost_citations.csv`:

*   **Early Drug Discovery**
    *   Target identification
    *   Target validation
    *   Assay development
    *   Hit identification
    *   Hit-to-Lead
    *   Lead identification
    *   Lead optimization
    *   Candidate selection & pre-formulation
*   **Pre-clinical Development**
    *   Pharmacology & ADME
    *   Toxicology
    *   Proof-of-concept & efficacy
    *   Phase 0 (microdosing)
    *   Formulation & delivery optimisation
    *   IND preparation
*   **Clinical Development**
    *   Study design & initiation
    *   Phase I
    *   Phase II
    *   Phase III
    *   Phase IV
*   **Regulatory Review & Approval**
    *   NDA/BLA submission
    *   FDA review & decision
    *   Reasons for failure
    *   Generics/ANDA
*   **Post-market & Lifecycle**
    *   Pharmacovigilance
    *   Additional indications & formulations
    *   Manufacturing scale-up & quality

Choose the input pipeline CSV:

```yaml
paths:
  pipeline_csv: data/Drug_Development_phase_segmentation_time_cost_citations.csv
```

For the cheaper first pass, keep:

```yaml
runtime:
  analysis_mode: landscape_scan
```

This mode is meant to map candidates quickly. It skips the expensive deep-dive operations: company enrichment, verification, funding/headcount/HQ extraction, fact-driven analysis, critical review, gap memo, and slide generation.

## Run Examples

Run the default configuration:

```shell
python main.py
```

Run a first-pass landscape scan with extra progress logs:

```shell
python main.py --mode landscape_scan --verbosity 1
```

Run a deep dive for selected subphases:

```shell
python main.py --mode deep_dive --deep-subphases "Pharmacovigilance,Toxicology" --verbosity 1
```

Or configure the same deep dive in `config.yml`:

```yaml
runtime:
  analysis_mode: deep_dive
  deep_dive_subphases:
    - Pharmacovigilance
    - Toxicology
```

Create a summary CSV from an existing report directory without running Tavily search:

```shell
python main.py --mode summary_only --report-dir reports/20260426_235802 --verbosity 1
```

This writes:

```text
reports/20260426_235802/competitor_summary.csv
```

The normal pipeline also writes `competitor_summary.csv` into each new run directory when:

```yaml
summary:
  enabled: true
```

## Outputs

Each run writes files under `reports/<run_id>/`. The most useful files are usually:

- `competitor_landscape_report.md`
- `competitor_summary.csv`
- `gap_memo.md` in `deep_dive` mode
- `presentation_outline.md` in `deep_dive` mode

## More Examples

See [docs/advanced_usage.md](docs/advanced_usage.md) for additional CLI examples, mode details, and summary-only options.

See [docs/agent_workflow.md](docs/agent_workflow.md) for the current agent orchestration workflow.
