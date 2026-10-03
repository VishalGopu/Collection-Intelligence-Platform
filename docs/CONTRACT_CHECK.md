# Contract check

`contracts/golden_c360_v1.json` was checked against the DC-COLL-001 example shape on 4 October 2026.

It contains:

- `owner`: Collections data product team;
- `schema`: grains and references to the two output schemas;
- `quality_rules`: uniqueness, identity confidence, case resolution, link-state, and protected-field rules;
- `allowed_uses` and `prohibited_uses`;
- `refresh_frequency`: once per dataset release in this build.

The C360 contract deliberately states a release-based refresh rather than claiming DC-COLL-001's daily 05:00 ET schedule, because this hackathon artifact is batch-published from a fixed dataset release. The executable shape check is `tests/c360/test_contract.py`.
