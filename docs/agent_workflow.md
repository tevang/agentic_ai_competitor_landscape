# Agent Workflow

This document describes how the agents are currently orchestrated by `main.py` and `lib/orchestrator.py`.

The workflow has three runtime modes:

- `landscape_scan`: cheaper first-pass discovery and lightweight reporting.
- `deep_dive`: full enrichment, verification, narrative analysis, and presentation outputs.
- `summary_only`: standalone summary CSV generation from an existing report directory.

## End-to-End Flow

```mermaid
flowchart TD
    A[CLI: python main.py] --> B[Load config.yml and CLI overrides]
    B --> C{runtime.analysis_mode}

    C -->|summary_only| S1[Build SummaryAgent only]
    S1 --> S2[Read existing report directory]
    S2 --> S3[Write competitor_summary.csv]
    S3 --> Z[Print output path]

    C -->|landscape_scan or deep_dive| D[Load pipeline CSV]
    D --> E[Filter steps for deep_dive phase/subphase selectors]
    E --> F[Load optional seed companies]
    F --> G[Instantiate services: LLM, WebSearchService, EvidenceStore]
    G --> H[Instantiate agents and orchestrator]
    H --> I[Run CompetitiveLandscapeOrchestrator]

    I --> J[Prepare seed company requests]
    J --> K{Preload seed profiles?}
    K -->|Only deep_dive when enabled| K1[EnrichmentAgent enriches seed companies]
    K -->|No| L[Process each pipeline step]
    K1 --> L

    L --> M[Build records and profile cache]
    M --> N[Download logos for reportable profiles]
    N --> O[Build profile, matrix, and gap dataframes]
    O --> P{Generate narrative agents?}

    P -->|deep_dive, or scan narratives enabled| P1[FactDrivenAnalystAgent writes analysis]
    P1 --> P2[CriticalAgent challenges findings]
    P2 --> P3[PresentationAgent writes gap memo]
    P3 --> P4[PresentationAgent writes slide outline]

    P -->|landscape_scan default| Q1[Build deterministic scan summary]
    P4 --> R{summary.enabled?}
    Q1 --> R

    R -->|Yes| R1[SummaryAgent writes competitor_summary.csv]
    R -->|No| T[Skip summary CSV]
    R1 --> U[ReportWriter writes markdown reports]
    T --> U
    U --> V[Return and print report paths]
```

## Per-Step Agent Flow

Each pipeline row is processed independently. The records from all rows are merged before reporting.

```mermaid
flowchart TD
    A[PipelineStep] --> B[TaxonomyEnforcementAgent maps step to controlled taxonomy]
    A --> C[Build deterministic step search terms]
    A --> D[PlannerAgent builds query plan]
    D --> E[ResearchAgent collects step evidence]
    E --> F[ExtractionAgent extracts candidate companies]

    F --> G{Too few candidates and refinement enabled?}
    G -->|Yes| H[PlannerAgent creates refinement queries]
    H --> I[ResearchAgent collects more evidence]
    I --> J[ExtractionAgent re-extracts candidates]
    G -->|No| K[Use extracted candidates]
    J --> K

    K --> L{Mode}

    L -->|landscape_scan| LS1[Filter out publisher-only and disallowed posture candidates]
    LS1 --> LS2[Create minimal CompanyProfile from candidate]
    LS2 --> LS3[TaxonomyEnforcementAgent applies step taxonomy]
    LS3 --> LS4[Write unverified first-pass record]

    L -->|deep_dive| DD1[Skip publisher-only candidates]
    DD1 --> DD2[Build CompanyResearchRequest]
    DD2 --> DD3{Profile already cached?}
    DD3 -->|No| DD4[EnrichmentAgent researches and enriches company]
    DD3 -->|Yes| DD5[Reuse cached CompanyProfile]
    DD4 --> DD6[VerificationAgent verifies company-step fit]
    DD5 --> DD6
    DD6 --> DD7{Include verdict?}
    DD7 -->|Yes| DD8[TaxonomyEnforcementAgent applies step taxonomy]
    DD8 --> DD9[Write verified competitor record]
    DD7 -->|No| DD10[Drop candidate for this step]
```

## Agent Responsibilities

| Agent | Role in the workflow |
| --- | --- |
| `UserCompanyIntakeAgent` | Converts optional seed-company CSV rows into research requests and step-specific seed candidates. |
| `TaxonomyEnforcementAgent` | Maps pipeline steps into the controlled taxonomy and applies that taxonomy to company profiles. |
| `PlannerAgent` | Builds the initial query plan for a pipeline step and creates refinement queries when too few candidates are found. |
| `ResearchAgent` | Executes web search and evidence collection through `WebSearchService` and the evidence store. |
| `ExtractionAgent` | Reads collected evidence and extracts candidate companies, products, posture labels, confidence, and source URLs. |
| `EnrichmentAgent` | In `deep_dive`, researches one company in detail and builds a richer `CompanyProfile`. |
| `VerificationAgent` | In `deep_dive`, decides whether a company actually belongs in the current pipeline step. |
| `FactDrivenAnalystAgent` | Produces evidence-led narrative analysis from the matrix, profile, and gap tables. |
| `CriticalAgent` | Reviews the analysis for weak assumptions, missing companies, and evidence gaps. |
| `PresentationAgent` | Generates the gap memo and presentation outline from the structured data and narrative review. |
| `SummaryAgent` | Writes `competitor_summary.csv` after a pipeline run or from an existing report directory in `summary_only` mode. |

## Mode Differences

| Step | `landscape_scan` | `deep_dive` | `summary_only` |
| --- | --- | --- | --- |
| Load pipeline CSV | Yes | Yes | No |
| Tavily/WebSearchService | Yes | Yes | No |
| Candidate extraction | Yes | Yes | No |
| Company enrichment | No | Yes | No |
| Company-step verification | No | Yes | No |
| Funding/headcount/HQ extraction | No | Yes | No |
| Fact-driven analysis | No by default | Yes | No |
| Critical review | No by default | Yes | No |
| Gap memo and slide outline | No by default | Yes | No |
| `competitor_summary.csv` | Yes when `summary.enabled` | Yes when `summary.enabled` | Yes |

## Output Assembly

After all steps finish, the orchestrator:

1. Selects reportable profiles from the profile cache.
2. Downloads or reuses company logos through `LogoDownloader`.
3. Builds `profile_df`, `matrix_df`, and `gap_df`.
4. Runs narrative agents only when the mode calls for them.
5. Runs `SummaryAgent` when `summary.enabled` is true.
6. Writes markdown reports through `ReportWriter`.
7. Returns the dataframes, narrative text, summary path, run context, and report paths to `main.py`.

