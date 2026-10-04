"""Run from the repository root: python -m streamlit run app/main.py."""

from __future__ import annotations

import streamlit as st

from app.ask import answer as answer_question
from app.answer_display import display_answer
from app.customer import load_customer
from app.recommend import connected, latest_audit_rows, recommend, review, worklist


HERO_ID = "G-39c6b287f70371cd9fc6"
DEMO_IDS = (
    HERO_ID,
    "G-ce8c778700c9b95b55d8",
    "G-f4b22f89068d857ebe87",
    "G-39214e6dde2a06706f89",
    "G-42ba77893259d13e6b27",
)


@st.cache_data(show_spinner="Loading linked C360 records…")
def cached_customer(golden_id: str) -> dict:
    return load_customer(golden_id)


st.set_page_config(page_title="Collection Intelligence", layout="wide")
st.title("Collection Intelligence")
st.caption("Published C360 snapshot · 28 September 2026 · linked source records only")

customer_tab, ask_tab, recommendation_tab, worklist_tab = st.tabs(
    ["Customer", "Ask", "Recommendation", "Worklist"]
)

customer = None
with customer_tab:
    if "golden_id" not in st.session_state:
        st.session_state.golden_id = HERO_ID

    def choose_demo() -> None:
        st.session_state.golden_id = st.session_state.demo_choice

    st.selectbox("Demo customer", DEMO_IDS, index=0, key="demo_choice",
                 on_change=choose_demo)
    golden_id = st.text_input("Golden customer ID", key="golden_id",
                              help="Select a demo customer or paste any published golden ID.").strip()
    if golden_id:
        try:
            customer = cached_customer(golden_id)
        except (FileNotFoundError, ValueError) as error:
            st.error(str(error))
        except Exception as error:
            st.error(f"Could not load this customer: {error}")
        else:
            if not customer["found"]:
                st.warning("No published golden customer has that ID.")
            else:
                summary = customer["summary"]
                st.subheader(golden_id)
                identity = customer["identity"]
                st.markdown("### Why linked?")
                st.caption(f"{identity['linked_source_count']} linked source records. "
                           "The evidence below shows which normalized fields agree with a linked CRM record; "
                           "it does not reveal the underlying birth dates, phone numbers, postcodes, or hashes. "
                           "Confidence scores are rule based, not calibrated probabilities.")
                st.dataframe([
                    {
                        "Source": link["source_system"].replace("_", " ").title(),
                        "Source record": link["source_customer_id"],
                        "Evidence observed": "; ".join(link["evidence"]),
                        "Match rule": link["match_method"].replace("_", " "),
                        "Confidence": f"{link['match_confidence']:.0%}",
                        "Status": link["link_status"],
                    }
                    for link in identity["links"]
                ], width="stretch", hide_index=True,
                   column_config={"Evidence observed": st.column_config.TextColumn(width="large")})

                st.subheader("Customer snapshot")
                a, b, c, d = st.columns(4)
                a.metric("CRM records", summary["crm_record_count"])
                b.metric("Open cases", summary["open_case_count"])
                c.metric("Highest DPD", summary["max_current_dpd"] or 0)
                d.metric("Overdue (CAD)", f"{summary['total_overdue_cad']:,.2f}")
                st.caption(f"Data quality: {summary['dq_status']} · "
                           f"Minimum linked confidence: {summary['min_match_confidence']:.2f} · "
                           f"Hardship review flag: {'yes' if summary['hardship_flag'] else 'no'}")

                st.subheader("Accounts")
                for label, rows in customer["accounts"].items():
                    with st.expander(f"{label.title()} ({len(rows)} shown)", expanded=bool(rows)):
                        st.dataframe(rows, width="stretch", hide_index=True)
                for title, key in (("Cases", "cases"), ("Contacts", "contacts"),
                                   ("Promises", "promises")):
                    st.subheader(title)
                    st.dataframe(customer[key], width="stretch", hide_index=True)
                    if len(customer[key]) == 50:
                        st.caption("Showing the 50 most recent records.")

with ask_tab:
    st.subheader("Ask Collections")
    st.caption("General metrics and policy answers use the 28 September 2026 release. "
               "Ask defaults to all Collections.")
    question = st.text_area("Question", key="ask_question",
                            placeholder="What is the average days past due of open cases by queue?")
    if st.button("Get answer", key="ask_submit"):
        try:
            st.session_state.ask_result = answer_question(
                question,
            )
        except Exception as error:
            st.session_state.ask_result = None
            st.error(f"Could not answer the question: {error}")
    result = st.session_state.get("ask_result")
    if result:
        st.caption(f"Scope: {result['scope']} · Data date: {result['data_date']}")
        if result["refused"]:
            st.warning(f"Refused: {result['answer']}")
        else:
            display = display_answer(result["answer"], result["mode"])
            if display["kind"] == "metric":
                st.metric(display["label"], display["value"])
            elif display["kind"] == "table":
                st.dataframe(display["rows"], width="stretch", hide_index=True)
            elif display["kind"] == "empty":
                st.info("No rows matched the filters in this question.")
            else:
                st.write(display["text"])
        if result["metric_definition"]:
            st.caption(f"Definition: {result['metric_definition']}")
        with st.expander("View SQL or sources"):
            st.code(result["sql_or_sources"], language="sql" if result["sql_or_sources"].lstrip().upper().startswith(("SELECT", "WITH")) else None)

with recommendation_tab:
    st.subheader("Recommendation and human review")
    selected_id = st.session_state.golden_id.strip()
    if not connected():
        st.info("Recommendation is not connected yet. The decisioning module is not available in this checkout.")
    elif not customer or not customer.get("found"):
        st.info("Select a published golden customer in the Customer tab first.")
    else:
        st.caption("A proposal is created only when requested. It never sends customer contact.")
        if st.button("Generate recommendation", key="recommend_submit"):
            try:
                st.session_state.recommendation = recommend(selected_id)
            except Exception as error:
                st.session_state.recommendation = None
                st.error(f"Could not generate a recommendation: {error}")
        proposal = st.session_state.get("recommendation")
        if proposal and proposal.get("customer_id") == selected_id:
            st.markdown(f"**Action:** {proposal['action']}")
            st.caption(f"Decision ID: {proposal['decision_id']} · "
                       f"Snapshot: {proposal['data_snapshot_date']} · "
                       f"Status: {proposal['status']}")
            for reason_text in proposal.get("reasons", []):
                st.write(reason_text)
            probability = proposal.get("probabilities", {}).get("promise_kept")
            if probability is not None:
                st.metric("Promise kept probability", f"{probability:.1%}")
            st.markdown("**Alternatives**")
            st.dataframe(proposal.get("alternatives", []), width="stretch", hide_index=True)
            st.markdown("**Policy checks**")
            checks = proposal.get("policy_checks", {})
            st.dataframe([{"action": action, "allowed": check["allowed"],
                           "reasons": ", ".join(check.get("reasons", []))}
                          for action, check in checks.items()],
                         width="stretch", hide_index=True)
            current_audit = latest_audit_rows(selected_id)
            already_reviewed = any(row["decision_id"] == proposal["decision_id"]
                                   and row["disposition"] != "pending_review"
                                   for row in current_audit)
            if already_reviewed:
                st.success("This decision has a recorded human review.")
            else:
                allowed = [action for action, check in checks.items()
                           if check.get("allowed") and action != proposal["action"]]
                with st.form("review_form"):
                    reviewer = st.text_input("Reviewer ID", key="reviewer_id")
                    review_reason = st.text_area("Review reason", key="review_reason")
                    alternative = st.selectbox("Modified action", allowed or ["No permitted alternative"],
                                               key="modified_action")
                    approve, modify, reject = st.columns(3)
                    approve_clicked = approve.form_submit_button("Approve", key="approve_button")
                    modify_clicked = modify.form_submit_button("Modify", disabled=not allowed,
                                                               key="modify_button")
                    reject_clicked = reject.form_submit_button("Reject", key="reject_button")
                disposition = ("approve" if approve_clicked else "modify" if modify_clicked
                               else "reject" if reject_clicked else None)
                if disposition:
                    try:
                        event = review(
                            proposal["decision_id"], disposition=disposition,
                            reviewer=reviewer, reason=review_reason,
                            action=alternative if disposition == "modify" else None,
                        )
                    except Exception as error:
                        st.error(f"Review was not recorded: {error}")
                    else:
                        st.success(f"Recorded {event['disposition']} review: {event['event_id']}")
        st.markdown("**Latest audit rows for this customer**")
        st.dataframe(latest_audit_rows(selected_id), width="stretch", hide_index=True)

with worklist_tab:
    st.subheader("Open promise worklist")
    st.caption("Linked open promises ranked by predicted break risk using only evidence available before each promise was created. Human review is required before any action.")
    if st.button("Load worklist", key="worklist_submit"):
        try:
            st.session_state.worklist_rows = worklist(20)
        except Exception as error:
            st.session_state.worklist_rows = None
            st.error(f"Could not load worklist: {error}")
    rows = st.session_state.get("worklist_rows")
    if rows is not None:
        st.dataframe([{
            "Promise ID": row["ptp_id"],
            "Golden customer ID": row["customer_id"],
            "Case ID": row["case_id"],
            "Break risk": row["probability_break"],
            "Top reason": row["top_reason"],
            "Model version": row["model_version"],
        } for row in rows], width="stretch", hide_index=True)
        st.caption(f"{len(rows)} ranked promises shown. This is a review queue, not an action list.")
