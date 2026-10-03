# App integration interfaces

The Customer tab is live. The Ask and Recommendation tabs in `app/main.py` are placeholders for the other work areas. Each tab receives the selected `golden_customer_id` from the Customer input. Both integrations must use published C360 links with `link_status = 'linked'` and must keep fairness-test fields out of answers and decision features.

## Ask tab — Questions team

Target app adapter:

```python
def answer(question: str, *, golden_customer_id: str) -> dict:
    """Return {answer, sql_or_sources, refused, mode, data_date}."""
```

The current `src.insights.engine.InsightEngine(dataset_root).answer(question, question_id=None)` returns an `AnswerCard` with `answer`, `sql_or_sources`, `refused`, and `mode`. The Questions team should add a customer-scope adapter that filters case-level records through the C360 crosswalk before wiring the tab. Do not pass the golden ID merely as display text; it must constrain the query or retrieval. The UI should show the SQL or source IDs, refusal status, and snapshot date.

## Recommendation tab — Decisioning team

Existing callable:

```python
from src.decisioning import RecommendationEngine

engine = RecommendationEngine()
try:
    result: dict = engine.recommend(golden_customer_id)
finally:
    engine.close()
```

`recommend(customer_id: str, *, as_of: datetime = DEMO_AS_OF) -> dict` returns `decision_id`, `action`, `probabilities`, `policy_checks`, `reasons`, `alternatives`, and review status. Display those fields and require an explicit reviewer action. For review, call `approve(decision_id, reviewer, reason)`, `modify(decision_id, reviewer, action, reason)`, or `reject(decision_id, reviewer, reason)`. The recommendation result is a proposal and does not execute customer contact. Keep engine creation and closing outside repeated render loops, or use an app-owned resource wrapper.
