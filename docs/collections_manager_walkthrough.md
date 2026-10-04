# Collections manager walkthrough: from portfolio question to reviewed action

Use this as a 6–8 minute live presentation. The two roles are **collections manager** (understands workload and assigns attention) and **collections specialist/agent** (reviews one customer and records a decision). The sign-in and review-role restriction are local demo UI controls, not production authentication or authorization.

> **Opening line:** “You ask a question about the collections book, find a case that needs attention, and hand the agent one linked customer record. The system proposes a policy-checked next step and explains it. A person still makes and records the decision.”

The demo uses the synthetic release dated **28 September 2026**. Start the app from the repository root with `python -m streamlit run app/main.py` using the project virtual environment. The local C360 build and customer-page cache must already exist; see the [run instructions](../README.md#how-to-run). Sign in as `manager / demo` for the portfolio segment. Set `COLLECTIONS_DEMO_PASSWORD` in the ignored `.env` if the demo password has been changed.

## Role 1 — Collections manager: ask, inspect, prioritize

### 1. Ask a portfolio question (about 1 minute)

Show the **Dashboard**: real open-case, overdue, open-promise, and golden-customer totals, a weekly case chart, arrears-age distribution, and queue overview. Then open **Ask Collections** in the sidebar, leave **Scope: All Collections**, and paste:

> How many open cases are there, and list top 10?

**Expected:** **86,059** open cases, followed by ten rows ordered by current days past due and then overdue balance. Open **View SQL or sources** and point out `case_status = 'open'`, the sort order, and the result limit. The card says **global Collections** and shows the data date. Say: “This is a live query over the published release, with its definition and SQL visible. The top ten are for investigation, not an instruction to contact them.”

Ask a second workload question:

> How many open cases are assigned to each team?

**Expected:** a table of team names and open-case counts. The SQL filters `case_status = 'open'` and groups by `assigned_team`. Use it to discuss queue capacity, without treating raw counts as agent performance.

Then ask a policy question:

> How many call attempts can we make on a mid-stage account in a week?

**Expected:** at most **3 outbound call attempts in a rolling 7 days per case**, with source `POL-COLL-001 §5.2`. Say: “Operational answers cite SQL; policy answers cite the policy source.”

These three exact prompts use governed routes and do not need an external LLM. New safe analytics questions may use the configured Gemini, Groq, or OpenAI SQL planner; response time and success then depend on that service. If a question cannot be answered without dropping a condition, the app refuses it.

### 2. Find work that deserves review (about 45 seconds)

Open **Priority queue** and click **Load worklist**. It shows 20 linked, open promises ordered by predicted break risk, with a top model reason. Explain that it helps the manager decide what to review first; it is **not** a list of approved actions. The probability is a model estimate, and a high score cannot override contact policy or specialist routing. Selecting a row opens that customer in Customer 360.

For a reproducible handoff, use customer `G-39c6b287f70371cd9fc6`. In **Customer 360**, expand **Browse linked customers**, keep the default **Open cases and promises** filter, search `39c6b287f70371cd9fc6`, and click its row. The browser also offers open cases, any promise, broken promises, open promises, and all linked customers. It shows ten rows per page and the relevant counts.

> **Handoff line:** “Here is a customer with both an open case and promise history. Before any action, the agent needs to see whether these records really belong together and what policy permits.”

## Role 2 — Collections specialist/agent: verify, decide, record

### 3. Inspect one linked customer (about 1 minute)

Sign out and sign in as `agent / demo` to show the specialist role. On **Customer 360**, show **Why these records are linked** first. Point to source record, observed match evidence, match rule, confidence, and link status. Then show the snapshot, cases, contacts, and promises. The hero has **1 open case** and **4 linked promises**. Say: “The evidence makes the joined view reviewable. The match confidence is a rule score, not a calibrated probability.”

Open **Ask Collections**, select **Scope: This customer**, and paste these questions one at a time:

| Exact question | Expected result | What to point out |
| --- | --- | --- |
| `How many open cases does this customer have?` | `open_cases = 1` | SQL joins the selected golden ID through the linked Collections crosswalk. |
| `How many broken promises does this customer have?` | `broken_promises = 3`, `total_promises = 4` | SQL requires both the linked case and linked CRM record. |

The scope label must say **selected golden customer**. A customer-specific question without the appropriate scope is refused; the app never silently substitutes a global count.

### 4. Generate a policy-checked proposal (about 1 minute)

Open **Decision review** and click **Generate recommendation**. For this hero, the proposal is **`specialist_review`** because the case hardship flag requires that route. Read the **first reason** aloud: the policy trigger comes before model factors. The app then shows three SHAP model factors as context, dated text evidence when available, and a **Blocked actions** panel. For this case, ordinary `call`, `sms`, and `email` are blocked with reason `specialist_route_required`.

Say: “The model informs the review, but policy decides what is permitted. Hardship and vulnerability flags route to a specialist; they are not model features or ranking inputs. A text signal alone cannot trigger adverse treatment.”

### 5. Make the human decision and show the audit (about 45 seconds)

Enter reviewer ID `demo-reviewer` and reason `Specialist route confirmed after case review`. Click **Approve** to record approval of the specialist route. Point to the resulting audit row: decision ID, proposed action, reviewer, disposition, final action, reason, and time. **Approve**, **Modify**, and **Reject** are available when applicable; modification only offers policy-permitted alternatives. The app records the review locally and **does not send a call, text, email, or other customer contact**.

If you want to demonstrate an ordinary eligible case afterward, select `G-b1714eca2809e88d7587` and generate a new recommendation. In the current snapshot its proposal is `call`; `push` is blocked for missing or conflicting channel consent. Re-check the on-screen policy reasons before describing any proposal as permitted.

## Close with the precise claim

> “The product joins customer records, answers scoped questions with visible evidence, ranks open promises for human review, and prevents a model score from bypassing policy. It gives our manager a clearer view and our agent a reviewable next step. We have **not** shown that it increases collections recovery.”

The retrospective promise model has **0.677 ROC-AUC** and **0.2245 calibrated Brier score** on a chronological test period; the signal is modest. Historical channel rates are observational because agents chose the channels. The synthetic data is a fixed snapshot, and this local demo has demo-only sign-in rather than production authentication. A pilot would need a controlled comparison, consent and policy review, authentication, monitoring, and measured customer outcomes before any uplift claim. See the [deck evidence](deck_outline.md), [model metrics](../src/decisioning/artifacts/promise_model_metrics.json), and [full limitations](../README.md#honest-limitations).
