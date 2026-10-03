# Implementation status: C360 and Insight/NLP

Last reviewed: 3 October 2026
Dataset snapshot: 28 September 2026

## Executive summary

Two layers now have working implementations:

1. **Layer 1 — Data Product Factory (Golden C360):** the implementation is merged into `main`. It normalizes source records, resolves customer identities conservatively, generates the contracted C360 outputs, and enforces publication quality gates. A committed report records a successful full-data run. The generated Parquet outputs are local artifacts and are not currently present in this checkout, so the pipeline must be run here before end-to-end integration.
2. **Layer 2 — Insight and NLP:** a local MVP is implemented and validated against all 35 released benchmark questions. It provides governed SQL metrics, document-grounded answers, transcript summaries, evidence, and safety refusals. The implementation is currently an uncommitted working-tree change and uses read-only raw views until the local C360 outputs are generated.

The layers are individually implemented, but they are **not yet connected end to end**. C360 generation, Layer 2 integration through the identity crosswalk, and a final combined regression run remain outstanding.

## Layer 1 — Data Product Factory

### Clearly implemented

The Layer 1 implementation is in `src/c360/build.py` and includes:

- Read-only ingestion of the Maple release with DuckDB.
- Normalization of postal codes, telephone numbers, dates of birth, and names.
- Preservation of source identifiers as strings, including leading zeroes.
- CRM record deduplication using explicit duplicate references and national-ID hashes.
- Deterministic golden customer IDs derived from stable source evidence.
- Customer matching across CRM, cards, lending, core banking, and Collections.
- Confidence-aware matching using date of birth, postal code, telephone number, and surname evidence.
- Conservative publication thresholds:
  - minimum confidence of `0.95`;
  - at least `0.05` separation from the next candidate;
  - no conflicting source profile.
- `linked`, `review_pending`, and `unlinked` identity states.
- Collections-case resolution through the copied CRM reference, with a unanimous account-based fallback where appropriate.
- Quarantine of conflicting CRM and account evidence.
- Golden-customer rollups for open cases, maximum DPD, overdue balance, hardship, and channel consent.
- Fail-closed handling of unknown or conflicting consent values.
- Exclusion of protected attributes from the golden customer output.
- Automated uniqueness, referential-integrity, confidence-range, amount, and case-resolution quality gates.
- Publication of curated and gold Parquet files plus JSON and Markdown quality reports.

### Published interface

The frozen interface is defined by `contracts/golden_c360_v1.json`:

| Output | Grain | Local path |
| --- | --- | --- |
| Golden customers | One row per `golden_customer_id` | `local_artifacts/c360/golden_customers.parquet` |
| Identity crosswalk | One row per source system and source customer ID | `local_artifacts/c360/identity_crosswalk.parquet` |

Collections cases join through `source_system = 'collections'`. CRM-keyed contacts, promises, and notes join through `source_system = 'crm'`. Only records with `link_status = 'linked'` may participate in customer-level answers or decisions.

### Reported full-data results

The committed `submission/data_quality_report.md` records:

| Result | Value |
| --- | ---: |
| Golden customers | 1,001,258 |
| Collections case resolution | 99.623% |
| CRM records collapsed into existing identities | 18,742 |
| Golden customers needing profile review | 15,183 |
| Conflicting CRM/account case identities quarantined | 583 |
| Cases without a published customer link | 1,386 |
| Duplicate golden IDs | 0 |
| Duplicate source keys | 0 |

The additional golden IDs above the synthetic population count are intentionally kept separate rather than merged using weak evidence.

### Current Layer 1 status

**Status: code complete and merged; local regeneration pending.**

- Commit on `main`: `edfb102` (`Build confidence-aware golden C360 pipeline`).
- Contract and data-quality report are committed.
- The Python implementation compiles successfully in this checkout.
- The committed quality report demonstrates a successful full-data run in the producing environment.
- The ignored `local_artifacts/c360/` outputs are not currently present in this checkout.
- Dedicated `tests/c360/` automated tests have not yet been added.

## Layer 2 — Insight and NLP

### Clearly implemented

The Layer 2 implementation is under `src/insights/` and includes:

- A deterministic question router for all 35 released benchmark questions.
- Certified, read-only DuckDB SQL for structured collection metrics.
- Current-policy and procedure answers with document and section citations.
- Incident and release-note grounding for operational questions.
- Case-scoped retrieval of the most recent recorded call.
- Transcript summaries that extract the customer situation, promised amount/date, cease-contact request, and appropriate next step.
- Relative-date resolution for transcript phrases such as “Thursday” and “the 5th.”
- Answer cards containing:
  - question ID and question;
  - answer;
  - executed SQL or cited sources;
  - refusal status;
  - structured, document, transcript, or refusal mode.
- Explicit refusals for:
  - protected-attribute profiling or prioritization;
  - bulk PII export;
  - questions outside Collections scope.
- A SQL validator that permits only read-only `SELECT` and CTE statements and blocks mutation or administrative commands.
- A command-line interface for an individual question or automated benchmark generation.
- Automatic output in the required benchmark schema: `question_id`, `answer`, `sql_or_sources`, and `refused`.

### Validation completed

The implementation has been exercised against the installed 9.4 GB release:

| Check | Result |
| --- | ---: |
| Unit tests | 7 passed |
| Released benchmark questions executed | 35 of 35 |
| Unique benchmark question IDs | 35 |
| Empty answers | 0 |
| Answers without SQL/source evidence | 0 |
| Safety refusals | 5 |

The five refusals are the weather question, bulk Ontario PII export, postal-area hardship exclusion, citizenship-based prioritization, and gender/marital-status disclosure.

The generated local benchmark file is:

`local_artifacts/insights/benchmark_answers.csv`

It is intentionally ignored by Git until the final submission artifacts are selected.

### Current Layer 2 status

**Status: working and locally validated; uncommitted and awaiting C360 integration.**

- Source implementation and tests exist in the working tree.
- All seven current unit tests pass after the latest C360 merge.
- All released benchmark routes run successfully on real data.
- Structured metrics currently query the release's governed raw views, as allowed by the parallel-build workflow.
- Unknown analytical wording fails closed unless it matches a governed route; unrestricted NL-to-SQL is not implemented.
- The Layer 2 changes have not yet been committed or pushed.

## Alignment with build-phase requirements

| Build requirement | Current status | Evidence or remaining work |
| --- | --- | --- |
| Raw-to-curated-to-golden C360 pipeline | Implemented | `src/c360/build.py` |
| Customer matching across five source systems | Implemented | Confidence-aware identity crosswalk |
| Match confidence and identity quarantine | Implemented | Contracted confidence and link-status fields |
| Data-quality checks and report | Implemented | Quality gates and `submission/data_quality_report.md` |
| Plain-English Collections questions | Implemented for released benchmark | Layer 2 deterministic router |
| SQL or source shown with every answer | Implemented | Answer-card evidence field |
| Out-of-scope refusal | Implemented | Guardrails and five benchmark refusals |
| Questions answered over C360 | Pending integration | Layer 2 still uses raw views |
| Automated benchmark CSV | Implemented | 35-row local benchmark output |
| End-to-end four-layer demonstration | Not complete | Layers 3 and 4 are still pending |

## Alignment with the system design

The current implementation follows the system design's central controls: conservative identity resolution, confidence and quarantine, read-only governed queries, evidence with every answer, case-scoped transcript access, protected-attribute restrictions, and safe refusal.

The following system-design capabilities remain future work:

- Role-based authorization and assigned-case access control.
- Semantic-catalog routing driven directly from `metric_definitions.csv`.
- General typed natural-language query planning.
- SQL AST validation with SQLGlot rather than the current deterministic validator.
- Hybrid keyword/vector document retrieval.
- Agent-note retrieval and cohort-scoped hybrid SQL/RAG.
- Citations to individual transcript turns.
- Freshness and certified-metric-definition metadata on answer cards.
- Immutable audit logs for questions, SQL, evidence, and responses.
- Prompt-injection defenses for retrieved unstructured content.

These are gaps against the full design, not blockers for the current deterministic build-phase MVP.

## Integration status and next actions

Current flow:

```text
Maple raw release
   ├── Layer 1 C360 pipeline ──> contracted Parquet outputs (must be generated locally)
   └── Layer 2 governed raw views ──> validated benchmark answers

Target integrated flow:

Maple raw release ──> Layer 1 C360 + identity crosswalk
                            │
                            └──> Layer 2 linked/approved customer scope ──> grounded answers
```

Recommended next actions, in order:

1. Run the C360 pipeline in this checkout and verify both contracted Parquet files and the local quality report.
2. Add Layer 1 automated tests for contract schema, uniqueness, link-status behavior, and quality-gate failure cases.
3. Update Layer 2 customer-level and case-level routes to consume the C360 identity crosswalk:
   - Collections cases: `source_system = 'collections'`;
   - contacts, promises, and notes: `source_system = 'crm'`;
   - always require `link_status = 'linked'`.
4. Run the full 35-question regression suite after C360 integration and compare development answers with the published tolerances.
5. Commit and push the Layer 2 implementation after review.
6. Begin the shared feature store and decisioning layers only after the integrated Layer 1/Layer 2 contract is stable.
