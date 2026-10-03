# Restricted fairness evaluation

Deterministic sample: up to 120 linked customers with an open promise from the frozen 2026-09-28 release. These are descriptive checks, not parity guarantees.

**gender_code and citizenship_status are used only for this aggregate measurement. They are never model features, ranking inputs or explanations.**

| Field | Group | N | Mean predicted break risk | Recommended action mix |
| --- | --- | ---: | ---: | --- |
| citizenship_status | citizen | 95 | 0.490 | call: 30.5%, payment_plan_discussion: 1.1%, specialist_review: 46.3%, wait: 22.1% |
| citizenship_status | permanent_resident | 18 | 0.560 | call: 22.2%, specialist_review: 66.7%, wait: 11.1% |
| gender_code | F | 63 | 0.489 | call: 25.4%, payment_plan_discussion: 1.6%, specialist_review: 54.0%, wait: 19.0% |
| gender_code | M | 54 | 0.516 | call: 37.0%, specialist_review: 40.7%, wait: 22.2% |

Groups with fewer than 10 sampled customers are suppressed. The sample is small, selected by existing open promises, and action mix reflects current policy/consent as well as model context. Differences are diagnostic only; no causal or production fairness claim is made.
