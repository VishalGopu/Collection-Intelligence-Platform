# Collections Intelligence Platform

Hackathon build for a golden customer view (C360), grounded collections questions, shared features, and an explainable Next Best Action.

## Work areas

| Path | Owner during parallel build |
| --- | --- |
| `src/c360/` | This laptop: raw-to-gold pipeline, identity resolution, data quality |
| `src/insights/` | Second laptop: certified metrics, document lookup, cited answers, refusals, benchmark runner |
| `src/features/` | Later integration: shared training/live feature definitions |
| `src/decisioning/` | Later integration: policy gate, scoring, reasons, human review |
| `contracts/` | Shared interface; coordinate changes before editing |
| `local_artifacts/` | Generated local files, ignored by Git |
| `submission/` | Final artifacts to commit for judging |

See [the parallel workflow](docs/PARALLEL_WORKFLOW.md) for folder ownership and integration steps. Each laptop downloads the dataset locally using [the dataset guide](docs/DATASET_DOWNLOAD.md). The dataset and virtual environment are not committed.

The build-phase requirements are in `build_phase.pdf`; the proposed architecture is in `HACKERS_SystemDesign.pdf`.

## How to run

Work from the repository root. Download the Maple release using [the dataset guide](docs/DATASET_DOWNLOAD.md); it must be extracted at `maple_data/maple_collections_release/`. The dataset and generated files are local and ignored by Git.

Windows PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r app\requirements.txt
.\.venv\Scripts\python.exe -m src.c360.build
.\.venv\Scripts\python.exe -m streamlit run app/main.py
```

Linux or macOS:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r app/requirements.txt
.venv/bin/python -m src.c360.build
.venv/bin/python -m streamlit run app/main.py
```

Open the local URL printed by Streamlit. The Customer tab starts with `G-39c6b287f70371cd9fc6`; choose another demo ID or paste a published golden ID. The Ask and Recommendation tabs show integration placeholders described in [the app interface note](app/INTERFACES.md). To verify Layer 1, run `python -m pytest tests/c360 -q` with the virtual-environment Python for your operating system after installing `pytest` into that environment.

## AI tools used (submission draft)

- Groq API (`openai/gpt-oss-120b`, fallback `openai/gpt-oss-20b`): SQL planning only for new Layer 2 analytics questions. The application validates and runs the SQL read-only in DuckDB, then builds answers solely from query results. A 24-question live API run has been completed.
- OpenAI API: optional alternative provider for the same SQL-planning-only path; not used for the Groq live run.
- Codex: implementation, test creation, and development workflow assistance.
