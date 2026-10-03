"""Run from the repository root: python -m streamlit run app/main.py."""

from __future__ import annotations

import streamlit as st

from app.ask import answer as answer_question
from app.customer import load_customer


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

customer_tab, ask_tab, recommendation_tab = st.tabs(
    ["Customer", "Ask", "Recommendation"]
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

                st.subheader("Why linked?")
                identity = customer["identity"]
                st.caption(f"{identity['linked_source_count']} linked source keys. "
                           "Confidence scores are rule based and are not calibrated probabilities.")
                st.dataframe(identity["links"], width="stretch", hide_index=True)

with ask_tab:
    st.subheader("Ask Collections")
    st.caption("General metrics and policy answers use the 28 September 2026 release. "
               "Case questions must refer to a case linked to the selected golden customer.")
    question = st.text_area("Question", key="ask_question",
                            placeholder="What is the average days past due of open cases by queue?")
    if st.button("Get answer", key="ask_submit"):
        try:
            st.session_state.ask_result = answer_question(
                question, golden_customer_id=st.session_state.golden_id.strip(),
                customer_context=customer if customer and customer["found"] else None,
            )
        except Exception as error:
            st.session_state.ask_result = None
            st.error(f"Could not answer the question: {error}")
    result = st.session_state.get("ask_result")
    if result:
        if result["refused"]:
            st.warning(f"Refused: {result['answer']}")
        else:
            st.write(result["answer"])
        st.caption(f"Data date: {result['data_date']} · Scope: {result['scope']} · "
                   f"Mode: {result['mode']}")
        st.markdown("**Metric definition**")
        st.write(result["metric_definition"] or "No certified metric definition applies to this answer.")
        st.markdown("**SQL or sources**")
        st.code(result["sql_or_sources"])

with recommendation_tab:
    st.info("The Decisioning team will connect recommend() here. See app/INTERFACES.md.")
