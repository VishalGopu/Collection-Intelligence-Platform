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

Use [the dataset guide](docs/DATASET_DOWNLOAD.md) to download the release locally. The dataset, virtual environment, text annotation cache, and generated Parquet files are not committed.

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
.\.venv\Scripts\python.exe -m src.features.text_rules
.\.venv\Scripts\python.exe -m src.features.text_data
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
.venv/bin/python -m src.features.text_rules
.venv/bin/python -m src.features.text_data
.venv/bin/python -m streamlit run app/main.py
```

Download the dataset before the build command; see the dataset guide for its exact commands and access steps. Open the local URL printed by Streamlit. The Customer tab starts with `G-39c6b287f70371cd9fc6`; the dropdown also includes `G-b1714eca2809e88d7587`. Ask defaults to **All Collections**. Choose **This customer** only for a certified linked-customer route; unsupported scoped filters are refused. Every non-refused answer shows SQL or sources. Recommendation shows its reasons, text context, blocked actions with policy reasons, and human-review audit rows. Worklist loads ranked open promises. The smoke command writes a local test rejection to the ignored audit database. Stop the app with Ctrl+C.

For the official benchmark output, run `python -m src.insights.submission --questions questions.csv --output answers.csv` from the repository root (use the venv's Python on either OS). The output columns are exactly `question_id,answer,sql_or_sources,refused`. See [the uncached first-run ledger](docs/insights/step3_first_run_34.csv) and [fresh-clone verification](docs/fresh_clone_verification.md).

The [implemented architecture diagram](docs/architecture_built.png) shows the built components, AI use, and human review. [App interfaces](app/INTERFACES.md) and [hero-flow results](app/INTEGRATION_TEST.md) describe the current integration.

## What changed from the design

| Proposed design | Built behavior |
| --- | --- |
| Dagster, dbt and Great Expectations for the data product | One reproducible Python/DuckDB batch creates curated and golden Parquet files, with publication quality gates and a 31-table profile. |
| Splink-style probabilistic identity matching and steward workflow | Rule-based matching publishes a link at confidence ≥0.95 only with a ≥0.05 lead over the next candidate and no conflicting profile. Ambiguous links remain `review_pending`; there is no steward UI or calibrated match probability. |
| Vector document search and an agent-style Q&A planner | Document answers use governed source IDs and section mappings; transcript facts use text patterns. Released questions use deterministic routes. Unknown safe analytics can use an optional LLM SQL planner, validated with SQLGlot before read-only DuckDB execution. There is no vector index. |
| Next.js application | Streamlit has Customer, Ask, Recommendation, and Worklist tabs. Ask has explicit All Collections / This customer scope; linked customer SQL supports only narrow certified routes and refuses unsupported filters. |
| Managed AI decision service and online feature store | Local point-in-time feature helpers feed a LightGBM promise-kept model with SHAP reasons. A policy gate ranks allowed actions; a typed reviewer ID approves, modifies, or rejects a proposal into SQLite. No customer contact is executed. |
| Broad use of customer profile signals | Protected fields are excluded from published C360 outputs and model ranking. Vulnerability flags route only to specialist review. Offline text rules from pre-scoring notes and customer transcript turns are context only. |

The optional SQL-planning provider is Groq (`openai/gpt-oss-120b` by default with `GROQ_API_KEY`) or OpenAI (`gpt-5-mini` by default with `OPENAI_API_KEY`); OpenAI takes precedence if both are configured. The hero smoke test used deterministic Layer 2 routes, so it did not call either provider. The promise model runs locally with LightGBM.

## AI tools used

- Groq API (`openai/gpt-oss-120b`, fallback `openai/gpt-oss-20b`): SQL planning only for new Layer 2 analytics questions. The application validates and runs the SQL read-only in DuckDB, then builds answers solely from query results. The 34-question uncached first run had 33 non-error executions, 10 retries, and 172 seconds of rate-limit waits; one request failed before SQL execution. The text features use no API.
- OpenAI API: optional alternative provider for the same SQL-planning-only path; not used for the Groq live run.
- LightGBM and SHAP: local promise-kept estimation and explanation for decision proposals.
- Codex: implementation, test creation, and development workflow assistance.

## Honest limitations

The channel score assumes `0.8 × smoothed right-party-contact rate − 0.2 × normalized channel cost` using the previous 90 days and the customer's local time band. These weights are human assumptions, not learned treatment effects.

The release is synthetic and fixed at 28 September 2026. Identity confidence is rule based, and historical crosswalk availability cannot be proven. The time-split promise test had a 62.4% break rate versus 35.7% in training, so calibration can drift. LightGBM's test ROC-AUC was 0.677 and calibrated Brier score 0.2245; the signal is modest. The calibrated model does not beat logistic regression on every ranking measure. Text-rule precision and recall were measured on 500 public labels for each source, but those examples influenced rule writing and are not independent validation. Rules can miss paraphrases and languages. The annotation cache must be built offline before the demo; missing text means unknown, never no hardship.

Channel and time-band weights are explicit assumptions based on observational right-party-contact rates; agents chose the historical channels. The backtest establishes neither uplift nor fair causal treatment. Protected fields are used only in a separate restricted measurement script, never in model features, action ranking, or explanations. Vulnerability flags only route to specialist review and suppress ordinary collection actions. No deposits or transactions enter the current feature matrix, so Canada Child Benefit deposits cannot enter it. The app has typed reviewer IDs rather than production authentication, uses local SQLite audit records, and sends no customer contact. An operational pilot would need randomized or carefully controlled comparison, consent and policy review, authentication, monitoring, and outcome measurement before any uplift claim.
