# Layer 2: Insight and NLP

Own certified metric queries, policy/document retrieval, out-of-scope refusal, cited answer cards, and automated benchmark answer generation. Keep implementation and module dependencies in this directory, and tests in `tests/insights/`.

Develop first against the release's read-only DuckDB views and benchmark files. When C360 is ready, consume only the paths and columns in `contracts/golden_c360_v1.json`. Every answer must show the executed SQL or source document/record IDs. Do not edit C360 pipeline code.

## Current implementation

The local MVP uses deterministic routing and read-only DuckDB queries. Questions are routed to certified SQL, current policy/procedure documents, case-scoped transcripts, or a safety refusal. This keeps benchmark answers reproducible and makes the evidence visible without requiring an external LLM.

Install the module dependency from the repository root:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r src/insights/requirements.txt
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

The generated CSV contains `question_id`, `answer`, `sql_or_sources`, and `refused`. The runner never modifies source data. Unknown ad-hoc questions fail closed unless they exactly match a governed route; protected-attribute profiling and bulk PII exports are refused explicitly.

Run the unit tests with:

```bash
.venv/bin/python -m pytest tests/insights
```
