"""Read-only source adapter and an allowlisted local cache for the frozen demo."""

from __future__ import annotations

from datetime import date, datetime
import hashlib
import json
from pathlib import Path

import duckdb

from src.features.contacts import utc_cutoff
from .policy import DecisionContext


SNAPSHOT_DATE = date(2026, 9, 28)
CACHE_VERSION = "thin-flow-v3"

# Safety flags below stay in policy context; none are supplied to the ranker.
CUSTOMER_COLUMNS = (
    "crm_customer_id", "time_zone", "consent_call", "consent_sms", "consent_email",
    "consent_push", "app_push_enabled", "internal_do_not_call_flag",
    "cease_communication_flag", "credit_counselling_agency_flag",
    "legal_representative_flag", "power_of_attorney_flag", "vulnerability_flag",
    "deceased_flag", "bankruptcy_flag", "consumer_proposal_flag", "fraud_victim_flag",
    "permitted_call_start_local", "permitted_call_end_local", "sunday_contact_permitted",
    "customer_status", "is_deleted",
)
CASE_COLUMNS = (
    "case_id", "coll_customer_ref", "case_status", "hardship_flag",
    "vulnerable_customer_flag", "cease_contact_flag", "insolvency_hold_flag",
    "deceased_hold_flag", "dispute_flag", "dispute_status", "complaint_flag",
    "contact_cap_7d", "primary_product", "current_dpd", "case_open_date",
    "total_overdue",
)
CONTACT_COLUMNS = (
    "contact_id", "crm_customer_id", "case_id", "direction", "channel",
    "contact_ts_utc", "contact_hour_local", "rpc_flag", "contact_cost_cad",
)
SUPPORT_CONTACT_COLUMNS = (
    "crm_customer_id", "case_id", "contact_ts_utc", "hardship_mentioned_flag",
    "vulnerability_disclosed_flag", "cease_request_flag", "sms_opt_out_flag",
    "email_unsubscribe_flag",
)


def truth(value) -> bool | None:
    if value is True or str(value).strip().lower() in {"true", "1", "yes"}:
        return True
    if value is False or str(value).strip().lower() in {"false", "0", "no"}:
        return False
    return None


def quote_path(path: Path) -> str:
    return "'" + path.resolve().as_posix().replace("'", "''") + "'"


def records(con, sql, parameters=None) -> list[dict]:
    cursor = con.execute(sql, parameters or [])
    names = [col[0] for col in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


class ReleaseAdapter:
    def __init__(self, data_dir: Path, c360_dir: Path, cache_path: Path):
        self.data_dir = data_dir.resolve()
        self.c360_dir = c360_dir.resolve()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        fingerprint = self._fingerprint()
        reusable = False
        if cache_path.is_file():
            try:
                self.connection = duckdb.connect(str(cache_path), read_only=True)
                reusable = (self.connection.execute('SELECT fingerprint FROM cache_metadata').fetchone()
                            == (fingerprint,))
            except duckdb.Error:
                reusable = False
            if not reusable:
                self.connection.close()
        if not reusable:
            self.connection = duckdb.connect(str(cache_path))
            self.connection.execute("SET memory_limit = '2GB'")
            self._prepare_cache(fingerprint)
            self.connection.close()
            self.connection = duckdb.connect(str(cache_path), read_only=True)
        self.connection.execute("SET memory_limit = '2GB'")
        self.has_c360 = (self.c360_dir / "identity_crosswalk.parquet").is_file()
        if self.has_c360:
            self._register_contract()

    def _source(self, name: str) -> str:
        return f"read_csv({quote_path(self.data_dir / 'data' / (name + '.csv'))}, header=true, all_varchar=true)"

    def _fingerprint(self):
        source_names = ("customers", "collections_cases", "contact_history", "promises_to_pay",
                        "external", "card_accounts", "agents", "hardship_programs")
        return hashlib.sha256(json.dumps([
            CACHE_VERSION, str(self.data_dir),
            [(n, (self.data_dir / 'data' / (n + '.csv')).stat().st_size,
              (self.data_dir / 'data' / (n + '.csv')).stat().st_mtime_ns) for n in source_names],
        ]).encode()).hexdigest()

    def _prepare_cache(self, fingerprint):
        con = self.connection
        con.execute("CREATE TABLE IF NOT EXISTS cache_metadata (fingerprint VARCHAR)")
        if con.execute("SELECT fingerprint FROM cache_metadata").fetchone() == (fingerprint,):
            return
        print("Building Task A allowlisted source cache...", flush=True)
        con.execute("BEGIN TRANSACTION")
        try:
            for table, source, columns in (
                ("customers_state", "customers", CUSTOMER_COLUMNS),
                ("cases_state", "collections_cases", CASE_COLUMNS),
                ("agents_state", "agents", ("agent_id", "status", "skill_hardship",
                  "vulnerable_customer_certified", "current_case_load", "max_concurrent_cases")),
                ("hardship_rules", "hardship_programs", ("program_id", "version", "product_types",
                  "max_dpd", "min_months_on_book", "max_uses_12m", "excludes_insolvency",
                  "excludes_broken_plan_90d", "requires_income_evidence", "effective_from", "effective_to")),
                ("external_holds", "external", ("bank_subject_ref", "pull_date", "fraud_alert_flag",
                  "deceased_indicator", "bankruptcy_on_file_flag", "consumer_proposal_on_file_flag")),
                ("card_holds", "card_accounts", ("src_customer_ref", "fraud_block_flag")),
            ):
                con.execute(f"CREATE OR REPLACE TABLE {table} AS SELECT "
                            f"{', '.join(columns)} FROM {self._source(source)}")
                print(f"Cached {table}", flush=True)
            # Separate safety-only event data from numerical ranking evidence.
            con.execute(f"CREATE OR REPLACE TEMP VIEW raw_contact_projection AS SELECT "
                        f"{', '.join(dict.fromkeys(CONTACT_COLUMNS + SUPPORT_CONTACT_COLUMNS))} "
                        f"FROM {self._source('contact_history')}")
            con.execute("""CREATE OR REPLACE TABLE contact_evidence AS SELECT
                contact_id, crm_customer_id, case_id, direction, channel,
                try_cast(contact_ts_utc AS TIMESTAMP) AS contact_ts_utc,
                try_cast(contact_hour_local AS INTEGER) AS contact_hour_local,
                try_cast(rpc_flag AS BOOLEAN) AS rpc_flag,
                try_cast(contact_cost_cad AS DOUBLE) AS contact_cost_cad
                FROM raw_contact_projection""")
            con.execute("""CREATE OR REPLACE TABLE support_events AS SELECT
                crm_customer_id, case_id, try_cast(contact_ts_utc AS TIMESTAMP) AS contact_ts_utc,
                try_cast(hardship_mentioned_flag AS BOOLEAN) AS hardship_mentioned_flag,
                try_cast(vulnerability_disclosed_flag AS BOOLEAN) AS vulnerability_disclosed_flag,
                try_cast(cease_request_flag AS BOOLEAN) AS cease_request_flag,
                try_cast(sms_opt_out_flag AS BOOLEAN) AS sms_opt_out_flag,
                try_cast(email_unsubscribe_flag AS BOOLEAN) AS email_unsubscribe_flag
                FROM raw_contact_projection""")
            con.execute(f"""CREATE OR REPLACE TABLE promise_evidence AS SELECT
                crm_customer_id, ptp_id, try_cast(ptp_created_ts AS TIMESTAMP) AS ptp_created_ts,
                try_cast(status_ts AS TIMESTAMP) AS status_ts, ptp_status
                FROM {self._source('promises_to_pay')}""")
            con.execute("DELETE FROM cache_metadata")
            con.execute("INSERT INTO cache_metadata VALUES (?)", [fingerprint])
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise

    def _register_contract(self):
        con = self.connection
        for view, filename in (("identity_crosswalk", "identity_crosswalk.parquet"),
                               ("golden_customers", "golden_customers.parquet")):
            path = self.c360_dir / filename
            if not path.is_file():
                raise FileNotFoundError(f"Incomplete C360 handoff: {path}")
            con.execute(f"CREATE OR REPLACE TEMP VIEW {view} AS SELECT * FROM read_parquet({quote_path(path)})")
        contract = json.loads((Path(__file__).resolve().parents[2] / 'contracts/golden_c360_v1.json').read_text())
        for table in ("identity_crosswalk", "golden_customers"):
            described = {row[0]: row[1] for row in con.execute(f"DESCRIBE {table}").fetchall()}
            actual = set(described)
            required = set(contract['outputs'][table]['required_columns'])
            if missing := required - actual:
                raise ValueError(f"C360 contract missing {table} columns: {sorted(missing)}")
            identifiers = ('source_system', 'source_customer_id', 'golden_customer_id') if table == 'identity_crosswalk' else ('golden_customer_id',)
            if any(described[column] != 'VARCHAR' for column in identifiers):
                raise ValueError('C360 identifiers must be strings to preserve leading zeros')
        invalid = con.execute("""SELECT count(*) FROM (
            SELECT source_system, source_customer_id FROM identity_crosswalk
            GROUP BY 1,2 HAVING count(*) > 1
            UNION ALL
            SELECT source_system, source_customer_id FROM identity_crosswalk
            WHERE link_status = 'linked' AND (golden_customer_id IS NULL OR
                  match_confidence IS NULL OR match_confidence < 0.95)
            UNION ALL
            SELECT source_system, source_customer_id FROM identity_crosswalk
            WHERE source_customer_id IS NULL OR source_system IS NULL
               OR source_system NOT IN ('crm','cards','lending','core_banking','collections')
               OR link_status IS NULL OR link_status NOT IN ('linked','unlinked','review_pending')
               OR (link_status <> 'linked' AND golden_customer_id IS NOT NULL)
               OR match_confidence IS NULL OR match_confidence NOT BETWEEN 0 AND 1
        )""").fetchone()[0]
        duplicates = con.execute("""SELECT count(*) FROM (
            SELECT golden_customer_id FROM golden_customers
            GROUP BY 1 HAVING count(*) > 1 OR golden_customer_id IS NULL
        )""").fetchone()[0]
        if invalid or duplicates:
            raise ValueError("Invalid or ambiguous C360 identity contract")
        orphans = con.execute("""SELECT count(*) FROM identity_crosswalk x
            LEFT JOIN golden_customers g USING (golden_customer_id)
            WHERE x.link_status='linked' AND g.golden_customer_id IS NULL""").fetchone()[0]
        if orphans:
            raise ValueError('Linked identity has no golden customer')

    def context(self, customer_id: str, as_of: datetime) -> DecisionContext:
        cutoff = utc_cutoff(as_of)
        if cutoff.date() != SNAPSHOT_DATE:
            raise ValueError("Current state is frozen at 2026-09-28; historical/live decisions require a versioned adapter")
        con = self.connection
        golden = None
        if self.has_c360:
            linked = records(con, """SELECT DISTINCT golden_customer_id FROM identity_crosswalk
                WHERE link_status='linked' AND (golden_customer_id=? OR
                  (source_system='crm' AND source_customer_id=?))""", [customer_id, customer_id])
            if len(linked) != 1:
                raise ValueError("Customer has no unique approved C360 link")
            golden_id = linked[0]['golden_customer_id']
            gold = records(con, """SELECT golden_customer_id, as_of_date, dq_status,
                consent_call, consent_sms, consent_email FROM golden_customers
                WHERE golden_customer_id=?""", [golden_id])
            if len(gold) != 1 or str(gold[0]['as_of_date']) != SNAPSHOT_DATE.isoformat():
                raise ValueError("Golden customer missing or snapshot mismatch")
            golden = gold[0]
            crm_ids = [r[0] for r in con.execute("""SELECT source_customer_id FROM identity_crosswalk
                WHERE golden_customer_id=? AND source_system='crm' AND link_status='linked'""", [golden_id]).fetchall()]
            profiles = records(con, "SELECT * FROM customers_state WHERE crm_customer_id IN (SELECT unnest(?))", [crm_ids])
            cases = records(con, """SELECT c.* FROM cases_state c JOIN identity_crosswalk x
                ON c.coll_customer_ref=x.source_customer_id AND x.source_system='collections'
                WHERE x.golden_customer_id=? AND x.link_status='linked'
                  AND c.case_status NOT IN ('cured','closed_paid','settled')""", [golden_id])
        else:
            # Explicit bootstrap mode: CRM identity only, no guessed cross-system joins.
            golden_id = customer_id
            crm_ids = [customer_id]
            profiles = records(con, "SELECT * FROM customers_state WHERE crm_customer_id=?", [customer_id])
            cases = []
        if not profiles:
            raise ValueError("Customer profile not found")
        def any_true(rows, field):
            return any(truth(row.get(field)) is True for row in rows)
        def all_false(rows, field):
            return bool(rows) and all(truth(row.get(field)) is False for row in rows)
        consent = {channel: all(truth(row.get('consent_' + channel)) is True for row in profiles)
                   for channel in ('call', 'sms', 'email', 'push')}
        if golden:
            for channel in ('call', 'sms', 'email'):
                consent[channel] &= golden['consent_' + channel] is True
        consent['push'] &= all(truth(r['app_push_enabled']) is True for r in profiles)
        if any_true(profiles, 'internal_do_not_call_flag'):
            consent['call'] = False
        zones = {r['time_zone'] for r in profiles}
        case_ids = [r['case_id'] for r in cases]
        support = records(con, """SELECT * FROM support_events
            WHERE crm_customer_id IN (SELECT unnest(?)) AND contact_ts_utc < ?""", [crm_ids, cutoff])
        # Older support disclosures are conservatively escalated for human review.
        hardship = any_true(cases, 'hardship_flag') or any_true(support, 'hardship_mentioned_flag')
        safeguard = (any_true(profiles, 'vulnerability_flag')
                     or any_true(cases, 'vulnerable_customer_flag')
                     or any_true(support, 'vulnerability_disclosed_flag'))
        routing_trigger = next((label for rows, field, label in (
            (cases, 'hardship_flag', 'collections_cases.hardship_flag'),
            (support, 'hardship_mentioned_flag', 'contact_history.hardship_mentioned_flag'),
            (profiles, 'vulnerability_flag', 'customers.vulnerability_flag'),
            (cases, 'vulnerable_customer_flag', 'collections_cases.vulnerable_customer_flag'),
            (support, 'vulnerability_disclosed_flag', 'contact_history.vulnerability_disclosed_flag'),
        ) if any_true(rows, field)), None)
        if any_true(support, 'sms_opt_out_flag'):
            consent['sms'] = False
        if any_true(support, 'email_unsubscribe_flag'):
            consent['email'] = False
        holds = []
        for label, fields in {
            'insolvency_hold': ('bankruptcy_flag', 'consumer_proposal_flag'),
            'deceased_hold': ('deceased_flag',), 'fraud_review_hold': ('fraud_victim_flag',),
        }.items():
            if any(any_true(profiles, f) for f in fields):
                holds.append(label)
            elif not all(all_false(profiles, f) for f in fields):
                holds.append('safety_status_unknown')
        for field, label in (
            ('insolvency_hold_flag', 'insolvency_hold'), ('deceased_hold_flag', 'deceased_hold'),
            ('complaint_flag', 'complaint_review_hold'),
        ):
            if any_true(cases, field):
                holds.append(label)
            elif cases and not all_false(cases, field):
                holds.append('safety_status_unknown')
        if (not all_false(profiles, 'cease_communication_flag') and
                not any_true(profiles, 'cease_communication_flag')):
            holds.append('safety_status_unknown')
        if any(truth(c['cease_contact_flag']) is None or truth(c['dispute_flag']) is None for c in cases):
            holds.append('safety_status_unknown')
        if any(truth(c['dispute_flag']) is True and c['dispute_status'] not in
               ('resolved_customer', 'resolved_bank') for c in cases):
            holds.append('open_dispute')
        if any(c['case_status'] in ('legal', 'placed_agency', 'charged_off') for c in cases):
            holds.append('special_case_queue_review')
        if any(truth(p['is_deleted']) is not False or p['customer_status'] != 'active' for p in profiles):
            holds.append('inactive_or_unknown_profile')
        if self.has_c360:
            externals = records(con, """SELECT e.* FROM external_holds e JOIN identity_crosswalk x
                ON e.bank_subject_ref=x.source_customer_id AND x.source_system='core_banking'
                WHERE x.golden_customer_id=? AND x.link_status='linked'
                  AND try_cast(e.pull_date AS DATE) <= ?""", [golden_id, SNAPSHOT_DATE])
            for field, label in (
                ('fraud_alert_flag', 'fraud_review_hold'), ('deceased_indicator', 'deceased_hold'),
                ('bankruptcy_on_file_flag', 'insolvency_hold'), ('consumer_proposal_on_file_flag', 'insolvency_hold'),
            ):
                if any_true(externals, field):
                    holds.append(label)
            if con.execute("""SELECT count(*) FROM card_holds c JOIN identity_crosswalk x
                ON c.src_customer_ref=x.source_customer_id AND x.source_system='cards'
                WHERE x.golden_customer_id=? AND x.link_status='linked'
                  AND try_cast(c.fraud_block_flag AS BOOLEAN)""", [golden_id]).fetchone()[0]:
                holds.append('fraud_review_hold')
        attempts = con.execute("""SELECT
            count(*) FILTER (WHERE channel='call'),
            count(*) FILTER (WHERE channel IN ('sms','email','push','ivr'))
            FROM contact_evidence WHERE case_id IN (SELECT unnest(?))
              AND direction='outbound' AND contact_ts_utc < ?
              AND contact_ts_utc >= ? - INTERVAL '7 days'""", [case_ids, cutoff, cutoff]).fetchone()
        agent = None
        if hardship or safeguard:
            agents = records(con, """SELECT agent_id FROM agents_state WHERE status='active'
                AND try_cast(vulnerable_customer_certified AS BOOLEAN)
                AND (? = false OR try_cast(skill_hardship AS BOOLEAN))
                AND try_cast(current_case_load AS INTEGER) < try_cast(max_concurrent_cases AS INTEGER)
                ORDER BY try_cast(current_case_load AS INTEGER), agent_id LIMIT 1""", [hardship])
            agent = agents[0]['agent_id'] if agents else None
        # The supported demo date is Monday 28 Sep, not a statutory holiday.
        # Other dates are rejected above rather than inventing a regional calendar.
        return DecisionContext(
            customer_id=golden_id, crm_ids=crm_ids, case_ids=case_ids, as_of=as_of,
            time_zone=next(iter(zones)) if len(zones) == 1 else None,
            linked=self.has_c360, identity_needs_review=bool(golden and golden['dq_status'] != 'passed'),
            consent=consent, hardship=hardship, specialist_safeguard=safeguard,
            routing_trigger=routing_trigger,
            holds=sorted(set(holds)),
            cease_contact=(any_true(profiles, 'cease_communication_flag') or
                           any_true(cases, 'cease_contact_flag') or any_true(support, 'cease_request_flag')),
            representative=any(any_true(profiles, f) for f in ('credit_counselling_agency_flag',
                              'legal_representative_flag', 'power_of_attorney_flag')),
            call_attempts_7d=attempts[0], payment_reminders_7d=attempts[1],
            contact_cap_7d=min([int(c['contact_cap_7d']) if str(c['contact_cap_7d']).isdigit() else 0
                              for c in cases] or [0]),
            sunday_permitted=all(truth(p['sunday_contact_permitted']) is True for p in profiles),
            permitted_start=max((p['permitted_call_start_local'] or 'unknown') for p in profiles),
            permitted_end=min((p['permitted_call_end_local'] or 'unknown') for p in profiles),
            holiday=False, specialist_agent_id=agent,
        )

    def model_features(self, context: DecisionContext) -> dict:
        """At-snapshot numerical inputs with the same ten definitions as training.

        Only linked source IDs are used; no safeguard flag, protected attribute,
        deposit or transaction amount is included.
        """
        from src.features.training import model_columns
        from .train import MODEL_COLUMNS

        model_columns(MODEL_COLUMNS)
        if not context.linked or not context.case_ids:
            return {}
        con = self.connection
        cutoff = utc_cutoff(context.as_of)
        cases = records(con, "SELECT current_dpd,total_overdue FROM cases_state WHERE case_id IN (SELECT unnest(?))",
                        [context.case_ids])
        def number(value):
            try:
                return float(value) if value not in (None, '') else None
            except (TypeError, ValueError):
                return None
        dpd_values = [number(row['current_dpd']) for row in cases]
        dpd = max((value for value in dpd_values if value is not None), default=None)
        overdue = sum((number(row['total_overdue']) or 0) for row in cases)
        prior = con.execute("""SELECT count(*) FROM promise_evidence
            WHERE crm_customer_id IN (SELECT unnest(?)) AND ptp_status='broken'
              AND ptp_created_ts<? AND status_ts<?""", [context.crm_ids, cutoff, cutoff]).fetchone()[0]
        broken90 = con.execute("""SELECT count(*) FROM promise_evidence
            WHERE crm_customer_id IN (SELECT unnest(?)) AND ptp_status='broken'
              AND ptp_created_ts<? AND status_ts<?
              AND status_ts>=? - INTERVAL '90 days'""",
            [context.crm_ids, cutoff, cutoff, cutoff]).fetchone()[0]
        earlier = con.execute("""SELECT count(*) FILTER (WHERE ptp_status='kept'), count(*)
            FROM promise_evidence WHERE crm_customer_id IN (SELECT unnest(?))
              AND ptp_status IN ('kept','broken') AND ptp_created_ts<? AND status_ts<?""",
            [context.crm_ids, cutoff, cutoff]).fetchone()
        contacts = con.execute("""SELECT count(*),count(*) FILTER (WHERE rpc_flag)
            FROM contact_evidence WHERE crm_customer_id IN (SELECT unnest(?))
              AND direction='outbound' AND contact_ts_utc<?
              AND contact_ts_utc>=? - INTERVAL '30 days'""",
            [context.crm_ids, cutoff, cutoff]).fetchone()
        salary_path = self.data_dir / 'data/salary_credit_history' / '*' / '*.parquet'
        payroll_date = None
        if list((self.data_dir / 'data/salary_credit_history').glob('*/*.parquet')):
            payroll_date = con.execute(f"""SELECT max(last_credit_date)
                FROM read_parquet({quote_path(salary_path)}, hive_partitioning=true)
                WHERE crm_customer_id IN (SELECT unnest(?)) AND employer_flag='Y'
                  AND last_credit_date < ?""", [context.crm_ids, cutoff.date()]).fetchone()[0]
        snapshots = self.data_dir / 'data/account_monthly_snapshot' / '*' / '*.parquet'
        card = con.execute(f"""SELECT arg_max(
                try_cast(balance AS DOUBLE)/nullif(try_cast(limit_or_original_amount AS DOUBLE),0),
                struct_pack(d:=CAST(try_strptime(CAST(month_end_date AS VARCHAR),
                    ['%Y-%m-%d','%d/%m/%Y','%Y%m%d']) AS DATE),a:=account_id))
            FROM read_parquet({quote_path(snapshots)}, hive_partitioning=true)
            WHERE product_type='card'
              AND crm_customer_id IN (SELECT unnest(?))
              AND CAST(try_strptime(CAST(month_end_date AS VARCHAR),
                    ['%Y-%m-%d','%d/%m/%Y','%Y%m%d']) AS DATE) < ?""",
            [context.crm_ids, cutoff.date()]).fetchone()[0]
        cores = [row[0] for row in con.execute("""SELECT source_customer_id FROM identity_crosswalk
            WHERE golden_customer_id=? AND source_system='core_banking' AND link_status='linked'""",
            [context.customer_id]).fetchall()]
        bureau_score = bureau_delta = None
        if cores:
            bureau_path = self.data_dir / 'data/bureau_history' / '*' / '*.parquet'
            bureau_rows = con.execute(f"""WITH scored AS (
              SELECT bank_subject_ref,pull_date,try_cast(risk_score AS DOUBLE) AS risk_score,
                     lag(try_cast(risk_score AS DOUBLE)) OVER (
                       PARTITION BY bank_subject_ref ORDER BY pull_date) AS previous_score
              FROM read_parquet({quote_path(bureau_path)}, hive_partitioning=true)
              WHERE bank_subject_ref IN (SELECT unnest(?)) AND pull_date<?
            ) SELECT risk_score,risk_score-previous_score FROM scored
              ORDER BY pull_date DESC, bank_subject_ref DESC LIMIT 1""",
              [cores, cutoff.date()]).fetchone()
            if bureau_rows:
                bureau_score, bureau_delta = bureau_rows
        result = {
            'dpd_at_creation': dpd,
            'dpd_bucket_at_creation': (0 if dpd < 30 else 1 if dpd < 60 else 2 if dpd < 90 else 3)
                                      if dpd is not None else None,
            'overdue_at_creation': overdue,
            'prior_broken_ptp_count_at_creation': prior,
            'broken_promises_90d': broken90,
            'recent_contacts_30d': contacts[0], 'recent_rpc_30d': contacts[1],
            'card_utilisation': card, 'bureau_risk_score': bureau_score,
            'earlier_kept_rate': earlier[0] / earlier[1] if earlier[1] else None,
            'days_since_last_payroll': (cutoff.date() - payroll_date).days if payroll_date else None,
        }
        model_columns(result)
        return result

    def close(self):
        self.connection.close()
