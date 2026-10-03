# Layer 1: Data Product Factory

Own raw-to-curated-to-gold processing, source-key matching, identity confidence, and data-quality reporting. Read the dataset locally; publish the two Parquet outputs in `contracts/golden_c360_v1.json` under `local_artifacts/c360/`. Keep implementation and module dependencies in this directory, and tests in `tests/c360/`.

The release README identifies CRM, Cards, Lending, Core banking, and Collections keys. Collections case references originate from CRM. Preserve leading-zero source IDs as strings. Quarantine uncertain links; do not silently merge customers on a shared phone or address.

## Run

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m pip install -r src\c360\requirements.txt
.\.venv\Scripts\python.exe src\c360\build.py
```

The build writes `golden_customers.parquet`, `identity_crosswalk.parquet`, two curated silver files, and quality reports under the ignored `local_artifacts/c360/` directory. The release's source files remain unchanged. Only links with confidence at least 0.95, a clear winner, and no conflicting profile are published as linked; other candidates require review or remain unlinked.

Collections cases first use their copied CRM reference. If that reference is missing, the primary account can supply a customer link only when every case for that Collections reference agrees on the same linked customer. Conflicting CRM and account evidence stays in review. The build checks that at least 99.5% of case rows resolve and publishes the counts in `quality_report.md`.
