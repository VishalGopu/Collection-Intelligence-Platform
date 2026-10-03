# Collection Intelligence Platform — 10-slide deck outline

## 1. The collections decision problem

- Agents need one trusted customer view across CRM, cards, lending, core banking, and Collections.
- Questions must be grounded in certified metrics or policy sources.
- Recommendations must be explainable, policy-checked, and reviewed by a human.

## 2. What we built

- Four-layer flow: C360 data product, governed insights, decisioning, and human review.
- Streamlit demo connects Customer, Ask, Recommendation, and Worklist views.
- Hero demo: `G-39c6b287f70371cd9fc6`.

## 3. Layer 1 — golden customer view

- A reproducible Python/DuckDB batch profiles 31 source tables and publishes Parquet outputs.
- Identity links require confidence at least 0.95, a 0.05 lead, and no conflicting profile.
- Unlinked and review-pending records stay out of customer-level answers and decisions.

## 4. “Why linked?” and data quality

- The UI shows source keys, match method, evidence names, confidence, and link status.
- Quality gates cover uniqueness, referential integrity, confidence, amounts, and case resolution.
- Protected fields are excluded from published C360 outputs.

## 5. Layer 2 — grounded answers

- Deterministic routes answer the released benchmark with certified read-only DuckDB SQL, documents, and transcript evidence.
- Every answer displays SQL or source IDs, snapshot date, and metric definition when applicable.
- Refusals cover out-of-scope questions, protected-attribute profiling, bulk PII, and unsafe actions.

## 6. Layer 3/4 — prediction plus policy

- Point-in-time features feed a local LightGBM promise-kept model.
- SHAP factors explain the proposal; policy rules control permitted actions and specialist routing.
- Vulnerability flags route support review; they do not rank ordinary collection actions.

## 7. Human review and audit

- Proposals are pending until a reviewer approves, modifies, or rejects them.
- Reviewer ID and reason are required; review events are append-only in SQLite.
- The system never sends customer contact or activates a payment plan.

## 8. Worklist for operations

- Linked open promises are ranked by predicted break risk.
- The queue shows customer ID, case, risk, top reason, and model version.
- Leakage checks ensure source data is available before promise creation; the queue is a review list, not an action list.

## 9. Demo evidence and safeguards

- Live screenshots cover Customer, Why linked?, Ask SQL, refusal, recommendation, audit, and Worklist.
- Fresh-clone verification: 142 tests passed, two data-dependent skips, and the Streamlit health endpoint returned `ok`.
- Current boundary: the app passes golden-ID scope when Layer 2 exposes it; customer-scoped Ask remains clearly refused until then.

## 10. Design decisions and next step

- Streamlit and local DuckDB/SQLite keep the build reproducible and inspectable.
- Optional Groq/OpenAI SQL planning is validated and read-only; governed routes need no API key.
- Next integration step: Layer 2 exposes its scoped answer interface, then the app enables customer-scoped metrics without changing the UI contract.
