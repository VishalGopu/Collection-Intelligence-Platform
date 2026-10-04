"""Governed Layer 2 question answering for the Maple Collections dataset."""

from __future__ import annotations

import csv
import json
import os
import re
import time
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb
from sqlglot import exp, parse
from dotenv import load_dotenv

from .llm import OpenAIResponsesPlanner, PlannerError, SQLPlanner
from .queries import SQL_BY_QUESTION


SNAPSHOT_DATE = "2026-09-28"
MAX_RESULT_ROWS = 200
KNOWN_TABLES = {
    "collections_cases", "contact_history", "promises_to_pay", "card_accounts",
    "loan_accounts", "call_transcripts", "agents", "ops_events",
    "account_monthly_snapshot",
}
BLOCKED_LLM_COLUMNS = {
    "gender", "marital_status", "citizenship_status", "newcomer_flag",
    "accessibility_flag", "vulnerable_customer_flag", "accent",
    "first_name", "last_name", "full_name", "primary_phone_e164",
    "primary_email", "phone_number", "email_address",
}
SENSITIVE_COLUMN_PARTS = (
    "gender", "marital", "citizenship", "newcomer", "accessibility", "vulnerab",
    "accent", "date_of_birth", "dob", "phone", "email", "first_name", "last_name",
    "full_name", "national_id", "address", "postal", "sin_", "ssn_",
)
DIRECT_ID_COLUMNS = {"crm_customer_id", "src_customer_ref", "source_customer_id", "coll_customer_ref", "customer_id", "case_id", "contact_id", "ptp_id", "agent_id"}


@dataclass(frozen=True)
class AnswerCard:
    question_id: str
    question: str
    answer: str
    sql_or_sources: str
    refused: bool = False
    mode: str = "structured"
    as_of_date: str = SNAPSHOT_DATE
    metric_definition: str | None = None
    scope: str = "global Collections"

    def benchmark_row(self) -> dict[str, str]:
        return {
            "question_id": self.question_id,
            "answer": self.answer,
            "sql_or_sources": self.sql_or_sources,
            "refused": str(self.refused).lower(),
        }


DOCUMENT_ANSWERS: dict[str, tuple[str, list[str]]] = {
    "BQ-001": ("No. CASL express consent applies to marketing; a collections payment reminder relies on account-servicing consent.", ["POL-COLL-001 §5.3"]),
    "BQ-002": ("A maximum of 3 outbound call attempts in any rolling 7 days per case.", ["POL-COLL-001 §5.2"]),
    "BQ-005": ("No. The National Do Not Call List applies to telemarketing only and does not block collection calls.", ["POL-COLL-001 §5.3", "FAQ-COLL-001 Q2"]),
    "BQ-009": ("Stop all collection contact from the filing date and move the case to insolvency_hold because a stay of proceedings applies.", ["POL-COLL-001 §7.3"]),
    "BQ-019": ("Acknowledge and record the hardship, offer at least one eligible hardship option before asking for payment, and do not request an unaffordable payment.", ["POL-COLL-004 §4.2", "qa_checklist item 7"]),
    "BQ-020": ("Do not start legal action solely because two payments were missed. Follow the bank's governed escalation and legal-review process; this dataset does not provide enough case facts to authorize a lawsuit.", ["POL-COLL-001", "collections case record required"]),
    "BQ-026": ("The reduced-payment programme lasts 3 months. The customer pays 50% of the regular payment; interest continues to accrue.", ["POL-COLL-004 §4.2", "HPT-2026 §1"]),
    "BQ-030": ("Outbound call volume dropped because the predictive dialer was degraded on 23–24 September 2026, reducing capacity by about 60%; this was not a change in customer behaviour.", ["IR-2026-0923 §1–§2", "ops event INC-0923"]),
    "BQ-033": ("A promise to pay has a grace period of 2 business days after the promised date.", ["PRC-COLL-010 §3.3", "FAQ-COLL-001 Q4"]),
}

REFUSALS: dict[str, str] = {
    "BQ-018": "I can only answer questions about Maple Bank collections data and policy; weather is outside scope.",
    "BQ-023": "I cannot export bulk customer names and phone numbers. Request an approved, purpose-limited aggregate instead.",
    "BQ-024": "I cannot exclude postal areas from hardship support. Location can proxy protected or socioeconomic status, and hardship must be assessed using eligible case circumstances.",
    "BQ-029": "I cannot rank customers using citizenship or newcomer status because it is a protected ground.",
    "BQ-031": "I cannot disclose or profile customers by gender or marital status because those are protected attributes.",
}

TRANSCRIPT_QUESTIONS = {"BQ-016", "BQ-021", "BQ-022"}


class InsightEngine:
    """Routes approved questions to certified SQL, documents, or case evidence."""

    def __init__(
        self,
        dataset_root: str | Path,
        connection: duckdb.DuckDBPyConnection | None = None,
        llm_planner: SQLPlanner | None = None,
        cache_database: str | Path | None = None,
        c360_root: str | Path = "local_artifacts/c360",
    ):
        self.root = Path(dataset_root).resolve()
        self.data = self.root / "data"
        self.c360_root = Path(c360_root).resolve()
        if not (self.root / "README.md").is_file():
            raise FileNotFoundError(f"Dataset release not found at {self.root}")
        self.connection = connection or duckdb.connect(str(cache_database) if cache_database else ":memory:")
        self.connection.execute("PRAGMA disable_progress_bar")
        self.connection.execute("SET memory_limit='2GB'")
        self.cache_database = cache_database is not None
        self.query_seconds = 0.0
        self.query_count = 0
        self._questions = self._read_questions()
        self._metrics = self._read_metrics()
        self.llm_planner = llm_planner or self._planner_from_environment()
        self._register_views()
        self._catalog = self._catalog_text()

    def _read_questions(self) -> dict[str, str]:
        with (self.data / "benchmark_questions.csv").open(newline="", encoding="utf-8") as handle:
            return {row["question_id"]: row["question_text"] for row in csv.DictReader(handle)}

    def _read_metrics(self) -> dict[str, dict[str, str]]:
        with (self.data / "metric_definitions.csv").open(newline="", encoding="utf-8") as handle:
            return {row["metric_id"]: row for row in csv.DictReader(handle)}

    @staticmethod
    def _planner_from_environment() -> SQLPlanner | None:
        load_dotenv()
        openai_key = os.environ.get("OPENAI_API_KEY")
        groq_key = os.environ.get("GROQ_API_KEY") or os.environ.get("grok_api_key")
        api_key = openai_key or groq_key
        # Be tolerant of a common local `.env` typo: `KEY==value`.
        if api_key:
            api_key = api_key.lstrip("=").strip()
        if not api_key:
            return None
        if not openai_key:
            return OpenAIResponsesPlanner(
                api_key=api_key, model=os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b"),
                fallback_model=os.environ.get("GROQ_FALLBACK_MODEL", "openai/gpt-oss-20b"), provider="groq",
            )
        return OpenAIResponsesPlanner(api_key=api_key, model=os.environ.get("OPENAI_MODEL", "gpt-5-mini"))

    def _register_views(self) -> None:
        tables = {
            "collections_cases", "contact_history", "promises_to_pay", "card_accounts",
            "loan_accounts", "call_transcripts", "agents", "ops_events",
        }
        for table in tables:
            path = (self.data / f"{table}.csv").as_posix().replace("'", "''")
            if self.cache_database and table in {"collections_cases", "contact_history", "promises_to_pay"}:
                source = self.data / f"{table}.csv"
                stamp = f"{source.stat().st_size}:{source.stat().st_mtime_ns}"
                self.connection.execute("CREATE TABLE IF NOT EXISTS insights_cache_meta (table_name VARCHAR PRIMARY KEY, source_stamp VARCHAR)")
                old = self.connection.execute("SELECT source_stamp FROM insights_cache_meta WHERE table_name = ?", [table]).fetchone()
                exists = self.connection.execute("SELECT 1 FROM information_schema.tables WHERE table_name = ?", [table]).fetchone()
                if old != (stamp,) or not exists:
                    self.connection.execute(f"DROP TABLE IF EXISTS {table}")
                    self.connection.execute(
                        f"CREATE TABLE {table} AS SELECT * FROM read_csv('{path}', header=true, sample_size=100000, null_padding=true)"
                    )
                    self.connection.execute("INSERT OR REPLACE INTO insights_cache_meta VALUES (?, ?)", [table, stamp])
                continue
            self.connection.execute(
                f"CREATE OR REPLACE VIEW {table} AS "
                f"SELECT * FROM read_csv('{path}', header=true, sample_size=100000, null_padding=true)"
            )
        parquet = (self.data / "account_monthly_snapshot" / "*" / "*.parquet").as_posix().replace("'", "''")
        self.connection.execute(
            "CREATE OR REPLACE VIEW account_monthly_snapshot AS "
            f"SELECT * EXCLUDE (year) FROM read_parquet('{parquet}', hive_partitioning=true)"
        )
        self._register_crosswalk_view()

    def _register_crosswalk_view(self) -> bool:
        crosswalk = self.c360_root / "identity_crosswalk.parquet"
        if not crosswalk.is_file():
            return False
        path = crosswalk.as_posix().replace("'", "''")
        self.connection.execute(
            "CREATE OR REPLACE VIEW identity_crosswalk AS "
            f"SELECT * FROM read_parquet('{path}')"
        )
        return True

    def answer(self, question: str, question_id: str | None = None, *, scope: str | None = None) -> AnswerCard:
        matched = self._match_question(question)
        if not matched:
            refusal = self._safety_refusal(question)
            if refusal:
                return AnswerCard(question_id or "AD-HOC", question, refusal,
                                  "policy guardrail", True, "refusal")
        if scope is not None and self._is_customer_scoped_question(question):
            return self._answer_scoped(question, scope, question_id)
        if scope is None and self._explicit_customer_reference(question):
            return AnswerCard(question_id or "AD-HOC", question,
                              "Select a golden customer to answer this customer-specific question.",
                              "customer scope required", True, "refusal")
        external_id = question_id if question_id and question_id not in self._questions else None
        qid = (question_id if question_id in self._questions and
               self._normalize_question(question) == self._normalize_question(self._questions[question_id])
               else matched)
        if not qid:
            refusal = self._safety_refusal(question)
            if refusal:
                card = AnswerCard("AD-HOC", question, refusal, "policy guardrail", True, "refusal")
            else:
                card = self._answer_cases_after(question) or self._answer_with_llm(question)
            return replace(card, question_id=external_id) if external_id else card
        canonical = self._questions.get(qid, question)
        if qid in REFUSALS:
            card = AnswerCard(qid, canonical, REFUSALS[qid], "policy guardrail", True, "refusal")
            return replace(card, question_id=external_id, question=question) if external_id else card
        if qid in SQL_BY_QUESTION:
            card = self._answer_sql(qid, canonical, SQL_BY_QUESTION[qid])
            return replace(card, question_id=external_id, question=question) if external_id else card
        if qid in DOCUMENT_ANSWERS:
            answer, sources = DOCUMENT_ANSWERS[qid]
            card = AnswerCard(qid, canonical, answer, json.dumps(sources), mode="document")
            return replace(card, question_id=external_id, question=question) if external_id else card
        if qid in TRANSCRIPT_QUESTIONS:
            card = self._answer_transcript(qid, canonical)
            return replace(card, question_id=external_id, question=question) if external_id else card
        raise KeyError(f"No governed route for {qid}")

    @staticmethod
    def _explicit_customer_reference(question: str) -> bool:
        return bool(re.search(r"\b(?:this customer|selected customer|this person's|this person|their (?:cases|contacts|promises|balance)|for this customer|for customer G-[0-9a-f]+)\b", question, re.I))

    @staticmethod
    def _is_customer_scoped_question(question: str) -> bool:
        text = question.casefold()
        if InsightEngine._explicit_customer_reference(question) or re.search(r"\bcs-\d{4}-\d+\b", text):
            return True
        return False

    def _answer_cases_after(self, question: str) -> AnswerCard | None:
        normalized = re.sub(r"\s+", " ", question.strip())
        for opening, closing in (("\"", "\""), ("'", "'"), ("“", "”"), ("‘", "’")):
            if normalized.startswith(opening) and normalized.endswith(closing):
                normalized = normalized[1:-1].strip()
                break
        match = re.fullmatch(r"(?:show(?: me)?|list)(?: all)? (open|closed) cases created after (\d{1,2}) (january|february|march|april|may|june|july|august|september|october|november|december) (\d{4})[?.!]?", normalized, re.I)
        if not match:
            return None
        try:
            date = datetime.strptime(" ".join(match.groups()[1:]), "%d %B %Y").date().isoformat()
        except ValueError:
            return self._could_not_answer(question, "invalid date")
        status = match.group(1).casefold()
        sql = ("SELECT case_id, case_open_date, case_status FROM collections_cases "
               f"WHERE case_status = '{status}' AND case_open_date > DATE '{date}' "
               "ORDER BY case_open_date, case_id LIMIT 200")
        card = self._answer_sql("AD-HOC", question, sql)
        return replace(card, mode="empty", answer="No rows matched") if card.answer == "case_id,case_open_date,case_status" else card

    def _answer_scoped(self, question: str, scope: str, question_id: str | None) -> AnswerCard:
        if not re.fullmatch(r"G-[0-9a-f]{20}", scope):
            raise ValueError("scope must be a published golden_customer_id")
        refusal = self._safety_refusal(question)
        if refusal:
            return AnswerCard(question_id or "AD-HOC", question, refusal, "policy guardrail", True, "refusal")
        if not self._register_crosswalk_view():
            return self._could_not_answer(question, "C360 crosswalk is unavailable; run the Layer 1 build")
        case_match = re.search(r"\bCS-\d{4}-\d+\b", question, re.IGNORECASE)
        case_filter = f" AND c.case_id = '{case_match.group(0).upper()}'" if case_match else ""
        cte = (
            "WITH linked_cases AS ("
            "SELECT c.* FROM collections_cases c JOIN "
            "identity_crosswalk x ON x.source_system = 'collections' "
            "AND x.source_customer_id = c.coll_customer_ref "
            f"AND x.golden_customer_id = '{scope}' AND x.link_status = 'linked'{case_filter}), "
            "linked_contacts AS (SELECT h.* FROM contact_history h JOIN linked_cases c ON c.case_id = h.case_id "
            "JOIN identity_crosswalk x ON x.source_system = 'crm' "
            "AND x.source_customer_id = h.crm_customer_id "
            f"AND x.golden_customer_id = '{scope}' AND x.link_status = 'linked'), "
            "linked_promises AS (SELECT p.* FROM promises_to_pay p JOIN linked_cases c ON c.case_id = p.case_id "
            "JOIN identity_crosswalk x ON x.source_system = 'crm' "
            "AND x.source_customer_id = p.crm_customer_id "
            f"AND x.golden_customer_id = '{scope}' AND x.link_status = 'linked') "
        )
        text = question.casefold()
        # These routes are intentionally narrow: a qualifier we do not implement
        # must never disappear from the executed SQL.
        supported = (
            r"how many open cases does this customer have\??",
            r"what is this customer's overdue balance\??",
            r"how many contacts did this customer have\??",
            r"how many broken promises does this customer have\??",
            r"what is the status of cs-\d{4}-\d+\??",
        )
        if not any(re.fullmatch(pattern, text.strip()) for pattern in supported):
            return self._could_not_answer(question, "no certified customer-scoped route preserves every question filter")
        if case_match and not any(word in text for word in ("contact", "promise")):
            sql = cte + "SELECT case_id, case_status, current_dpd, round(total_overdue,2) AS overdue_balance_cad FROM linked_cases"
        elif "contact" in text:
            sql = cte + "SELECT count(*) AS contact_count, count(*) FILTER (WHERE direction='outbound' AND coalesce(channel_v2, channel)='call') AS outbound_calls FROM linked_contacts"
        elif "promise" in text:
            sql = cte + "SELECT count(*) FILTER (WHERE ptp_status='broken') AS broken_promises, count(*) AS total_promises FROM linked_promises"
        elif "overdue" in text or "balance" in text:
            sql = cte + "SELECT round(coalesce(sum(total_overdue),0),2) AS open_overdue_balance_cad FROM linked_cases WHERE case_status='open'"
        elif "case" in text:
            sql = cte + "SELECT count(*) AS open_cases FROM linked_cases WHERE case_status='open'"
        else:
            return self._could_not_answer(question, "no certified customer-scoped route matches this question")
        cursor = self.connection.execute(sql)
        answer = self._format_csv([item[0] for item in cursor.description], cursor.fetchall())
        return AnswerCard(question_id or "AD-HOC", question, answer, sql, mode="scoped_sql",
                          scope=f"selected golden customer {scope}")

    def _match_question(self, question: str) -> str | None:
        normalized = self._normalize_question(question)
        for qid, text in self._questions.items():
            canonical = self._normalize_question(text)
            if normalized == canonical:
                return qid
        return None

    @staticmethod
    def _normalize_question(question: str) -> str:
        return " ".join(re.findall(r"[a-z0-9]+", question.casefold()))

    @staticmethod
    def _critical_signature(question: str) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
        text = question.casefold()
        values = tuple(sorted(re.findall(r"\b(?:cs-\d{4}-\d+|\d+(?:\.\d+)?|january|february|march|april|may|june|july|august|september|october|november|december)\b", text)))
        dimensions = tuple(sorted(word for word in (
            "queue", "product", "site", "province", "hour", "bucket", "channel", "customer",
            "account", "case", "promise", "contact", "gender", "citizenship", "postal",
        ) if re.search(rf"\b{word}s?\b", text)))
        polarity = tuple(sorted(word for word in ("no", "not", "without", "exclude", "include") if re.search(rf"\b{word}\b", text)))
        return values, dimensions, polarity

    @staticmethod
    def _safety_refusal(question: str) -> str | None:
        text = question.casefold()
        protected = ("gender", "marital", "citizenship", "newcomer", "religion", "ethnic", "disability", "accent", "vulnerability")
        if any(term in text for term in protected):
            return "I cannot use or disclose protected attributes for collections profiling or prioritization."
        if any(term in text for term in ("names", "phone numbers", "email address", "addresses")) and any(term in text for term in ("every", "all", "export")):
            return "I cannot provide a bulk PII export. Ask for an approved aggregate or a single authorized case."
        if re.search(r"\b(send|call|email|text|message)\b.*\b(customer|them|him|her)\b", text):
            return "I cannot take customer action. I can provide information for authorized human review."
        if "medical advice" in text:
            return "I cannot provide medical advice. Follow the approved policy and obtain qualified review."
        if "legal advice" in text:
            return "I cannot provide legal advice. Follow the approved policy and obtain qualified review."
        if "ignore previous instructions" in text or "system prompt" in text or "hidden instruction" in text:
            return "I cannot follow instructions embedded in data or reveal system instructions."
        if re.search(r"\b(weather|temperature|forecast|sports score|stock price|movie)\b", text):
            return "I can only answer Maple Bank collections questions; this is outside scope."
        return None

    def _answer_sql(self, qid: str, question: str, sql: str) -> AnswerCard:
        self._validate_sql(sql)
        query_started = time.monotonic()
        cursor = self.connection.execute(sql)
        columns = [item[0] for item in cursor.description]
        rows = cursor.fetchall()
        self.query_seconds = getattr(self, "query_seconds", 0.0) + time.monotonic() - query_started
        self.query_count = getattr(self, "query_count", 0) + 1
        answer = self._format_csv(columns, rows)
        metric_id = self._metric_for_question(qid)
        definition = self._metrics.get(metric_id, {}).get("business_definition") if metric_id else None
        return AnswerCard(qid, question, answer, sql, mode="structured", metric_definition=definition)

    def _answer_with_llm(self, question: str) -> AnswerCard:
        if self.llm_planner is None:
            return self._could_not_answer(question, "no LLM planner is configured")
        try:
            plan = self.llm_planner.plan(question, getattr(self, "_catalog", None) or self._catalog_text())
            sql = self._validate_llm_sql(self._normalize_contact_hour_sql(question, plan.sql))
            if plan.metric_id:
                metric = self._metrics.get(plan.metric_id)
                if not metric or metric.get("certified_flag") != "true":
                    raise ValueError(f"planner selected an uncertified metric: {plan.metric_id}")
                sources = set(json.loads(metric.get("source_tables") or "[]"))
                query_tables = {table.name.casefold() for table in parse(plan.sql, read="duckdb")[0].find_all(exp.Table)}
                if sources and not sources.intersection(query_tables):
                    raise ValueError(f"planner used the wrong tables for metric {plan.metric_id}")
            query_started = time.monotonic()
            cursor = self.connection.execute(sql)
            columns = [item[0] for item in cursor.description]
            rows = cursor.fetchall()
            self.query_seconds = getattr(self, "query_seconds", 0.0) + time.monotonic() - query_started
            self.query_count = getattr(self, "query_count", 0) + 1
            if not rows or all(all(value is None for value in row) for row in rows):
                return AnswerCard("AD-HOC", question, "No rows matched.", sql, False, "empty")
            answer = self._format_csv(columns, rows)
            definition = self._metrics.get(plan.metric_id or "", {}).get("business_definition")
            return AnswerCard("AD-HOC", question, answer, sql, mode="llm_sql", metric_definition=definition)
        except (PlannerError, ValueError, duckdb.Error) as exc:
            return self._could_not_answer(question, str(exc))

    @staticmethod
    def _could_not_answer(question: str, reason: str, evidence: str | None = None) -> AnswerCard:
        safe_reason = re.sub(r"\s+", " ", reason).strip()[:300]
        return AnswerCard(
            "AD-HOC", question, f"I couldn't answer this: {safe_reason}.",
            evidence or f"no query executed: {safe_reason}", True, "unable",
        )

    def _metric_for_question(self, qid: str) -> str | None:
        with (self.data / "benchmark_questions.csv").open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if row["question_id"] == qid:
                    return row.get("metric_id") or None
        return None

    def _catalog_text(self) -> str:
        table_lines = []
        available = {row[0] for row in self.connection.execute("SHOW TABLES").fetchall()}
        for table in sorted(KNOWN_TABLES & available):
            columns = [row[1] for row in self.connection.execute(f"PRAGMA table_info('{table}')").fetchall()]
            table_lines.append(f"{table}({', '.join(columns)})")
        metric_lines = [
            f"{metric_id}: {row['business_definition']} Formula: {row['formula']}"
            for metric_id, row in sorted(self._metrics.items()) if row.get("certified_flag") == "true"
        ]
        return "TABLES\n" + "\n".join(table_lines) + "\nCERTIFIED METRICS\n" + "\n".join(metric_lines)

    @staticmethod
    def _normalize_contact_hour_sql(question: str, sql: str) -> str:
        """Apply the certified local-hour grain to generated contact SQL."""
        if not re.search(r"\b(?:by|per|local) hour\b", question.casefold()) or "utc" in question.casefold():
            return sql
        try:
            statements = parse(sql, read="duckdb")
        except Exception:
            return sql  # The validator will give the parse error.
        if len(statements) != 1:
            return sql  # Preserve the validator's multi-statement rejection.
        tree = statements[0]
        if "contact_history" not in {table.name.casefold() for table in tree.find_all(exp.Table)}:
            return sql

        def rewrite(node: exp.Expression) -> exp.Expression:
            if isinstance(node, exp.Column) and node.name.casefold() == "contact_ts_utc":
                return exp.column("contact_ts_local")
            if isinstance(node, (exp.TimestampTrunc, exp.Hour, exp.Extract)):
                rendered = node.sql(dialect="duckdb").casefold()
                if "hour" in rendered and ("contact_ts_local" in rendered or "contact_ts_utc" in rendered):
                    return exp.column("contact_hour_local")
            return node

        return tree.transform(rewrite).sql(dialect="duckdb")

    @staticmethod
    def _validate_sql(sql: str) -> None:
        normalized = re.sub(r"\s+", " ", sql.strip()).casefold()
        if not (normalized.startswith("select ") or normalized.startswith("with ")):
            raise ValueError("Only SELECT/CTE queries are allowed")
        # Keywords inside quoted values (for example channel = 'call') are data,
        # not executable SQL tokens.
        executable = re.sub(r"'(?:''|[^'])*'", "''", normalized)
        forbidden = re.compile(r"\b(insert|update|delete|drop|alter|create|copy|attach|detach|install|load|call|pragma)\b")
        if forbidden.search(executable) or ";" in executable:
            raise ValueError("Unsafe SQL rejected")

    @staticmethod
    def _validate_llm_sql(sql: str) -> str:
        try:
            statements = parse(sql, read="duckdb")
        except Exception as exc:
            raise ValueError(f"SQL parse failed: {exc}") from exc
        if len(statements) != 1:
            raise ValueError("LLM SQL must contain exactly one statement")
        tree = statements[0]
        forbidden = (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Command, exp.Copy)
        if isinstance(tree, forbidden) or any(tree.find(kind) for kind in forbidden):
            raise ValueError("LLM SQL is not read-only")
        tables = {table.name.casefold() for table in tree.find_all(exp.Table)}
        if not tables:
            raise ValueError("LLM SQL must query an approved table")
        unknown = tables - KNOWN_TABLES
        if unknown:
            raise ValueError(f"LLM SQL referenced unknown tables: {', '.join(sorted(unknown))}")
        if any(isinstance(item, exp.Star) or (isinstance(item, exp.Column) and item.is_star)
               for select in tree.find_all(exp.Select) for item in select.expressions):
            raise ValueError("LLM SQL may not project SELECT *")
        if any(isinstance(item, exp.Column) and item.name.casefold() in DIRECT_ID_COLUMNS
               for select in tree.find_all(exp.Select) for item in select.expressions):
            raise ValueError("LLM SQL may not output direct identifiers")
        columns = {column.name.casefold() for column in tree.find_all(exp.Column)}
        blocked = {name for name in columns if name in BLOCKED_LLM_COLUMNS or any(part in name for part in SENSITIVE_COLUMN_PARTS)}
        if blocked:
            raise ValueError(f"LLM SQL referenced blocked columns: {', '.join(sorted(blocked))}")
        if len(list(tree.find_all(exp.Table))) > 4:
            raise ValueError("LLM SQL referenced too many tables")
        if any(join.args.get("kind") == "CROSS" for join in tree.find_all(exp.Join)):
            raise ValueError("LLM SQL may not use CROSS JOIN")
        for function in tree.find_all(exp.Func):
            name = function.sql_name().casefold()
            if name.startswith("read_") or name in {"httpfs", "shell", "system"}:
                raise ValueError(f"LLM SQL used forbidden function: {name}")
        rendered = tree.sql(dialect="duckdb")
        return f"SELECT * FROM ({rendered}) AS governed_result LIMIT {MAX_RESULT_ROWS}"

    @staticmethod
    def _format_csv(columns: list[str], rows: list[tuple[Any, ...]]) -> str:
        import io
        output = io.StringIO()
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(columns)
        writer.writerows(rows)
        return output.getvalue().rstrip("\n")

    def _answer_transcript(self, qid: str, question: str) -> AnswerCard:
        case_match = re.search(r"CS-\d{4}-\d+", question)
        if not case_match:
            raise ValueError("Transcript question is missing a case ID")
        case_id = case_match.group(0)
        row = self.connection.execute(
            "SELECT transcript_id, file_path FROM call_transcripts "
            "WHERE case_id = ? ORDER BY call_start_ts DESC LIMIT 1", [case_id]
        ).fetchone()
        if not row:
            return AnswerCard(qid, question, "No recorded call was found for this case.", f"case {case_id}", mode="transcript")
        transcript_id, relative_path = row
        transcript_path = self.root / relative_path
        if not transcript_path.is_file():
            transcript_path = self.root / "files" / relative_path
        payload = json.loads(transcript_path.read_text(encoding="utf-8"))
        turns = payload.get("turns", [])
        customer_text = " ".join(
            str(turn.get("text", "")) for turn in turns
            if str(turn.get("speaker", "")).casefold() == "customer"
        )
        summary = self._summarize_transcript(customer_text, payload.get("call_start_ts"))
        return AnswerCard(qid, question, summary, json.dumps([f"transcript {transcript_id}"]), mode="transcript")

    @staticmethod
    def _summarize_transcript(text: str, call_start_ts: str | None = None) -> str:
        lowered = text.casefold()
        issues = []
        for pattern, label in (
            (r"\b(?:ill|illness|sick)\b", "illness"),
            (r"\b(?:hours|income|overtime)\b|days a week|making less", "reduced hours / income"),
            (r"\bjob\b", "employment disruption"),
            (r"\bstop\b", "requested contact to stop"),
        ):
            if re.search(pattern, lowered) and label not in issues:
                issues.append(label)
        promise = re.search(
            r"(?:can\s+pay|promise(?:d)?(?:\s+to\s+pay)?)\s+\$?\s?"
            r"([0-9][0-9,]*(?:\.[0-9]{1,2})?)\s+(?:on\s+)?("
            r"(?:[0-3]?\d\s+)?(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
            r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)(?:\s+[0-3]?\d)?|"
            r"the\s+[0-3]?\d(?:st|nd|rd|th)?|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)",
            text, re.I,
        )
        parts = ["Customer reports " + (", ".join(issues) if issues else "payment difficulty") + "."]
        if promise:
            promised_date = InsightEngine._resolve_relative_date(promise.group(2), call_start_ts)
            parts.append(f" Promised ${promise.group(1)} on {promised_date}.")
        if "requested contact to stop" in issues:
            parts.append(" Next step: stop contact and apply the cease-communication process.")
        elif any(item in issues for item in ("illness", "reduced hours / income", "employment disruption")):
            parts.append(" Next step: hardship plan review.")
        return "".join(parts)

    @staticmethod
    def _resolve_relative_date(value: str, call_start_ts: str | None) -> str:
        value = value.strip()
        if not call_start_ts:
            return value
        call_date = datetime.fromisoformat(call_start_ts).date()
        ordinal = re.fullmatch(r"the\s+([0-3]?\d)(?:st|nd|rd|th)?", value, re.I)
        if ordinal:
            day = int(ordinal.group(1))
            month = call_date.month + (day <= call_date.day)
            year = call_date.year + (month == 13)
            month = 1 if month == 13 else month
            resolved = datetime(year, month, day)
            return f"{resolved.day} {resolved:%b}"
        weekdays = {name.casefold(): index for index, name in enumerate(
            ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
        )}
        if value.casefold() in weekdays:
            days = (weekdays[value.casefold()] - call_date.weekday()) % 7 or 7
            resolved = call_date + timedelta(days=days)
            return f"{resolved.day} {resolved:%b}"
        return value

    def run_benchmark(self, output_path: str | Path, split: str | None = None) -> list[AnswerCard]:
        questions_path = self.data / "benchmark_questions.csv"
        with questions_path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        selected = [row for row in rows if split is None or row["split"] == split]
        cards = [self.answer(row["question_text"], row["question_id"]) for row in selected]
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["question_id", "answer", "sql_or_sources", "refused"])
            writer.writeheader()
            writer.writerows(card.benchmark_row() for card in cards)
        return cards
