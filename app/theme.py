"""Presentation styling for the Streamlit collections workspace."""

from __future__ import annotations

import streamlit as st


CSS = """
<style>
:root { --ink:#172238; --muted:#69778b; --navy:#101a29; --blue:#175cd3;
        --line:#e5eaf1; --surface:#ffffff; --canvas:#f3f6fa; }
html, body, [class*="css"] { font-family: Inter, "Segoe UI", Arial, sans-serif; }
[data-testid="stAppViewContainer"] { background: var(--canvas); color: var(--ink); }
[data-testid="stHeader"] { background: var(--canvas); }
.block-container { max-width: 1510px; padding-top: 1.6rem; padding-bottom: 2.8rem; }
h1,h2,h3 { color: var(--ink); letter-spacing: -.025em; }
h1 { font-size: 2rem !important; }
h2 { font-size: 1.35rem !important; }
[data-testid="stSidebar"] { background: var(--navy); border-right: 0; }
[data-testid="stSidebar"] * { color: #e8eef6 !important; }
[data-testid="stSidebar"] [data-testid="stRadio"] label { border-radius: 10px; padding: .42rem .55rem; }
[data-testid="stSidebar"] [data-testid="stRadio"] label:hover { background: #26354b; }
[data-testid="stSidebar"] button { border-color: #40516a !important; background: #18273a !important; }
[data-testid="stMetric"] { background: var(--surface); border: 1px solid var(--line);
  border-radius: 16px; padding: 1.15rem 1.3rem; box-shadow: 0 8px 28px rgba(18,32,53,.035); }
[data-testid="stMetricLabel"] { color: var(--muted); font-weight: 600; }
[data-testid="stMetricValue"] { color: var(--ink); font-weight: 750; }
[data-testid="stVerticalBlockBorderWrapper"] { background: var(--surface); border-color: var(--line);
  border-radius: 16px; box-shadow: 0 8px 28px rgba(18,32,53,.035); }
[data-testid="stDataFrame"] { border: 1px solid var(--line); border-radius: 12px; overflow: hidden; }
.stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {
  background: #17263b; color: white; border: 1px solid #17263b; border-radius: 10px; }
.stButton > button, .stFormSubmitButton > button { border-radius: 10px; font-weight: 650; }
.eyebrow { color:#54749b; font-size:.76rem; letter-spacing:.13em; font-weight:800; text-transform:uppercase; }
.page-lede { color:#68788e; margin-top:-.6rem; margin-bottom:1.2rem; }
.brand { color:#fff; font-size:1.25rem; font-weight:850; letter-spacing:-.035em; margin:.7rem 0 0; }
.brand span { background:#fff; color:#17263b; padding:.13rem .42rem; border-radius:6px; margin-right:.35rem; }
.brand-sub { color:#9db0c6; font-size:.82rem; margin-bottom:1.5rem; }
.hero-panel { background: radial-gradient(circle at 82% 14%, #314f76 0, transparent 34%),
  linear-gradient(135deg,#101a29 0%,#17263b 62%,#1b3654 100%);
  color:#fff; border-radius:22px; padding:3.4rem 3.3rem; min-height:510px;
  box-shadow:0 20px 55px rgba(13,26,43,.2); position:relative; overflow:hidden; }
.hero-panel:after { content:""; position:absolute; right:-5rem; bottom:-8rem; width:25rem;
  height:25rem; border:1px solid rgba(255,255,255,.17); border-radius:50%;
  box-shadow:0 0 0 4rem rgba(255,255,255,.035),0 0 0 8rem rgba(255,255,255,.025); }
.hero-panel .eyebrow { color:#a8c9ef; }
.hero-panel h1 { color:white; font-size:3rem !important; max-width:570px; line-height:1.08; margin:2.4rem 0 1.2rem; }
.hero-panel p { color:#c9d6e4; font-size:1.05rem; max-width:500px; line-height:1.65; }
.hero-points { display:flex; flex-wrap:wrap; gap:.55rem; margin-top:2.5rem; }
.hero-points span { border:1px solid #56708d; border-radius:999px; padding:.4rem .7rem;
  color:#eaf3fc; font-size:.82rem; }
.login-title { margin:2rem 0 .35rem; font-size:1.9rem; font-weight:800; color:#172238; }
.login-sub { color:#69778b; margin-bottom:1.4rem; }
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
