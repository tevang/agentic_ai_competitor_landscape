import os
import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI
from tavily import TavilyClient

from lib.utils import load_config, parse_pipeline_csv
from lib.llm_utils import LLM
from lib.evidence import EvidenceStore
from lib.agents.orchestrator import process_step
from lib.reporting import (
    build_profile_df, 
    build_matrix_df, 
    compute_gap_scores, 
    generate_gap_memo, 
    generate_slide_outline
)

def main() -> None:
    """
    Main entry point for the agentic competitor landscape analysis.
    Loads configuration, initializes agents, and processes the drug development pipeline.
    """
    # Load environment variables and configuration
    load_dotenv()
    config = load_config("config.yml")
    
    openai_key = os.getenv(config['openai']['api_key_env'])
    tavily_key = os.getenv(config['tavily']['api_key_env'])
    
    if not openai_key:
        raise RuntimeError(f"Missing {config['openai']['api_key_env']}")
    if not tavily_key:
        raise RuntimeError(f"Missing {config['tavily']['api_key_env']}")
        
    # Initialize clients
    openai_client = OpenAI(api_key=openai_key)
    tavily_client = TavilyClient(api_key=tavily_key)
    
    # Initialize shared services
    llm = LLM(client=openai_client, model=config['openai']['model'])
    store = EvidenceStore(path=config['storage']['chroma_path'])
    
    # Load and prepare pipeline steps
    steps = parse_pipeline_csv(config['data']['input_csv'])
    max_steps = config['execution']['max_steps']
    run_steps = steps[:max_steps] if max_steps > 0 else steps
    
    profile_cache = {}
    all_records = []
    
    print(f"Loaded {len(steps)} pipeline steps. Running {len(run_steps)} step(s).")
    
    # Process each step in the pipeline
    for step in run_steps:
        step_records = process_step(
            llm=llm, 
            tavily_client=tavily_client, 
            store=store, 
            profile_cache=profile_cache, 
            step=step,
            search_results_per_query=config['search']['results_per_query']
        )
        all_records.extend(step_records)
        
    # Build dataframes for reporting
    records_df = pd.DataFrame(all_records)
    profile_df = build_profile_df(profile_cache)
    matrix_df = build_matrix_df(records_df)
    gap_df = compute_gap_scores(records_df, run_steps)
    
    # Print reports
    print("\n\n# COMPETITOR COVERAGE MATRIX\n")
    if matrix_df.empty:
        print("No records yet.")
    else:
        print(matrix_df.to_markdown(index=False))

    print("\n\n# COMPANY PROFILES\n")
    if profile_df.empty:
        print("No profiles yet.")
    else:
        print(profile_df.to_markdown(index=False))

    print("\n\n# GAP SCORES\n")
    if gap_df.empty:
        print("No gap scores available.")
    else:
        print(gap_df.to_markdown(index=False))

    print("\n\n# STRATEGIC GAP MEMO\n")
    if not matrix_df.empty:
        gap_memo = generate_gap_memo(llm, matrix_df, profile_df, gap_df)
        print(gap_memo)
    else:
        print("Insufficient data for memo.")

    print("\n\n# PRESENTATION OUTLINE\n")
    if not gap_df.empty:
        slide_outline = generate_slide_outline(llm, matrix_df, profile_df, gap_df)
        print(slide_outline)
    else:
        print("Insufficient data for slide outline.")


if __name__ == "__main__":
    main()