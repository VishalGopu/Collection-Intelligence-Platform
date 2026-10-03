# Layer 1 handoff

Run `python src/c360/build.py` to create the contracted golden and crosswalk Parquet files. Run `python src/c360/views.py` to register typed, read-only `clean_<table>` views for all 31 release tables in the ignored `local_artifacts/c360/clean_views.duckdb`. The view builder reads `schema/schema.json`, keeps identifiers as text (including leading zeros), casts declared dates, timestamps, booleans and numbers, and normalizes the mixed-format `account_monthly_snapshot.month_end_date` to `DATE`. Source files stay unchanged. These views are a local handoff surface, not a versioned historical warehouse or an authorization boundary; query only the columns needed for a specific approved use.

The published identity interface is `contracts/golden_c360_v1.json`. It has the same core contract elements as the release's `DC-COLL-001` example: owner, refresh, schema, quality rules and allowed/prohibited uses. Its `batch for hackathon build` refresh is a deliberate limitation; it does not claim the daily 05:00 ET schedule of `DC-COLL-001`, which is a different table's contract.

## Customer joins

Always join through `identity_crosswalk` with `link_status = 'linked'`. `review_pending` and `unlinked` source keys have no published golden ID.

| Data | Join route |
| --- | --- |
| CRM `customers` | `crm_customer_id` → crosswalk `source_system = 'crm'`, `source_customer_id` |
| `collections_cases` | `coll_customer_ref` → crosswalk `source_system = 'collections'`, `source_customer_id` |
| `contact_history`, `promises_to_pay`, `agent_notes` | `crm_customer_id` → crosswalk `source_system = 'crm'`, `source_customer_id`; also join `case_id` to `collections_cases` when case scope is needed |
| `card_accounts` | `src_customer_ref` → crosswalk `source_system = 'cards'`, `source_customer_id` |
| `loan_accounts` | `src_customer_ref` → crosswalk `source_system = 'lending'`, `source_customer_id` |
| `deposit_accounts`, `external`, `bureau_history` | `src_customer_ref` or `bank_subject_ref` → crosswalk `source_system = 'core_banking'`, `source_customer_id` |
| `card_statements`, `loan_instalments`, `salary_credit_history` | `card_account_id`, `loan_id`, or `deposit_account_id` → respective account table → its source-system crosswalk |
| `transactions`, `account_monthly_snapshot` | `account_id` → product account table; use `account_type` or `product_type` to select the correct account namespace before joining |
| `call_transcripts`, `voice_samples` | `case_id` or `contact_id` → case/contact → approved customer crosswalk; `voice_samples` can also join `transcript_id` |
| `offers`, `model_scores`, `case_assignment_history` | `case_id` → `collections_cases`; `model_scores` can also use its explicit `crm_customer_id` when present |
| `agents`, `agent_shifts`, `qa_checklist` | `agent_id` or checklist `item_code`; operational context, not customer identity |
| `channel_capacity`, `ops_events`, `geo_reference`, `code_lookups` | Date/channel/event ID, FSA/province, or code type/code; dimensions, not customer identity |
| `metric_definitions`, `benchmark_questions`, `reference_documents`, `hardship_programs` | `metric_id`, `doc_id`, or `program_id` as relevant; governance/reference tables, not customer identity |

The golden table is a **28 September 2026 snapshot**. It cannot be used as a historical customer state for a model trained on earlier promises.

## Point-in-time feature inputs

`views.as_of_sql(table)` returns a parameterized query for `clean_contact_history`, `clean_transactions`, `clean_account_monthly_snapshot`, or `clean_bureau_history`. Bind the prediction time; the query includes only rows strictly before it. Date-only sources exclude the cutoff day because intraday availability is unknown. For one training row per promise, compare each source timestamp with **that promise's** `ptp_created_ts` in the join, not a single global cutoff.

Do not use current-state `collections_cases`, `card_accounts`, `loan_accounts`, `deposit_accounts`, `external`, or `golden_customers` fields as past features. `promises_to_pay.ptp_status`, payment amounts, and status timestamps are outcomes; use them only for labels or when their own observation time precedes the prediction. `card_statements` and `salary_credit_history` contain period summaries and outcomes that need feature-specific availability rules. The release does not give a complete data-arrival timestamp for every historical table, so the date filters are a conservative first guard, not proof that every selected feature was available at that time.
