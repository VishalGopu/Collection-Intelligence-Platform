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

The per-promise training matrix is the next phase. It must use event-specific
historical availability, not current accounts, cases, external bureau snapshots
or the current golden-customer rollups. Any future deposit/transaction feature
must explicitly exclude Canada Child Benefit deposits, with regression fixtures
that prove exclusion. Shared numerical feature definitions will be used by both
training and scoring.
