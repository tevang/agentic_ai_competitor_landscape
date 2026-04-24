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
from lib.agents.user_company_intake_agent import UserCompanyIntakeAgent
from lib.agents.verification_agent import VerificationAgent
from lib.config import load_config
from lib.llm import LLM
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
    return parser.parse_args()


def print_dataframe_section(title: str, dataframe, empty_message: str) -> None:
    """Print a dataframe section to stdout, or a fallback message when the dataframe is empty."""

    print(f"\n\n# {title}\n")
    if dataframe.empty:
        print(empty_message)
    else:
        print(dataframe.to_markdown(index=False))


def main() -> None:
    """Load configuration, initialize services, run the workflow, and print the outputs."""

    load_dotenv()
    args = parse_args()
    config = load_config(args.config)

    steps = load_pipeline_csv(config.paths.pipeline_csv)
    seed_companies = load_seed_companies_csv(
        path=config.paths.seed_companies_csv,
        enabled=config.user_inputs.seed_companies_enabled,
        required=config.user_inputs.seed_companies_required,
    )

    llm = LLM(config.openai)
    web_search = WebSearchService(config)
    store = EvidenceStore(config.paths, config.rag)

    planner_agent = PlannerAgent(llm, config, store)
    research_agent = ResearchAgent(config, web_search, store)
    extraction_agent = ExtractionAgent(llm, config, store)
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

    print(f"Loaded {len(steps)} pipeline steps. Running {len(processed_steps)} step(s).")
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

    print("\n\n# FACT-DRIVEN ANALYST VIEW\n")
    print(results["fact_analysis"])

    print("\n\n# CRITICAL AGENT REVIEW\n")
    print(results["critical_review"])

    print("\n\n# GAP MEMO\n")
    print(results["gap_memo"])

    print("\n\n# PRESENTATION OUTLINE\n")
    print(results["slide_outline"])

    if results["report_paths"]:
        print("\n\n# WRITTEN REPORT FILES\n")
        for label, path in results["report_paths"].items():
            print(f"- {label}: {path}")


if __name__ == "__main__":
    main()