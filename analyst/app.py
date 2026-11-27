"""Streamlit front end: streamlit run analyst/app.py"""
import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import altair as alt
import pandas as pd
import streamlit as st

from analyst import agent, overview, present, semantic, warehouse
from analyst.config import ROOT, load_env, model_name
from analyst.limits import RateLimit
from analyst.llm import ModelError, OpenAIModel

EXAMPLES = [("💰", "Channels", "Compare retail and wholesale revenue and margin % in 2026"),
            ("📈", "Trend", "Show monthly company net revenue in 2026"),
            ("🏬", "Wholesale", "Which 5 wholesale accounts had the highest net revenue in 2026?"),
            ("👟", "Sizes", "Weeks of supply by men's shoe size right now"),
            ("📦", "Fill rate", "What was the wholesale fill rate by month in 2026?"),
            ("🛡️", "Safety test", "Delete all orders from 2025")]
STEPS = {"writing": "🧠  Planning the analysis and writing SQL", "checking": "🛡️  Reviewing the query against safety rules",
         "running": "⚡  Querying the warehouse", "repairing": "🔧  That failed: correcting the query"}
COMPANY = "Northgate Footwear Co."
ACCENT = "#4F46E5"

STYLE = """
<style>
.block-container {max-width: 1060px; padding-top: 2.2rem; padding-bottom: 3rem;}
header[data-testid="stHeader"] {background: transparent;}
.bar {display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; margin-bottom: 14px;}
.bar .co {font-size: 1.55rem; font-weight: 750; color: #14162B; line-height: 1.2;}
.bar .sub {color: #5B5F7A; font-size: .9rem;}
.pill {background: #EEF2FF; color: #3730A3; border-radius: 999px; padding: 6px 14px; font-size: .82rem; font-weight: 600;}
.kpis {display: grid; grid-template-columns: repeat(auto-fit, minmax(175px, 1fr)); gap: 12px; margin-bottom: 16px;}
.kpi {background: #fff; border: 1px solid #E6E8F2; border-radius: 14px; padding: 14px 16px;}
.kpi .l {color: #5B5F7A; font-size: .8rem;} .kpi .n {font-size: 1.6rem; font-weight: 750; color: #14162B;}
.kpi .d {font-size: .76rem; color: #5B5F7A;} .up {color: #047857; font-weight: 700;} .down {color: #B91C1C; font-weight: 700;}
.card {background: #fff; border: 1px solid #E6E8F2; border-radius: 16px; padding: 18px 22px; margin: 6px 0 12px 0;}
.card .tag {font-size: .74rem; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; margin-bottom: 6px;}
.card .text {font-size: 1.18rem; line-height: 1.5;}
.ok {border-left: 6px solid #10B981;} .ok .tag {color: #047857;}
.warn {border-left: 6px solid #F59E0B;} .warn .tag {color: #B45309;}
.stop {border-left: 6px solid #EF4444;} .stop .tag {color: #B91C1C;}
.checks {display: flex; gap: 8px; flex-wrap: wrap; margin: 2px 0 14px 0;}
.checks span {background: #ECFDF5; color: #065F46; border-radius: 999px; padding: 4px 12px; font-size: .8rem; font-weight: 600;}
.big {background: #fff; border: 1px solid #E6E8F2; border-radius: 16px; padding: 20px 24px; margin-bottom: 12px;}
.big .n {font-size: 2.6rem; font-weight: 750; color: #312E81; line-height: 1.15;}
.big .l {color: #5B5F7A; font-size: .9rem;}
div[data-testid="stButton"] button {width: 100%; text-align: left; justify-content: flex-start; background: #fff; border: 1px solid #E0E3F0;
       min-height: 88px; height: auto;}
div[data-testid="stButton"] button p {white-space: normal; text-align: left; line-height: 1.4;}
div[data-testid="stButton"] button > div {justify-content: flex-start; width: 100%;}
div[data-testid="stButton"] button:hover {border-color: #4F46E5; box-shadow: 0 4px 14px rgba(79,70,229,.14);}
div[data-testid="stForm"] {background: #fff; border: 1px solid #E6E8F2; border-radius: 16px;}
div[data-testid="stTextInput"] input {font-size: 1.08rem;}
</style>
"""

st.set_page_config(page_title="SequelAgent · Governed AI Analyst Agent", page_icon="🛡️", layout="wide", initial_sidebar_state="expanded")
load_env()
st.html(STYLE)


@st.cache_resource
def model():
    return OpenAIModel(model_name())


def card(kind: str, tag: str, text: str) -> None:
    # st.html, not markdown: text from the model must never become a link or an image that calls out to another site
    st.html(f'<div class="card {kind}"><div class="tag">{html.escape(tag)}</div><div class="text">{html.escape(text)}</div></div>')


def change(value: float | None, unit: str, against: str) -> str:
    if value is None:
        return ""
    direction, arrow = ("up", "▲") if value >= 0 else ("down", "▼")
    return f'<span class="{direction}">{arrow} {abs(value):.1f}{unit}</span> vs {against}'


@st.cache_data
def headline() -> dict:
    return overview.headline()


def header() -> None:
    try:
        data = headline()
    except (FileNotFoundError, warehouse.QueryError):
        st.error("The data is not built yet. Run `make data`, then reload.")
        st.stop()
    month = data["month"].strftime("%B %Y")
    tiles = ""
    for m in data["metrics"]:
        unit = " pts" if m["name"].endswith("_pct") else "%"
        tiles += (f'<div class="kpi"><div class="l">{html.escape(present.label(m["name"]))}</div>'
                  f'<div class="n">{html.escape(present.show(m["value"], m["name"]))}</div>'
                  f'<div class="d">{change(m["vs_previous"], unit, "last month")}<br>{change(m["vs_year_ago"], unit, "last year")}</div></div>')
    st.html(f'<div class="bar"><div><div class="co">{COMPANY}</div><div class="sub">Business overview · {month}</div></div>'
            f'<div class="pill">🛡️ SequelAgent · Governed AI Analyst Agent</div></div><div class="kpis">{tiles}</div>')


def sidebar() -> None:
    with st.sidebar:
        st.markdown("## 🛡️ SequelAgent")
        st.markdown("**Governed AI Analyst Agent**  \nfor footwear retail and wholesale")
        st.caption("Ask in plain English. It writes the query, checks it is safe, runs it read-only and shows its work. "
                   "Demo footwear company, fictional data, Jan 2025 to Sep 2026.")
        score = ROOT / "evals" / "results" / "latest.json"
        if score.exists():
            s = json.loads(score.read_text())
            st.markdown("#### Tested before you trust it")
            left, right = st.columns(2)
            left.metric("Correct", f"{s['correct']}/{s['questions']}", help=f"Recorded evaluation run, {s['model']}")
            right.metric("Handled safely", f"{s['attacks_stopped']}/{s['attacks']}", help="Hostile or unanswerable requests")
        st.markdown("#### You can ask about")
        st.markdown("Retail sales · Wholesale accounts · Margin · Inventory and sizes · Customers · Marketing")
        with st.expander("How metrics are defined"):
            for name, formula in semantic.layer()["metrics"].items():
                st.markdown(f"**{present.label(name)}**")
                st.code(formula, language="sql")


def draw(a: agent.Answer) -> None:
    frame = pd.DataFrame(a.rows, columns=a.columns)
    kind = a.chart.get("type")
    if len(a.rows) == 1:
        for column, (name, value) in zip(st.columns(len(a.columns)), zip(a.columns, a.rows[0])):
            with column:
                st.html(f'<div class="big"><div class="l">{html.escape(present.label(name))}</div>'
                        f'<div class="n">{html.escape(present.show(value, name))}</div></div>')
        return
    if kind in ("bar", "line"):
        x, y = a.chart["x"], a.chart["y"]
        xi, yi = a.columns.index(x), a.columns.index(y)
        data = pd.DataFrame({"x": [present.show(r[xi], x) if r[xi] is not None else "Not set" for r in a.rows],
                             "y": [None if r[yi] is None else float(r[yi]) for r in a.rows],
                             "shown": [present.show(r[yi], y) for r in a.rows]})
        axis_format = {"money": "$~s", "percent": ".0f", "ratio": ".1f"}.get(present.column_kind(y), "~s")
        base = alt.Chart(data).encode(
            x=alt.X("x:N", sort=None, title=None, axis=alt.Axis(labelAngle=0 if len(data) <= 8 else -40, labelFontSize=13)),
            y=alt.Y("y:Q", title=present.label(y), axis=alt.Axis(format=axis_format, gridColor="#EEF0F7")),
            tooltip=[alt.Tooltip("x:N", title=present.label(x)), alt.Tooltip("shown:N", title=present.label(y))])
        if kind == "bar":
            marks = base.mark_bar(color=ACCENT, cornerRadiusTopLeft=8, cornerRadiusTopRight=8)
        else:
            marks = base.mark_line(color=ACCENT, strokeWidth=3, point=alt.OverlayMarkDef(color=ACCENT, size=80, filled=True))
        if len(data) <= 10:
            marks = marks + base.mark_text(dy=-12, fontSize=13, fontWeight="bold", color="#14162B").encode(text="shown:N")
        st.altair_chart(marks.properties(height=340).configure_view(strokeWidth=0), width="stretch")
    table = pd.DataFrame({present.label(c): [present.show(r[i], c) for r in a.rows] for i, c in enumerate(a.columns)})
    # the chart shows one measure, so when the answer has more, the table is open
    with st.expander(f"Table ({len(table)} rows)", expanded=kind == "table" or len(a.columns) > 2):
        st.dataframe(table, hide_index=True, width="stretch")
        safe = frame.rename(columns=present.spreadsheet_safe).map(present.spreadsheet_safe)
        st.download_button("Download CSV", safe.to_csv(index=False), "answer.csv", "text/csv")


def show_answer(a: agent.Answer) -> None:
    if a.status == "answered":
        card("ok", "Answer", a.message)
        st.html('<div class="checks"><span>✓ Read-only query</span><span>✓ Approved tables only</span>'
                '<span>✓ No personal data</span></div>')
        draw(a)
    elif a.status == "refused":
        card("warn", "Not answered", a.message)
        st.caption("Nothing was run. Try a question about retail or wholesale sales, inventory, customers or marketing.")
    elif a.status == "blocked":
        card("stop", "Blocked by a safety check", a.message)
        st.caption("The query never reached the database.")
    else:
        card("stop", "No working query", a.message)
        st.caption("Try rewording the question, for example by naming the metric and the time period.")
    if a.sql:
        with st.expander("See the SQL"):
            st.code(a.sql, language="sql")
    st.caption(f"{a.seconds}s · {a.attempts} attempt(s) · {a.input_tokens + a.output_tokens:,} tokens")


def pick(question: str) -> None:
    st.session_state.question = question
    st.session_state.pending = question


sidebar()
header()

with st.form("ask", clear_on_submit=False, border=True):
    left, right = st.columns([6, 1], vertical_alignment="bottom")
    left.text_input("Ask your AI analyst", key="question", placeholder="e.g. Sell-through by brand in August 2026",
                    max_chars=agent.MAX_QUESTION)
    if right.form_submit_button("Ask →", type="primary", width="stretch"):
        st.session_state.pending = st.session_state.question

question = st.session_state.pop("pending", None)
if question and question.strip():
    limit = st.session_state.setdefault("limit", RateLimit(calls=20, seconds=600))
    if not limit.allow():
        st.warning("That is a lot of questions in a short time. Please wait a few minutes.")
        question = ""
if question and question.strip():
    try:
        with st.status("SequelAgent is working…", expanded=True) as status:
            a = agent.ask(question, model(), on_step=lambda step: status.write(STEPS[step]))
            status.update(label="Done", state="complete", expanded=False)
        st.session_state.answer = a
    except (ModelError, FileNotFoundError) as exc:
        st.session_state.pop("answer", None)
        st.error(str(exc))

if "answer" in st.session_state:
    show_answer(st.session_state.answer)
    st.markdown("#### Try another")
else:
    st.markdown("#### Not sure where to start? Pick one")
columns = st.columns(3)
for i, (icon, topic, text) in enumerate(EXAMPLES):
    columns[i % 3].button(f"{icon} **{topic}**  \n{text}", key=f"example-{i}", on_click=pick, args=(text,), width="stretch")
