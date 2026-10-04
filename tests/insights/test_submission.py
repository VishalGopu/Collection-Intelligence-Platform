import csv
from pathlib import Path

import pytest

from src.insights import submission
from src.insights.engine import AnswerCard


class _Connection:
    def close(self) -> None:
        pass


def test_submission_writes_official_columns_and_preserves_question_ids(
    tmp_path: Path, monkeypatch
) -> None:
    class Engine:
        def __init__(self, root) -> None:
            self.connection = _Connection()
            self.llm_planner = None

        def answer(self, question, question_id):
            return AnswerCard(question_id, question, "count\n1", "SELECT count(*) FROM collections_cases")

    monkeypatch.setattr(submission, "InsightEngine", Engine)
    questions = tmp_path / "questions.csv"
    questions.write_text("question_id,question_text\nQ1,How many cases?\n", encoding="utf-8")
    output = tmp_path / "answers.csv"
    assert submission.run(questions, output) == 1
    with output.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows == [{"question_id": "Q1", "answer": "count\n1",
                     "sql_or_sources": "SELECT count(*) FROM collections_cases", "refused": "false"}]


def test_submission_rejects_answer_without_evidence(tmp_path: Path, monkeypatch) -> None:
    class Engine:
        def __init__(self, root) -> None:
            self.connection = _Connection()
            self.llm_planner = None

        def answer(self, question, question_id):
            return AnswerCard(question_id, question, "1", "")

    monkeypatch.setattr(submission, "InsightEngine", Engine)
    questions = tmp_path / "questions.csv"
    questions.write_text("question_id,question_text\nQ1,How many cases?\n", encoding="utf-8")
    output = tmp_path / "answers.csv"
    with pytest.raises(ValueError, match="no SQL or sources"):
        submission.run(questions, output)
    assert not output.exists()
