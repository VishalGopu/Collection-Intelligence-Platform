"""Presentation styling for the Streamlit collections workspace."""

from __future__ import annotations

import streamlit as st


CSS = """
<style>
:root { --ink:#29222a; --muted:#6e6570; --burgundy:#8b1b41; --red:#c41230;
        --line:#e9dce1; --surface:#ffffff; --canvas:#faf7f8; }
html, body, [class*="css"] { font-family: Inter, "Segoe UI", Arial, sans-serif; }
[data-testid="stAppViewContainer"] { background: var(--canvas); color: var(--ink); }
[data-testid="stHeader"] { background: var(--burgundy); }
.block-container { max-width: 1510px; padding-top: 1.6rem; padding-bottom: 2.8rem; }
h1,h2,h3 { color: var(--ink); letter-spacing: -.025em; }
h1 { font-size: 2rem !important; }
h2 { font-size: 1.35rem !important; }
[data-testid="stSidebar"] { background: #fff; border-right: 1px solid var(--line); }
[data-testid="stSidebar"] * { color: var(--ink) !important; }
[data-testid="stSidebar"] [data-testid="stRadio"] label { border-radius: 10px; padding: .42rem .55rem; }
[data-testid="stSidebar"] [data-testid="stRadio"] label:hover { background: #fae8ed; }
[data-testid="stSidebar"] button { border-color: #d8c7ce !important; background: #fff !important; }
[data-testid="stMetric"] { background: var(--surface); border: 1px solid var(--line);
  border-radius: 16px; padding: 1.15rem 1.3rem; box-shadow: 0 8px 28px rgba(18,32,53,.035); }
[data-testid="stMetricLabel"] { color: var(--muted); font-weight: 600; }
[data-testid="stMetricValue"] { color: var(--ink); font-weight: 750; }
[data-testid="stVerticalBlockBorderWrapper"] { background: var(--surface); border-color: var(--line);
  border-radius: 16px; box-shadow: 0 8px 28px rgba(18,32,53,.035); }
[data-testid="stDataFrame"] { border: 1px solid var(--line); border-radius: 12px; overflow: hidden; }
.stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {
  background: var(--red); color: white; border: 1px solid var(--red); border-radius: 10px; }
.stButton > button[kind="primary"]:hover, .stFormSubmitButton > button[kind="primary"]:hover {
  background: #9e1028; border-color: #9e1028; color: #fff; }
.stButton > button, .stFormSubmitButton > button { border-radius: 10px; font-weight: 650; }
.st-key-top_navigation .stButton > button[kind="secondary"] {
  background: #fff !important; border: 1px solid #e1cbd3 !important; color: var(--ink) !important; }
.st-key-top_navigation .stButton > button[kind="secondary"] p,
.st-key-top_navigation .stButton > button[kind="secondary"] span { color: var(--ink) !important; }
.st-key-top_navigation .stButton > button[kind="primary"] {
  background: var(--red) !important; border: 1px solid var(--red) !important; color: #fff !important; }
.st-key-top_navigation .stButton > button[kind="primary"] p,
.st-key-top_navigation .stButton > button[kind="primary"] span { color: #fff !important; }
.st-key-top_navigation .stButton > button[kind="secondary"]:hover {
  background: #fbe8ed !important; border-color: var(--red) !important; }
.st-key-top_navigation .stButton > button[kind="primary"]:hover {
  background: #9e1028 !important; border-color: #9e1028 !important; }
.eyebrow { color:var(--burgundy); font-size:.76rem; letter-spacing:.13em; font-weight:800; text-transform:uppercase; }
.page-lede { color:var(--muted); margin-top:-.6rem; margin-bottom:1.2rem; }
.brand { color:var(--ink); font-size:1.15rem; font-weight:850; letter-spacing:-.035em; margin:.7rem 0 0; }
.brand-sub { color:var(--muted); font-size:.82rem; margin-bottom:1.5rem; }
.hero-panel { background: radial-gradient(circle at 82% 14%, #f6dce5 0, transparent 34%),
  linear-gradient(135deg,#f8e9ed 0%,#f3dfe6 62%,#edcbd7 100%);
  color:var(--ink); border-radius:22px; padding:3.4rem 3.3rem; min-height:510px;
  box-shadow:0 20px 55px rgba(99,20,48,.08); position:relative; overflow:hidden; }
.hero-panel:after { content:""; position:absolute; right:-5rem; bottom:-8rem; width:25rem;
  height:25rem; border:1px solid rgba(139,27,65,.17); border-radius:50%;
  box-shadow:0 0 0 4rem rgba(139,27,65,.035),0 0 0 8rem rgba(139,27,65,.025); }
.hero-panel .eyebrow { color:var(--burgundy); }
.hero-panel h1 { color:var(--ink); font-size:3rem !important; max-width:570px; line-height:1.08; margin:2.4rem 0 1.2rem; }
.hero-panel p { color:#4e3e48; font-size:1.05rem; max-width:500px; line-height:1.65; }
.hero-points { display:flex; flex-wrap:wrap; gap:.55rem; margin-top:2.5rem; }
.hero-points span { border:1px solid #c9869d; border-radius:999px; padding:.4rem .7rem;
  color:var(--burgundy); font-size:.82rem; }
.login-title { margin:2rem 0 .35rem; font-size:1.9rem; font-weight:800; color:var(--ink); }
.login-sub { color:var(--muted); margin-bottom:1.4rem; }
.status-pill { display:inline-block; border-radius:999px; background:#e8f4ee; color:#20764b;
  font-size:.78rem; font-weight:750; padding:.34rem .7rem; }
.small-note { color:#718098; font-size:.82rem; }
@media (max-width: 850px) {
  .block-container { padding-left:1rem; padding-right:1rem; }
  .hero-panel { min-height:300px; padding:2rem; }
  .hero-panel h1 { font-size:2.1rem !important; margin:1rem 0; }
}
</style>
"""


def inject_theme(*, login: bool = False) -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    if login:
        st.markdown("<style>[data-testid='stSidebar']{display:none}</style>",
                    unsafe_allow_html=True)
