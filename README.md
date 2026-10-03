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

## AI tools used (submission draft)

- OpenAI API: optional structured SQL planning for new Layer 2 analytics questions. Generated SQL is validated and executed read-only in DuckDB; current live API validation is pending available account credits.
- Codex: implementation, test creation, and development workflow assistance.
