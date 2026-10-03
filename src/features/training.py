"""Rebuild the point-in-time promise table from the synthetic Maple release.

Run ``python -m src.features.training`` from the repository root after C360.
Only explicitly selected numeric fields become model inputs. Source dates and
the promise outcome timestamp are retained for leakage checks, not training.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb

from .contacts import PROTECTED_FIELDS, ROUTING_ONLY_FIELDS, check_feature_columns


FEATURE_COLUMNS = (
    'dpd_at_creation', 'dpd_bucket_at_creation', 'overdue_at_creation',
    'prior_broken_ptp_count_at_creation', 'broken_promises_90d',
    'recent_contacts_30d', 'recent_rpc_30d', 'card_utilisation',
    'bureau_risk_score', 'bureau_score_change',
)
APPROVED_CANDIDATES = ('earlier_kept_rate', 'days_since_last_payroll')
AUDIT_DATES = ('latest_contact_ts', 'latest_prior_broken_ts',
               'card_snapshot_date', 'bureau_pull_date', 'bureau_previous_pull_date')


def model_columns(columns) -> tuple[str, ...]:
    check_feature_columns(columns)
    unexpected = set(columns) - set(FEATURE_COLUMNS + APPROVED_CANDIDATES)
    if unexpected:
        raise ValueError(f'Unapproved model features: {sorted(unexpected)}')
    return tuple(columns)


def quote(path: Path) -> str:
    return "'" + path.resolve().as_posix().replace("'", "''") + "'"


def validate_frame(con: duckdb.DuckDBPyConnection, table='training_table') -> dict:
    columns = {name for name, *_ in con.execute(f'DESCRIBE {table}').fetchall()}
    if missing := set(FEATURE_COLUMNS + AUDIT_DATES) - columns:
        raise ValueError(f'Missing training columns: {sorted(missing)}')
    model_columns(FEATURE_COLUMNS)
    clauses = [f'{name} >= promise_created_ts' for name in AUDIT_DATES]
    clauses += ["status_ts < promise_created_ts", "status_ts IS NULL",
                "promise_created_ts IS NULL", "ptp_id IS NULL",
                "label_kept NOT IN (0, 1)"]
    bad = con.execute(f"SELECT count(*) FROM {table} WHERE {' OR '.join(clauses)}").fetchone()[0]
    duplicates = con.execute(f'''SELECT count(*) FROM (
        SELECT ptp_id FROM {table} GROUP BY 1 HAVING count(*) > 1)''').fetchone()[0]
    if bad or duplicates:
        raise ValueError(f'Training time/label/uniqueness violations: {bad}, {duplicates}')
    return {'rows': con.execute(f'SELECT count(*) FROM {table}').fetchone()[0],
            'future_or_invalid_rows': bad, 'duplicate_ptp_ids': duplicates,
            'features': list(FEATURE_COLUMNS)}


def build(data_dir: Path, c360_dir: Path, output_path: Path) -> dict:
    data = (data_dir / 'data').resolve()
    crosswalk = (c360_dir / 'identity_crosswalk.parquet').resolve()
    if not crosswalk.is_file():
        raise FileNotFoundError('Run src/c360/build.py first')
    output_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(output_path.parent / 'training_work.duckdb'))
    con.execute("SET memory_limit='5GB'")
    con.execute(f"SET temp_directory={quote(output_path.parent / 'tmp')}")
    promises = f"read_csv({quote(data / 'promises_to_pay.csv')}, header=true, all_varchar=true)"
    contacts = f"read_csv({quote(data / 'contact_history.csv')}, header=true, all_varchar=true)"
    snapshots = f"read_parquet({quote(data / 'account_monthly_snapshot' / '*' / '*.parquet')}, hive_partitioning=true)"
    bureau = f"read_parquet({quote(data / 'bureau_history' / '*' / '*.parquet')}, hive_partitioning=true)"
    try:
        # The source has supplied at-creation DPD and prior broken count. The
        # rest are reconstructed with strict, per-promise event-time cutoffs.
        con.execute(f'''CREATE OR REPLACE TABLE promise_events AS SELECT
            ptp_id, crm_customer_id, case_id,
            try_cast(ptp_created_ts AS TIMESTAMP) AS promise_created_ts,
            try_cast(status_ts AS TIMESTAMP) AS status_ts,
            ptp_status,
            try_cast(dpd_at_creation AS DOUBLE) AS dpd_at_creation,
            try_cast(overdue_at_creation AS DOUBLE) AS overdue_at_creation,
            try_cast(prior_broken_ptp_count AS DOUBLE) AS prior_broken_ptp_count_at_creation
            FROM {promises}''')
        con.execute('''CREATE OR REPLACE TABLE promises AS SELECT *,
            CASE WHEN ptp_status='kept' THEN 1 ELSE 0 END AS label_kept,
            CASE WHEN dpd_at_creation IS NULL THEN NULL
                 WHEN dpd_at_creation < 30 THEN 0 WHEN dpd_at_creation < 60 THEN 1
                 WHEN dpd_at_creation < 90 THEN 2 ELSE 3 END AS dpd_bucket_at_creation
            FROM promise_events
            WHERE ((ptp_status IN ('kept','broken')
                    AND status_ts >= promise_created_ts
                    AND status_ts <= TIMESTAMP '2026-09-28 23:59:59')
                   OR ptp_status='open')
              AND promise_created_ts IS NOT NULL AND ptp_id IS NOT NULL''')
        print('Promise outcomes staged', flush=True)
        con.execute(f'''CREATE OR REPLACE TABLE prior_contacts AS
            SELECT p.ptp_id, count(c.contact_ts_utc) AS recent_contacts_30d,
                count(*) FILTER (WHERE c.rpc_flag) AS recent_rpc_30d,
                max(c.contact_ts_utc) AS latest_contact_ts
            FROM promises p LEFT JOIN (
                SELECT crm_customer_id, try_cast(contact_ts_utc AS TIMESTAMP) AS contact_ts_utc,
                       try_cast(rpc_flag AS BOOLEAN) AS rpc_flag
                FROM {contacts} WHERE direction='outbound'
            ) c ON c.crm_customer_id=p.crm_customer_id
                AND c.contact_ts_utc < p.promise_created_ts
                AND c.contact_ts_utc >= p.promise_created_ts - INTERVAL '30 days'
            GROUP BY p.ptp_id''')
        print('Prior contacts joined', flush=True)
        con.execute('''CREATE OR REPLACE TABLE prior_broken AS
            SELECT p.ptp_id,
                count(previous.ptp_id) AS broken_promises_90d,
                max(previous.status_ts) AS latest_prior_broken_ts
            FROM promises p LEFT JOIN promise_events previous
              ON previous.crm_customer_id=p.crm_customer_id
                 AND previous.ptp_id<>p.ptp_id
                 AND previous.ptp_status='broken'
                 AND previous.promise_created_ts < p.promise_created_ts
                 AND previous.status_ts < p.promise_created_ts
                 AND previous.status_ts >= p.promise_created_ts - INTERVAL '90 days'
            GROUP BY p.ptp_id''')
        print('Prior outcomes joined', flush=True)
        # Monthly snapshots have mixed date strings. Day-grain data excludes
        # the promise day because intraday availability is unknown.
        con.execute(f'''CREATE OR REPLACE TABLE card_snapshots AS SELECT
            crm_customer_id, account_id,
            CAST(try_strptime(CAST(month_end_date AS VARCHAR),
                ['%Y-%m-%d','%d/%m/%Y','%Y%m%d']) AS DATE) AS snapshot_date,
            try_cast(balance AS DOUBLE) / nullif(try_cast(limit_or_original_amount AS DOUBLE),0)
                AS card_utilisation
            FROM {snapshots} WHERE product_type='card' ''')
        con.execute('''CREATE OR REPLACE TABLE card_at_promise AS SELECT
            p.ptp_id, arg_max(s.card_utilisation,
                struct_pack(snapshot_date:=s.snapshot_date,account_id:=s.account_id))
                AS card_utilisation,
            max(s.snapshot_date) AS card_snapshot_date
            FROM promises p LEFT JOIN card_snapshots s
              ON s.crm_customer_id=p.crm_customer_id
             AND s.snapshot_date < CAST(p.promise_created_ts AS DATE)
            GROUP BY p.ptp_id''')
        print('Past card snapshots joined', flush=True)
        # Bureau source key is core-banking CIF; the approved crosswalk resolves
        # its identity. The values themselves always precede each promise.
        con.execute(f'''CREATE OR REPLACE TABLE bureau_events AS SELECT
            b.bank_subject_ref, b.pull_date,
            try_cast(b.risk_score AS DOUBLE) AS risk_score,
            lag(try_cast(b.risk_score AS DOUBLE)) OVER (
                PARTITION BY b.bank_subject_ref ORDER BY b.pull_date) AS previous_risk_score,
            lag(b.pull_date) OVER (
                PARTITION BY b.bank_subject_ref ORDER BY b.pull_date) AS previous_pull_date
            FROM {bureau} b''')
        con.execute(f'''CREATE OR REPLACE TABLE approved_bureau AS SELECT DISTINCT
            crm.source_customer_id AS crm_customer_id,
            b.pull_date, b.previous_pull_date, b.risk_score,
            b.risk_score-b.previous_risk_score AS bureau_score_change,
            b.bank_subject_ref
            FROM bureau_events b JOIN read_parquet({quote(crosswalk)}) core
              ON core.source_system='core_banking'
             AND core.source_customer_id=b.bank_subject_ref AND core.link_status='linked'
            JOIN read_parquet({quote(crosswalk)}) crm
              ON crm.golden_customer_id=core.golden_customer_id
             AND crm.source_system='crm' AND crm.link_status='linked' ''')
        con.execute('''CREATE OR REPLACE TABLE bureau_at_promise AS SELECT
            p.ptp_id,
            arg_max(b.risk_score,
                struct_pack(pull_date:=b.pull_date,subject:=b.bank_subject_ref))
                AS bureau_risk_score,
            arg_max(b.bureau_score_change,
                struct_pack(pull_date:=b.pull_date,subject:=b.bank_subject_ref))
                AS bureau_score_change,
            max(b.pull_date) AS bureau_pull_date,
            arg_max(b.previous_pull_date,
                struct_pack(pull_date:=b.pull_date,subject:=b.bank_subject_ref))
                AS bureau_previous_pull_date
            FROM promises p LEFT JOIN approved_bureau b
              ON b.crm_customer_id=p.crm_customer_id
             AND b.pull_date < CAST(p.promise_created_ts AS DATE)
            GROUP BY p.ptp_id''')
        print('Past bureau pulls joined', flush=True)
        con.execute('''CREATE OR REPLACE TABLE training_table AS SELECT
            p.ptp_id, p.crm_customer_id, p.case_id, p.promise_created_ts, p.status_ts,
            p.label_kept, p.dpd_at_creation, p.dpd_bucket_at_creation,
            p.overdue_at_creation, p.prior_broken_ptp_count_at_creation,
            broken.broken_promises_90d, contacts.recent_contacts_30d,
            contacts.recent_rpc_30d, card.card_utilisation, bureau.bureau_risk_score,
            bureau.bureau_score_change, contacts.latest_contact_ts,
            broken.latest_prior_broken_ts, card.card_snapshot_date,
            bureau.bureau_pull_date, bureau.bureau_previous_pull_date
            FROM promises p JOIN prior_contacts contacts USING (ptp_id)
              JOIN prior_broken broken USING (ptp_id)
              JOIN card_at_promise card USING (ptp_id)
              JOIN bureau_at_promise bureau USING (ptp_id)
            WHERE p.ptp_status IN ('kept','broken')''')
        validation = validate_frame(con)
        con.execute(f"COPY training_table TO {quote(output_path)} (FORMAT PARQUET, COMPRESSION ZSTD)")
        con.execute('''CREATE OR REPLACE TABLE open_table AS SELECT
            p.ptp_id,p.crm_customer_id,p.case_id,p.promise_created_ts,
            p.dpd_at_creation,p.dpd_bucket_at_creation,p.overdue_at_creation,
            p.prior_broken_ptp_count_at_creation,broken.broken_promises_90d,
            contacts.recent_contacts_30d,contacts.recent_rpc_30d,
            card.card_utilisation,bureau.bureau_risk_score,bureau.bureau_score_change,
            contacts.latest_contact_ts,broken.latest_prior_broken_ts,
            card.card_snapshot_date,bureau.bureau_pull_date,bureau.bureau_previous_pull_date
            FROM promises p JOIN prior_contacts contacts USING(ptp_id)
            JOIN prior_broken broken USING(ptp_id)
            JOIN card_at_promise card USING(ptp_id)
            JOIN bureau_at_promise bureau USING(ptp_id)
            WHERE p.ptp_status='open' AND p.promise_created_ts<=TIMESTAMP '2026-09-28 23:59:59' ''')
        open_path = output_path.with_name('open_promise_features.parquet')
        con.execute(f"COPY open_table TO {quote(open_path)} (FORMAT PARQUET, COMPRESSION ZSTD)")
        validation['open_rows'] = con.execute('SELECT count(*) FROM open_table').fetchone()[0]
        return validation
    finally:
        con.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=Path('maple_data/maple_collections_release'))
    parser.add_argument('--c360-dir', type=Path, default=Path('local_artifacts/c360'))
    parser.add_argument('--output', type=Path, default=Path('local_artifacts/features/promise_training.parquet'))
    args = parser.parse_args()
    print(json.dumps(build(args.data_dir, args.c360_dir, args.output), indent=2))


if __name__ == '__main__':
    main()
