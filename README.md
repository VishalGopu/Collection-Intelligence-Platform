# Collections Intelligence Platform

Hackathon build for a golden customer view (C360), grounded collections questions, shared features, and an explainable Next Best Action.

## Work areas

| Path | Purpose |
| --- | --- |
| `src/c360/` | Raw-to-gold pipeline, identity resolution, data quality |
| `src/insights/` | Certified metrics, document lookup, cited answers, refusals, benchmark runner |
| `src/features/` | Shared point-in-time feature definitions |
| `src/decisioning/` | Policy gate, scoring, reasons, human review |
| `app/` | Streamlit Customer, Ask, Recommendation, and Worklist tabs |
| `contracts/` | Published data interface |
| `local_artifacts/` | Generated local files, ignored by Git |
| `submission/` | Final artifacts to commit for judging |

See [the parallel workflow](docs/PARALLEL_WORKFLOW.md) for folder ownership and integration steps. Each laptop downloads the dataset locally using [the dataset guide](docs/DATASET_DOWNLOAD.md). The dataset and virtual environment are not committed.

The build-phase requirements are in `build_phase.pdf`; the proposed architecture is in `HACKERS_SystemDesign.pdf`.

## How to run

For a fresh clone, work from the repository root and download the Maple release using [the dataset guide](docs/DATASET_DOWNLOAD.md). Extract it at `maple_data/maple_collections_release/`. The dataset and generated files are local and ignored by Git. Python 3.14 is the verified version.

Windows PowerShell:

```powershell
git clone git@github.com:VishalGopu/Collection-Intelligence-Platform.git
cd Collection-Intelligence-Platform
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m src.c360.build
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe -m app.smoke
.\.venv\Scripts\python.exe -m src.features.training
.\.venv\Scripts\python.exe -m src.features.candidates --base local_artifacts/features/open_promise_features.parquet --output local_artifacts/features/open_promise_candidates.parquet
.\.venv\Scripts\python.exe -m streamlit run app/main.py
```

Linux or macOS:

```bash
git clone git@github.com:VishalGopu/Collection-Intelligence-Platform.git
cd Collection-Intelligence-Platform
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m src.c360.build
.venv/bin/python -m pytest tests -q
.venv/bin/python -m app.smoke
.venv/bin/python -m src.features.training
.venv/bin/python -m src.features.candidates --base local_artifacts/features/open_promise_features.parquet --output local_artifacts/features/open_promise_candidates.parquet
.venv/bin/python -m streamlit run app/main.py
```

Download the dataset before the build command; see the dataset guide for its exact commands and access steps. Open the local URL printed by Streamlit. The Customer tab starts with `G-39c6b287f70371cd9fc6`; choose another demo ID or paste a published golden ID. Ask shows answers with evidence and refusals; Recommendation creates a proposal for human review and shows local audit rows. Worklist loads ranked open promises after the two feature commands. The smoke command writes a local test rejection to the ignored audit database. Stop the app with Ctrl+C.

The [implemented architecture diagram](docs/architecture_built.png) shows the built components, AI use, and human review. [App interfaces](app/INTERFACES.md) and [hero-flow results](app/INTEGRATION_TEST.md) describe the current integration.

## What changed from the design

| Proposed design | Built behavior |
| --- | --- |
| Dagster, dbt and Great Expectations for the data product | One reproducible Python/DuckDB batch creates curated and golden Parquet files, with publication quality gates and a 31-table profile. |
| Splink-style probabilistic identity matching and steward workflow | Rule-based matching publishes a link at confidence ≥0.95 only with a ≥0.05 lead over the next candidate and no conflicting profile. Ambiguous links remain `review_pending`; there is no steward UI or calibrated match probability. |
| Vector document search and an agent-style Q&A planner | Document answers use governed source IDs and section mappings; transcript facts use text patterns. Released questions use deterministic routes. Unknown safe analytics can use an optional LLM SQL planner, validated with SQLGlot before read-only DuckDB execution. There is no vector index. |
| Next.js application | Streamlit has Customer, Ask, and Recommendation tabs. Customer records use linked C360 keys; Ask labels global metrics and refuses unsupported customer-scoped analytics. |
| Managed AI decision service and online feature store | Local point-in-time feature helpers feed a LightGBM promise-kept model with SHAP reasons. A policy gate ranks allowed actions; a typed reviewer ID approves, modifies, or rejects a proposal into SQLite. No customer contact is executed. |
| Broad use of customer profile signals | Fairness-test fields are excluded from published C360 outputs and model ranking. Support flags are used only to route a case to specialist review. |

The optional SQL-planning provider is Groq (`openai/gpt-oss-120b` by default with `GROQ_API_KEY`) or OpenAI (`gpt-5-mini` by default with `OPENAI_API_KEY`); OpenAI takes precedence if both are configured. The hero smoke test used deterministic Layer 2 routes, so it did not call either provider. The promise model runs locally with LightGBM.

## AI tools used (submission draft)

- Groq API (`openai/gpt-oss-120b`, fallback `openai/gpt-oss-20b`): SQL planning only for new Layer 2 analytics questions. The application validates and runs the SQL read-only in DuckDB, then builds answers solely from query results. A 24-question live API run has been completed.
- OpenAI API: optional alternative provider for the same SQL-planning-only path; not used for the Groq live run.
- LightGBM and SHAP: local promise-kept estimation and explanation for decision proposals.
- Codex: implementation, test creation, and development workflow assistance.
