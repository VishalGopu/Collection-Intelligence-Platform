from pathlib import Path

import duckdb
import pytest

from src.insights.engine import InsightEngine


@pytest.fixture
def fixture_root(tmp_path: Path) -> Path:
    root = tmp_path / "release"
    data = root / "data"
    data.mkdir(parents=True)
    (root / "README.md").write_text("fixture", encoding="utf-8")
    (data / "benchmark_questions.csv").write_text(
        "question_id,question_text,difficulty,metric_id,as_of_date,tolerance,split\n"
        "BQ-018,What will the weather be in Toronto tomorrow?,easy,,2026-09-28,,dev\n",
        encoding="utf-8",
    )
    return root


def bare_engine(root: Path) -> InsightEngine:
    engine = InsightEngine.__new__(InsightEngine)
    engine.root = root
    engine.data = root / "data"
    engine.connection = duckdb.connect(":memory:")
    engine._questions = {"BQ-018": "What will the weather be in Toronto tomorrow?"}
    return engine


def test_out_of_scope_question_is_refused(fixture_root: Path) -> None:
    card = bare_engine(fixture_root).answer("What will the weather be in Toronto tomorrow?")
    assert card.refused is True
    assert card.mode == "refusal"


def test_protected_attribute_ad_hoc_question_is_refused(fixture_root: Path) -> None:
    card = bare_engine(fixture_root).answer("Rank customers by citizenship")
    assert card.refused is True
    assert "protected" in card.answer


def test_sql_validator_allows_select_and_blocks_mutation() -> None:
    InsightEngine._validate_sql("SELECT 1")
    InsightEngine._validate_sql("WITH x AS (SELECT 1) SELECT * FROM x")
    InsightEngine._validate_sql("SELECT * FROM contacts WHERE channel = 'call'")
    with pytest.raises(ValueError):
        InsightEngine._validate_sql("DELETE FROM collections_cases")
    with pytest.raises(ValueError):
        InsightEngine._validate_sql("SELECT 1; DROP TABLE collections_cases")


def test_csv_answer_formatting() -> None:
    assert InsightEngine._format_csv(["queue", "count"], [("early", 2)]) == "queue,count\nearly,2"


def test_transcript_summary_uses_promised_date_not_hardship_date() -> None:
    text = "I've been off work sick since Jul. I can pay $95 Oct 14."
    summary = InsightEngine._summarize_transcript(text)
    assert "illness" in summary
    assert "$95 on Oct 14" in summary


def test_transcript_summary_does_not_find_ill_inside_calling() -> None:
    text = "Please stop calling me. I'm only getting 3 days a week now. I can pay 595 the 5th."
    summary = InsightEngine._summarize_transcript(text, "2026-09-27 16:58:41")
    assert "illness" not in summary
    assert "reduced hours / income" in summary
    assert "$595 on 5 Oct" in summary


def test_transcript_summary_resolves_weekday_after_call() -> None:
    text = "I lost my overtime so I'm making less. I can pay $195 Thursday."
    summary = InsightEngine._summarize_transcript(text, "2026-09-27 12:00:00")
    assert "reduced hours / income" in summary
    assert "$195 on 1 Oct" in summary
