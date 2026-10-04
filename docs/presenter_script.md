# Read-aloud demo script: CIBC-themed Collections Intelligence concept

Use this script with the published **28 September 2026** synthetic-data snapshot. Allow about **12–15 minutes** for the full version, or skip the optional agent sign-in and review write for a shorter presentation. Text in **Say** is ready to read aloud; **Do** tells you what to click. Numbers below were checked against this snapshot. If the release changes, read the values on screen instead.

Example customer: **`G-883e676faa7837d10aa7`**. This is a useful example because the promise looks urgent, but the policy gate prevents ordinary contact. The distinction between *priority for review* and *permission to act* is the main story.

## 1. Sign in and orient the manager

**Do:** Open `http://localhost:8501`. Sign in with user ID `manager` and the local demo password (`demo` unless `COLLECTIONS_DEMO_PASSWORD` is set). Point to the CIBC-themed header, then the top menu: **Dashboard**, **Priority queue**, **Customer 360**, **Ask Collections**, **Decision review**. The sidebar contains the same pages and the selected customer ID.

**Say:** “This is the manager workspace. I can see the portfolio, ask a governed question, find a promise that needs review, and follow it into one linked customer record. The pages are reachable from the top menu even if the sidebar is closed.”

**Security line:** “This login only separates two roles in a local synthetic-data demo. It is **not** production bank authentication or authorization. Production deployment would require SSO, server-side role checks, access logs, and approved data controls.”

## 2. Dashboard: explain every displayed area

**Do:** Open **Dashboard**. Read the data date under the four cards.

**Say:** “These values are computed from the published dataset and cached for display; they are not invented targets or a live operational feed. **Open cases** counts cases whose status is `open`. **Open overdue** sums overdue Canadian dollars on those open cases. **Open promises** counts promises whose status is `open`. **Golden customers** counts published C360 customer records. The date tells us which release we are looking at.”

**Do:** Point to **New cases by week**, **Open cases by arrears age**, and **Queue overview**.

**Say:** “The weekly bars count new cases opened in each week of the displayed eight-week period. The arrears chart groups currently open cases by days past due: 0–29, 30–59, 60–89, 90 or more, or unknown. The queue table shows each queue’s open-case count, average days past due, and overdue balance. It is a workload view, not a measure of an individual agent’s performance.”

**Do:** Point to **Open priority queue** and **Find a customer**. These are shortcuts to the corresponding pages.

## 3. Ask Collections: show an answer and its evidence

**Do:** Open **Ask Collections**. Leave **Scope** at **All Collections**. Enter `How many open cases are there, and list top 10?` and click **Get answer**.

**Say:** “The answer is **86,059** open cases in this release. The ten-row list is ordered by days past due and overdue balance. The result card states the actual scope and data date. **View SQL or sources** shows the query, including `case_status = 'open'`, the ordering, and the limit. A result is evidence for investigation; it does not authorize contact.”

**Do:** In the same page ask `How many call attempts can we make on a mid-stage account in a week?` Expand **View SQL or sources**.

**Say:** “This is a policy question, so the answer cites policy source **POL-COLL-001 §5.2**: at most **three outbound call attempts in a rolling seven days per case**. Data questions show SQL; document answers show their source. If the system cannot keep a requested condition, it must refuse rather than quietly change the question.”

**Fields to identify:** **Scope** chooses global versus the currently selected golden customer; **Question** is the exact request; **Get answer** runs it; the answer card includes scope and data date; **Definition**, when present, states the certified metric meaning; **View SQL or sources** exposes the evidence; **Questions to try** provides examples. An empty result means no rows matched the filters, not that a filter was dropped.

## 4. Priority queue: why this customer is first

**Do:** Open **Priority queue** and click **Load worklist**. Point to the first row for `G-883e676faa7837d10aa7`, promise `PTP-3511285`, case `CS-2026-123687`.

**Say:** “This queue contains **linked open promises**, sorted by the model’s estimated chance of breaking the promise. This promise has **85.2% estimated break risk** and appears first in the top 20. **Top model reason** says ‘days past due’. That means the model associates the customer’s arrears age with a lower chance of keeping the promise. The score is a review priority, **not** a contact instruction or a prediction that this specific person will definitely miss payment.”

**Do:** Click the first row. It opens the customer in **Customer 360**. If selecting the row does not respond in your browser, open Customer 360 from the top menu and paste `G-883e676faa7837d10aa7` into **Golden customer ID**.

## 5. Customer 360: verify the join and explain the record

**Do:** Point to **Golden customer ID** and **Browse linked customers**.

**Say:** “The `G-...` ID is our cross-system identifier. The browser can search all linked customers or filter for open cases, promises, and broken promises; it shows ten rows per page. Clicking a row selects that customer. We will inspect the evidence before treating records from different systems as one person.”

**Do:** Start with **Why these records are linked**.

**Say:** “There are **five linked source records**: CRM, collections, cards, lending, and core banking. **Source record** is each system’s original reference. **Evidence observed** names the fields that agreed, such as date of birth, postcode, phone, surname, or a CRM reference; the page hides the raw values. **Match rule** tells us how the link was formed. **Confidence** is a rule score, **not** a calibrated probability of identity. **Status** shows that the record is linked. The minimum displayed match confidence is **0.97**, and the customer’s data-quality status is **passed**.”

**Do:** Point to **Customer snapshot** and explicitly clarify the apparent mismatch.

**Say:** “**CRM records: 1** means one CRM record anchors this golden customer. **Open cases: 0**, **Highest DPD: 0**, and **Overdue: CAD 0** here are the *open-case summary*. The case below is marked **legal**, so it is excluded from those open-case cards. This is why we should inspect the detailed rows before drawing a conclusion. **Hardship review flag: no** is a structured routing flag, not a model feature.”

**Do:** Open the four tabs one by one.

**Say — Cases:** “The one linked case, `CS-2026-123687`, opened **19 May 2026**. Its status is **legal**, arrears bucket **121–150 days**, current days past due **133**, and overdue balance **CAD 738.68**. Case hardship is false. The case status is crucial to the action gate.”

**Say — Promises:** “The open promise `PTP-3511285` was created **22 September 2026**, is for **CAD 300**, and is due **9 October 2026**. ‘Open’ means the promise has not yet been resolved in the snapshot. It is not a recorded broken promise.”

**Say — Contacts:** “The page shows **24** linked contact events: 17 calls, five letters, one inbound IVR event, and one internal system event. Each row has an event ID, case ID, local timestamp, channel, direction, and outcome code. The 22 September call has outcome `PTP`, matching the promise creation. Outcome codes need operational interpretation; they are not proof that every attempted contact reached the customer.”

**Say — Accounts:** “The account tables show source account ID, snapshot date, product, status, balance, and days past due. Two cards are present: one active card with **CAD 3,230.44** and 0 DPD, and one blocked card with **CAD 5,223.36** and 133 DPD. A current personal loan has **CAD 15,815.98** and 0 DPD. The chequing balance is **CAD 7.30**. These balances provide context; they are not a claim about ability to pay, and protected or benefit-deposit information is excluded from decision features.”

## 6. Ask about this selected customer

**Do:** Open **Ask Collections**, choose **This customer**, and ask `How many broken promises does this customer have?`

**Say:** “The result is **0 broken promises out of 1 linked promise**. The answer card must say **selected golden customer**, and the SQL must contain this golden ID and linked C360 joins. This keeps a customer question from silently becoming a portfolio-wide query. The selected customer in the sidebar is context, but customer scope is applied only when I explicitly choose **This customer**.”

## 7. Decision review: model context, policy gate, and audit

**Do:** Open **Decision review** and click **Generate recommendation**. Point to the selected ID and the proposal.

**Say:** “The recommended next step is **Wait**, with no contact channel. **Estimated chance of keeping a promise** is about **14.8%** in this snapshot, which is the complement of the 85.2% break risk. The worklist scored evidence at the promise’s creation time, when days past due was **127**; this page scores the current snapshot, when it is **133**. These are two time points, not a contradiction.”

**Do:** Read the short **Why?** statement, then expand **Model factors and text evidence**.

**Say:** “The three model explanations are days past due, card utilisation, and the earlier bureau risk score. They describe contributions to this model output, not causal reasons or a moral judgement. An earlier note dated **29 August** has a rule-based stated-delay signal of ‘dispute’. It is context only: a text signal alone cannot trigger adverse treatment or decide the action.”

**Do:** Expand **Blocked actions and permitted alternatives**. Point to both tables or their empty-state message.

**Say:** “The **policy gate** blocks calls and payment-plan discussions because this legal case requires its assigned specialist queue. SMS, email, and push are also blocked for missing or conflicting channel consent. **Wait** is permitted. **Permitted alternatives** is empty here. A high model score cannot override the blocked-actions table.”

**Do:** Expand **Recent audit for this customer**. Generating a proposal writes a pending decision. As `manager`, note the message that a collections specialist must record the human review.

**Say:** “The **decision ID**, snapshot date, proposal status, policy checks, explanation, and audit row make the suggestion inspectable. Generating it does **not** send a call, text, email, or other contact.”

**Do, only if you want to demonstrate a review write:** Sign out; sign in as `agent` with the demo password; reselect this customer if needed; open **Decision review** and generate a new proposal. In **Your decision**, leave reviewer ID as `agent`, enter `Legal case requires assigned-queue review; no direct contact authorised` in **Review reason**, and click **Approve**. Reopen **Recent audit for this customer**.

**Say:** “Here, approving records acceptance of the **Wait** proposal; it does not approve outreach. **Modify** is available only when the policy gate offers another permitted action. **Reject** records that the specialist disagrees. The audit records reviewer, disposition, final action, reason, and time. In this local demo the role boundary is UI-level; a production service must enforce it server-side.”

## 8. Close with the honest claim

**Say:** “We can connect source records with visible match evidence, answer scoped questions with SQL or policy citations, rank promises for human review, and show why policy blocks a suggested action. For this high-risk customer, the system correctly says **wait**, despite the 85.2% break-risk estimate. The model signal is modest and observational; we have **not** shown recovery uplift. A controlled pilot would need production access controls, monitoring, policy review, and measured outcomes before making that claim.”

### Presenter reminders

- The snapshot is synthetic and fixed at **28 September 2026**. Do not call it live bank data.
- The worklist predicts promise break risk; it does not authorize collection contact or assign legal-case ownership.
- Protected fields do not enter decision features, ranking, or explanations. Hardship and vulnerability flags are used only for specialist routing and suppression of ordinary collection actions.
- Consent, contact hours, rolling contact caps, holds, and specialist routing are checked before an action can be proposed. Unknown or conflicting evidence can block an action.
- Sign-in is a local demo convenience. Do not claim encryption, enterprise SSO, multi-user isolation, or production-grade authorization from this implementation.
- If a question is refused or an external planner is unavailable, show the refusal and its visible evidence instead of guessing an answer.
