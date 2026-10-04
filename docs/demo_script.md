# Five-minute demo script

Start from the repository root with `python -m streamlit run app/main.py` using the
project virtual environment. The hero is `G-39c6b287f70371cd9fc6`; the second
demo customer is `G-b1714eca2809e88d7587`.

## 0:00-0:55 — Customer and identity evidence

Open Customer. Show the 28 September 2026 snapshot and the **Why linked?**
table at the top. Point to source record IDs, observed matching evidence, rule,
confidence, and link status. Say that the values are rule scores, not calibrated
match probabilities. Show the one open case and overdue amount. Protected
identity fields are not displayed.

## 0:55-1:45 — Ask and scope

In Ask, leave **All Collections** selected. Ask “What is the average days past
due of open cases by queue?” Show the global scope, definition, SQL, and data
date. Then choose **This customer** and ask “How many open cases are there?”
Show the one-case result and linked-crosswalk SQL. Explain that unsupported
customer filters are refused instead of silently becoming global answers.

## 1:45-2:05 — Refusal

Ask “What will the weather be in Toronto tomorrow?” Show the refusal. No
unsupported answer is invented.

## 2:05-3:05 — Recommendation and policy

Open Recommendation and click **Generate recommendation**. The hero routes to
specialist review. Show the policy reason first, model SHAP context, and dated
text-rule evidence. Point to **Blocked actions** and their exact policy reasons.
Explain that text alone does not authorize an adverse collection action.

## 3:05-3:40 — Human review and audit

Enter reviewer ID `demo-reviewer`, reason `Demo review: specialist route
confirmed`, then click **Reject**. Show the new audit row. A proposal never
sends customer contact; human review is recorded locally.

## 3:40-4:20 — Worklist

Open Worklist and click **Load worklist**. Show break risk and the top SHAP reason
for each linked open promise. This is a review queue, not an automatic action
list.

## 4:20-5:00 — Second customer and limits

Search `b1714eca2809e88d7587` in Browse all linked customers and click its row. Show that the
identity and case views change. Close with the limits: historical channels were
chosen by agents; the model's signal is modest; no uplift is proven. A pilot
needs controlled comparison and outcome monitoring.
