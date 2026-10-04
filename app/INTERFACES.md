# App integration interfaces

The Streamlit sidebar connects Dashboard, Priority queue, Customer 360, Ask Collections, and Decision review in `app/main.py`. The local demo sign-in offers manager and specialist roles; only the specialist role sees review controls. This is a UI demonstration, not production authorization. Customer-level joins require published C360 links with `link_status = 'linked'`; fairness-test fields stay out of displayed answers and decision features. Ask defaults to All Collections and has an explicit This customer selector. The selected scope supports only certified customer routes and refuses unsupported filters. Decision review uses the selected `golden_customer_id` and shows blocked actions with policy reasons. Priority queue shows open promises ranked for human review.

Customer 360 has a searchable, 10-at-a-time browser over all published
CRM-linked golden customers. Its count, rows, search, activity filter, and page
cursors are queried from C360 Parquet and the local customer-activity cache in
DuckDB with a 1 GB memory limit. It defaults to linked customers with both an
open case and promise history. Only the golden ID and non-protected case and
promise counts appear. Clicking a row updates the same Customer, Ask, and
Recommendation ID state.

## Ask Collections

App adapter in `app/ask.py`:

```python
def answer(question: str, *, golden_customer_id: str | None = None,
           scope_requested: bool = False) -> dict:
    """Return {answer, sql_or_sources, refused, mode, data_date, scope}."""
```

`src.insights.engine.InsightEngine(dataset_root).answer(question, question_id=None, scope=None)` returns an `AnswerCard` with `answer`, `sql_or_sources`, `refused`, `mode`, `as_of_date`, `metric_definition`, and `scope`. The adapter sends a golden ID when explicitly supplied as an argument or written in the question, after C360 validation. It verifies explicit case IDs against that customer's linked C360 cases and refuses mismatched customer IDs. Customer-scoped wording without an ID is refused. The UI labels the actual scope, evidence, refusal, metric definition, and data date.

## Decision review

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
