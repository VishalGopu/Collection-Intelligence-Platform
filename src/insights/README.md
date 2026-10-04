# Layer 2: Insight and NLP

This module handles certified metric queries, policy/document retrieval, out-of-scope refusal, cited answer cards, and automated benchmark answer generation.

It reads the release through read-only DuckDB views and uses the C360 crosswalk for supported customer-scoped questions. Every answered question shows executed SQL or source document/record IDs.

## Current implementation

Released questions use deterministic routing to certified SQL, current policy/procedure documents, case-scoped transcripts, or a safety refusal. Unknown safe analytics questions may use the optional LLM SQL planner; its query is validated before read-only execution.

Routing is deliberately strict. A released question ID always uses its governed route. Text-only routing requires an exact or near-exact match and rejects changed dates, numbers, case IDs, dimensions, or negation. Other safe questions use the optional LLM SQL planner; they never inherit a loosely matched canned answer.

Install the module dependency from the repository root:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Ask a released question:

```bash
.venv/bin/python -m src.insights.cli \
  --question "What is the average days past due of open cases by queue?"
```

Generate the benchmark submission (all questions, or add `--split dev` while developing):

```bash
.venv/bin/python -m src.insights.cli \
  --benchmark local_artifacts/insights/benchmark_answers.csv
```

The generated CSV contains `question_id`, `answer`, `sql_or_sources`, and `refused`. The runner never modifies source data. Unsupported questions fail closed; protected-attribute profiling and bulk PII exports are refused explicitly.

Run the unit tests with:

```bash
.venv/bin/python -m pytest tests/insights
```

Run the full development regression, including comparison with the published answers:

```bash
.venv/bin/python -m src.insights.regression
```

The report and generated answers are written below `local_artifacts/insights/regression/`.

To run a newly released question set with columns `question_id` and `question_text`:

```bash
.venv/bin/python -m src.insights.regression --questions path/to/new_questions.csv
```

The report records setup, per-question API, DuckDB, and other time, API calls, cache hits, and whether each question was answered, refused, empty, or unable to run. The new-question run also compares 10 queries with independent hand-checked reference SQL and writes a full question/SQL/answer table to `question_results.md`. Questions without published gold answers are recorded without pretending that execution proves correctness.

For a reproducible 60-question mixed workload (24 new, 35 released, one additional question):

```bash
.venv/bin/python -m src.insights.regression --workload-60 --output-dir local_artifacts/insights/performance_60
```

The runner keeps a local DuckDB cache of the three large CSV tables and builds the schema catalog once per run. Both the DuckDB cache and LLM response cache live under ignored `local_artifacts/`; the first DuckDB cache build costs extra time. The 60-question workload includes cached and deterministic routes, so its timing is not a proxy for 60 fresh LLM calls. Questions run sequentially by default to avoid amplifying Groq's per-model rate limits.

## Optional LLM SQL fallback

Set `INSIGHTS_LLM_PROVIDER=gemini`, `groq`, or `openai` in the ignored `.env` along with the matching `GEMINI_API_KEY`, `GROQ_API_KEY`, or `OPENAI_API_KEY`. Without an explicit provider, OpenAI is selected if its key exists; otherwise Groq is selected. Without a key for the selected provider, unknown questions fail closed. Optional model variables are `GEMINI_MODEL`, `GROQ_MODEL`, `GROQ_FALLBACK_MODEL`, and `OPENAI_MODEL`. The planner retries transient failures, respects Groq's `Retry-After` on 429, and caches successful plans in `local_artifacts/insights/llm_cache.json`. Its cache key includes provider, models, and prompt version. Groq requests use the `curl` executable because this environment's edge rejects Python HTTP clients.

Every generated query is parsed before execution. It must be one read-only statement over approved views, cannot reference protected or direct-identifier columns, cannot call file/network readers, cannot use a cross join, and is wrapped in a 200-row output limit. Invalid SQL and execution errors return `I couldn't answer this` with a reason; an empty result returns `No rows matched.` with the validated SQL. The system does not guess.

AI providers are used for SQL planning only; answers come from validated, read-only DuckDB query results. No API key or response cache is committed.
