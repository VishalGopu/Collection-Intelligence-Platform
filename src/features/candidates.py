"""Rebuild extra, strictly earlier candidate features for a short model round."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb

from .training import quote


CANDIDATES = ('days_since_last_contact', 'earlier_kept_rate',
              'promise_amount_to_overdue', 'days_since_last_payroll')


def build(data_dir: Path, table_path: Path, output_path: Path) -> dict:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("SET memory_limit='5GB'")
    con.execute(f"SET temp_directory={quote(output_path.parent / 'tmp')}")
    data = data_dir / 'data'
    promises = quote(data / 'promises_to_pay.csv')
    salary = quote(data / 'salary_credit_history' / '*' / '*.parquet')
    try:
        con.execute(f'CREATE VIEW base AS SELECT * FROM read_parquet({quote(table_path)})')
        con.execute(f'''CREATE TABLE previous_promises AS SELECT
            ptp_id, crm_customer_id,
            try_cast(ptp_created_ts AS TIMESTAMP) AS created_ts,
            try_cast(status_ts AS TIMESTAMP) AS status_ts, ptp_status,
            try_cast(ptp_amount AS DOUBLE) AS promise_amount
            FROM read_csv({promises}, header=true, all_varchar=true)''')
        con.execute('''CREATE TABLE earlier_kept AS SELECT
            p.ptp_id,
            sum(CASE WHEN earlier.ptp_status='kept' THEN 1 ELSE 0 END) AS kept_count,
            count(earlier.ptp_id) AS prior_resolved_count,
            max(earlier.status_ts) AS latest_prior_status_ts
            FROM base p LEFT JOIN previous_promises earlier
              ON earlier.crm_customer_id=p.crm_customer_id
             AND earlier.ptp_id<>p.ptp_id
             AND earlier.ptp_status IN ('kept','broken')
             AND earlier.created_ts<p.promise_created_ts
             AND earlier.status_ts<p.promise_created_ts
            GROUP BY p.ptp_id''')
        # Salary history explicitly marks employer payroll. Other income,
        # including benefits, is excluded by employer_flag='Y'. Never inspect
        # deposit_accounts or transactions for this candidate.
        con.execute(f'''CREATE TABLE employer_salary AS SELECT
            crm_customer_id, last_credit_date
            FROM read_parquet({salary}, hive_partitioning=true)
            WHERE employer_flag='Y' AND last_credit_date IS NOT NULL''')
        con.execute('''CREATE TABLE earlier_payroll AS SELECT p.ptp_id,
            max(s.last_credit_date) AS last_payroll_date
            FROM base p LEFT JOIN employer_salary s
              ON s.crm_customer_id=p.crm_customer_id
             AND s.last_credit_date<CAST(p.promise_created_ts AS DATE)
            GROUP BY p.ptp_id''')
        con.execute('''CREATE TABLE candidate_table AS SELECT
            p.ptp_id,p.promise_created_ts,
            date_diff('day',p.latest_contact_ts,p.promise_created_ts)
                AS days_since_last_contact,
            try_cast(e.kept_count AS DOUBLE)/nullif(e.prior_resolved_count,0)
                AS earlier_kept_rate,
            amount.promise_amount/nullif(p.overdue_at_creation,0)
                AS promise_amount_to_overdue,
            date_diff('day',pay.last_payroll_date,CAST(p.promise_created_ts AS DATE))
                AS days_since_last_payroll,
            e.latest_prior_status_ts,pay.last_payroll_date
            FROM base p JOIN earlier_kept e USING(ptp_id)
              JOIN earlier_payroll pay USING(ptp_id)
              JOIN previous_promises amount USING(ptp_id)''')
        bad = con.execute('''SELECT count(*) FROM candidate_table WHERE
            latest_prior_status_ts>=promise_created_ts OR
            last_payroll_date>=CAST(promise_created_ts AS DATE) OR
            days_since_last_contact<0 OR days_since_last_payroll<0''').fetchone()[0]
        rows = con.execute('SELECT count(*) FROM candidate_table').fetchone()[0]
        duplicate = con.execute('''SELECT count(*) FROM (
            SELECT ptp_id FROM candidate_table GROUP BY 1 HAVING count(*)>1)''').fetchone()[0]
        if bad or duplicate or rows != con.execute('SELECT count(*) FROM base').fetchone()[0]:
            raise ValueError(f'Candidate leakage/uniqueness issue: {bad}, {duplicate}, {rows}')
        con.execute(f'COPY candidate_table TO {quote(output_path)} (FORMAT PARQUET, COMPRESSION ZSTD)')
        return {'rows': rows, 'future_or_invalid_rows': bad, 'duplicate_ptp_ids': duplicate,
                'candidates': CANDIDATES}
    finally:
        con.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=Path('maple_data/maple_collections_release'))
    parser.add_argument('--base', type=Path, default=Path('local_artifacts/features/promise_training.parquet'))
    parser.add_argument('--output', type=Path, default=Path('local_artifacts/features/promise_candidates.parquet'))
    args = parser.parse_args()
    print(json.dumps(build(args.data_dir,args.base,args.output),indent=2))


if __name__ == '__main__':
    main()
