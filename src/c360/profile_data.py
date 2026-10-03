"""Profile every release table and append reproducible findings to the C360 report."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import duckdb


KEYS = {
    "customers": ["crm_customer_id"],
    "card_accounts": ["card_account_id", "snapshot_date"],
    "loan_accounts": ["loan_id", "snapshot_date"],
    "deposit_accounts": ["deposit_account_id", "snapshot_date"],
    "collections_cases": ["case_id"],
    "contact_history": ["contact_id"],
    "promises_to_pay": ["ptp_id"],
    "agent_notes": ["note_id"],
    "call_transcripts": ["transcript_id"],
    "voice_samples": ["voice_sample_id"],
    "external": ["bureau_request_id"],
    "loan_instalments": ["loan_id", "instalment_no", "schedule_version"],
    "transactions": ["txn_id"],
    "card_statements": ["card_account_id", "statement_date", "cycle_no"],
    "account_monthly_snapshot": ["account_id", "month_end_date"],
    "bureau_history": ["bank_subject_ref", "pull_date"],
    "salary_credit_history": ["deposit_account_id", "credit_month"],
    "model_scores": ["score_id"],
    "offers": ["offer_id"],
    "metric_definitions": ["metric_id"],
    "benchmark_questions": ["question_id"],
    "reference_documents": ["doc_id", "version"],
    "hardship_programs": ["program_id", "version"],
    "qa_checklist": ["item_no", "version"],
    "agents": ["agent_id"],
    "case_assignment_history": ["assignment_id"],
    "agent_shifts": ["shift_id"],
    "channel_capacity": ["date", "channel", "time_band"],
    "ops_events": ["event_id"],
    "geo_reference": ["fsa"],
    "code_lookups": ["code_type", "code"],
}

PROTECTED = ("gender", "marital", "citizenship", "household", "newcomer",
             "accessibility", "vulnerab", "accent", "ethnic", "religion",
             "disability")
NEGATIVE_INVALID = re.compile(
    r"(^dpd$|_dpd$|^days_to_due_at_creation$|^days_late$|^duration_sec$|"
    r"_count$|_count_\w+$|^count_\w+$|^total_overdue$|"
    r"^credit_limit$|^risk_score$|^risk_score_prev_3m$)"
)
OPTIONAL = {"description", "description_en", "description_fr", "file_path",
            "question_text", "business_definition", "formula", "metric_name"}


def path_sql(path: Path) -> str:
    return "'" + path.resolve().as_posix().replace("'", "''") + "'"


def quote(name: str) -> str:
    if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
        raise ValueError(f"Invalid schema name: {name}")
    return '"' + name + '"'


def source_sql(root: Path, spec: dict) -> str:
    path = root / spec["path"]
    if spec["format"] == "csv":
        return f"read_csv({path_sql(path)}, header=true, all_varchar=true)"
    if spec["format"].startswith("parquet"):
        return f"read_parquet({path_sql(path / '*' / '*.parquet')}, hive_partitioning=true)"
    raise ValueError(spec["format"])


def add_issue(issues: list[dict], category: str, table: str, count: int,
              rows: int, handling: str, risk: str, field: str = "") -> None:
    if count:
        issues.append({"issue": category + (f": {field}" if field else ""),
                       "table": table, "affected_count": int(count),
                       "percentage": round(100 * count / rows, 3) if rows else 0,
                       "handling": handling, "residual_risk": risk})


def profile(root: Path) -> tuple[list[dict], dict[str, int]]:
    schema = json.loads((root / "schema/schema.json").read_text(encoding="utf-8"))
    con = duckdb.connect(":memory:")
    con.execute("SET memory_limit = '4GB'")
    issues: list[dict] = []
    row_counts: dict[str, int] = {}
    try:
        for table, spec in schema.items():
            source = source_sql(root, spec)
            actual = {r[0] for r in con.execute(f"DESCRIBE SELECT * FROM {source}").fetchall()}
            expected = {c["name"] for c in spec["columns"]}
            extra = actual - expected - ({"year"} if spec["format"].startswith("parquet") else set())
            missing = expected - actual
            for name in sorted(extra | missing):
                add_issue(issues, "schema drift", table, 1, 1,
                          "Stop downstream use until schema is reconciled.",
                          "A changed field may alter joins or metrics.", name)
            available = [c for c in spec["columns"] if c["name"] in actual]
            fields = []
            expressions = ["count(*)"]
            for col in available:
                name = col["name"]
                if any(token in name for token in PROTECTED):
                    continue
                q = quote(name)
                expressions.append(f"count(*) FILTER (WHERE {q} IS NULL OR trim(CAST({q} AS VARCHAR)) = '')")
                fields.append(("missing", name))
                typ = col.get("physical_type", col.get("type", "")).upper()
                if spec["format"] == "csv" and typ in {"DATE", "TIMESTAMP"}:
                    pattern = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$" if typ == "DATE" else r"^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}$"
                    expressions.append(f"count(*) FILTER (WHERE {q} IS NOT NULL AND trim({q}) <> '' AND NOT regexp_matches({q}, '{pattern}'))")
                    fields.append(("mixed date format", name))
                if name in {"dob_raw", "cardholder_dob_raw", "borrower_dob_raw",
                            "holder_dob_raw", "month_end_date"}:
                    pattern = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
                    expressions.append(f"count(*) FILTER (WHERE {q} IS NOT NULL AND trim(CAST({q} AS VARCHAR)) <> '' AND NOT regexp_matches(CAST({q} AS VARCHAR), '{pattern}'))")
                    fields.append(("mixed date representation", name))
                if typ in {"BIGINT", "DOUBLE"} and NEGATIVE_INVALID.search(name):
                    expressions.append(f"count(*) FILTER (WHERE try_cast({q} AS DOUBLE) < 0)")
                    fields.append(("impossible negative value", name))
                if name in {"dpd", "current_dpd", "dpd_at_creation", "dpd_at_contact"}:
                    expressions.append(f"count(*) FILTER (WHERE try_cast({q} AS DOUBLE) > 3650)")
                    fields.append(("implausible DPD over ten years", name))
                if name in {"utilisation", "revolving_utilisation", "loc_utilisation"}:
                    expressions.append(f"count(*) FILTER (WHERE try_cast({q} AS DOUBLE) < 0)")
                    fields.append(("impossible negative utilisation", name))
            values = con.execute(f"SELECT {', '.join(expressions)} FROM {source}").fetchone()
            rows = values[0]
            row_counts[table] = rows
            for (kind, name), count in zip(fields, values[1:]):
                if kind == "missing":
                    if name in KEYS[table]:
                        handling = "Reject from keyed joins; retain in source quarantine."
                        risk = "The record cannot be reliably joined."
                    elif name in OPTIONAL:
                        handling = "Keep null; omit this optional field from derived values."
                        risk = "Some detail is unavailable."
                    else:
                        handling = "Keep null; do not infer a value from current snapshots."
                        risk = "Metrics or features requiring this field have reduced coverage."
                elif kind in {"mixed date format", "mixed date representation"}:
                    handling = "Parse with explicit accepted formats; quarantine unparseable dates."
                    risk = "Historical order may be ambiguous until source correction."
                else:
                    handling = "Exclude invalid values from metrics and features; send to source correction."
                    risk = "Coverage falls until the source record is corrected."
                add_issue(issues, kind, table, count, rows, handling, risk, name)
            keys = KEYS[table]
            if all(k in actual for k in keys):
                key_sql = ", ".join(quote(k) for k in keys)
                duplicate = con.execute(f"""SELECT coalesce(sum(n - 1), 0) FROM (
                    SELECT count(*) n FROM {source} GROUP BY {key_sql} HAVING count(*) > 1
                )""").fetchone()[0]
                add_issue(issues, "duplicate grain key", table, duplicate, rows,
                          "Deduplicate by stable key and source version; hold conflicting records for review.",
                          "A duplicate may still describe a legitimate new version if source versioning is incomplete.",
                          "+".join(keys))
            print(f"{table}: {rows:,} rows, {len(issues)} cumulative findings", flush=True)

        # Foreign-key mismatches use source keys, not inferred customer identity.
        checks = [
            ("contact_history", "case_id", "collections_cases", "case_id"),
            ("promises_to_pay", "case_id", "collections_cases", "case_id"),
            ("agent_notes", "case_id", "collections_cases", "case_id"),
            ("call_transcripts", "case_id", "collections_cases", "case_id"),
            ("offers", "case_id", "collections_cases", "case_id"),
            ("case_assignment_history", "case_id", "collections_cases", "case_id"),
            ("voice_samples", "transcript_id", "call_transcripts", "transcript_id"),
        ]
        for child, ck, parent, pk in checks:
            csrc = source_sql(root, schema[child])
            psrc = source_sql(root, schema[parent])
            count = con.execute(f"""SELECT count(*) FROM {csrc} c
                WHERE c.{quote(ck)} IS NOT NULL AND trim(CAST(c.{quote(ck)} AS VARCHAR)) <> ''
                AND NOT EXISTS (SELECT 1 FROM {psrc} p WHERE p.{quote(pk)} = c.{quote(ck)})""").fetchone()[0]
            add_issue(issues, "mismatched ID", child, count, row_counts[child],
                      "Quarantine orphaned rows from customer-level joins; retain source evidence.",
                      "Orphaned events are unavailable in linked metrics.", f"{ck} -> {parent}.{pk}")
    finally:
        con.close()
    return issues, row_counts


def render(issues: list[dict], rows: dict[str, int]) -> str:
    lines = ["## Full release profile (31 tables)", "",
             "Generated by `src/c360/profile_data.py` from the installed 28 September 2026 release.",
             "Counts are rows affected within each table; percentages use that table's row count. Findings may overlap.",
             "The checks cover declared schema, null or blank fields, declared and raw date formats, selected impossible numeric values, grain-key duplicates, and explicit foreign-key joins. Missing values include optional or inapplicable fields; their presence is a completeness observation, not automatically a defect. A zero in the coverage table means no finding from those checks; it is not a guarantee of error-free data.",
             "Columns designated for fairness testing are excluded from this report and downstream decision outputs.",
             "", "| Table | Rows | Findings |", "| --- | ---: | ---: |"]
    by_table = {name: 0 for name in rows}
    for item in issues:
        by_table[item["table"]] += 1
    lines += [f"| {name} | {count:,} | {by_table[name]} |" for name, count in rows.items()]
    lines += ["", "| Issue | Table | Affected count | Percentage | Handling | Residual risk |",
              "| --- | --- | ---: | ---: | --- | --- |"]
    for item in issues:
        lines.append("| " + " | ".join((item["issue"], item["table"],
            f'{item["affected_count"]:,}', f'{item["percentage"]:.3f}%',
            item["handling"], item["residual_risk"])) + " |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("maple_data/maple_collections_release"))
    parser.add_argument("--report", type=Path, default=Path("submission/data_quality_report.md"))
    parser.add_argument("--output-dir", type=Path, default=Path("local_artifacts/c360"))
    args = parser.parse_args()
    issues, rows = profile(args.data_dir.resolve())
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "full_profile.json").write_text(
        json.dumps({"issues": issues, "row_counts": rows}, indent=2), encoding="utf-8")
    marker = "## Full release profile (31 tables)"
    original = args.report.read_text(encoding="utf-8")
    report = original.split(marker, 1)[0].rstrip() + "\n\n" + render(issues, rows)
    args.report.write_text(report, encoding="utf-8")
    print(f"Profiled {len(rows)} tables; recorded {len(issues)} findings", flush=True)


if __name__ == "__main__":
    main()
