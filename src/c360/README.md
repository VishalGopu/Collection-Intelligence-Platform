# Layer 1: Data Product Factory

Own raw-to-curated-to-gold processing, source-key matching, identity confidence, and data-quality reporting. Read the dataset locally; publish the two Parquet outputs in `contracts/golden_c360_v1.json` under `local_artifacts/c360/`. Keep implementation and module dependencies in this directory, and tests in `tests/c360/`.

The release README identifies CRM, Cards, Lending, Core banking, and Collections keys. Collections case references originate from CRM. Preserve leading-zero source IDs as strings. Quarantine uncertain links; do not silently merge customers on a shared phone or address.
