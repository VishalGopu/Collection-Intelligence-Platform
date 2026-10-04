# Collections Intelligence Platform

Hackathon build for a golden customer view (C360), grounded collections questions, shared features, and an explainable Next Best Action.

The Streamlit interface is a **CIBC-themed concept demo** based on the supplied CIBC screenshot. Its [CIBC logo](https://www.cibc.com/content/dam/global-assets/logos/cibc-logos/no-tagline/cibc-logo-colour-142x36.svg) is from CIBC's public site; CIBC owns its marks. The app uses a synthetic Maple data release and local demo sign-in, so it must not be presented as a CIBC production system or online banking login.

## Work areas

| Path | Purpose |
| --- | --- |
| `src/c360/` | Raw-to-gold pipeline, identity resolution, data quality |
| `src/insights/` | Certified metrics, document lookup, cited answers, refusals, benchmark runner |
| `src/features/` | Shared point-in-time feature definitions |
| `src/decisioning/` | Policy gate, scoring, reasons, human review |
| `app/` | Streamlit sign-in, dashboard, Customer 360, Ask, decision review, and priority queue |
| `contracts/` | Published data interface |
| `local_artifacts/` | Generated local files, ignored by Git |
| `submission/` | Final artifacts to commit for judging |

Download the synthetic release from [the Maple dataset](https://huggingface.co/datasets/nuxsh/maple-collections-hackathon) and extract it under `maple_data/maple_collections_release/`. The dataset, virtual environment, text annotation cache, and generated Parquet files are not committed.

The submission artifacts are the [architecture diagram](submission/architecture_built.png), [C360 contract](contracts/golden_c360_v1.json), [data-quality report](submission/data_quality_report.md), and [benchmark answers](submission/benchmark_answers.csv).

## How to run

For a fresh clone, work from the repository root and extract the Maple release at `maple_data/maple_collections_release/`. The dataset and generated files are local and ignored by Git. Python 3.14 is the verified version.

Windows PowerShell:

```powershell
git clone git@github.com:VishalGopu/Collection-Intelligence-Platform.git
cd Collection-Intelligence-Platform
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m src.c360.build
.\.venv\Scripts\python.exe -m app.prepare_customer_data
.\.venv\Scripts\python.exe -m src.features.training
.\.venv\Scripts\python.exe -m src.features.candidates --base local_artifacts/features/open_promise_features.parquet --output local_artifacts/features/open_promise_candidates.parquet
.\.venv\Scripts\python.exe -m src.features.text_rules
.\.venv\Scripts\python.exe -m src.features.text_data
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe -m app.smoke
.\.venv\Scripts\python.exe -m streamlit run app/main.py
```

Linux or macOS:

```bash
git clone git@github.com:VishalGopu/Collection-Intelligence-Platform.git
cd Collection-Intelligence-Platform
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m src.c360.build
.venv/bin/python -m app.prepare_customer_data
.venv/bin/python -m src.features.training
.venv/bin/python -m src.features.candidates --base local_artifacts/features/open_promise_features.parquet --output local_artifacts/features/open_promise_candidates.parquet
.venv/bin/python -m src.features.text_rules
.venv/bin/python -m src.features.text_data
.venv/bin/python -m pytest tests -q
.venv/bin/python -m app.smoke
.venv/bin/python -m streamlit run app/main.py
```

Download the dataset before the build command. Open the local URL printed by Streamlit. The local demo sign-in uses `manager / demo` or `agent / demo`; set `COLLECTIONS_DEMO_PASSWORD` in the ignored `.env` to replace the shared demo password. The manager opens on a portfolio dashboard; the specialist opens on the priority queue. The sidebar links to Customer 360, Ask Collections, and Decision review. Customer 360 starts with `G-39c6b287f70371cd9fc6`; browse the catalog or paste another published golden ID. Ask defaults to **All Collections**. Choose **This customer** only for a certified linked-customer route; unsupported scoped filters are refused. Every non-refused answer shows SQL or readable sources. The specialist can record approve/modify/reject reviews; the manager can inspect proposals but cannot submit a review through the UI. The smoke command writes a local test rejection to the ignored audit database. Stop the app with Ctrl+C.

For the official benchmark output, run `python -m src.insights.submission --questions questions.csv --output answers.csv` from the repository root (use the venv's Python on either OS). The output columns are exactly `question_id,answer,sql_or_sources,refused`.

**Browse all linked customers** searches and pages through the full published C360 catalog (1,001,258 linked golden IDs in this release), 10 at a time, without loading all IDs into Streamlit. The activity filter defaults to customers with both open cases and promises; switch it to open cases, any promise, broken promises, open promises, or all linked customers. The row shows open-case and linked promise counts. Click a row to make it the selected customer. Rebuild the local customer-page cache with `python -m app.prepare_customer_data` after updating the data or C360 crosswalk.

`app.prepare_customer_data` builds an ignored DuckDB cache of only the Customer page's approved source columns, with lookup indexes. Build it once after the C360 output; the catalog browser requires it, while an individual customer lookup can fall back to the raw release. On this laptop, the hero's uncached customer load took 43.0 seconds and the indexed load took 1.57 seconds; the second customer's load fell from 48.0 to 0.85 seconds. The cache build took about 25 seconds and uses a 1 GB DuckDB memory limit.

The [implemented architecture diagram](submission/architecture_built.png) shows the built components, AI use, and human review.

## What changed from the design

| Proposed design | Built behavior |
| --- | --- |
| Dagster, dbt and Great Expectations for the data product | One reproducible Python/DuckDB batch creates curated and golden Parquet files, with publication quality gates and a 31-table profile. |
| Splink-style probabilistic identity matching and steward workflow | Rule-based matching publishes a link at confidence ≥0.95 only with a ≥0.05 lead over the next candidate and no conflicting profile. Ambiguous links remain `review_pending`; there is no steward UI or calibrated match probability. |
| Vector document search and an agent-style Q&A planner | Document answers use governed source IDs and section mappings; transcript facts use text patterns. Released questions use deterministic routes. Unknown safe analytics can use an optional LLM SQL planner, validated with SQLGlot before read-only DuckDB execution. There is no vector index. |
| Next.js application | Streamlit has a CIBC-themed concept UI with demo sign-in, portfolio dashboard, priority queue, Customer 360, Ask, and Decision review. Ask has explicit All Collections / This customer scope; linked customer SQL supports only narrow certified routes and refuses unsupported filters. |
| Managed AI decision service and online feature store | Local point-in-time feature helpers feed a LightGBM promise-kept model with SHAP reasons. A policy gate ranks allowed actions; a typed reviewer ID approves, modifies, or rejects a proposal into SQLite. No customer contact is executed. |
| Broad use of customer profile signals | Protected fields are excluded from published C360 outputs and model ranking. Vulnerability flags route only to specialist review. Offline text rules from pre-scoring notes and customer transcript turns are context only. |

Unknown safe analytics questions can use Gemini, Groq, or OpenAI for SQL planning. Put the selected key in the ignored `.env` and set `INSIGHTS_LLM_PROVIDER=gemini`, `groq`, or `openai`. Gemini uses `GEMINI_API_KEY` and defaults to `GEMINI_MODEL=gemini-flash-latest`; Groq uses `GROQ_API_KEY` and defaults to `GROQ_MODEL=openai/gpt-oss-120b` with its existing backup model. OpenAI remains available through `OPENAI_API_KEY`. If no provider is selected, the old OpenAI-then-Groq precedence remains. The planner's output still goes through SQLGlot validation and read-only DuckDB execution. The hero smoke test uses deterministic routes and calls no provider. The promise model runs locally with LightGBM.

## AI tools used

- Groq API (`openai/gpt-oss-120b`, fallback `openai/gpt-oss-20b`): SQL planning only for new Layer 2 analytics questions. The application validates and runs the SQL read-only in DuckDB, then builds answers solely from query results. The 34-question uncached first run had 33 non-error executions, 10 retries, and 172 seconds of rate-limit waits; one request failed before SQL execution. The text features use no API.
- OpenAI API: optional alternative provider for the same SQL-planning-only path; not used for the Groq live run.
- Gemini API (`gemini-flash-latest` alias): optional SQL-planning provider through `generateContent`; selected by `.env` on this laptop. A live planner call completed in 2.6 seconds without retries. An end-to-end uncached Ask call took 29.9 seconds, mostly from loading and querying the local release rather than model inference. The alias can change the underlying model over time; set `GEMINI_MODEL` to a fixed version for reproducible later runs.
- LightGBM and SHAP: local promise-kept estimation and explanation for decision proposals.
- Codex: implementation, test creation, and development workflow assistance.

## Honest limitations

The channel score assumes `0.8 × smoothed right-party-contact rate − 0.2 × normalized channel cost` using the previous 90 days and the customer's local time band. These weights are human assumptions, not learned treatment effects.

The release is synthetic and fixed at 28 September 2026. Identity confidence is rule based, and historical crosswalk availability cannot be proven. The time-split promise test had a 62.4% break rate versus 35.7% in training, so calibration can drift. LightGBM's test ROC-AUC was 0.677 and calibrated Brier score 0.2245; the signal is modest. The calibrated model does not beat logistic regression on every ranking measure. Text-rule precision and recall were measured on 500 public labels for each source, but those examples influenced rule writing and are not independent validation. Rules can miss paraphrases and languages. The annotation cache must be built offline before the demo; missing text means unknown, never no hardship.

Channel and time-band weights are explicit assumptions based on observational right-party-contact rates; agents chose the historical channels. The backtest establishes neither uplift nor fair causal treatment. Protected fields are used only in a separate restricted measurement script, never in model features, action ranking, or explanations. Vulnerability flags only route to specialist review and suppress ordinary collection actions. No deposits or transactions enter the current feature matrix, so Canada Child Benefit deposits cannot enter it. The sign-in and role restriction are local demo UI controls, not production authentication or authorization; the default demo password is public and can be overridden through `.env`. Reviews use local SQLite audit records, and the app sends no customer contact. An operational pilot would need controlled comparison, consent and policy review, real authentication and authorization, monitoring, and outcome measurement before any uplift claim.
