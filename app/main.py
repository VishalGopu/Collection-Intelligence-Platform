"""Run from the repository root: python -m streamlit run app/main.py."""

from __future__ import annotations

import json

import altair as alt
import pandas as pd
import streamlit as st

from app.ask import answer as answer_question
from app.answer_display import display_answer
from app.auth import authenticate, configured_password
from app.catalog import browse_customers
from app.customer import load_customer
from app.dashboard import portfolio_snapshot
from app.recommend import connected, latest_audit_rows, recommend, review, worklist
from app.theme import inject_theme


HERO_ID = "G-39c6b287f70371cd9fc6"
PAGES = ("Dashboard", "Priority queue", "Customer 360", "Ask Collections", "Decision review")


@st.cache_data(show_spinner="Loading linked C360 records…")
def cached_customer(golden_id: str) -> dict:
    return load_customer(golden_id)


@st.cache_data(show_spinner="Searching linked customers…")
def cached_customer_page(search: str, after_id: str | None, activity_filter: str) -> dict:
    return browse_customers(search, after_id=after_id, activity_filter=activity_filter)


@st.cache_data(show_spinner="Loading the portfolio snapshot…")
def cached_portfolio() -> dict:
    return portfolio_snapshot()


def change_page(page: str) -> None:
    st.session_state.page = page


def select_customer(golden_id: str) -> None:
    st.session_state.golden_id = golden_id
    st.session_state.customer_input = golden_id


def page_header(label: str, title: str, description: str) -> None:
    st.markdown(f'<div class="eyebrow">{label}</div>', unsafe_allow_html=True)
    st.title(title)
    st.markdown(f'<div class="page-lede">{description}</div>', unsafe_allow_html=True)


def render_login() -> None:
    inject_theme(login=True)
    st.write("")
    left, right = st.columns([1.3, 1], gap="large", vertical_alignment="center")
    with left:
        st.markdown("""<div class="hero-panel">
          <div class="eyebrow">Maple Bank · Internal collections workspace</div>
          <h1>Clarity for every collection decision.</h1>
          <p>Understand the portfolio, verify a linked customer, and review a policy-checked next step in one place.</p>
          <div class="hero-points"><span>Customer 360</span><span>Grounded answers</span>
          <span>Policy checks</span><span>Human review</span></div>
        </div>""", unsafe_allow_html=True)
    with right:
        st.markdown('<div class="eyebrow">Team access</div>', unsafe_allow_html=True)
        st.markdown('<div class="login-title">Welcome back</div>', unsafe_allow_html=True)
        st.markdown('<div class="login-sub">Sign in to the local collections demo workspace.</div>',
                    unsafe_allow_html=True)
        with st.form("login_form"):
            user_id = st.text_input("User ID", placeholder="manager or agent", key="login_user")
            password = st.text_input("Password", type="password", key="login_password")
            submitted = st.form_submit_button("Sign in", key="login_submit", type="primary",
                                              use_container_width=True)
        if submitted:
            user = authenticate(user_id, password)
            if user is None:
                st.error("Check the user ID and password.")
            else:
                st.session_state.auth_user = user
                st.session_state.golden_id = HERO_ID
                st.session_state.page = "Dashboard" if user["role"] == "manager" else "Priority queue"
                st.rerun()
        if configured_password():
            st.caption("Local demo accounts: manager and agent. Use the configured demo password.")
        else:
            st.info("Local demo access: use **manager / demo** or **agent / demo**.")
        st.caption("Demo role selection is not production authentication. No customer contact is sent.")


def render_sidebar(user: dict) -> None:
    with st.sidebar:
        st.markdown('<div class="brand"><span>M</span> Maple Collections</div>',
                    unsafe_allow_html=True)
        st.markdown('<div class="brand-sub">Team workspace · 28 Sep 2026 snapshot</div>',
                    unsafe_allow_html=True)
        st.radio("Navigate", PAGES, key="page", label_visibility="collapsed")
        st.divider()
        st.caption(f"Signed in as **{user['name']}**")
        st.caption(f"Selected customer: `{st.session_state.golden_id}`")
        if st.button("Sign out", use_container_width=True):
            st.session_state.clear()
            st.rerun()


def render_top_navigation() -> None:
    """Keep every page reachable when Streamlit's sidebar is collapsed."""
    st.caption("MENU")
    for column, page in zip(st.columns(len(PAGES)), PAGES):
        column.button(page, key=f"top_nav_{page}",
                      type="primary" if st.session_state.page == page else "secondary",
                      on_click=change_page, args=(page,), use_container_width=True)


def render_dashboard() -> None:
    user = st.session_state.auth_user
    page_header("Portfolio overview", f"Good day, {user['name']}",
                "A clear view of the published Collections snapshot. Counts are portfolio-wide, not personal targets.")
    try:
        snapshot = cached_portfolio()
    except (FileNotFoundError, ValueError) as error:
        st.error(f"Portfolio snapshot unavailable: {error}")
        return
    a, b, c, d = st.columns(4)
    a.metric("Open cases", f"{snapshot['open_cases']:,}")
    b.metric("Open overdue · CAD", f"${snapshot['overdue_cad']:,.0f}")
    c.metric("Open promises", f"{snapshot['open_promises']:,}")
    d.metric("Golden customers", f"{snapshot['linked_customers']:,}")
    st.caption(f"Data date: {snapshot['snapshot_date']} · Published release · No invented targets or daily change figures")

    left, right = st.columns([1.2, 1], gap="medium")
    with left:
        with st.container(border=True):
            st.subheader("New cases by week")
            st.caption("Cases opened during the eight weeks before the snapshot")
            chart = alt.Chart(pd.DataFrame(snapshot["weekly"])).mark_bar(
                color="#213d5d", cornerRadiusTopLeft=5, cornerRadiusTopRight=5
            ).encode(x=alt.X("week:N", title=None, sort=None),
                     y=alt.Y("new_cases:Q", title="Cases"),
                     tooltip=["week:N", "new_cases:Q"]).properties(height=260)
            st.altair_chart(chart, width="stretch")
    with right:
        with st.container(border=True):
            st.subheader("Open cases by arrears age")
            buckets = pd.DataFrame(snapshot["buckets"])
            order = ["0–29 days", "30–59 days", "60–89 days", "90+ days", "Unknown"]
            chart = alt.Chart(buckets).mark_arc(innerRadius=67, outerRadius=108).encode(
                theta=alt.Theta("cases:Q"),
                color=alt.Color("bucket:N", sort=order, scale=alt.Scale(
                    domain=order, range=["#3b9b73", "#e7ae42", "#ef7f58", "#bc4e5b", "#8493a8"]),
                    legend=alt.Legend(title=None, orient="bottom")),
                tooltip=["bucket:N", "cases:Q"],
            ).properties(height=280)
            st.altair_chart(chart, width="stretch")

    with st.container(border=True):
        st.subheader("Queue overview")
        st.caption("Open cases only. Use this for workload review, not individual agent performance.")
        st.dataframe([{"Queue": row["queue"].replace("_", " ").title(),
                       "Open cases": row["open_cases"],
                       "Average DPD": row["avg_dpd"],
                       "Overdue (CAD)": row["overdue_cad"]} for row in snapshot["queues"]],
                     width="stretch", hide_index=True)
    queue_col, customer_col, _ = st.columns([1, 1, 3])
    queue_col.button("Open priority queue", type="primary", on_click=change_page,
                     args=("Priority queue",), use_container_width=True)
    customer_col.button("Find a customer", on_click=change_page,
                        args=("Customer 360",), use_container_width=True)


def reset_catalog() -> None:
    st.session_state.catalog_page = 0
    st.session_state.catalog_cursors = [None]


def next_catalog(last_id: str) -> None:
    st.session_state.catalog_cursors.append(last_id)
    st.session_state.catalog_page += 1


def previous_catalog() -> None:
    st.session_state.catalog_page -= 1
    st.session_state.catalog_cursors.pop()


def render_customer_browser() -> None:
    if "catalog_page" not in st.session_state:
        reset_catalog()
    with st.expander("Browse linked customers", expanded=False):
        search_col, filter_col = st.columns([1.1, 1])
        search_col.text_input("Search golden ID", key="catalog_search", on_change=reset_catalog)
        labels = {"Open cases and promises": "open_cases_and_promises",
                  "Open cases": "open_cases", "Any promise": "any_promise",
                  "Broken promises": "broken_promise", "Open promises": "open_promise",
                  "All linked customers": "all"}
        filter_col.selectbox("Show customers with", list(labels), key="catalog_filter",
                             on_change=reset_catalog)
        try:
            page = cached_customer_page(
                st.session_state.catalog_search,
                st.session_state.catalog_cursors[st.session_state.catalog_page],
                labels[st.session_state.catalog_filter],
            )
        except (FileNotFoundError, ValueError) as error:
            st.error(str(error))
            return
        st.caption(f"{page['total']:,} matching linked customers · Page "
                   f"{st.session_state.catalog_page + 1} · Select a row to open its profile")
        rows = page["rows"]
        if rows:
            table_key = (f"catalog_rows_{st.session_state.catalog_page}_"
                         f"{st.session_state.catalog_search}_{st.session_state.catalog_filter}")

            def select_catalog_customer() -> None:
                selected = st.session_state[table_key]["selection"]["rows"]
                if selected:
                    select_customer(rows[selected[0]]["golden_customer_id"])

            st.dataframe([{"Golden customer ID": row["golden_customer_id"],
                           "Open cases": row["open_case_count"],
                           "Promises": row["promise_count"],
                           "Broken": row["broken_promise_count"],
                           "Open promises": row["open_promise_count"],
                           "Highest DPD": row["max_current_dpd"]} for row in rows],
                         width="stretch", hide_index=True,
                         height=max(75, 35 * (len(rows) + 1)), key=table_key,
                         on_select=select_catalog_customer, selection_mode="single-row")
        else:
            st.info("No linked customers match this search.")
        prev, nxt = st.columns(2)
        prev.button("Previous page", disabled=st.session_state.catalog_page == 0,
                    on_click=previous_catalog, use_container_width=True)
        nxt.button("Next page", disabled=not page["has_next"], on_click=next_catalog,
                   args=(rows[-1]["golden_customer_id"],) if rows else (),
                   use_container_width=True)


def render_customer() -> None:
    page_header("Customer intelligence", "Customer 360",
                "One linked record with the source evidence, case history, and promises behind it.")

    def update_customer_input() -> None:
        st.session_state.golden_id = st.session_state.customer_input.strip()

    if st.session_state.get("customer_input") != st.session_state.golden_id:
        st.session_state.customer_input = st.session_state.golden_id
    st.text_input("Golden customer ID", key="customer_input", on_change=update_customer_input,
                  help="Choose a row below or paste a published G-... ID.")
    render_customer_browser()
    golden_id = st.session_state.golden_id.strip()
    if not golden_id:
        st.info("Enter a published golden customer ID to open its profile.")
        return
    try:
        customer = cached_customer(golden_id)
    except (FileNotFoundError, ValueError) as error:
        st.error(str(error))
        return
    except Exception as error:
        st.error(f"Could not load this customer: {error}")
        return
    if not customer["found"]:
        st.warning("No published golden customer has that ID.")
        return
    summary = customer["summary"]
    identity = customer["identity"]
    with st.container(border=True):
        st.subheader("Why these records are linked")
        st.caption(f"{identity['linked_source_count']} linked source records. Evidence names show "
                   "which normalized fields agree with CRM; raw birth dates, phones and postcodes are hidden. "
                   "Confidence is a rule score, not a calibrated probability.")
        st.dataframe([{"Source": link["source_system"].replace("_", " ").title(),
                       "Source record": link["source_customer_id"],
                       "Evidence observed": "; ".join(link["evidence"]),
                       "Match rule": link["match_method"].replace("_", " "),
                       "Confidence": f"{link['match_confidence']:.0%}",
                       "Status": link["link_status"]} for link in identity["links"]],
                     width="stretch", hide_index=True,
                     column_config={"Evidence observed": st.column_config.TextColumn(width="large")})
    st.subheader("Customer snapshot")
    a, b, c, d = st.columns(4)
    a.metric("CRM records", summary["crm_record_count"])
    b.metric("Open cases", summary["open_case_count"])
    c.metric("Highest DPD", summary["max_current_dpd"] or 0)
    d.metric("Overdue · CAD", f"${summary['total_overdue_cad']:,.2f}")
    st.caption(f"Data quality: {summary['dq_status']} · Minimum link confidence: "
               f"{summary['min_match_confidence']:.2f} · Hardship review flag: "
               f"{'yes' if summary['hardship_flag'] else 'no'}")
    cases, promises, contacts, accounts = st.tabs(["Cases", "Promises", "Contacts", "Accounts"])
    with cases:
        st.dataframe(customer["cases"], width="stretch", hide_index=True)
    with promises:
        st.dataframe(customer["promises"], width="stretch", hide_index=True)
    with contacts:
        st.dataframe(customer["contacts"], width="stretch", hide_index=True)
    with accounts:
        for label, rows in customer["accounts"].items():
            with st.expander(f"{label.title()} ({len(rows)} shown)"):
                st.dataframe(rows, width="stretch", hide_index=True)
    if any(len(customer[key]) == 50 for key in ("cases", "promises", "contacts")):
        st.caption("Tables show the 50 most recent records in each category.")
    st.button("Review next action", type="primary", on_click=change_page,
              args=("Decision review",))


def render_ask() -> None:
    page_header("Governed answers", "Ask Collections",
                "Ask about the portfolio or the selected linked customer. Every answer shows SQL or a source.")
    ask_scope = st.radio("Scope", ("All Collections", "This customer"),
                         horizontal=True, key="ask_scope")
    if ask_scope == "This customer":
        st.caption(f"Selected golden customer: {st.session_state.golden_id}")
    st.text_area("Question", key="ask_question", height=95,
                 placeholder="How many open cases are there, and list top 10?")
    if st.button("Get answer", key="ask_submit", type="primary"):
        try:
            st.session_state.ask_result = answer_question(
                st.session_state.ask_question,
                golden_customer_id=(st.session_state.golden_id
                                    if ask_scope == "This customer" else None),
                scope_requested=ask_scope == "This customer",
            )
        except Exception as error:
            st.session_state.ask_result = None
            st.error(f"Could not answer the question: {error}")
    result = st.session_state.get("ask_result")
    if result:
        with st.container(border=True):
            st.caption(f"Scope: {result['scope']} · Data date: {result['data_date']}")
            if result["refused"]:
                st.warning(f"Refused: {result['answer']}")
            else:
                display = display_answer(result["answer"], result["mode"])
                if display["kind"] in ("metric", "table_with_total"):
                    st.metric(display["label"], display["value"])
                    if display["kind"] == "table_with_total" and display["rows"]:
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
                evidence = result["sql_or_sources"]
                if evidence.lstrip().upper().startswith(("SELECT", "WITH")):
                    st.code(evidence, language="sql")
                else:
                    try:
                        sources = json.loads(evidence)
                    except (ValueError, TypeError):
                        sources = None
                    if isinstance(sources, list):
                        for source in sources:
                            st.write(f"• {source}")
                    else:
                        st.write(evidence)
    with st.expander("Questions to try"):
        st.markdown("- How many open cases are there, and list top 10?\n"
                    "- How many open cases are assigned to each team?\n"
                    "- How many call attempts can we make on a mid-stage account in a week?\n"
                    "- With **This customer** selected: How many broken promises does this customer have?")


def render_decision() -> None:
    page_header("Policy and human review", "Decision review",
                "A proposal is generated only on request. It never sends customer contact.")
    selected_id = st.session_state.golden_id.strip()
    st.caption(f"Selected customer: `{selected_id}`")
    if not connected():
        st.error("The recommendation service is unavailable in this checkout.")
        return
    try:
        customer = cached_customer(selected_id)
    except (FileNotFoundError, ValueError) as error:
        st.error(str(error))
        return
    if not customer.get("found"):
        st.info("Select a published golden customer in Customer 360 first.")
        return
    if st.button("Generate recommendation", key="recommend_submit", type="primary"):
        try:
            st.session_state.recommendation = recommend(selected_id)
        except Exception as error:
            st.session_state.recommendation = None
            st.error(f"Could not generate a recommendation: {error}")
    proposal = st.session_state.get("recommendation")
    if proposal and proposal.get("customer_id") == selected_id:
        with st.container(border=True):
            st.subheader("Proposed next step")
            st.markdown(f"### {proposal['action'].replace('_', ' ').title()}")
            st.caption(f"Decision ID: {proposal['decision_id']} · "
                       f"Snapshot: {proposal['data_snapshot_date']} · Status: {proposal['status']}")
            probability = proposal.get("probabilities", {}).get("promise_kept")
            if probability is not None:
                st.metric("Promise kept probability", f"{probability:.1%}")
            st.markdown("**Why this proposal?**")
            for reason_text in proposal.get("reasons", []):
                st.write(reason_text)
            if proposal.get("text_evidence"):
                st.caption(f"Text evidence: {proposal['text_evidence']}")
        checks = proposal.get("policy_checks", {})
        blocked = [{"Action": action.replace("_", " ").title(),
                    "Why blocked": "; ".join(check.get("reasons", []))}
                   for action, check in checks.items() if not check.get("allowed")]
        left, right = st.columns([1.15, 1], gap="medium")
        with left:
            with st.container(border=True):
                st.subheader("Blocked actions")
                if blocked:
                    st.dataframe(blocked, width="stretch", hide_index=True)
                else:
                    st.caption("No action was blocked by the current policy checks.")
        with right:
            with st.container(border=True):
                st.subheader("Permitted alternatives")
                st.dataframe(proposal.get("alternatives", []), width="stretch", hide_index=True)
        current_audit = latest_audit_rows(selected_id)
        already_reviewed = any(row["decision_id"] == proposal["decision_id"]
                               and row["disposition"] != "pending_review" for row in current_audit)
        if already_reviewed:
            st.success("This decision has a recorded human review.")
        elif st.session_state.auth_user["role"] != "agent":
            st.info("Sign in as a collections specialist to approve, modify, or reject this proposal.")
        else:
            allowed = [action for action, check in checks.items()
                       if check.get("allowed") and action != proposal["action"]]
            with st.container(border=True):
                st.subheader("Record human review")
                with st.form("review_form"):
                    reviewer = st.text_input("Reviewer ID", value=st.session_state.auth_user["user_id"],
                                             key="reviewer_id")
                    reason = st.text_area("Review reason", key="review_reason")
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
                        event = review(proposal["decision_id"], disposition=disposition,
                                       reviewer=reviewer, reason=reason,
                                       action=alternative if disposition == "modify" else None)
                    except Exception as error:
                        st.error(f"Review was not recorded: {error}")
                    else:
                        st.success(f"Recorded {event['disposition']} review: {event['event_id']}")
    with st.expander("Recent audit for this customer", expanded=bool(proposal)):
        st.dataframe(latest_audit_rows(selected_id), width="stretch", hide_index=True)


def render_worklist() -> None:
    page_header("Human review queue", "Priority queue",
                "Linked open promises ranked by estimated break risk. This is a review queue, not an action list.")
    st.caption("The ranking uses evidence available before each promise. Policy is rechecked for any proposed action.")
    if st.button("Load worklist", key="worklist_submit", type="primary"):
        try:
            st.session_state.worklist_rows = worklist(20)
        except Exception as error:
            st.session_state.worklist_rows = None
            st.error(f"Could not load the worklist: {error}")
    rows = st.session_state.get("worklist_rows")
    if rows is not None:
        a, b = st.columns([1, 3])
        a.metric("Open promises shown", len(rows))
        b.caption("Select a row to open that customer's linked record.")

        def select_worklist_customer() -> None:
            selected = st.session_state.worklist_table["selection"]["rows"]
            if selected:
                select_customer(rows[selected[0]]["customer_id"])
                st.session_state.page = "Customer 360"

        st.dataframe([{"Promise ID": row["ptp_id"],
                       "Golden customer ID": row["customer_id"],
                       "Case ID": row["case_id"],
                       "Break risk": f"{row['probability_break']:.1%}",
                       "Top model reason": row["top_reason"]} for row in rows],
                     width="stretch", hide_index=True, key="worklist_table",
                     on_select=select_worklist_customer, selection_mode="single-row")
        st.caption("A high risk score does not authorize contact. Review the customer and policy checks first.")


st.set_page_config(page_title="Maple Collections | Team workspace", page_icon="M",
                   layout="wide", initial_sidebar_state="expanded")
if "auth_user" not in st.session_state:
    render_login()
    st.stop()

inject_theme()
if "golden_id" not in st.session_state:
    st.session_state.golden_id = HERO_ID
if "page" not in st.session_state:
    st.session_state.page = "Dashboard"
render_sidebar(st.session_state.auth_user)
render_top_navigation()

page = st.session_state.page
if page == "Dashboard":
    render_dashboard()
elif page == "Priority queue":
    render_worklist()
elif page == "Customer 360":
    render_customer()
elif page == "Ask Collections":
    render_ask()
elif page == "Decision review":
    render_decision()
