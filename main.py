"""Entry point for the biotech agentic competitive-intelligence pipeline."""

import argparse

from dotenv import load_dotenv

from lib.agents.critical_agent import CriticalAgent
from lib.agents.enrichment_agent import EnrichmentAgent
from lib.agents.extraction_agent import ExtractionAgent
from lib.agents.fact_driven_analyst_agent import FactDrivenAnalystAgent
from lib.agents.planner_agent import PlannerAgent
from lib.agents.presentation_agent import PresentationAgent
from lib.agents.research_agent import ResearchAgent
from lib.agents.taxonomy_enforcement_agent import TaxonomyEnforcementAgent
from lib.agents.user_company_intake_agent import UserCompanyIntakeAgent
from lib.agents.verification_agent import VerificationAgent
from lib.config import AppConfig, load_config
from lib.llm import LLM
from lib.models import PipelineStep
from lib.orchestrator import CompetitiveLandscapeOrchestrator
from lib.retrieval.evidence_store import EvidenceStore
from lib.retrieval.web_search import WebSearchService
from lib.utils.io_utils import load_pipeline_csv, load_seed_companies_csv
from lib.utils.logo_downloader import LogoDownloader
from lib.utils.report_writer import ReportWriter


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the application entry point."""

    parser = argparse.ArgumentParser(description="Run the biotech AI competitor-landscape workflow.")
    parser.add_argument(
        "--config",
        default="config.yml",
        help="Path to the YAML configuration file.",
    )
    parser.add_argument(
        "--mode",
        choices=["landscape_scan", "deep_dive"],
        default=None,
        help="Override runtime.analysis_mode from config.yml.",
    )
    parser.add_argument(
        "--deep-subphases",
        default=None,
        help="Comma-separated subphase names to keep for deep_dive mode.",
    )
    parser.add_argument(
        "--deep-phases",
        default=None,
        help="Comma-separated phase names to keep for deep_dive mode.",
    )
    parser.add_argument(
        "--verbosity",
        type=int,
        choices=[0, 1],
        default=None,
        help="Override runtime.verbosity from config.yml.",
    )
    return parser.parse_args()


def apply_cli_overrides(config: AppConfig, args: argparse.Namespace) -> AppConfig:
    """Apply optional command-line overrides to the loaded configuration."""

    if args.mode:
        config.runtime.analysis_mode = args.mode

    if args.verbosity is not None:
        config.runtime.verbosity = args.verbosity

    if args.deep_subphases is not None:
        config.runtime.deep_dive_subphases = _parse_csv_arg(args.deep_subphases)

    if args.deep_phases is not None:
        config.runtime.deep_dive_phases = _parse_csv_arg(args.deep_phases)

    return config


def filter_steps_for_runtime(steps: list[PipelineStep], config: AppConfig) -> list[PipelineStep]:
    """Filter pipeline steps for deep_dive mode when the user supplied narrower phase/subphase lists."""

    if config.runtime.analysis_mode != "deep_dive":
        return steps

    phase_filter = {value.strip().lower() for value in config.runtime.deep_dive_phases if value.strip()}
    subphase_filter = {value.strip().lower() for value in config.runtime.deep_dive_subphases if value.strip()}

    if not phase_filter and not subphase_filter:
        return steps

    filtered: list[PipelineStep] = []
    for step in steps:
        phase_matches = not phase_filter or step.phase.strip().lower() in phase_filter
        subphase_matches = not subphase_filter or step.step.strip().lower() in subphase_filter
        if phase_matches and subphase_matches:
            filtered.append(step)

    return filtered


def print_dataframe_section(title: str, dataframe, empty_message: str) -> None:
    """Print a dataframe section to stdout, or a fallback message when the dataframe is empty."""

    print(f"\n\n# {title}\n")
    if dataframe.empty:
        print(empty_message)
    else:
        print(dataframe.to_markdown(index=False))


def print_text_section(title: str, text: str) -> None:
    """Print a text section only when the content is non-empty."""

    clean = (text or "").strip()
    if clean:
        print(f"\n\n# {title}\n")
        print(clean)


def _parse_csv_arg(value: str) -> list[str]:
    """Parse a comma-separated CLI value into clean strings."""

    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def main() -> None:
    """Load configuration, initialize services, run the workflow, and print the outputs."""

    load_dotenv()
    args = parse_args()
    config = apply_cli_overrides(load_config(args.config), args)

    all_steps = load_pipeline_csv(config.paths.pipeline_csv)
    steps = filter_steps_for_runtime(all_steps, config)
    seed_companies = load_seed_companies_csv(
        path=config.paths.seed_companies_csv,
        enabled=config.user_inputs.seed_companies_enabled,
        required=config.user_inputs.seed_companies_required,
    )

    if config.runtime.verbosity >= 1:
        print(
            "[config] "
            f"analysis_mode={config.runtime.analysis_mode}, "
            f"search_profile={config.get_active_search_profile_name()}, "
            f"pipeline_rows_loaded={len(all_steps)}, "
            f"pipeline_rows_after_filter={len(steps)}"
        )

    llm = LLM(config.openai, verbosity=config.runtime.verbosity)
    web_search = WebSearchService(config)
    store = EvidenceStore(config.paths, config.rag)

    planner_agent = PlannerAgent(llm, config, store)
    research_agent = ResearchAgent(config, web_search, store)
    extraction_agent = ExtractionAgent(llm, config, store)
    taxonomy_enforcement_agent = TaxonomyEnforcementAgent(config, store)
    user_company_intake_agent = UserCompanyIntakeAgent(config)
    enrichment_agent = EnrichmentAgent(llm, config, research_agent, store)
    verification_agent = VerificationAgent(llm, config, store)
    fact_driven_analyst_agent = FactDrivenAnalystAgent(llm, config)
    critical_agent = CriticalAgent(llm, config)
    presentation_agent = PresentationAgent(llm, config)
    report_writer = ReportWriter(config)
    logo_downloader = LogoDownloader(config)

    orchestrator = CompetitiveLandscapeOrchestrator(
        config=config,
        planner_agent=planner_agent,
        research_agent=research_agent,
        extraction_agent=extraction_agent,
        taxonomy_enforcement_agent=taxonomy_enforcement_agent,
        enrichment_agent=enrichment_agent,
        verification_agent=verification_agent,
        presentation_agent=presentation_agent,
        user_company_intake_agent=user_company_intake_agent,
        fact_driven_analyst_agent=fact_driven_analyst_agent,
        critical_agent=critical_agent,
        report_writer=report_writer,
        logo_downloader=logo_downloader,
    )
    results = orchestrator.run(steps=steps, seed_companies=seed_companies)
    processed_steps = results["run_steps"]

    print(f"Loaded {len(all_steps)} pipeline steps. Running {len(processed_steps)} step(s).")
    print(f"Analysis mode: {config.runtime.analysis_mode}")

    print_dataframe_section(
        title="COMPETITOR COVERAGE MATRIX",
        dataframe=results["matrix_df"],
        empty_message="No records yet.",
    )
    print_dataframe_section(
        title="COMPANY PROFILES",
        dataframe=results["profile_df"],
        empty_message="No profiles yet.",
    )
    print_dataframe_section(
        title="GAP SCORES",
        dataframe=results["gap_df"],
        empty_message="No gaps yet.",
    )

    print_text_section("FACT-DRIVEN ANALYST VIEW", str(results.get("fact_analysis", "")))
    print_text_section("CRITICAL AGENT REVIEW", str(results.get("critical_review", "")))
    print_text_section("GAP MEMO", str(results.get("gap_memo", "")))
    print_text_section("PRESENTATION OUTLINE", str(results.get("slide_outline", "")))

    if results["report_paths"]:
        print("\n\n# WRITTEN REPORT FILES\n")
        for label, path in results["report_paths"].items():
            print(f"- {label}: {path}")


if __name__ == "__main__":
    main()