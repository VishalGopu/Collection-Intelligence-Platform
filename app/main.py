"""Run from the repository root: python -m streamlit run app/main.py."""

from __future__ import annotations

import streamlit as st

from app.ask import answer as answer_question
from app.answer_display import display_answer
from app.catalog import browse_customers
from app.customer import load_customer
from app.recommend import connected, latest_audit_rows, recommend, review, worklist


HERO_ID = "G-39c6b287f70371cd9fc6"


@st.cache_data(show_spinner="Loading linked C360 records…")
def cached_customer(golden_id: str) -> dict:
    return load_customer(golden_id)


@st.cache_data(show_spinner="Searching linked C360 customers…")
def cached_customer_page(search: str, after_id: str | None,
                         activity_filter: str) -> dict:
    return browse_customers(search, after_id=after_id,
                            activity_filter=activity_filter)


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

    def reset_catalog() -> None:
        st.session_state.catalog_page = 0
        st.session_state.catalog_cursors = [None]

    def next_catalog(last_id: str) -> None:
        st.session_state.catalog_cursors.append(last_id)
        st.session_state.catalog_page += 1

    def previous_catalog() -> None:
        st.session_state.catalog_page -= 1
        st.session_state.catalog_cursors.pop()

    if "catalog_page" not in st.session_state:
        reset_catalog()
    st.text_input("Selected golden customer ID", key="golden_id",
                  help="Click a customer below or paste a published golden ID.")
    with st.expander("Browse all linked customers", expanded=False):
        st.text_input("Search golden ID or fragment", key="catalog_search",
                      on_change=reset_catalog)
        filter_labels = {
            "Open cases and promises": "open_cases_and_promises",
            "Open cases": "open_cases",
            "Any promise": "any_promise",
            "Broken promises": "broken_promise",
            "Open promises": "open_promise",
            "All linked customers": "all",
        }
        st.selectbox("Show customers with", list(filter_labels), key="catalog_filter",
                     on_change=reset_catalog)
        try:
            page_data = cached_customer_page(
                st.session_state.catalog_search,
                st.session_state.catalog_cursors[st.session_state.catalog_page],
                filter_labels[st.session_state.catalog_filter],
            )
        except (FileNotFoundError, ValueError) as error:
            st.error(str(error))
        else:
            st.caption(f"{page_data['total']:,} linked customers match · "
                       f"Page {st.session_state.catalog_page + 1} · Click a row to select")
            page_rows = page_data["rows"]
            if page_rows:
                table_key = (f"catalog_rows_{st.session_state.catalog_page}_"
                             f"{st.session_state.catalog_search}_"
                             f"{st.session_state.catalog_filter}")

                def select_catalog_customer() -> None:
                    selected_rows = st.session_state[table_key]["selection"]["rows"]
                    if selected_rows:
                        st.session_state.golden_id = page_rows[selected_rows[0]]["golden_customer_id"]

                st.dataframe([{
                    "Golden customer ID": row["golden_customer_id"],
                    "Open cases": row["open_case_count"],
                    "Promises": row["promise_count"],
                    "Broken": row["broken_promise_count"],
                    "Open promises": row["open_promise_count"],
                    "Highest DPD": row["max_current_dpd"],
                } for row in page_rows], width="stretch", hide_index=True,
                             height=max(75, 35 * (len(page_rows) + 1)),
                             key=table_key, on_select=select_catalog_customer,
                             selection_mode="single-row")
            else:
                st.info("No linked customers matched this search.")
            previous_page, next_page = st.columns(2)
            previous_page.button("Previous page", key="catalog_previous",
                                 disabled=st.session_state.catalog_page == 0,
                                 on_click=previous_catalog, use_container_width=True)
            next_page.button("Next page", key="catalog_next",
                             disabled=not page_data["has_next"],
                             on_click=next_catalog,
                             args=(page_rows[-1]["golden_customer_id"],) if page_rows else (),
                             use_container_width=True)
    golden_id = st.session_state.golden_id.strip()
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
    ask_scope = st.radio("Scope", ("All Collections", "This customer"),
                         horizontal=True, key="ask_scope")
    if ask_scope == "This customer":
        st.caption(f"Selected golden customer: {st.session_state.golden_id.strip()}")
    question = st.text_area("Question", key="ask_question",
                            placeholder="What is the average days past due of open cases by queue?")
    if st.button("Get answer", key="ask_submit"):
        try:
            st.session_state.ask_result = answer_question(
                question,
                golden_customer_id=(st.session_state.golden_id.strip()
                                    if ask_scope == "This customer" else None),
                scope_requested=ask_scope == "This customer",
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
            elif display["kind"] == "table_with_total":
                st.metric(display["label"], display["value"])
                if display["rows"]:
                    st.dataframe(display["rows"], width="stretch", hide_index=True)
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
            if proposal.get("text_evidence"):
                st.markdown("**Text evidence**")
                st.caption(proposal["text_evidence"])
            probability = proposal.get("probabilities", {}).get("promise_kept")
            if probability is not None:
                st.metric("Promise kept probability", f"{probability:.1%}")
            st.markdown("**Alternatives**")
            st.dataframe(proposal.get("alternatives", []), width="stretch", hide_index=True)
            st.markdown("**Policy checks**")
            checks = proposal.get("policy_checks", {})
            blocked_actions = [
                {"Action": action, "Why blocked": "; ".join(check.get("reasons", []))}
                for action, check in checks.items() if not check.get("allowed")
            ]
            st.markdown("**Blocked actions**")
            if blocked_actions:
                st.dataframe(blocked_actions, width="stretch", hide_index=True)
            else:
                st.caption("No action was blocked by the current policy checks.")
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
