from app.answer_display import display_answer


def test_ask_count_is_readable_without_changing_value() -> None:
    assert display_answer("open_cases_60plus_dpd\n27112", "llm_sql") == {
        "kind": "metric", "label": "Open Cases 60+ DPD", "value": "27,112",
    }


def test_ask_table_and_prose_keep_their_meaning() -> None:
    assert display_answer("queue,open_cases\nearly,1\nlate,2", "structured") == {
        "kind": "table", "rows": [
            {"queue": "early", "open_cases": "1"},
            {"queue": "late", "open_cases": "2"},
        ],
    }
    assert display_answer("A maximum of 3 outbound calls.", "document") == {
        "kind": "text", "text": "A maximum of 3 outbound calls.",
    }
    assert display_answer("No rows matched", "empty") == {"kind": "empty"}


def test_top_list_shows_total_once_and_keeps_ranked_rows() -> None:
    answer = "total_open_cases,Rank,Days past due\n86059,1,150\n86059,2,149"
    assert display_answer(answer, "structured") == {
        "kind": "table_with_total", "label": "Open cases", "value": "86,059",
        "rows": [{"Rank": "1", "Days past due": "150"},
                 {"Rank": "2", "Days past due": "149"}],
    }
