# Interview Debugging Checkpoints

This guide is meant to be used with PyCharm's debugger while preparing to discuss the project in a Senior AI Developer interview.

The goal is not to step through every line. The goal is to stop at the points where the system changes shape:

- config and runtime mode selection
- agent orchestration
- query planning
- web search and page retrieval
- evidence persistence in Chroma
- RAG retrieval
- LLM prompt/JSON boundaries
- candidate extraction
- deep-dive enrichment and verification
- dataframe/report/summary assembly

## Recommended First Runs

Use small runs while debugging. They are easier to explain and cheaper to execute.

### Option A: current Early Drug Discovery config

For the first landscape scan, temporarily set this in `config.yml`:

```yaml
runtime:
  analysis_mode: landscape_scan
  max_steps: 1
  max_candidates_per_step: 5
```

Then run:

```shell
python main.py --mode landscape_scan --verbosity 1
```

For the matching deep dive, use the first subphase in the current CSV:

```shell
python main.py --mode deep_dive --deep-subphases "Target identification" --verbosity 1
```

For a cheaper deep-dive debug session, temporarily keep:

```yaml
runtime:
  max_candidates_per_step: 3
```

### Option B: Pharmacovigilance one-row subset

If you want to match your previous one-subphase report, temporarily set:

```yaml
paths:
  pipeline_csv: data/subests/one_most_expensive.csv

runtime:
  max_steps: 0
```

Then run:

```shell
python main.py --mode landscape_scan --verbosity 1
python main.py --mode deep_dive --deep-subphases "Pharmacovigilance" --verbosity 1
```

## Concepts To Be Ready To Explain

| Concept | Where this project demonstrates it |
| --- | --- |
| Agentic orchestration | `main.py` wires specialized agents; `CompetitiveLandscapeOrchestrator` controls mode-specific execution. |
| RAG | Evidence is stored in Chroma, then retrieved by semantic query during enrichment and verification. |
| Vector database | `EvidenceStore` persists evidence, profiles, candidates, query plans, and verification decisions in Chroma collections. |
| Retrieval strategy | The system combines Tavily search, page extraction, cached evidence, direct URL evidence, and vector similarity retrieval. |
| Prompt engineering | Planner, extractor, enricher, verifier, analyst, critic, presentation, and summary agents use role-specific prompts. |
| Structured LLM outputs | `LLM.ask_json()` parses JSON into Pydantic models such as `Candidate`, `CompanyProfile`, and `VerificationResult`. |
| Caching and cost control | Query plans, candidates, evidence, profiles, and verification results can be reused; scan mode skips expensive operations. |
| Responsible AI / safety | Retrieval guards detect CAPTCHA/challenge pages and avoid bypassing protected content. |
| Observability | `--verbosity 1` logs OpenAI calls, Tavily calls, rough token estimates, and search/fetch counts. |
| Production gaps to discuss | No REST API yet, limited automated evaluation, limited CI/CD/MLOps/monitoring, no container/runtime deployment layer. |

## Essential Breakpoints

Set these before launching the debugger. Start with this list; add deeper breakpoints only after you understand the object flow.

| # | File:line | Stop here to inspect | Key objects |
| --- | --- | --- | --- |
| 1 | `main.py:185` | Program entry, `.env` load, CLI parsing. | `args` after line 186 |
| 2 | `main.py:187` | YAML config becomes typed `AppConfig`; CLI overrides are applied. | `config`, `config.runtime`, `config.tavily.profiles` |
| 3 | `main.py:193` | Pipeline CSV is loaded into Pydantic `PipelineStep` objects. | `all_steps`, `steps` after line 194 |
| 4 | `main.py:210` | Core services are instantiated. | `llm`, `web_search`, `store` |
| 5 | `main.py:214` | Agents are composed from shared dependencies. | all `*_agent` objects |
| 6 | `main.py:244` | Control passes into the orchestrator. | `orchestrator`, `steps`, `seed_companies` |
| 7 | `lib/orchestrator.py:71` | Run-level state is initialized. | `run_steps`, `profile_cache`, `all_records` |
| 8 | `lib/orchestrator.py:76` | User seed companies become normalized research requests. | `seed_companies`, `seed_requests`, `seed_request_map` |
| 9 | `lib/orchestrator.py:90` | One pipeline step enters the multi-agent workflow. | `step`, `step_seed_candidates`, `profile_cache` |
| 10 | `lib/orchestrator.py:189` | Step taxonomy is assigned before discovery. | `step_taxonomy` |
| 11 | `lib/orchestrator.py:195` | Query planning output is produced. | `queries`, `step_terms` |
| 12 | `lib/orchestrator.py:196` | Web evidence collection returns normalized docs. | `docs` |
| 13 | `lib/orchestrator.py:197` | LLM extraction returns candidate companies. | `candidates` |
| 14 | `lib/orchestrator.py:205` | Mode branch: landscape scan skips enrichment/verification. | `config.runtime.analysis_mode` |
| 15 | `lib/orchestrator.py:226` | Deep dive converts a candidate into a company research request. | `candidate`, `research_request` |
| 16 | `lib/orchestrator.py:240` | Deep dive enrichment returns a normalized company profile. | `profile`, `profile_cache` |
| 17 | `lib/orchestrator.py:255` | Deep dive verification checks company-step fit. | `verdict`, `profile`, `candidate` |
| 18 | `lib/orchestrator.py:275` | A normalized competitor record is appended. | `records`, returned `_build_record()` dict |
| 19 | `lib/orchestrator.py:98` | All step records become a dataframe. | `records_df`, `all_records` |
| 20 | `lib/orchestrator.py:112` | Report dataframes are built. | `profile_df`, `matrix_df`, `gap_df` |
| 21 | `lib/orchestrator.py:117` | Narrative branch differs by mode. | `_should_generate_narratives()` |
| 22 | `lib/orchestrator.py:142` | Summary CSV agent runs after structured outputs exist. | `summary_df`, `summary_csv_path` |
| 23 | `lib/orchestrator.py:170` | Markdown reports are written. | `results`, `report_paths` |
| 24 | `main.py:247` | Final outputs return to CLI printing. | `results` |

## Deep Breakpoints By Concept

Use these when you want to understand the internals behind the essential checkpoints.

### Data Models And Contracts

Break at `lib/models.py:6`.

Inspect the classes, then watch instances appear during the run:

- `PipelineStep`: one row from the CSV.
- `EvidenceDoc`: normalized web/search evidence.
- `Candidate`: extracted possible competitor.
- `CompanyResearchRequest`: enrichment request for one company.
- `CompanyProfile`: enriched or minimal profile.
- `VerificationResult`: include/exclude decision.

Interview angle: explain why Pydantic models help enforce structured contracts around unreliable LLM outputs.

### Query Planning

Breakpoints:

- `lib/agents/planner_agent.py:22`
- `lib/agents/planner_agent.py:34`
- `lib/agents/planner_agent.py:51`
- `lib/agents/planner_agent.py:123`

Inspect:

- `step`
- `step_signature`
- `should_skip_llm_plan`
- `llm_queries`
- `auto_queries`
- `queries`

What to learn:

- In `landscape_scan`, LLM query planning is skipped by default and deterministic queries are used to reduce cost.
- In `deep_dive`, the planner can ask the LLM for search queries and then merges them with deterministic queries.
- Query plans are saved in Chroma-backed persistence via `store.save_query_plan()`.

### Web Search And Evidence Collection

Breakpoints:

- `lib/agents/research_agent.py:20`
- `lib/agents/research_agent.py:52`
- `lib/agents/research_agent.py:144`
- `lib/agents/research_agent.py:196`
- `lib/agents/research_agent.py:212`
- `lib/agents/research_agent.py:179`

Inspect:

- `cached_docs`
- `queries`
- `max_results`
- `fetch_top_n`
- each Tavily `result`
- each constructed `EvidenceDoc`
- `deduped_docs`

What to learn:

- Search results are converted into a uniform `EvidenceDoc` schema.
- In scan mode, `step_fetch_text_for_top_n_results` is usually `0`, so the system relies on snippets and avoids full page fetches.
- In deep dive, top results are fetched and cleaned, producing richer prompt context.
- Evidence is persisted through `EvidenceStore.add_docs()`.

### Tavily Payload And Page Fetching

Breakpoints:

- `lib/retrieval/web_search.py:46`
- `lib/retrieval/web_search.py:75`
- `lib/retrieval/web_search.py:87`
- `lib/retrieval/web_search.py:110`
- `lib/retrieval/web_search.py:124`
- `lib/retrieval/web_search.py:129`

Inspect:

- `payload`
- `cache_key`
- `result`
- `results`
- `downloaded`
- `extracted`
- `assessment`
- `PageFetchResult`

What to learn:

- Search payloads are config-driven and mode-dependent.
- Search and fetch calls have in-memory LRU-style caches.
- Page text is extracted with `trafilatura`.
- Browser rendering is used only as a conservative fallback for normal JS-rendered pages.

### Retrieval Guard And Responsible AI

Breakpoints:

- `lib/retrieval/page_quality.py:73`
- `lib/retrieval/page_quality.py:96`
- `lib/retrieval/page_quality.py:105`
- `lib/retrieval/page_quality.py:158`
- `lib/retrieval/browser_render.py:23`
- `lib/retrieval/browser_render.py:46`

Inspect:

- `raw_text`
- `raw_html`
- `cleaned_text`
- `assessment.status`
- `assessment.blocked_reason`

What to learn:

- The system detects anti-bot pages, CAPTCHA pages, access-denied pages, consent walls, low-content pages, and JS placeholders.
- It does not attempt challenge or CAPTCHA bypass.
- This is a concrete responsible-AI/security point for enterprise environments.

### Vector Database And RAG

Breakpoints:

- `lib/retrieval/evidence_store.py:17`
- `lib/retrieval/evidence_store.py:31`
- `lib/retrieval/evidence_store.py:71`
- `lib/retrieval/evidence_store.py:73`
- `lib/retrieval/evidence_store.py:85`
- `lib/retrieval/evidence_store.py:240`
- `lib/retrieval/evidence_store.py:275`

Inspect:

- Chroma collections: `evidence_collection`, `profile_collection`, `query_plan_collection`, `candidate_collection`, `verification_collection`
- `ids`
- `documents`
- `metadatas`
- vector query `result`
- normalized retrieval output

What to learn:

- The vector DB is used both as a semantic retrieval layer and as a persistence/cache layer.
- RAG context is created by querying stored evidence with a task-specific text query.
- Metadata filters support deterministic cache lookup by phase, step, URL, company, and activity signature.

### LLM Boundary

Breakpoints:

- `lib/llm.py:31`
- `lib/llm.py:58`
- `lib/llm.py:82`
- `lib/llm.py:85`
- `lib/llm.py:87`

Inspect:

- `prompt`
- `self.config.model`
- `response`
- `output_text`
- `json_blob`
- parsed Python `data`

What to learn:

- All LLM calls go through one wrapper.
- Retry behavior is centralized with `tenacity`.
- `ask_json()` appends a JSON-only instruction, extracts the JSON blob, and parses it.
- The next agent layer validates parsed output with Pydantic models.

### Candidate Extraction

Breakpoints:

- `lib/agents/extraction_agent.py:27`
- `lib/agents/extraction_agent.py:62`
- `lib/agents/extraction_agent.py:68`
- `lib/agents/extraction_agent.py:93`
- `lib/agents/extraction_agent.py:102`
- `lib/agents/extraction_agent.py:169`
- `lib/agents/extraction_agent.py:176`
- `lib/agents/extraction_agent.py:71`

Inspect:

- `docs`
- `ranked_docs`
- `evidence_batches`
- `context`
- `prompt`
- `data`
- each `Candidate`
- `merged_candidates`

What to learn:

- Evidence is ranked and chunked before prompting.
- The extraction prompt explicitly handles source-vs-subject errors.
- The output schema distinguishes company owner, product, website, posture, evidence role, rationale, confidence, and URLs.
- Candidates are fuzzy-deduplicated and cached.

### Landscape Scan Branch

Breakpoints:

- `lib/orchestrator.py:292`
- `lib/orchestrator.py:308`
- `lib/orchestrator.py:314`
- `lib/orchestrator.py:322`
- `lib/orchestrator.py:329`
- `lib/orchestrator.py:351`

Inspect:

- `allowed_postures`
- `candidate`
- `posture`
- minimal `CompanyProfile`
- record returned by `_build_record()`

What to learn:

- Scan mode is a deliberate cheaper approximation.
- It creates minimal profiles from candidates.
- It labels records as `landscape_scan_unverified`.
- It avoids company enrichment, verification, funding/headcount/HQ extraction, and most narrative generation.

### Deep Dive Branch

Breakpoints:

- `lib/orchestrator.py:217`
- `lib/orchestrator.py:226`
- `lib/agents/user_company_intake_agent.py:78`
- `lib/agents/enrichment_agent.py:30`
- `lib/agents/enrichment_agent.py:42`
- `lib/agents/enrichment_agent.py:43`
- `lib/agents/enrichment_agent.py:66`
- `lib/agents/enrichment_agent.py:141`
- `lib/agents/verification_agent.py:20`
- `lib/agents/verification_agent.py:48`
- `lib/agents/verification_agent.py:55`
- `lib/agents/verification_agent.py:117`
- `lib/orchestrator.py:268`

Inspect:

- `candidate`
- `research_request`
- `docs`
- `rag_docs`
- enrichment `context`
- enrichment LLM `data`
- `CompanyProfile`
- verification `context`
- `VerificationResult`

What to learn:

- Deep dive is where RAG matters most.
- Enrichment uses both newly collected company evidence and vector-retrieved prior evidence.
- Verification uses direct candidate URLs plus RAG retrieval to decide whether the company truly belongs in the current subphase.
- The deep-dive branch labels records as `deep_dive_verified`.

### Analytics, Scoring, And Reports

Breakpoints:

- `lib/analytics/scoring.py:9`
- `lib/analytics/scoring.py:26`
- `lib/analytics/scoring.py:97`
- `lib/utils/report_writer.py:21`
- `lib/utils/report_writer.py:42`
- `lib/utils/report_writer.py:76`
- `lib/utils/report_writer.py:148`

Inspect:

- `records_df`
- `profile_cache`
- `profile_df`
- `matrix_df`
- `gap_df`
- `run_context`
- `report_paths`

What to learn:

- LLM/agent outputs are converted back into deterministic pandas tables.
- The reporting layer is mode-aware.
- Gap scoring is heuristic, not a trained ML model; be clear about this in an interview.

### Summary CSV

Breakpoints:

- `lib/agents/summary_agent.py:36`
- `lib/agents/summary_agent.py:49`
- `lib/agents/summary_agent.py:58`
- `lib/agents/summary_agent.py:91`
- `lib/agents/summary_agent.py:100`
- `lib/agents/summary_agent.py:111`
- `lib/agents/summary_agent.py:225`

Inspect:

- `matrix_df`
- `profile_df`
- `gap_df`
- `prompt`
- `fallback_rows`
- `rows`
- final `summary_df`

What to learn:

- The summary agent is a post-processing agent.
- It can use the LLM or deterministic fallback rows.
- In `summary_only`, it reads existing markdown reports and does not instantiate Tavily.

## Suggested PyCharm Debug Strategy

1. First run `landscape_scan` with only essential breakpoints.
2. Watch the transition from `PipelineStep` to `queries` to `EvidenceDoc` to `Candidate`.
3. Resume through the scan branch and inspect the minimal `CompanyProfile`.
4. Run `deep_dive` for the same subphase.
5. Focus on the new objects that did not appear in scan mode: `CompanyResearchRequest`, enriched `CompanyProfile`, `VerificationResult`, RAG `rag_docs`.
6. In both modes, finish by inspecting `records_df`, `profile_df`, `matrix_df`, `gap_df`, and `summary_df`.

## Good Interview Talking Points

- "I decomposed the system into specialized agents with typed inputs and outputs instead of one monolithic prompt."
- "The orchestrator owns control flow; agents own bounded responsibilities."
- "RAG is used as an evidence reuse and grounding mechanism during enrichment and verification."
- "The vector DB stores not only raw evidence but also reusable intermediate artifacts such as query plans, candidates, profiles, and verifications."
- "I used Pydantic schemas to make LLM outputs explicit and inspectable."
- "Landscape scan is a cost-controlled approximation; deep dive performs richer retrieval, enrichment, verification, and narrative synthesis."
- "The retrieval guard avoids unsafe behavior such as CAPTCHA or anti-bot bypass attempts."
- "For production, I would add automated evaluation sets, tracing, model-quality metrics, CI/CD, containerization, API serving, access control, and monitoring."

## Questions You Should Be Able To Answer

1. What is the difference between `Candidate`, `CompanyResearchRequest`, and `CompanyProfile`?
2. Where does the vector database enter the workflow?
3. What is retrieved during enrichment versus verification?
4. How does `landscape_scan` reduce cost compared with `deep_dive`?
5. How are LLM outputs validated?
6. What happens when page extraction returns a CAPTCHA or low-content page?
7. Which operations are deterministic and which depend on LLM output?
8. How would you evaluate extraction quality?
9. How would you expose this as a REST API?
10. What observability would you add before production deployment?

