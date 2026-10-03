# Layer 3/4: Next Best Action

`RecommendationEngine.recommend(customer_id)` now reads an approved identity,
applies policy controls, routes support cases to internal specialist review,
ranks permitted channels, returns a factual plain-English reason, and persists
the recommendation. `approve`, `modify`, and `reject` write append-only review
events. No contact is sent and no payment plan is activated.

The promise-kept model adds a probability and the three largest **actual SHAP**
factors for linked customers. It estimates keeping a hypothetical promise if
one were made at the snapshot date. It does not decide the contact channel.

## Reproduce

From the repository root, using the environment described in the dataset guide:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe src/c360/build.py
.\.venv\Scripts\python.exe -m src.features.training
.\.venv\Scripts\python.exe -m src.features.candidates
.\.venv\Scripts\python.exe -m src.features.candidates --base local_artifacts/features/open_promise_features.parquet --output local_artifacts/features/open_promise_candidates.parquet
.\.venv\Scripts\python.exe -m src.decisioning.train
.\.venv\Scripts\python.exe -m src.decisioning.restricted.fairness
.\.venv\Scripts\python.exe -m pytest tests/features tests/decisioning -q
.\.venv\Scripts\python.exe -m src.decisioning.demo
.\.venv\Scripts\python.exe -m src.decisioning.cli recommend G-39c6b287f70371cd9fc6
```

Python API:

```python
from src.decisioning import RecommendationEngine

engine = RecommendationEngine()
try:
    result = engine.recommend("G-39c6b287f70371cd9fc6")
    event = engine.approve(result["decision_id"], "reviewer-1", "Reviewed evidence and policy checks")
finally:
    engine.close()
```

Review from the CLI, replacing the decision ID with the returned value:

```powershell
python -m src.decisioning.cli approve DECISION_ID --reviewer reviewer-1 --reason "Reviewed policy checks"
python -m src.decisioning.cli modify DECISION_ID --reviewer reviewer-1 --action wait --reason "Defer contact"
python -m src.decisioning.cli reject DECISION_ID --reviewer reviewer-1 --reason "Reject proposed contact"
```

Each decision has one terminal review event. Modification records the reviewer's
chosen final action. Review revalidates the frozen source context; a high score
or reviewer cannot override a policy block. Reviewer and reason are required.
SQLite prevents updates/deletes through ordinary SQL; filesystem administrators
can still alter the database. This is not a tamper-proof production audit service
or an authenticated reviewer system.

## Identity and frozen time

The adapter accepts CRM IDs or golden IDs. It reads the existing C360 contract,
checks required columns, source-key uniqueness, string IDs, linked confidence and
referential integrity. Case, account and external joins use their own source
namespace and `link_status='linked'`. Golden profiles with `dq_status=needs_review`
cannot generate outbound recommendations.

If C360 files are absent, the CRM bootstrap returns `wait` for manual identity
review; it never guesses cross-system joins or permits contact. The committed
real-data demos use **linked** customers:

| CRM ID | Golden ID | Result |
| --- | --- | --- |
| AAA-4262 | G-b1714eca2809e88d7587 | Call |
| AAA-7546 | G-c4a6b6148266a0018109 | Specialist review; proposed certified agent AG-1584 |
| RUB-7738 | G-39c6b287f70371cd9fc6 | Documented C360 hero; same specialist action for CRM or golden ID |

Default prediction time is **2026-09-28 16:00 UTC**, explicitly tied to the frozen
release snapshot. Current-state inputs are never used for dates outside that
snapshot day. The demo treats 28 September as a non-holiday; a live implementation
requires a maintained regional holiday calendar and fresh versioned state.
Policy tests cover unknown holiday status, holidays and Sunday windows. Agent
selection proposes an active certified agent with capacity; it does not reserve
capacity or execute an assignment.

## Policy and support controls

`POL-COLL-001 v3.0` and `POL-COLL-004 v4.2` are the supplied synthetic policies.
The gate covers consent, cease communication, authorised representatives,
customer-local contact windows, conservative rolling-seven-day caps, open
disputes, complaints, insolvency, deceased and fraud holds. Calls and payment
reminders share a conservative cap: all outbound SMS/email/push/IVR events are
counted as payment reminders. Cap enforcement aggregates the customer's linked
active cases, which can block more contact than the per-case policy requires.
Unknown/conflicting consent blocks the channel; unknown critical safety status
blocks outbound actions. Payment-plan discussion uses call transport and is
subject to the same call controls.

Hardship triggers specialist review and suppresses ordinary collection actions.
`customers.vulnerability_flag`, `collections_cases.vulnerable_customer_flag`,
and `contact_history.vulnerability_disclosed_flag` are used **only** for this
support route. They never enter numerical features, ranking, repayment models
or risk explanations. Prefer an active agent with
`vulnerable_customer_certified=true`, and hardship skills when needed. If none is
available, retain specialist review without claiming an agent was assigned.
Earlier support disclosures and cease requests are conservatively retained for
review because the release does not provide complete revocation history.
Insolvency/deceased/fraud/identity holds take precedence over the support route.

Hardship programmes are not automatically offered or approved in this first
slice. The specialist must assess eligibility; the next phase will evaluate the
effective `hardship_programs` rows and all eligibility/evidence requirements.

The exact forbidden inputs are `gender_code`, `marital_status`,
`citizenship_status`, `household_size`, `dependants_count`,
`newcomer_program_flag`, `newcomer_arrival_date`, `accessibility_needs_flag`,
`accessibility_type`, `vulnerability_type`, `customer_accent_region`, and
`deposit_accounts.ccb_deposit_flag`. These fields are never selected for ranking
or explanations. No deposit/transaction feature is built, so Canada Child
Benefit deposits are excluded entirely at this stage. Age/DOB are also excluded
from numerical decision features.

## Explicit ranking assumptions and evidence limits

From `contact_history`, use observed outbound right-party-contact rates by
channel and local time band over the prior 90 days. Bands are morning (00–11),
afternoon (12–16), and evening (17–23); policy separately blocks contact outside
permitted hours. Evidence is global, without demographic cohorting.

The MVP score is an **assumed utility**, not a repayment probability:

```text
0.8 × smoothed_RPC_rate − 0.2 × mean_channel_cost / highest_observed_channel_cost
smoothed_RPC_rate = (right_party_contacts + 1) / (attempts + 2)
payment-plan discussion: call score + 0.05, only after ≥2 earlier broken promises
wait score = 0.02
```

Only policy-permitted actions enter ranking. A channel without observed RPC/cost
evidence is not ranked. Ties are resolved deterministically by action name.
The empirical RPC rates and assumed weights are returned in structured fields.
`probabilities.promise_kept` comes from the separate LightGBM model. Its
plain-English reason uses the actual top three SHAP factors and policy facts;
the user can inspect feature names, values, directions and log-odds
contributions in `shap_reasons`. For specialist cases, the specialist route
remains mandatory regardless of the model probability or explanation.

These rates are **observational**: agents chose the channels, so the ranking
does not estimate causal treatment effects. In the demo afternoon band, call
RPC is about 39.77%, while all three digital channels have zero recorded RPCs.
The flag may be call-oriented; zero does not prove that digital reminders have
no benefit. This metric favours calls under the current assumptions. Historical
event timestamps establish the implemented cutoff, but not a complete source
arrival/availability history. Current-profile fields are used only for the
snapshot demo's safeguards, not historical training.

## Promise-kept model and backtest

`src/features/training.py` builds one-row-per-promise training and open-promise
Parquet tables. The final model uses eleven allowlisted numeric features. It uses
contacts, earlier resolved promises, earlier employer payroll credits, prior
monthly card snapshots and bureau pulls dated before each promise. The
source-provided DPD, overdue balance and prior broken count are explicitly
recorded at promise creation. Labels come from later observed `kept` or `broken`
outcomes. No present-day account balances or protected/support flags enter
the training matrix. Source availability timestamps are incomplete, and the
historical bureau join uses a later C360 identity mapping.

The chronological split trains only on promises **created and resolved before
1 July 2026**, then tests promises created from 1 July through the snapshot.
This excludes 5,014 early promises whose outcomes were recorded after the
training cutoff. The train set has 137,149 rows (64.30% kept); the test set has
54,657 rows (37.61% kept). This large shift weakens probability calibration.
The model itself fits 121,784 cases created and resolved before 1 May; isotonic
calibration fits 13,465 different cases created from 1 May and resolved before
1 July. The July-onward test labels enter neither fit. The reported reliability
table and Brier score still show residual miscalibration.

| Model | Test rows | ROC AUC | PR-AUC (broken) | Brier | Top 10% broken capture | Top 20% broken capture |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Logistic regression | 54,657 | 0.6770 | 0.7523 | 0.2492 | 13.05% | 25.67% |
| LightGBM, raw | 54,657 | 0.6781 | 0.7530 | 0.2465 | 12.89% | 25.61% |
| LightGBM, isotonic | 54,657 | 0.6767 | 0.7463 | 0.2245 | 12.95% | 25.60% |

The signal is modest. The test broken-promise rate is **62.39%**. A constant
prediction at the observed test rate has Brier **0.2347** (oracle reference);
using the pre-July train rate as a deployable constant gives **0.3059**.
Calibrated LightGBM improves on both, but only slightly on the test-rate oracle.
The logistic baseline uses all eligible pre-July training labels, while
LightGBM reserves May-June for calibration and therefore fits fewer rows.
The older **0.2391** Brier came from the v2 LightGBM fitted on all 137,149
pre-July rows. The v3 **0.2465** raw Brier comes from a new model fitted on
121,784 pre-May rows, leaving May-June for isotonic calibration. The calibrated
v3 Brier is **0.2245**. The calibrator never saw test-period labels; full
reconciliation is in `artifacts/brier_reconciliation.md`.
Top-decile capture only modestly exceeds random ranking. The committed metrics JSON includes
the full reliability table, risk-decile lift table and same-row comparisons to
pre-promise `model_scores`.

In the feature round, employer-only payroll timing and earlier kept rate helped.
Card utilisation stayed, while bureau score change was removed after its
time-holdout ablation improved results. Days since last contact had negligible
gain and slightly worse Brier. Promise amount divided by overdue produced an
implausible AUC above 0.94 in this synthetic dataset, so it was excluded as a
likely outcome-generation artifact. `employer_flag='Y'` excludes benefits and
other income; no CCB deposit or transaction source is used. This same holdout
selected features, so the measured gains may be optimistic.

The supplied `model_scores` comparison uses only scores timestamped **before**
each promise. Rows marked `uses_protected_attributes=true` or with an unknown
flag are discarded. The existing `ptp_break` model has 1,881 eligible test
rows: AUC **0.7129** versus **0.6809** for logistic regression and **0.6826**
for LightGBM on those exact rows. Its Brier score and calibration bins are in
the report. The `collections_risk` score covers 11,584 rows, but predicts a
different target; its inverse is a directional proxy only. Its AUC is 0.5484,
versus 0.6340 and 0.6290 for our models on the same rows. These subset results
are not directly comparable with the full 54,657-row test metrics.

The channel data is observational: agents chose channels, and customers with
promises are selected. This backtest **does not establish treatment uplift** or
show that one channel causes more repayment. The explicit channel weights above
are assumptions and do not come from the promise-kept model.

## Streamlit and Layer 2 function contract

Import `RecommendationEngine` from `src.decisioning`. Keep one engine instance
per app process and call `close()` on shutdown. `app.recommend` holds a locked,
process-cached instance for Streamlit; restart the app after rebuilding data or
the model. The methods are:

```python
engine.recommend(customer_id: str, *, as_of: datetime = DEMO_AS_OF) -> dict
engine.worklist(limit: int = 20) -> list[dict]
engine.approve(decision_id: str, reviewer: str, reason: str) -> dict
engine.modify(decision_id: str, reviewer: str, action: str, reason: str) -> dict
engine.reject(decision_id: str, reviewer: str, reason: str) -> dict
```

`recommend()` accepts `G-...` or linked CRM IDs such as `AAA-4262`. Example
selected fields for `engine.recommend('G-39c6b287f70371cd9fc6')`:

```json
{"decision_id":"<uuid>","customer_id":"G-39c6b287f70371cd9fc6","action":"specialist_review","channel":null,"probabilities":{"promise_kept":0.42,"observed_rpc_by_channel":{"call":0.3977}},"reasons":["collections_cases.hardship_flag triggered mandatory specialist review; normal collection actions are suppressed.","Policy requires specialist review. The three strongest model factors are ..."],"shap_reasons":[{"feature":"card_utilisation","label":"card utilisation in the last completed monthly snapshot","value":0.8,"shap_log_odds":-0.12,"direction":"lowers"}],"status":"pending_review"}
```

Probabilities and SHAP values above illustrate the shape; display values from
the returned object. The full object includes all policy checks and all three
SHAP factors. The first reason for support routing names the triggering flag.

`worklist()` returns linked **open** promises ranked by predicted probability
of breaking, using only features available before each promise was created. It
does not approve or execute any action. Example actual leading row from this
release (the top reason is the leading SHAP factor):

```json
[{"ptp_id":"PTP-3511285","customer_id":"G-883e676faa7837d10aa7","case_id":"CS-2026-123687","probability_break":0.852273,"top_reason":"days past due","shap_reasons":[{"feature":"dpd_at_creation","value":127.0,"shap_log_odds":-1.489817,"direction":"lowers"}],"model_version":"promise-kept-v3"}]
```

`PTP-5510250` previously had 0.9413 predicted break risk. Its creation-time
features are DPD 159, bucket 3, overdue 1,311.41, four prior broken promises,
two broken in 90 days, five recent contacts, zero recent RPCs, card utilisation
0.8975, bureau risk score 834, earlier kept rate 0 and last employer payroll
14 days earlier. Source contact (2 Sep), prior outcome (19 Aug), card snapshot
(30 Jun), bureau pull (15 Apr) and payroll (28 Aug) all precede its 11 Sep
promise; values are plausible. Isotonic calibration gives it **0.8523** break
risk. Extreme cases can remain miscalibrated because the kept rate changed
after the calibration period. SHAP factors explain the raw model margin; the
isotonic mapping changes probability but not the underlying factor ranking.

For a non-specialist example, `engine.recommend('AAA-4262')` resolves to
`G-b1714eca2809e88d7587` and proposes **call** (score 0.118139). Policy
allows call and has no specialist trigger. Afternoon observed call RPC is
0.397672 versus zero recorded for SMS/email/push. Calibrated promise-kept
probability is 0.222517. Its top SHAP factors are card utilisation 0.8412
(lowers keeping), DPD 72 (lowers), and one earlier broken promise (slightly
raises this model's keeping score). The last direction is a model association,
not a claim that breaking a promise helps a customer.

On the local Windows benchmark (`python -m src.decisioning.benchmark`), engine
initialization took **2,134 ms**; the first `recommend('AAA-4262')` took
**519 ms** and five subsequent calls had **1.9 ms median**. The first
`worklist(20)` took **438 ms** and warm calls had **0.19 ms median**. A reused
engine caches frozen contexts, evidence, model scores and the worklist; each
recommendation still writes a fresh audit decision. Timing varies by machine.

Every review call takes a fresh `decision_id` from `recommend()`. Each decision
may have only one terminal review event. The return object has `event_id`,
`decision_id`, `reviewed_at`, `reviewer`, `disposition`, `original_action`,
`final_action`, `reason` and `validation` (the rechecked policy results). The
three calls yield, for example:

```json
{"disposition":"approve","original_action":"call","final_action":"call","reviewer":"demo-reviewer"}
{"disposition":"modify","original_action":"call","final_action":"wait","reviewer":"demo-reviewer"}
{"disposition":"reject","original_action":"call","final_action":null,"reviewer":"demo-reviewer"}
```

The restricted fairness report at `artifacts/fairness_evaluation.md` compares
predicted risk and recommended action mix across gender and citizenship groups
for a small linked sample. Protected fields are selected only in
`restricted/fairness.py` for aggregate measurement and never enter the model,
ranking or explanation paths.

- Measured: predicted break risk and recommended action mix for 120 linked
  customers, grouped by gender and citizenship.
- Observed gaps: permanent residents averaged 0.613 risk versus 0.550 for
  citizens and received 66.7% versus 46.3% specialist reviews; women and men
  averaged 0.554 and 0.566 risk, with 54.0% and 40.7% specialist reviews.
- Interpretation: this small selected sample is diagnostic. Policy/consent and
  support routing affect actions; no causal disparity or parity conclusion is
  warranted, and protected fields remain measurement-only.

The expanded `artifacts/fairness_test_period.md` covers **all 52,283** linked,
quality-passed test-period promises and reports customer-clustered 95% intervals.
It measures predicted break risk, actual break rate and the last **historical**
outbound channel before each promise. It does not reconstruct historical
recommendations. Women and men have similar mean predicted risk (0.540 and
0.541). Citizens average 0.544 versus 0.530 for permanent residents; actual
broken rates are 0.630 versus 0.610. Those differences are descriptive. The
broken rate rose from 35.7% in pre-July training to 62.5% in this linked test
cohort, a material drift that limits calibration and group comparisons.

The supported presentation claims and pilot evidence requirements are listed
in `docs/TASK_A_DECK_CLAIMS.md`.

## Point-in-time text signals (API extraction pending)

`src/features/text.py` defines `hardship_signal` (`none`, `possible`, `clear`)
and `stated_delay_reason` once. Both the training text table builder and live
`recommend()` call `features_at()`, which selects only a cached source before
the promise or scoring time. Completed transcripts require a prior calendar
day because their local/UTC alignment is uncertain. A parity test checks the
same cutoff behavior. The separate `src/features/text_groq.py` wrapper reads
`GROQ_API_KEY` from `.env`, extracts bounded batches, and writes
`local_artifacts/decisioning/text_annotations.json`; it imports nothing from
Layer 2. It refuses batches that cannot finish before 18:00 IST. The local
cache is kept outside Git, and no API is called in the demo.

The 500 public note labels and 500 transcript labels were loaded and prepared
for evaluation. **Groq extraction has not run:** at implementation time it was
after 18:00 IST and this workspace had no `.env` or `GROQ_API_KEY`. The
committed `artifacts/text_public_evaluation.json` therefore reports 0/500
evaluated for each source and null precision/recall. Do not cite text accuracy
or claim populated text features until the shared key is available in an
approved pre-18:00 window and the cache is rebuilt. Missing annotations yield
unknown text features. Text signals are context only and cannot alone trigger
adverse treatment or change the model/ranker.

When the window and key are available, run `python -m src.features.text_public
run`, then `python -m src.features.text_data` before the demo. The first command
resumes from its separate cache after each successful batch; the second writes
`local_artifacts/features/promise_text.parquet` with the same feature definition.
Rerun the public evaluator and review its precision/recall before using any
text result in a decision workflow.

## Committed evidence and remaining work

`artifacts/thin_flow_metrics.json` records the real-data channel evidence,
scoring assumptions, linked demo IDs, timing and successful audit checks.
`artifacts/audit_sample.json` contains four real-data decisions and their review
events: approve, modify, reject and specialist approval. These are synthetic
customer IDs without names, contact details or protected attributes. Rebuild
both with `python -m src.decisioning.demo`. The source cache and full SQLite audit
database stay under ignored `local_artifacts/decisioning/`.

`artifacts/promise_model_metrics.json` has class balance, missingness,
calibration, decile lift, model comparisons and limitations.
`artifacts/promise_kept_lightgbm.joblib` is the evaluated model. Rebuild these
with `src.features.training`, `src.features.candidates` and
`src.decisioning.train` as shown above.
The full Parquet training table remains ignored under `local_artifacts/`.

Effective hardship-programme eligibility and a maintained regional holiday
calendar are still needed for use beyond the frozen demo.

## Integration and ownership

Task A edits only `src/features/`, `src/decisioning/`, `tests/features/` and
`tests/decisioning/`. Shared C360 contracts and Layer 1/2 source are read-only.
Merge `origin/main` into `feature/task-a` regularly and check the adapter contract,
real-data demo and regression tests before merging into `main`.

Two existing Layer 2 transcript-summary tests fail on Windows because
`strftime("%-d %b")` is unsupported. They were reproduced on unchanged
`origin/main`, and Task A tests pass. Task A's thin flow was merged into main
after the user accepted those known Layer 2 failures. Layer 1/2 source and
shared contracts were not modified by Task A.
