# Collections Intelligence Platform

A CIBC-themed **concept demo** for collections teams, built on the synthetic Maple Bank release dated **28 September 2026**. It connects customer records, answers collections questions with visible evidence, ranks open promises for review, and proposes policy-checked next steps. It is not a CIBC production system. The CIBC mark in the app belongs to CIBC.

## What is implemented

| Layer | Working component |
| --- | --- |
| Customer 360 | `src/c360/build.py` normalizes CRM, cards, lending, core banking, and collections records. DuckDB produces curated tables, `golden_customers.parquet`, and `identity_crosswalk.parquet`. Uncertain matches stay pending or unlinked; publication checks and a data-quality report record the counts. |
| Ask Collections | `src/insights/engine.py` answers supported metrics with governed SQL, retrieves passages from release policy/procedure documents, and summarizes supported call transcripts. Unknown analytics can use Gemini, Groq, or OpenAI to plan read-only SQL. SQLGlot validation and constraint checks run before DuckDB executes it; the answer displays SQL or sources. The default scope is the whole portfolio. Customer scope uses linked C360 records for a limited set of certified questions. |
| Features | `src/features/` builds dated, point-in-time structured promise features and rule-derived context from notes and transcripts. Training and scoring share approved feature definitions. Text signals are shown as context, not used as model inputs or sole grounds for adverse treatment. |
| Decisioning | The committed LightGBM artifact predicts **P(promise kept)**. The priority queue displays **1 − P(kept)** for linked open promises and SHAP model factors. A separate rule-based policy gate blocks impermissible actions and routes hardship or vulnerability to specialist review. A specialist can approve, modify, or reject a proposal; SQLite records the review. No customer contact is sent. |

The Streamlit app in `app/main.py` has a portfolio dashboard, Priority queue, Customer 360, Ask Collections, and Decision review. The local demo login provides `manager` and `agent` views; it is not production authentication. The manager can inspect proposals, while the agent view can record reviews.

## Run locally

Download the **core** release from the [Maple Collections dataset](https://huggingface.co/datasets/nuxsh/maple-collections-hackathon), then extract it so `maple_data/maple_collections_release/data/customers.csv` exists. The voice ZIP is optional. Run commands from the repository root using **Python 3.14**. The release and generated `local_artifacts/` are ignored by Git. The trained model is already committed, so setup does not retrain it.

Windows PowerShell:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m app.bootstrap
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe -m streamlit run app/main.py
```

Linux or macOS:

```bash
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m app.bootstrap
.venv/bin/python -m pytest tests -q
.venv/bin/python -m streamlit run app/main.py
```

`app.bootstrap` runs the C360 build, indexed customer-page cache, structured feature builds, and offline text extraction **sequentially**. These are substantial data jobs; do not run them alongside model training or the benchmark. If the artifacts already exist, start Streamlit directly. Open the URL printed by Streamlit (normally `http://localhost:8501`). Sign in with `manager / demo` or `agent / demo`, unless `COLLECTIONS_DEMO_PASSWORD` is set in an ignored `.env` file.

Docker Compose is also available through `compose.yaml`: after placing the release locally, run `docker compose build`, `docker compose run --rm collections python -m app.bootstrap`, and `docker compose up -d collections`. Its default host URL is `http://localhost:8504`. Compose mounts the dataset, local artifacts, and submission directory; it does not bundle the release or secrets. The Python setup above is the verified primary path.

## Follow a customer through the app

On **Priority queue**, click **Refresh priority queue**. The table ranks linked open Promise-to-Pay records by estimated break risk. For example, `PTP-3511285` is linked to `G-883e676faa7837d10aa7`; its displayed DPD and overdue amount are values **when the promise was made**, not current case totals. Select its row to open Customer 360. **Why these records are linked** shows source keys, matching evidence names, a rule score, and link status without exposing raw identity fields. The Cases, Promises, Contacts, and Accounts tabs then connect the case and account history under one golden ID.

Open **Decision review** for that customer and generate a proposal. Its case is in a legal status, so policy blocks ordinary outreach even though its open promise ranks high. The page shows the blocked actions, model factors, and pending audit row. Sign in as `agent` to record an approve/modify/reject review with a reason. Approval records a review; it does **not** execute contact.

On **Ask Collections**, leave **All Collections** selected and ask `How many open cases are there, and list top 10?`. The result shows the portfolio count, a ranked table, and the executed SQL. Choose **This customer** only for a supported linked-customer question. The system refuses unsafe requests and unsupported customer filters rather than silently dropping them. Policy answers display document sources; ad hoc policy retrieval reads the latest English release documents rather than storing benchmark answer text in code.

For official benchmark output, run `python -m src.insights.submission --questions <questions.csv> --output <answers.csv>`. The four columns are `question_id,answer,sql_or_sources,refused`. The committed [benchmark answers](submission/benchmark_answers.csv) contain **50 generated rows**, including the 15 extra questions; **8 are refusals**. This is an execution result, not an accuracy score, and LLM answers can vary with provider availability and generated SQL.

## Model and responsible use

The committed `src/decisioning/artifacts/promise_kept_lightgbm.joblib` uses structured, pre-promise features such as DPD and overdue balance at creation, earlier broken promises, recent contacts, card utilisation, an earlier bureau score, earlier kept rate, and days since a prior payroll credit. The feature matrix excludes protected attributes, vulnerability flags, and deposits/transactions; Canada Child Benefit deposits cannot enter it. Vulnerability and hardship indicators are **routing safeguards only**. The offline note/transcript rules add dated context, not model features.

The evaluation uses a chronological split: **137,149** resolved promises in the pre-July training period and **54,657** in the July–September test period. A separate May–June validation period fits isotonic calibration; test labels are not used for calibration. On the test period, calibrated LightGBM reached **ROC-AUC 0.677** and **Brier score 0.2245**. The test break rate was **62.4%**, compared with **35.7%** in training, so the signal is modest and probability calibration can drift. Logistic regression and eligible historical `model_scores` are comparisons in the committed metrics report.

The promise model estimates what may happen. It does **not** choose a customer action. Action ranking is an explicit rule using observed right-party-contact rates by channel/time band and contact cost, with assumed weights of `0.8` and `−0.2`. Policy checks run before an action can be proposed. SHAP explains model associations, not causes or policy permission. Historical channels were selected by agents, so the backtest does not establish action uplift. A production pilot would need real authentication and authorization, monitored refreshes, policy review, and a controlled outcome comparison.

## Submission and design changes

The repo keeps the required [architecture diagram](submission/architecture_built.png), [Golden C360 data contract](contracts/golden_c360_v1.json), [data-quality report](submission/data_quality_report.md), and [benchmark answers](submission/benchmark_answers.csv). The contract specifies owner, schema, quality rules, allowed uses, and refresh. The small trained model and its [evaluation metrics](src/decisioning/artifacts/promise_model_metrics.json) are committed. The dataset and generated C360/features stay local.

The original design proposed orchestration tools, probabilistic identity matching, a vector document index, a Next.js interface, and a managed decision service. The built version uses reproducible Python/DuckDB batches, conservative rule-based identity links, source-document passage retrieval, Streamlit, a local LightGBM model, explicit policy rules, and SQLite audit. There is no vector index, live customer-contact execution, or production steward workflow.

AI is used for the trained LightGBM prediction and optional LLM **SQL planning** for unfamiliar safe analytics questions; SHAP explains the model. Gemini is selected with `INSIGHTS_LLM_PROVIDER=gemini` and `GEMINI_API_KEY`; Groq and OpenAI are optional alternatives. When Gemini returns a 429/503 and a Groq key is configured, the planner can fall back to Groq. SQL execution, identity matching, text extraction, policy checks, action ranking, dashboard calculations, and audit writes are deterministic code. Codex assisted implementation and tests.
