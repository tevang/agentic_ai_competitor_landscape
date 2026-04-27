# Advanced Usage

This page collects examples that are useful after the basic README flow is working.

## Modes

### `landscape_scan`

Use this for a cheaper first pass over many pipeline rows.

```yaml
runtime:
  analysis_mode: landscape_scan
```

Or from the CLI:

```shell
python main.py --mode landscape_scan --verbosity 1
```

Expected expensive operations skipped in `landscape_scan`:

- Company enrichment
- Verification
- Funding, headcount, headquarters, and related fact extraction
- Fact-driven analyst narrative
- Critical review
- Gap memo
- Slide generation

The scan still performs discovery and writes the standard run outputs that are available for that mode.

### `deep_dive`

Use this when you want stronger evidence and richer reports for a smaller set of phases or subphases.

```yaml
runtime:
  analysis_mode: deep_dive
  deep_dive_subphases:
    - Pharmacovigilance
    - Toxicology
```

Equivalent CLI:

```shell
python main.py --mode deep_dive --deep-subphases "Pharmacovigilance,Toxicology" --verbosity 1
```

You can also filter by phase:

```shell
python main.py --mode deep_dive --deep-phases "Clinical Development,Post-market & Lifecycle"
```

When both phase and subphase filters are supplied, a row must match both filters.

### `summary_only`

Use this when you already have a report directory and only want to create or recreate `competitor_summary.csv`.

```shell
python main.py --mode summary_only --report-dir reports/20260426_235802 --verbosity 1
```

This mode does not instantiate Tavily search. By default, it writes:

```text
reports/20260426_235802/competitor_summary.csv
```

You can choose an explicit output path:

```shell
python main.py \
  --mode summary_only \
  --report-dir reports/20260426_235802 \
  --summary-output reports/20260426_235802/custom_summary.csv
```

## Summary Settings

The full pipeline writes `competitor_summary.csv` into the new run directory when summary generation is enabled:

```yaml
summary:
  enabled: true
```

For deterministic table extraction without an LLM summary pass:

```yaml
summary:
  enabled: true
  use_llm: false
```

For standalone summary mode from config instead of CLI:

```yaml
runtime:
  analysis_mode: summary_only

summary:
  standalone_report_dir: reports/20260426_235802
```

Then run:

```shell
python main.py
```

## Useful CLI Overrides

Use a non-default config file:

```shell
python main.py --config config.local.yml
```

Run a quiet default command:

```shell
python main.py --verbosity 0
```

Run with rough progress logs for API calls and search/fetch activity:

```shell
python main.py --verbosity 1
```

## Practical Workflow

A simple cost-conscious workflow is:

1. Run `landscape_scan` across the pipeline.
2. Open the newest `reports/<run_id>/competitor_landscape_report.md`.
3. Pick the subphases that deserve more evidence.
4. Run `deep_dive` only for those subphases.
5. Use `summary_only` if you need to regenerate the CSV from an existing report.
