# App integration interfaces

All three tabs are connected in `app/main.py`. Each receives the selected `golden_customer_id` from the Customer input. Customer-level joins require published C360 links with `link_status = 'linked'`; fairness-test fields stay out of displayed answers and decision features.

## Ask tab — Questions team

App adapter in `app/ask.py`:

```python
def answer(question: str, *, golden_customer_id: str) -> dict:
    """Return {answer, sql_or_sources, refused, mode, data_date}."""
```

`src.insights.engine.InsightEngine(dataset_root).answer(question, question_id=None)` returns an `AnswerCard` with `answer`, `sql_or_sources`, `refused`, `mode`, `as_of_date`, and `metric_definition`. The app adapter verifies explicit case IDs against the selected customer's linked C360 cases. Existing Layer 2 SQL metrics remain global; customer-scoped analytical wording is refused until Layer 2 supports a golden-ID filter. The UI labels the scope, evidence, refusal, metric definition, and data date.

## Recommendation tab — Decisioning team

App wrapper in `app/recommend.py` uses the merged callable:

```python
from src.decisioning import RecommendationEngine

engine = RecommendationEngine()
try:
    result: dict = engine.recommend(golden_customer_id)
finally:
    engine.close()
```

`recommend(customer_id: str, *, as_of: datetime = DEMO_AS_OF) -> dict` returns `decision_id`, `action`, `probabilities`, `policy_checks`, `reasons`, `alternatives`, and review status. The app displays those fields and offers explicit approve, modify, and reject buttons. Each action calls the corresponding engine method and writes a local SQLite audit event; the app reads recent rows through `latest_audit_rows(golden_customer_id)`. A recommendation is generated only on button click and never executes customer contact.
