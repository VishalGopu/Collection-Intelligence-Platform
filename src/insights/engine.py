"""Governed Layer 2 question answering for the Maple Collections dataset."""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb

from .queries import SQL_BY_QUESTION


@dataclass(frozen=True)
class AnswerCard:
    question_id: str
    question: str
    answer: str
    sql_or_sources: str
    refused: bool = False
    mode: str = "structured"

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

    def __init__(self, dataset_root: str | Path, connection: duckdb.DuckDBPyConnection | None = None):
        self.root = Path(dataset_root).resolve()
        self.data = self.root / "data"
        if not (self.root / "README.md").is_file():
            raise FileNotFoundError(f"Dataset release not found at {self.root}")
        self.connection = connection or duckdb.connect(":memory:")
        self._questions = self._read_questions()
        self._register_views()

    def _read_questions(self) -> dict[str, str]:
        with (self.data / "benchmark_questions.csv").open(newline="", encoding="utf-8") as handle:
            return {row["question_id"]: row["question_text"] for row in csv.DictReader(handle)}

    def _register_views(self) -> None:
        tables = {
            "collections_cases", "contact_history", "promises_to_pay", "card_accounts",
            "loan_accounts", "call_transcripts", "agents", "ops_events",
        }
        for table in tables:
            path = (self.data / f"{table}.csv").as_posix().replace("'", "''")
            self.connection.execute(
                f"CREATE OR REPLACE VIEW {table} AS "
                f"SELECT * FROM read_csv('{path}', header=true, sample_size=100000, null_padding=true)"
            )
        parquet = (self.data / "account_monthly_snapshot" / "*" / "*.parquet").as_posix().replace("'", "''")
        self.connection.execute(
            "CREATE OR REPLACE VIEW account_monthly_snapshot AS "
            f"SELECT * EXCLUDE (year) FROM read_parquet('{parquet}', hive_partitioning=true)"
        )

    def answer(self, question: str, question_id: str | None = None) -> AnswerCard:
        qid = question_id or self._match_question(question)
        if not qid:
            refusal = self._safety_refusal(question)
            if refusal:
                return AnswerCard("AD-HOC", question, refusal, "policy guardrail", True, "refusal")
            return AnswerCard(
                "AD-HOC", question,
                "I cannot answer this reliably with the current certified query and document catalog.",
                "no approved query or sufficiently specific source", True, "refusal",
            )
        canonical = self._questions.get(qid, question)
        if qid in REFUSALS:
            return AnswerCard(qid, canonical, REFUSALS[qid], "policy guardrail", True, "refusal")
        if qid in SQL_BY_QUESTION:
            return self._answer_sql(qid, canonical, SQL_BY_QUESTION[qid])
        if qid in DOCUMENT_ANSWERS:
            answer, sources = DOCUMENT_ANSWERS[qid]
            return AnswerCard(qid, canonical, answer, json.dumps(sources), mode="document")
        if qid in TRANSCRIPT_QUESTIONS:
            return self._answer_transcript(qid, canonical)
        raise KeyError(f"No governed route for {qid}")

    def _match_question(self, question: str) -> str | None:
        normalized = " ".join(question.casefold().split())
        for qid, text in self._questions.items():
            if normalized == " ".join(text.casefold().split()):
                return qid
        return None

    @staticmethod
    def _safety_refusal(question: str) -> str | None:
        text = question.casefold()
        protected = ("gender", "marital", "citizenship", "newcomer", "religion", "ethnic", "disability")
        if any(term in text for term in protected):
            return "I cannot use or disclose protected attributes for collections profiling or prioritization."
        if ("names" in text or "phone numbers" in text) and ("every" in text or "all" in text or "export" in text):
            return "I cannot provide a bulk PII export. Ask for an approved aggregate or a single authorized case."
        return None

    def _answer_sql(self, qid: str, question: str, sql: str) -> AnswerCard:
        self._validate_sql(sql)
        cursor = self.connection.execute(sql)
        columns = [item[0] for item in cursor.description]
        rows = cursor.fetchall()
        answer = self._format_csv(columns, rows)
        return AnswerCard(qid, question, answer, sql, mode="structured")

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
            return datetime(year, month, day).strftime("%-d %b")
        weekdays = {name.casefold(): index for index, name in enumerate(
            ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
        )}
        if value.casefold() in weekdays:
            days = (weekdays[value.casefold()] - call_date.weekday()) % 7 or 7
            return (call_date + timedelta(days=days)).strftime("%-d %b")
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
