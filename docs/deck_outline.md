# Collection Intelligence Platform — ten-slide outline

## 1. Problem

Collections agents need a linked customer view, grounded answers, and a
policy-checked proposal they can review before any action.

## 2. Built flow

The Streamlit Customer, Ask, Recommendation, and Worklist tabs connect a
Python/DuckDB C360 build, governed SQL/documents, point-in-time features,
LightGBM/SHAP, a policy gate, and SQLite review audit. Hero:
`G-39c6b287f70371cd9fc6`.

## 3. Golden customer and quality

31 source tables are profiled. Linked identities require rule confidence at
least 0.95, at least 0.05 lead over another candidate, and no conflicting
profile. The Why linked? table displays source record, matching evidence,
method, confidence, and status. Ambiguous links stay pending.

## 4. Governed Ask

All Collections is the default; This customer uses a narrow certified
crosswalk route. Unsupported filters are refused. Every non-refused answer
shows SQL or source IDs. The 34-question uncached fresh/blind run produced 33
non-error executions; 1 failed on Groq JSON validation before SQL. It took
349.93 seconds including 136.98 seconds setup, with 10 retries and 172 seconds
of rate-limit waits. This is an execution result, not an accuracy score.

## 5. Promise model evidence

On 54,657 test-period resolved promises: 62.4% broke. Logistic regression
ROC-AUC 0.677, broken-class PR-AUC 0.752, Brier 0.2492. Calibrated LightGBM
ROC-AUC 0.677, broken-class PR-AUC 0.746, Brier 0.2245. The constant test-rate
oracle Brier is 0.2347; the pre-July training-rate constant is 0.3059.
Isotonic calibration was fitted on a pre-test validation period.

## 6. Policy, reasons, and text

Policy blocks forbidden channels and routes hardship/vulnerability to a
specialist. SHAP supplies model reasons only after policy. Offline text rules
add dated context and cannot alone trigger adverse treatment. On 500 public
labels per source, hardship precision/recall was 1.000/0.815 for notes and
0.991/0.863 for transcripts. Delay-reason presence was 0.856/0.628 and
0.808/0.770. Public examples influenced rule writing, so these are
development-set results.

## 7. Human review and audit

Approve, modify, or reject requires reviewer ID and reason. Policy is checked
again during review. Audit events are append-only locally; no contact is sent.
The app shows each blocked action and its reason.

## 8. Worklist

Linked open promises are sorted by predicted break risk with the top SHAP
reason. It is a human review queue. The top 10% of test risks contained 12.9%
of broken promises; the top 20% contained 25.6%. The signal is modest.

## 9. Fairness and limitations

The restricted measurement script examined 52,283 linked test promises,
comparing predicted risk, observed break rate, and historical channel mix with
confidence intervals. Protected fields are measurement-only. Mean predicted
break risk was 0.540/0.541 for women/men, and 0.544/0.530 for citizens/permanent
residents. Break-rate drift was 35.7% training to 62.5% in the linked test
cohort. Agents selected historical channels; no causal fairness or uplift claim
follows from these observations.

## 10. Pilot and deployment boundary

Use a controlled pilot with fixed policy and model versions, explicit consent,
authentication, monitoring, and outcome measurement to test whether agent
decisions improve. The current demo is local, synthetic, and does not execute
customer contact. Exact dependencies and 185 tests are committed; the
fresh-clone check passed 183 tests before the latest two app tests were added.
