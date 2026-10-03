# TASKS.md — what to build next, who does it

I read "layer 0 and 1" as Layer 1 (C360) and Layer 2 (questions). Layer 3/4 (recommendations) is new and is the biggest gap.

Deadline: 9:00 PM IST, 4 Oct. Extra questions arrive at 7:00 PM. Submit by 8:15 PM.

## Rules for every task

- Only edit your own folder. Commit after each finished step.
- Never invent a column. Check the data dictionary.
- Never use gender, marital status, citizenship, household, newcomer, accessibility, vulnerability or accent in any decision or model.
- Do not edit benchmark answers by hand. The CSV must come from the running code.
- If a step takes more than 90 minutes, stop, commit what works and move on.

## How to give a task to Codex

Paste this, then paste the task:

> Read the repo first. Do only the task below. Do not change other folders. Use the real column names from the data dictionary. When done, run the tests, tell me what works and what doesn't, and commit.

---

## TASK A — Layer 3/4: Next Best Action (start now, biggest job)

Goal: pick a customer, get a recommended action with reasons, and let a person approve or reject it.

Do in this order. Each step has a "done when".

1. **Training table.** For each past promise in `promises_to_pay`, build one row with the label "was it kept?" and features known *before* the promise date (DPD, bucket, earlier broken promises, recent contacts, card utilisation, bureau change). Use data from `collections_cases`, `contact_history`, accounts and `external`.
   Done when: a parquet file exists and no feature uses information from after the promise date.
2. **Models.** Split by time (older for training, newest for testing). Train a simple baseline (logistic regression, or the existing `model_scores`), then LightGBM. Save metrics.
   Done when: you can print baseline vs LightGBM on the newest period.
3. **Policy gate.** A plain Python function that removes actions that are not allowed: no consent for that channel, cease-contact request, outside permitted hours, too many recent contacts, open dispute or complaint, bankruptcy, deceased, fraud alert. Use `hardship_programs` rules for hardship offers.
   Done when: a test shows a high-scoring action being blocked by the gate.
4. **Hardship route.** If a hardship or vulnerability flag is present, send the case to a specialist and skip the normal collection actions.
   Done when: a test shows a hardship case ending up with "specialist review".
5. **Ranker.** For the allowed actions (SMS, email, push, call, payment-plan discussion, wait), score each and sort. Return the top choice and the alternatives.
6. **Reasons.** Use SHAP to get the top 3 reasons. Turn them into one plain sentence ("Two broken promises in the last 90 days and a high card balance"). The sentence may only use real reasons from SHAP.
7. **Review and audit.** Functions to approve, modify or reject a recommendation. Save who, when, what and why in a table.
   Done when: after approving, a row exists in the audit table.
8. **One entry point.** `recommend(customer_id)` returns: action, probabilities, policy checks, reasons, alternatives, decision id.
9. **Text features (only if time).** Pull hardship signal and reason for delay from notes and transcripts using the 500 labelled examples to measure accuracy. Use only text written before the prediction date.

Key tests: policy blocks a forbidden action, protected fields are not in the model, hardship goes to a specialist, audit row is written.

---

## TASK B — Improve Layer 2: questions and answers

Goal: new, differently worded questions also work, and the answers are correct.

1. **Commit and push the current code now.**
2. **Check correctness.** Compare `benchmark_answers.csv` with the dev answers file using the tolerances in the README. List every wrong answer and fix it. (Running without errors is not the same as being right.)
3. **Add a general path.** If no route matches, send the question plus the table list and `metric_definitions` to an LLM, get one SQL query, check it (SELECT only, known tables only, row limit), run it read-only, and show the SQL. Keep the existing routes as the first choice.
4. **Write 20 new test questions** in different wording from the released ones, including 5 that should be refused. Test them.
5. **Refusals.** Add tests for: gender/citizenship/etc. used to pick customers, bulk personal data export, "send this customer a message", legal or medical advice, off-topic questions, and an instruction hidden inside a note.
6. **Show more on each answer.** Add data date (snapshot 28 Sep 2026) and the metric definition used.
7. **One command to rerun everything.** Time it. It must finish well before 7:30 PM with new questions dropped in.
8. **Later:** switch customer-level questions to the C360 crosswalk (see Task C), then re-run all 35 and compare.

Done when: all dev questions match the expected answers, 20 new questions give sensible answers, and the rerun works with one command.

---

## TASK C — Improve Layer 1: C360

Goal: outputs exist, are tested, and others can use them.

1. **Run the pipeline** in the current checkout. Confirm both parquet files exist: golden customers and identity crosswalk.
2. **Check the numbers** against the committed report (1,001,258 golden customers, 99.623% case resolution, 0 duplicates).
3. **Add tests:** golden ID unique, source key maps to one golden ID, low-confidence matches are not linked, protected columns are absent, bad rows go to quarantine.
4. **Explain the 15,183 "review pending" customers** in plain words in the quality report: what they are and why they were not auto-linked.
5. **"Why were these linked?" function.** Given a golden ID, list the source records, method, confidence and evidence.
6. **Data contract file.** Make sure `contracts/golden_c360_v1.json` has owner, schema, quality rules, allowed uses and refresh, in the shape of the example contract `DC-COLL-001`.
7. **Hand-off for others:** cleaned views of all 31 tables, plus a short note saying which key joins which table.
8. **Point-in-time support** for Task A: if the data has monthly snapshots or dates, make sure features can be built "as of" a past date.

Done when: Task A and Task B can read the C360 files without asking you questions.

---

## TASK D — Connect it and show it (after A, B and C have something)

1. Pick one **demo customer**: duplicate CRM records, a broken promise, notes or transcripts, ideally a hardship signal.
2. Simple Streamlit page with three tabs: **Customer** (accounts, case, contacts, promises, identity and "why linked"), **Ask** (question, answer, SQL, refusal), **Recommendation** (action, reasons, alternatives, approve/modify/reject, audit row).
3. Run the whole path on the demo customer.

---

## TASK E — Submission pack (start a little each day, finish by 6:30 PM)

- README: how to run it, what changed from the design and why, which AI tools were used for what.
- Architecture diagram, final version, PDF or PNG, in the repo.
- Data quality report: issue, table, how many, how handled.
- Pitch deck, 10 slides max, PDF.
- Demo video, 5 minutes max, unlisted link, real data.
- Final benchmark CSV after the 7 PM questions. Commit.
- Add the organisers to the private repo.

---

## Suggested order

| When | Task A | Task B | Task C |
|---|---|---|---|
| Now to +4h | steps 1 to 3 | steps 1 to 2 | steps 1 to 3 |
| +4h to +10h | steps 4 to 8 | steps 3 to 5 | steps 4 to 8 |
| +10h to +18h | step 9, tests | steps 6 to 8 | help Task D |
| +18h onward | hardening | hardening | Task D, Task E |

Freeze new features about 26 hours from now. After that, fix bugs only.
