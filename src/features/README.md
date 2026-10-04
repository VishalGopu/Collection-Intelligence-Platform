# Layer 3: shared feature inputs

The first implementation is `contacts.py`: preceding-90-day right-party-contact
rates and average cost by channel and customer-local time band, plus previously
observed broken promises. Contact timestamps and promise outcome timestamps must
be strictly before the prediction timestamp. Unknown RPC labels, inbound events,
other time bands and out-of-window events are excluded. IDs stay as strings.

`RANKING_FIELDS` is the explicit numerical input allowlist. `check_feature_columns`
rejects the requested protected fields and the support-routing-only flags.
Support flags are loaded separately by the decisioning policy adapter; they do
not enter the ranker or its explanations. No deposit or transaction input is read
by this MVP, so Canada Child Benefit deposits cannot enter its features.

Run `python -m pytest tests/features tests/decisioning -q` from the repository root.

`training.py` now creates `local_artifacts/features/promise_training.parquet`.
It builds 196,820 resolved promise rows with ten allowlisted numerical features,
one row per promise. Contacts and prior broken promises have strict event-time
cutoffs. Card snapshots and bureau pulls have date-only cutoffs before the
promise day. Source-provided at-creation DPD, overdue balance and prior broken
count are used as recorded then. Open, cancelled and partially kept promises
are excluded from binary training. The status timestamp is used only for the
label and time-split guard, never as a feature.

Historical bureau rows join CRM through the approved C360 crosswalk because
they use the core-banking ID. The crosswalk was produced from the later
snapshot, so historical identity availability cannot be proved from this
release. Source event times also do not prove ingestion availability. These
limits are stated in the model report.

No deposit or transaction table is read, so Canada Child Benefit deposits
cannot enter this matrix. Any future deposit/transaction feature must
explicitly exclude them, with regression fixtures that prove exclusion.
`FEATURE_COLUMNS` is the shared training/scoring contract.

Text evidence uses deterministic rules in `text.py` for `hardship_signal` and
`stated_delay_reason`. Run `python -m src.features.text_rules` to evaluate the
500 public labels for each source and build the separate, ignored annotation
cache; then run `python -m src.features.text_data` to make point-in-time
training text rows. `features_at` is used for both those rows and live scoring.
Only customer speech in transcripts is scanned, and only notes or completed
calls strictly before the scoring time are eligible. These signals are context
in the recommendation, not repayment-model features or independent reasons to
take an adverse action. The committed evaluation is in
`src/decisioning/artifacts/text_public_evaluation.json`.
