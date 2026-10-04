# Five-minute demo script

Use the running app from the repository root:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app/main.py
```

The demo uses the hero customer `G-39c6b287f70371cd9fc6` and the second customer `G-b1714eca2809e88d7587`.

## 0:00–0:35 — Set the context

Open the Customer tab. Say: “This is a published 28 September C360 snapshot. Every customer-level record shown here comes through a linked identity crosswalk. Protected fields are excluded.” Point to the hero ID, the one open case, DPD 150, overdue balance, and hardship flag.

## 0:35–1:10 — Show identity evidence

At the top of the Customer page, point to “Why linked?”. Say: “These six source records are linked by visible evidence: the CRM records share an exact hashed-ID match, Collections uses a CRM reference, and the account sources show which normalized identity fields agree. The table shows source keys, methods, confidence, and link status without exposing personal values. Confidence is rule based; ambiguous links stay out of customer views.”

## 1:10–1:55 — Show a certified Ask answer

Open Ask and enter: “What is the average days past due of open cases by queue?” Click Get answer. Say: “The answer is routed to a certified read-only SQL metric. The screen shows the release date, scope, metric definition, and exact SQL so a reviewer can reproduce it.” Do not imply this global metric is scoped to the selected customer.

## 1:55–2:20 — Show refusal behavior

Ask: “What will the weather be in Toronto tomorrow?” Say: “The system fails closed outside Collections scope and makes the refusal visible. It does not invent an answer or call an external service.”

## 2:20–3:05 — Show a recommendation

Open Recommendation and click Generate recommendation. Say: “Layer 3 combines point-in-time features, a local promise-kept model, SHAP reasons, and a policy gate. This customer is routed to specialist review because hardship suppresses ordinary collection actions.” Point to alternatives and policy checks.

## 3:05–3:40 — Show human review and audit

Enter reviewer ID `demo-reviewer`, reason `Demo review: specialist route confirmed`, and click Reject. Say: “The proposal is not an action. A human must approve, modify, or reject it. The decision and review reason are append-only audit records, and no customer contact is sent.” Point to the latest audit row.

## 3:40–4:20 — Show the Worklist

Open Worklist and click Load worklist. Say: “This is a review queue of linked open promises ranked by predicted break risk. The top reason is shown beside each row, and the data is constrained to evidence available before the promise was created. It is not an automated contact list.”

## 4:20–5:00 — Change customer and close

Return to Customer and select `G-b1714eca2809e88d7587`. Say: “The same views work for another published golden ID. The second customer demonstrates that the UI is driven by the selected identity rather than hard-coded to the hero.” Point to its accounts, cases, and Why linked? panel. Close by saying: “Layer 2 owns the future customer-scoped Ask API; the app already passes the selected golden ID when that interface is available and explains the current boundary until then.”
