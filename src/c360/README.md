# Layer 1: Data Product Factory

This module handles raw-to-curated-to-gold processing, source-key matching, identity confidence, and data-quality reporting. It publishes the two Parquet outputs in `contracts/golden_c360_v1.json` under `local_artifacts/c360/`. See [the handoff](HANDOFF.md) for source-key joins and point-in-time constraints.

The release README identifies CRM, Cards, Lending, Core banking, and Collections keys. Collections case references originate from CRM. Preserve leading-zero source IDs as strings. Quarantine uncertain links; do not silently merge customers on a shared phone or address.

## Run

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe src\c360\build.py
```

The build writes `golden_customers.parquet`, `identity_crosswalk.parquet`, two curated silver files, and quality reports under the ignored `local_artifacts/c360/` directory. The release's source files remain unchanged. Only links with confidence at least 0.95, a clear winner, and no conflicting profile are published as linked; other candidates require review or remain unlinked.

Collections cases first use their copied CRM reference. If that reference is missing, the primary account can supply a customer link only when every case for that Collections reference agrees on the same linked customer. Conflicting CRM and account evidence stays in review. The build checks that at least 99.5% of case rows resolve and publishes the counts in `quality_report.md`.

To inspect the source keys behind a published customer without displaying DOB, phone, postcode, or name:

```powershell
.\.venv\Scripts\python.exe src\c360\explain.py G-a68042b56cee36b677bd
```

The command shows each linked source key, match method, rule-based confidence, and which normalized identity fields agree. A CRM anchor and a Collections reference report their link method instead of raw identity fields. A `review_pending` source has no published golden ID and is intentionally absent from this lookup.

The Streamlit app can import `from src.c360.explain import explain_customer` and call `explain_customer(golden_id)`. It returns a dictionary with `golden_customer_id`, `linked_source_count`, and `links`; each link includes the source key, method, confidence, status, and evidence names.

Run the Layer 1 checks with `.\.venv\Scripts\python.exe -m pytest tests\c360 -q`. The tests cover invalid published links, protected columns, quality-gate failures, and the explanation output. If local Parquet outputs exist, the suite also verifies their row counts and identity invariants against the quality report.
