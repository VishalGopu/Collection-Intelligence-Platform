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
.\.venv\Scripts\python.exe -m pip install -r src/decisioning/requirements.txt pytest
.\.venv\Scripts\python.exe src/c360/build.py
.\.venv\Scripts\python.exe -m src.features.training
.\.venv\Scripts\python.exe -m src.decisioning.train
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

`src/features/training.py` builds a one-row-per-promise Parquet table with ten
allowlisted numeric features. It uses contacts, earlier broken promises, prior
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
The reported Brier score and ten calibration bins show its size; no calibrated
probability or causal effect is claimed.

| Model | Test rows | ROC AUC | Average precision | Brier | Calibration error |
| --- | ---: | ---: | ---: | ---: | ---: |
| Logistic regression | 54,657 | 0.6734 | 0.5416 | 0.2534 | 0.1908 |
| LightGBM | 54,657 | 0.6746 | 0.5447 | 0.2464 | 0.1577 |

The supplied `model_scores` comparison uses only scores timestamped **before**
each promise. Rows marked `uses_protected_attributes=true` or with an unknown
flag are discarded. The existing `ptp_break` model has 1,881 eligible test
rows: AUC **0.7129** versus **0.6808** for logistic regression and **0.6849**
for LightGBM on those exact rows. Its Brier score and calibration bins are in
the report. The `collections_risk` score covers 11,584 rows, but predicts a
different target; its inverse is a directional proxy only. Its AUC is 0.5484,
versus 0.6316 and 0.6226 for our models on the same rows. These subset results
are not directly comparable with the full 54,657-row test metrics.

The channel data is observational: agents chose channels, and customers with
promises are selected. This backtest **does not establish treatment uplift** or
show that one channel causes more repayment. The explicit channel weights above
are assumptions and do not come from the promise-kept model.

## Committed evidence and remaining work

`artifacts/thin_flow_metrics.json` records the real-data channel evidence,
scoring assumptions, linked demo IDs, timing and successful audit checks.
`artifacts/audit_sample.json` contains four real-data decisions and their review
events: approve, modify, reject and specialist approval. These are synthetic
customer IDs without names, contact details or protected attributes. Rebuild
both with `python -m src.decisioning.demo`. The source cache and full SQLite audit
database stay under ignored `local_artifacts/decisioning/`.

`artifacts/promise_model_metrics.json` has class balance, missingness,
calibration bins, model comparisons and limitations. The 122 KB
`artifacts/promise_kept_lightgbm.joblib` is the evaluated model. Rebuild both
with `python -m src.features.training` and `python -m src.decisioning.train`.
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
