# Interview Question Answers

This document gives interview-ready answers for questions that could come from the debugging guide and from the Senior AI Developer job description.

Use these answers as a learning scaffold. In the interview, keep answers shorter first, then expand when asked.

## 60-Second Project Explanation

**Question: Can you briefly explain this project?**

This project is an agentic AI competitive-intelligence pipeline for biotech and drug-development workflows. It takes pipeline subphases from a CSV, searches the web for relevant AI companies, stores evidence in a Chroma vector database, uses LLM agents to extract and enrich companies, verifies whether they belong to a specific workflow step, and writes markdown reports plus a structured summary CSV.

The key architecture is a multi-agent orchestration pattern. `main.py` loads configuration and wires services and agents. `CompetitiveLandscapeOrchestrator` controls the workflow. Each agent has a focused responsibility: planning searches, collecting evidence, extracting candidates, enriching company profiles, verifying fit, analyzing gaps, critiquing results, preparing presentation outputs, and summarizing the final report.

Implementation: `main.py` (lines 182-282), `lib/orchestrator.py` (lines 27-529)

The project demonstrates RAG because evidence is persisted in Chroma and later semantically retrieved during enrichment and verification to ground LLM decisions in collected source material.

## Architecture And Orchestration

### What does "agentic AI" mean in this project?

In this project, agentic AI means the task is decomposed into multiple specialized LLM-driven components, where each component performs a bounded step in a larger workflow. The agents do not act randomly or autonomously without control. They are orchestrated by deterministic Python code.

The orchestrator decides the order:

1. Plan search queries.
2. Collect web evidence.
3. Extract candidate companies.
4. Optionally enrich and verify them.
5. Build tables and reports.
6. Generate summaries and narratives.

So the "agentic" part is the specialized reasoning and decision-making inside each agent, while the overall workflow remains controlled and inspectable.

Implementation: `CompetitiveLandscapeOrchestrator.run()` in `lib/orchestrator.py` (lines 64-175)

### Why did you use multiple agents instead of one big prompt?

I used multiple agents because the problem naturally separates into different responsibilities. A search planner needs a different prompt and output schema from a verifier or a summary writer.

This gives several benefits:

- Easier debugging: I can inspect the input and output of each agent.
- Better prompts: each agent has a narrow role and clearer instructions.
- Better structured data: outputs are converted into Pydantic models.
- Better maintainability: changing verification logic does not require changing search planning.
- Better cost control: expensive agents can be skipped in `landscape_scan`.

The tradeoff is that orchestration becomes more complex, so the orchestrator must be carefully designed.

Implementation: `lib/agents/` (various classes)

### What is the role of `main.py`?

`main.py` is the entry point. It does not contain most business logic. Its responsibilities are:

- Parse CLI arguments.
- Load `.env` and `config.yml`.
- Apply CLI overrides.
- Load pipeline CSV and seed companies.
- Instantiate core services: `LLM`, `WebSearchService`, and `EvidenceStore`.
- Instantiate all agents.
- Create the `CompetitiveLandscapeOrchestrator`.
- Run the orchestrator and print outputs.

In interview terms, `main.py` is the composition root.

Implementation: `main.py:main()` (lines 182-282)

### What is the role of `CompetitiveLandscapeOrchestrator`?

The orchestrator owns the control flow. It decides which agents run, in which order, and what data is passed between them.

At a high level, it:

- Iterates through pipeline steps.
- Calls query planning, research, extraction, enrichment, and verification.
- Applies mode-specific logic for `landscape_scan` versus `deep_dive`.
- Builds final dataframes.
- Runs narrative and summary agents.
- Writes reports.

The agents own narrow operations; the orchestrator owns the workflow.

Implementation: `lib/orchestrator.py:CompetitiveLandscapeOrchestrator` (lines 27-529)

### What is the difference between deterministic code and agent behavior here?

Deterministic code is regular Python logic: loading CSVs, filtering steps, building dictionaries, grouping dataframes, checking configuration flags, writing files, and applying cache rules.

Agent behavior is LLM-driven: generating search queries, extracting candidates from text, enriching company profiles, verifying whether a company fits a step, and writing narrative summaries.

The design tries to wrap non-deterministic LLM behavior in deterministic boundaries by using Pydantic models, JSON parsing, caches, and explicit workflow control.

Implementation: `lib/orchestrator.py:process_step()` (lines 177-290)

## Runtime Modes

### What are the three runtime modes?

The project has three modes:

- `landscape_scan`: cheaper first-pass discovery.
- `deep_dive`: richer search, enrichment, verification, and reporting.
- `summary_only`: create a summary CSV from an existing report directory.

`landscape_scan` is for broad exploration. `deep_dive` is for deeper evidence on selected subphases. `summary_only` is for post-processing existing results.

Implementation: `lib/orchestrator.py:run()` (lines 64-175), `main.py:_run_summary_only()` (lines 153-179)

### How does `landscape_scan` reduce cost?

`landscape_scan` reduces cost by skipping expensive operations:

- LLM query planning is skipped by default.
- Company enrichment is skipped.
- Per-company verification is skipped.
- Funding, headcount, founding year, and headquarters extraction are skipped.
- Fact-driven analysis, critical review, gap memo, and slide generation are skipped by default.
- Full page fetching is usually disabled by setting `step_fetch_text_for_top_n_results` to `0` in the scan profile.

It still searches the web and extracts candidates, but it produces minimal unverified profiles.

Implementation: `lib/orchestrator.py:_process_landscape_scan_candidates()` (lines 292-341)

### What is the main limitation of `landscape_scan`?

The main limitation is that it is not deeply verified. It can find plausible companies, but because it skips enrichment and verification, some candidates may be false positives, incomplete, or only loosely relevant.

That is why records are marked as `landscape_scan_unverified`.

### What does `deep_dive` add?

`deep_dive` adds:

- LLM-assisted query planning.
- Broader and deeper Tavily search.
- Full page fetching for top results.
- Company-level evidence collection.
- RAG retrieval from Chroma.
- Company profile enrichment.
- Step-specific verification.
- Narrative analysis.
- Critical review.
- Gap memo and slide outline.

It is slower and more expensive, but produces stronger evidence and richer outputs.

Implementation: `lib/orchestrator.py:process_step()` (lines 177-290)

### What does `summary_only` do?

`summary_only` reads an existing report directory and creates `competitor_summary.csv`. It does not instantiate Tavily and does not run the full web-search pipeline.

This is useful when reports already exist and only the clean CSV summary needs to be regenerated.

Implementation: `main.py:_run_summary_only()` (lines 153-179)

## Data Structures

### What is a `PipelineStep`?

`PipelineStep` represents one row from the input pipeline CSV.

It contains:

- `phase`
- `step`
- `activities`

Example: phase could be `Post-market & Lifecycle`, step could be `Pharmacovigilance`, and activities could describe adverse-event reporting, signal detection, MedDRA coding, and related workflows.

This is the starting object for the pipeline.

Implementation: `PipelineStep` in `lib/models.py` (lines 6-12)

### What is an `EvidenceDoc`?

`EvidenceDoc` is a normalized evidence record. It represents a search result or fetched page.

It contains:

- phase and step context
- search query
- URL
- title
- snippet
- extracted page text
- source type
- extraction status
- quality score

This is the main unit stored in Chroma and passed into extraction prompts.

Implementation: `EvidenceDoc` in `lib/models.py` (lines 24-41)

### What is a `Candidate`?

`Candidate` is a possible competitor extracted from evidence.

It is not yet a fully trusted company profile. It contains:

- company name
- owning company name
- product or solution
- website if visible
- rationale
- evidence URLs
- confidence
- evidence role
- agentic posture

A `Candidate` means: "This company/product appears possibly relevant based on the current evidence."

Implementation: `Candidate` in `lib/models.py` (lines 43-63)

### What is a `CompanyResearchRequest`?

`CompanyResearchRequest` is the input to company enrichment.

It tells the enrichment stage:

- which company to research
- which phase and step it came from
- what product was discovered
- what rationale and evidence URLs came from extraction
- what query hints to use
- what known fields came from user seed data
- what preferred domains should be searched

It bridges candidate extraction and deeper company research.

Implementation: `CompanyResearchRequest` in `lib/models.py` (lines 123-139)

### What is a `CompanyProfile`?

`CompanyProfile` is the normalized enriched company representation.

It contains:

- company name
- vertical or horizontal classification
- funding
- funding rounds
- employees
- founded year
- headquarters
- website
- specialization
- products or solutions
- evidence URLs
- confidence
- taxonomy labels
- logo path

In `landscape_scan`, the profile is minimal. In `deep_dive`, it is enriched with more facts.

Implementation: `CompanyProfile` in `lib/models.py` (lines 74-96)

### What is a `VerificationResult`?

`VerificationResult` is the verifier's decision about whether a company belongs in a specific pipeline step.

It contains:

- `include`: true or false
- `confidence`
- `reason`

This is important because a company can be real and AI-related but still not relevant to the exact subphase being analyzed.

Implementation: `VerificationResult` in `lib/models.py` (lines 98-104)

### What is the difference between `Candidate`, `CompanyResearchRequest`, and `CompanyProfile`?

A `Candidate` is a possible company found during extraction.

A `CompanyResearchRequest` is a structured request to research that candidate more deeply.

A `CompanyProfile` is the enriched output after research and LLM normalization.

The flow is:

```text
EvidenceDoc -> Candidate -> CompanyResearchRequest -> CompanyProfile -> VerificationResult -> record
```

Implementation: `lib/orchestrator.py:process_step()` (lines 177-290)

### Why use Pydantic models?

Pydantic models make data contracts explicit. This is especially important with LLMs because LLM output can be inconsistent.

The project asks the LLM for JSON, parses it, and then validates it into models like `Candidate`, `CompanyProfile`, and `VerificationResult`.

This gives:

- clearer schemas
- runtime validation
- easier debugging in PyCharm
- more reliable downstream code
- better documentation of data shape

Implementation: `lib/models.py` (lines 1-139)

## Query Planning

### What does the `PlannerAgent` do?

The `PlannerAgent` creates search queries for a pipeline step.

In `landscape_scan`, it usually skips LLM query planning and uses deterministic query templates to reduce cost.

In `deep_dive`, it can ask the LLM to generate search queries, then merges those with deterministic queries.

The output is a list of query strings passed to the `ResearchAgent`.

Implementation: `lib/agents/planner_agent.py:PlannerAgent` (lines 12-127)

### Why combine deterministic and LLM-generated queries?

Deterministic queries provide consistency and cost control. They ensure the system always searches for obvious terms derived from the pipeline step.

LLM-generated queries add flexibility. The LLM can infer useful domain terms, synonyms, acronyms, and vendor-search patterns.

Combining both gives a practical balance between reliability and creativity.

Implementation: `PlannerAgent.build_query_plan()` in `lib/agents/planner_agent.py` (lines 22-64)

### Why save query plans?

Saving query plans supports caching and reproducibility. If the same phase and step are run again, the system can reuse or inspect previous query plans.

It also makes debugging easier because the generated search strategy is persisted.

Implementation: `EvidenceStore.save_query_plan()` in `lib/retrieval/evidence_store.py` (lines 146-156)

## Web Search And Evidence Collection

### What does the `ResearchAgent` do?

The `ResearchAgent` collects evidence. It:

- checks cached evidence from Chroma
- runs Tavily searches
- optionally fetches full page text
- converts search results and page text into `EvidenceDoc` objects
- deduplicates evidence
- saves evidence to the vector store

It is the bridge between external web data and the LLM extraction pipeline.

Implementation: `lib/agents/research_agent.py:ResearchAgent` (lines 10-325)

### How does Tavily fit into the project?

Tavily is used as the web search API. The project builds a search payload from config, sends the query to Tavily, and receives search results with URLs, titles, and snippets.

Those results are then normalized into `EvidenceDoc` objects. In deep modes, top results may also be fetched for full text.

Implementation: `lib/retrieval/web_search.py:WebSearchService` (lines 18-218)

### What is in the Tavily payload?

The Tavily payload includes:

- query
- topic
- search depth
- max results
- domain filters
- time range if configured
- options for images, raw content, and usage

The payload is mode-dependent because `landscape_scan` uses the cheaper `scan` profile, while `deep_dive` uses the `deep` profile.

Implementation: `WebSearchService._build_search_payload()` in `lib/retrieval/web_search.py` (lines 147-189)

### Why fetch web pages if Tavily already returns snippets?

Snippets are useful for a cheap first pass, but they are often too short for reliable enrichment and verification.

Full page text gives richer evidence:

- product descriptions
- company claims
- funding or headcount facts
- official positioning
- details about AI/automation capabilities

That is why deep dive fetches top pages and scan mode often does not.

Implementation: `WebSearchService.fetch_page()` in `lib/retrieval/web_search.py` (lines 87-140)

### What is `trafilatura` used for?

`trafilatura` fetches and extracts clean text from web pages. It removes much of the HTML noise and returns readable article or page content.

The extracted text is then assessed for quality before entering prompts or Chroma.

Implementation: `lib/retrieval/page_quality.py` (lines 1-215)

### What is browser rendering used for?

Browser rendering is a fallback for normal JavaScript-rendered pages where simple extraction returns empty or low-content text.

It uses Playwright when available. It does not bypass CAPTCHA, Cloudflare challenges, or anti-bot systems. It only renders pages that can normally load in a browser.

Implementation: `lib/retrieval/browser_render.py:BrowserRenderService` (lines 8-97)

### What happens if a page is blocked or low quality?

The retrieval guard checks for:

- CAPTCHA
- anti-bot challenge pages
- access denied responses
- cookie or consent walls
- JavaScript placeholders
- low-content extraction

If the page is unsafe or unusable, the system stores a `PageFetchResult` with empty text, status, blocked reason, render mode, and quality score.

This protects the pipeline from feeding bad or misleading content into LLM prompts.

Implementation: `lib/retrieval/page_quality.py:assess_extracted_content()` (lines 73-172)

## RAG And Vector Database

### What is RAG in this project?

RAG means retrieval-augmented generation. Instead of asking the LLM to answer from memory, the system first retrieves relevant evidence from Chroma and includes that evidence in the prompt.

In this project, RAG is used mainly during:

- company enrichment
- company-step verification

The LLM is asked to reason over retrieved evidence, not just generate unsupported claims.

Implementation: `EvidenceStore.query()` in `lib/retrieval/evidence_store.py` (lines 73-114)

### Where does the vector database enter the workflow?

The vector database enters through `EvidenceStore`.

When evidence is collected, it is saved into Chroma. Later, enrichment and verification call `store.query()` with a semantic query. Chroma returns relevant stored evidence, which is converted into prompt context.

So the vector DB supports both persistence and semantic retrieval.

Implementation: `lib/retrieval/evidence_store.py:EvidenceStore` (lines 14-404)

### What does Chroma store?

The project uses multiple Chroma collections:

- evidence documents
- company profiles
- query plans
- extracted candidates
- verification decisions

The most important RAG collection is the evidence collection, because it stores text that can be semantically retrieved.

Implementation: `EvidenceStore.add_docs()` in `lib/retrieval/evidence_store.py` (lines 31-71)

### What is stored as document text versus metadata?

Document text is the actual content used for semantic search, such as page text or snippets.

Metadata stores structured fields used for filtering and traceability:

- phase
- step
- activity signature
- query
- URL
- title
- company name
- source type
- extraction status
- quality score

This allows both vector similarity search and deterministic lookup.

Implementation: `lib/retrieval/evidence_store.py:EvidenceStore` (lines 14-404)

### What is retrieved during enrichment?

During enrichment, the system retrieves evidence related to:

- company name
- product or solution
- phase and step
- funding
- employees
- founded year
- headquarters
- AI, automation, agentic, product, platform terms

This helps the `EnrichmentAgent` build a richer `CompanyProfile`.

Implementation: `EnrichmentAgent.enrich_company()` in `lib/agents/enrichment_agent.py` (lines 30-147)

### What is retrieved during verification?

During verification, the system retrieves evidence related to:

- company name
- product or solution
- phase and step
- activities
- AI, automation, agentic, platform, product terms

The goal is not general company enrichment. The goal is to decide whether the company truly fits the exact pipeline subphase.

Implementation: `VerificationAgent.verify_company_for_step()` in `lib/agents/verification_agent.py` (lines 20-127)

### Why use both cached URL evidence and vector retrieval?

Cached URL evidence gives direct evidence from known URLs, especially URLs discovered during extraction.

Vector retrieval finds semantically related evidence from previous searches, even if the URL was not directly attached to the current candidate.

Together, they improve grounding.

Implementation: `VerificationAgent._candidate_url_docs()` in `lib/agents/verification_agent.py` (lines 129-160)

### Is Chroma being used only as a vector database?

No. It is used as both a vector retrieval system and a persistence/cache layer.

Vector retrieval is used through semantic queries. Cache-like behavior is used when fetching stored profiles, candidates, query plans, URL evidence, and verification decisions by metadata.

Implementation: `lib/retrieval/evidence_store.py` (lines 14-404)

## LLM Integration And Prompting

### How are LLM calls centralized?

All LLM calls go through the `LLM` wrapper.

The wrapper:

- reads the OpenAI API key from the environment
- calls the configured model
- applies retry behavior with `tenacity`
- logs rough token estimates when verbosity is enabled
- supports plain text and JSON prompts

This keeps LLM integration consistent across agents.

Implementation: `lib/llm.py:LLM` (lines 14-87)

### What does `ask_json()` do?

`ask_json()` sends a prompt to the LLM with an extra instruction to return valid JSON only. It then extracts a JSON blob from the response and parses it with `json.loads()`.

The parsed data is then validated by Pydantic models in the calling agent.

Implementation: `LLM.ask_json()` in `lib/llm.py` (lines 82-87)

### How are LLM outputs validated?

LLM outputs are validated in two steps:

1. `ask_json()` parses the response into a Python dictionary.
2. The calling agent converts dictionary items into Pydantic models.

For example:

- extracted rows become `Candidate`
- enriched profiles become `CompanyProfile`
- verification decisions become `VerificationResult`

Invalid items are skipped or cause the relevant operation to fail depending on the agent.

Implementation: `lib/agents/` (various classes using `ask_json`)

### Why ask for JSON instead of prose?

JSON is easier for software to consume. It allows downstream code to validate fields, build dataframes, cache results, and make deterministic decisions.

Prose is useful for final reports, but structured JSON is better for intermediate pipeline stages.

Implementation: `LLM.ask_json()` in `lib/llm.py` (lines 82-87)

### What is prompt engineering in this project?

Prompt engineering appears in each agent's role-specific prompt.

Examples:

- Planner prompt asks for search queries.
- Extraction prompt asks for candidate companies with product ownership and source-vs-subject rules.
- Enrichment prompt asks for company facts and profile fields.
- Verification prompt asks for an include/exclude decision.
- Summary prompt asks for a CSV-ready table.

Each prompt defines task, context, rules, and required output schema.

Implementation: `lib/agents/` (various classes)

### What is the source-vs-subject problem?

The source-vs-subject problem happens when an article publisher writes about another company's product. A naive extractor might incorrectly return the publisher as the competitor.

The extraction prompt explicitly says to extract the company that owns the product or platform, not merely the article publisher.

Example: if an article discusses Veeva Vault Safety, the candidate should be Veeva Systems, not the blog or publisher.

Implementation: `ExtractionAgent` prompt in `lib/agents/extraction_agent.py` (lines 90-183)

## Candidate Extraction

### What does the `ExtractionAgent` do?

The `ExtractionAgent` reads evidence documents and asks the LLM to extract candidate competitor companies.

It:

- ranks evidence documents
- chunks them into prompt-sized batches
- builds extraction context
- calls the LLM
- validates candidates
- filters publisher-only entries
- fuzzy-deduplicates candidates
- saves candidates to Chroma

Implementation: `lib/agents/extraction_agent.py:ExtractionAgent` (lines 17-207)

### Why rank and chunk evidence before extraction?

LLMs have context limits and cost constraints. Ranking chooses the most useful evidence first. Chunking keeps each prompt manageable.

This is a standard RAG/prompting pattern: retrieve or rank context, fit it into a bounded prompt, and process it in batches.

Implementation: `ExtractionAgent.extract_candidates()` in `lib/agents/extraction_agent.py` (lines 27-88)

### What fields does the extractor produce?

The extractor produces:

- company name
- owning company name
- product or solution
- website
- agentic posture
- evidence role
- rationale
- vertical or horizontal guess
- confidence
- evidence URLs

This gives enough structure for either a cheap scan profile or a deeper enrichment request.

Implementation: `Candidate` model in `lib/models.py` (lines 43-63)

### Why fuzzy-deduplicate candidates?

Search evidence can mention the same company in slightly different forms, such as "Veeva", "Veeva Systems", and "Veeva Vault".

Fuzzy deduplication reduces duplicates before enrichment or reporting.

Implementation: `ExtractionAgent._extract_from_batch()` (lines 90-183)

### What is `evidence_role`?

`evidence_role` describes how the evidence relates to the company:

- `target_vendor`: the company appears to sell or own the relevant product.
- `publisher_only`: the company only published content.
- `customer`: the company is a customer or case-study subject.
- `partner`: the company appears as a partner.
- `unclear`: role is not clear.

This helps filter false positives.

Implementation: `ExtractionAgent._filter_candidates()` in `lib/agents/extraction_agent.py` (lines 185-207)

### What is `explicit_agentic_posture`?

It labels how strongly the evidence supports agentic or AI capability:

- `explicit`: AI agents, agentic AI, autonomous workflows, copilots, or similar language.
- `adjacent`: AI, ML, NLP, GenAI, cognitive automation, or workflow automation, but not clearly agentic.
- `unclear`: not enough AI or automation evidence.

In landscape scan, only configured posture labels are kept.

Implementation: `ExtractionAgent._filter_candidates()` (lines 185-207)

## Enrichment And Verification

### What does the `EnrichmentAgent` do?

The `EnrichmentAgent` builds a richer `CompanyProfile`.

It collects company-level evidence, retrieves related evidence from Chroma, builds prompt context, and asks the LLM to fill fields such as:

- funding
- funding rounds
- employees
- founded year
- headquarters
- website
- specialization
- products or solutions
- agentic posture

Implementation: `lib/agents/enrichment_agent.py:EnrichmentAgent` (lines 13-221)

### Why is enrichment skipped in `landscape_scan`?

Enrichment is expensive because it can require company-specific searches, page fetches, RAG retrieval, and LLM calls for every candidate.

Skipping it allows landscape scan to map the landscape faster and cheaper.

Implementation: `lib/orchestrator.py:_process_landscape_scan_candidates()` (lines 292-341)

### What does the `VerificationAgent` do?

The `VerificationAgent` decides whether an enriched company profile actually belongs in the current pipeline step.

It uses:

- the company profile
- candidate rationale
- candidate evidence URLs
- RAG-retrieved evidence
- controlled taxonomy target
- pipeline step activities

It returns a `VerificationResult` with include/exclude, confidence, and reason.

Implementation: `VerificationAgent.verify_company_for_step()` in `lib/agents/verification_agent.py` (lines 20-127)

### Why is verification needed after enrichment?

Enrichment answers: "What is this company?"

Verification answers: "Does this company truly belong in this exact subphase?"

A company can be AI-related and still not be relevant to the current workflow step. Verification reduces false positives.

Implementation: `lib/agents/verification_agent.py` (lines 10-160)

### How does taxonomy enforcement work?

The `TaxonomyEnforcementAgent` maps each pipeline step to a controlled taxonomy assignment. It then applies that taxonomy to included company profiles.

This ensures reports use consistent taxonomy labels instead of arbitrary LLM-generated categories.

Implementation: `lib/agents/taxonomy_enforcement_agent.py:TaxonomyEnforcementAgent` (lines 10-50)

### Why use controlled taxonomy?

Controlled taxonomy improves consistency, comparability, and reporting quality.

Without it, the LLM might use slightly different labels for similar concepts, making analysis harder.

Implementation: `TaxonomyEnforcementAgent.apply_step_taxonomy()` in `lib/agents/taxonomy_enforcement_agent.py` (lines 30-50)

## Analytics, Scoring, And Reports

### What happens after all steps are processed?

After all steps are processed, the orchestrator:

1. Converts records into `records_df`.
2. Selects reportable profiles.
3. Downloads or reuses logos.
4. Builds `profile_df`.
5. Builds `matrix_df`.
6. Computes `gap_df`.
7. Runs narrative agents if enabled.
8. Runs the summary agent if enabled.
9. Writes markdown reports.

Implementation: `CompetitiveLandscapeOrchestrator.run()` in `lib/orchestrator.py` (lines 64-175)

### What is `records_df`?

`records_df` is the normalized table of included step-company links.

Each row represents one company/product included for one pipeline step.

It includes fields like:

- phase
- step
- company
- product or solution
- taxonomy labels
- confidence
- reason
- verification mode

Implementation: `lib/orchestrator.py:_build_record()` (lines 366-399)

### What is `profile_df`?

`profile_df` is the company-level table. It is built from `CompanyProfile` objects.

In scan mode, it contains minimal profile fields. In deep dive, it contains richer facts such as funding, employees, founded year, headquarters, presence, and specialization.

Implementation: `build_profile_df()` in `lib/analytics/scoring.py` (lines 26-94)

### What is `matrix_df`?

`matrix_df` is the coverage matrix. It groups competitors by phase and step.

It answers: "Which companies are active in each pipeline subphase?"

Implementation: `build_matrix_df()` in `lib/analytics/scoring.py` (lines 9-23)

### What is `gap_df`?

`gap_df` contains heuristic saturation and whitespace scores per pipeline step.

It uses:

- competitor count
- explicit agentic count
- vertical company count
- configured pain weights
- regulatory tailwind

It is not a machine learning model. It is a transparent heuristic scoring layer.

Implementation: `compute_gap_scores()` in `lib/analytics/scoring.py` (lines 97-144)

### How is whitespace score calculated conceptually?

The system estimates saturation based on the number and type of competitors. Then it combines that with a configured pain weight and regulatory tailwind.

High whitespace means the step appears important or painful but not crowded with many strong competitors.

This is a heuristic to guide analysis, not a statistically validated market model.

Implementation: `lib/analytics/scoring.py` (lines 1-144)

### What does the `ReportWriter` do?

`ReportWriter` creates the run directory and writes markdown outputs.

It is mode-aware:

- `landscape_scan` writes a compact first-pass report.
- `deep_dive` writes richer reports including analysis, critical review, gap memo, and slide outline.

Implementation: `lib/utils/report_writer.py:ReportWriter` (lines 13-423)

### What does the `SummaryAgent` do?

The `SummaryAgent` creates `competitor_summary.csv`.

It can summarize current pipeline outputs or read an existing report directory in `summary_only` mode.

It can use the LLM or deterministic fallback rows from the profile table.

Implementation: `lib/agents/summary_agent.py:SummaryAgent` (lines 27-509)

## Evaluation And Quality

### How would you evaluate extraction quality?

I would create a labeled evaluation set of pipeline steps with expected companies, products, and relevance labels.

Then I would measure:

- precision: how many extracted companies are correct
- recall: how many known relevant companies were found
- F1 score
- duplicate rate
- false-positive categories
- product-owner correctness
- evidence citation quality

I would also manually review borderline cases and use regression tests to check that prompt changes improve results rather than just changing them.

### How would you evaluate enrichment quality?

I would compare enriched facts against trusted sources or a manually curated dataset.

Metrics could include:

- field completeness
- field accuracy
- hallucination rate
- source support rate
- confidence calibration
- freshness of facts

For sensitive enterprise use, I would require every important factual field to be traceable to source evidence.

### How would you evaluate verification quality?

I would create labeled company-step pairs with include/exclude ground truth.

Metrics:

- precision and recall for inclusion decisions
- false-positive rate
- false-negative rate
- confidence calibration
- reason quality
- consistency across repeated runs

I would pay special attention to false positives because including irrelevant companies can damage trust.

### How would you evaluate the RAG pipeline?

I would evaluate RAG in stages:

- retrieval recall: does Chroma retrieve relevant evidence?
- retrieval precision: are retrieved docs useful or noisy?
- context quality: does the prompt include enough source material?
- answer faithfulness: does the LLM stay grounded in retrieved evidence?
- end-to-end task quality: does the final profile or verification improve?

This separates retrieval problems from generation problems.

### How would you reduce hallucinations?

I would:

- require structured JSON outputs
- use Pydantic validation
- include source evidence in prompts
- instruct the model to use "unknown" when evidence is missing
- verify claims against retrieved evidence
- add post-processing validation rules
- require citations or evidence URLs for key facts
- evaluate against a labeled test set

## Observability And Reliability

### What observability exists now?

The project has basic CLI observability through `--verbosity 1`.

It logs:

- OpenAI call counts
- rough prompt token estimates
- Tavily search counts
- estimated Tavily credits
- page fetch counts
- query counts
- candidate counts
- cached document counts

This is helpful for debugging, but not enough for production.

### What observability would you add for production?

I would add:

- structured JSON logs
- request IDs and run IDs
- per-agent latency
- model name and version
- token usage and cost
- Tavily usage and failures
- cache hit rates
- retrieval quality metrics
- prompt and response tracing with redaction
- error tracking
- dashboard metrics
- alerts for failure rates, latency, and cost spikes

For enterprise use, I would also add audit logs and data lineage.

### How would you make the system more reliable?

I would add:

- automated tests around each agent boundary
- schema validation for all outputs
- retries with exponential backoff
- circuit breakers for external APIs
- rate limiting
- persistent task state
- resumable runs
- better error classification
- evaluation datasets
- monitoring and alerting

### What happens if OpenAI or Tavily fails?

Some parts catch exceptions and continue, such as failed enrichment or verification for a candidate. The LLM wrapper also retries calls.

However, production robustness could be improved with stronger error handling, resumable jobs, fallback models, and clearer failure reporting.

## Security, Compliance, And Responsible AI

### What responsible AI practices are demonstrated?

The project demonstrates several responsible AI practices:

- It grounds LLM decisions in retrieved evidence.
- It uses "unknown" rather than forcing unsupported facts.
- It validates structured outputs.
- It avoids CAPTCHA or anti-bot bypass.
- It separates unverified scan results from verified deep-dive results.
- It keeps evidence URLs for traceability.

### What security improvements would be needed for enterprise use?

I would add:

- secret management instead of local environment variables
- role-based access control
- audit logging
- data retention policies
- PII detection and redaction
- network egress controls
- dependency scanning
- container security scanning
- encryption policies
- approval workflows for sensitive data sources

### Why is CAPTCHA bypass avoidance important?

Bypassing CAPTCHA or anti-bot systems can violate website terms, legal rules, and enterprise compliance policies.

The project intentionally detects these pages and treats them as blocked instead of attempting to bypass them.

This is important for a company like MSD where compliance and responsible technology use matter.

## Productionization

### How would you expose this as a REST API?

I would wrap the pipeline in a FastAPI service.

Possible endpoints:

- `POST /runs` to start a run with config overrides.
- `GET /runs/{run_id}` to check status.
- `GET /runs/{run_id}/results` to fetch outputs.
- `GET /runs/{run_id}/summary.csv` to download the summary CSV.
- `POST /summary` to run summary-only mode on an existing report.

For long-running jobs, I would not run the whole pipeline inside a synchronous HTTP request. I would enqueue a background job using Celery, RQ, AWS SQS, or a workflow orchestrator.

### How would you containerize it?

I would create a Docker image with:

- Python runtime
- dependencies from `environment.yml` or a locked requirements file
- Playwright dependencies if browser rendering is needed
- application code
- non-root user
- health check

Configuration would come from environment variables or mounted config files.

### How would you deploy it in the cloud?

One AWS-oriented approach:

- API layer: ECS/Fargate or Lambda for lightweight endpoints
- job execution: ECS tasks or AWS Batch for long-running pipeline jobs
- queue: SQS
- storage: S3 for reports
- vector DB: managed vector service or persistent Chroma alternative
- secrets: AWS Secrets Manager
- logs/metrics: CloudWatch
- CI/CD: GitHub Actions or AWS CodePipeline

The exact design depends on expected scale, latency, and data-sensitivity requirements.

### What CI/CD would you add?

I would add a pipeline that runs:

- linting
- type checks
- unit tests
- integration tests with mocked OpenAI/Tavily
- prompt regression tests
- Docker build
- vulnerability scanning
- deployment to staging
- smoke tests
- manual approval for production

### What MLOps or LLMOps practices would you add?

I would add:

- prompt versioning
- model version tracking
- evaluation datasets
- automated regression evaluation
- output quality dashboards
- cost monitoring
- latency monitoring
- drift monitoring for retrieval results
- human review workflows for high-impact outputs
- trace storage for prompt, retrieved context, and model output with sensitive-data redaction

## Tradeoffs And Limitations

### What are the main strengths of the current design?

The strengths are:

- modular agent design
- typed data contracts
- clear orchestration
- RAG grounding with Chroma
- cost-aware scan versus deep-dive modes
- reusable evidence and profile cache
- practical web retrieval
- mode-aware reporting
- inspectability in a debugger

### What are the main limitations?

The limitations are:

- no REST API yet
- no production job queue
- limited automated evaluation
- limited tests
- no full observability stack
- no CI/CD pipeline shown
- no Docker deployment shown
- heuristic scoring rather than validated ML scoring
- web evidence quality depends on search results and accessible pages
- LLM outputs can still be imperfect despite validation

### What would you improve first?

For interview purposes, I would say:

1. Add an evaluation dataset for extraction and verification.
2. Add structured tracing for each agent call.
3. Add more tests with mocked LLM and Tavily responses.
4. Add a FastAPI/job queue interface.
5. Add Docker and CI/CD.
6. Improve source citation and confidence calibration.

This shows you understand how to move from a learning project to a production-grade AI system.

### Why is the scoring heuristic and not ML?

The project does not have labeled training data for market opportunity scoring. So it uses a transparent heuristic combining competitor count, explicit agentic posture, vertical specialization, pain weights, and regulatory tailwind.

This is appropriate for exploratory analysis, but for production decision support I would validate or replace it with a data-backed scoring model.

## Business And Collaboration Questions

### How would you explain this to non-technical stakeholders?

I would say:

The system researches a selected part of the drug-development workflow, finds AI companies that appear relevant, verifies them more deeply when requested, and produces a report and summary table. It helps analysts move faster, but the outputs should still be reviewed because web evidence and LLM reasoning can be imperfect.

### How would you work with domain experts?

I would ask domain experts to help define:

- relevant pipeline taxonomy
- known benchmark companies
- inclusion and exclusion rules
- trusted data sources
- evaluation examples
- acceptable confidence thresholds

Their feedback would become prompt rules, taxonomy updates, evaluation labels, and acceptance criteria.

### How would you communicate risk and tradeoffs?

I would separate:

- first-pass unverified scan outputs
- verified deep-dive outputs
- facts supported by evidence
- unknown fields
- model-generated interpretations

I would communicate cost, latency, confidence, and evidence limitations clearly.

Implementation: `CompetitiveLandscapeOrchestrator` (lines 27-529), `ReportWriter` (lines 13-423)

### How does this align with the MSD role?

The project aligns with the role because it demonstrates:

- Python AI engineering
- RAG design
- vector database usage
- LLM prompt workflows
- structured data pipelines
- agent orchestration
- web/API integration
- documentation
- debugging and explainability
- awareness of production gaps like CI/CD, observability, APIs, security, and MLOps

## Short Answers To The Ten Checklist Questions

### 1. What is the difference between `Candidate`, `CompanyResearchRequest`, and `CompanyProfile`?

`Candidate` is a possible company extracted from evidence. `CompanyResearchRequest` is the structured input used to research that company more deeply. `CompanyProfile` is the enriched or minimal normalized company record used for reporting.

Implementation: `Candidate`, `CompanyResearchRequest`, `CompanyProfile` in `lib/models.py` (lines 43-139)

### 2. Where does the vector database enter the workflow?

The vector database enters through `EvidenceStore`. Evidence is saved into Chroma after search and page extraction. Later, enrichment and verification query Chroma semantically to retrieve relevant context for LLM prompts.

Implementation: `lib/retrieval/evidence_store.py` (lines 14-404)

### 3. What is retrieved during enrichment versus verification?

Enrichment retrieves evidence to describe the company and fill profile facts. Verification retrieves evidence to decide whether the company belongs in the exact pipeline step. Enrichment asks "what is this company?" Verification asks "does it fit this subphase?"

Implementation: `lib/agents/enrichment_agent.py` and `lib/agents/verification_agent.py`

### 4. How does `landscape_scan` reduce cost compared with `deep_dive`?

It skips LLM query planning, company enrichment, per-company verification, deep fact extraction, full narrative generation, and usually full page fetching. It produces minimal unverified profiles instead of deeply verified profiles.

Implementation: `lib/orchestrator.py:_process_landscape_scan_candidates()` (lines 292-341)

### 5. How are LLM outputs validated?

LLM outputs are requested as JSON, parsed by `LLM.ask_json()`, and converted into Pydantic models such as `Candidate`, `CompanyProfile`, and `VerificationResult`. Invalid or malformed items can be skipped or cause the relevant step to fail.

Implementation: `lib/llm.py:LLM.ask_json()` (lines 82-87)

### 6. What happens when page extraction returns a CAPTCHA or low-content page?

The retrieval guard marks the page as unusable with a status and blocked reason. For low-content or JavaScript-placeholder pages, the system may try browser rendering. For CAPTCHA or challenge pages, it does not attempt bypass.

Implementation: `lib/retrieval/page_quality.py` (lines 1-215)

### 7. Which operations are deterministic and which depend on LLM output?

Deterministic operations include config loading, CSV parsing, filtering, web payload construction, caching, dataframe building, scoring, and report writing. LLM-dependent operations include query generation in deep dive, candidate extraction, enrichment, verification, narrative analysis, critical review, presentation writing, and summary generation when LLM summary is enabled.

Implementation: `lib/orchestrator.py:process_step()` (lines 177-290)

### 8. How would you evaluate extraction quality?

I would build a labeled benchmark of pipeline steps and expected company/product outputs, then measure precision, recall, F1, duplicate rate, source-vs-subject correctness, evidence quality, and false-positive categories.

Implementation: `ExtractionAgent` in `lib/agents/extraction_agent.py`

### 9. How would you expose this as a REST API?

I would use FastAPI with endpoints to start runs, check run status, retrieve results, and download summary CSVs. Long-running runs should execute in background jobs through a queue rather than inside synchronous HTTP requests.

Implementation: `main.py` entry point

### 10. What observability would you add before production deployment?

I would add structured logs, run IDs, per-agent latency, token and cost tracking, Tavily usage, cache hit rates, retrieval quality metrics, prompt/response tracing with redaction, error tracking, dashboards, and alerts.

Implementation: `main.py` and agent logging

