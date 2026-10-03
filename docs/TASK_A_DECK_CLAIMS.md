# Task A: claims the deck can support

## Demonstrated strengths

- A linked golden or CRM customer ID returns a policy-gated recommendation,
  ranked permitted alternatives, three actual SHAP factors, and an append-only
  decision record. A reviewer can approve, modify or reject it. The Streamlit
  hero flow was exercised end to end.
- A chronological July–September test has 54,657 resolved promises. Calibrated
  LightGBM has ROC AUC **0.6767**, broken-promise PR-AUC **0.7463** and Brier
  **0.2245**, compared with a constant-at-test-rate Brier **0.2347**. The
  logistic baseline has ROC AUC **0.6770**. This is modest discrimination and
  calibration improvement, not a breakthrough.
- Point-in-time joins, an allowlisted model matrix, CCB exclusion, protected
  field checks and a policy gate prevent high predicted risk from overriding
  forbidden actions. Support flags route to specialist review rather than
  becoming model inputs.
- Reused local model/data caches make repeated demo calls fast on one measured
  Windows host: median **1.9 ms** for `recommend()` and **0.19 ms** for
  `worklist(20)` after initialization. These are local, warm-cache measurements.

## Limits to state plainly

- The synthetic dataset is observational. Agents selected channels; the
  backtest estimates promise outcomes, not which action causes repayment.
  Channel weights are explicit assumptions. No recovery or treatment uplift
  has been established.
- The broken-promise rate shifts from **35.7%** in pre-July training to
  **62.4%** in the full test (62.5% in the linked fairness cohort). Residual
  miscalibration, synthetic-label artifacts and missing source-availability
  timestamps limit deployment claims.
- The full linked fairness check reports descriptive group differences with
  customer-clustered intervals. Protected fields are measurement-only.
  Historical channel mix is not the mix of model recommendations. The analysis
  cannot attribute group differences to the model or show parity.
- Text extraction is **pending**, not validated: 500 note and 500 transcript
  public labels were prepared, but the shared Groq key was unavailable after
  the 18:00 IST cutoff. Do not put text precision/recall or a text-enabled
  prediction claim in the deck. The current text outputs are unknown and cannot
  trigger adverse treatment.

## What a pilot must show before any uplift claim

1. Freeze the policy gate, model version, eligibility, outcomes and adverse
   event guardrails. Keep all decisions under human review; do not randomize
   into a prohibited contact or away from required specialist support.
2. Within policy-permitted options, randomly assign customers to the current
   process and the proposed workflow. Record assignment, actual action,
   consent, delivery and outcomes. Pre-register the primary outcome (for
   example, kept promise or net recovery by a fixed date) and a sample-size
   calculation; monitor complaints, contact burden and group-level harms.
3. Estimate the difference between assigned groups with uncertainty intervals,
   including an intent-to-treat analysis. Only a favorable, adequately powered
   randomized comparison with acceptable guardrails supports an uplift claim.

Random assignment is the basis for a direct treatment comparison; see the
[NIST explanation of completely randomized designs](https://www.itl.nist.gov/div898/handbook/pri/section3/pri331.htm).

Evidence in this repository: `src/decisioning/artifacts/promise_model_metrics.json`,
`src/decisioning/artifacts/brier_reconciliation.md`,
`src/decisioning/artifacts/fairness_test_period.md`,
`src/decisioning/artifacts/latency_report.json`, and
`src/decisioning/artifacts/text_public_evaluation.json`.
