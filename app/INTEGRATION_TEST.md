# Hero customer integration check

Run from the repository root with the project environment and extracted release:

```text
python -m app.smoke
```

Tested against the 28 September 2026 release with `G-39c6b287f70371cd9fc6`:

| Path | Result |
| --- | --- |
| Customer | One linked case, 38 contacts, four promises, and six linked source keys displayed. |
| Ask, certified metric | Answer returned with executed SQL, metric definition, and data date. |
| Ask, refusal | Off-topic question displayed a refusal message. |
| Recommendation | `specialist_review` returned with policy checks, reasons, alternatives, and an audit decision row. |
| Human review | Reject was submitted through the Streamlit form and appeared in the audit table. Separate real-data calls verified Approve and Modify audit writes; `wait` was the permitted modified action. |

The first smoke-test run failed because the test harness reran Streamlit between typing the reviewer ID and reason in a form. The app correctly rejected that empty submission. The test now submits both fields together and passes. The model emits a SHAP compatibility warning during scoring, but the recommendation and audit write succeed.

Current functional limit: customer-scoped analytical wording is refused because the Layer 2 SQL engine still uses global metric routes. Explicit case questions are allowed only for cases linked to the selected customer. The review form takes a typed reviewer ID; authentication and authorization are not implemented in this demo. The smoke test writes local audit rows under ignored `local_artifacts/decisioning/` and never contacts a customer.
