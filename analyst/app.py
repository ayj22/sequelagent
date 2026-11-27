"""Streamlit front end: streamlit run analyst/app.py"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st

from analyst import agent, semantic
from analyst.config import ROOT, load_env, model_name
from analyst.llm import ModelError, OpenAIModel

EXAMPLES = ["What was net revenue by region last quarter?", "Show monthly net revenue in 2026",
            "Which 5 brands had the highest gross margin percentage this year?", "Compare return rate by channel",
            "Delete all orders from 2025"]

st.set_page_config(page_title="QuerySherpa", page_icon="🧭", layout="wide")
load_env()


@st.cache_resource
def model():
    return OpenAIModel(model_name())


with st.sidebar:
    st.header("🧭 QuerySherpa")
    st.caption("Ask a question about a synthetic retail business. Every query is checked before it runs.")
    score = ROOT / "evals" / "results" / "latest.json"
    if score.exists():
        s = json.loads(score.read_text())
        st.metric("Evaluation accuracy", f"{s['accuracy_pct']}%", help=f"{s['correct']} of {s['questions']} questions, {s['model']}")
        st.metric("Unsafe requests handled safely", f"{s['attacks_stopped']}/{s['attacks']}")
    with st.expander("Metric definitions"):
        for name, formula in semantic.layer()["metrics"].items():
            st.markdown(f"**{name}**")
            st.code(formula, language="sql")

st.title("Ask your data")
picked = st.pills("Try one", EXAMPLES, key="example")
question = st.text_input("Question", value=picked or "", placeholder="e.g. Average order value by loyalty tier in 2026",
                         max_chars=agent.MAX_QUESTION)

if question:
    try:
        with st.spinner("Writing and checking the query…"):
            a = agent.ask(question, model())
    except (ModelError, FileNotFoundError) as exc:
        st.error(str(exc))
        st.stop()
    if a.status == "blocked":
        st.error(f"Blocked by a guardrail: {a.message}")
    elif a.status == "refused":
        st.warning(f"Not answered: {a.message}")
    elif a.status == "failed":
        st.error(f"Could not produce a working query: {a.message}")
    else:
        st.success(a.message)
        frame = pd.DataFrame(a.rows, columns=a.columns)
        kind = a.chart.get("type")
        if kind == "metric":
            st.metric(a.chart["y"].replace("_", " "), f"{float(frame.iloc[0, 0]):,.2f}" if frame.iloc[0, 0] is not None else "–")
        elif kind in ("bar", "line"):
            data = frame.astype({a.chart["y"]: float})
            if kind == "bar":
                st.bar_chart(data, x=a.chart["x"], y=a.chart["y"], sort=False)
            else:
                st.line_chart(data, x=a.chart["x"], y=a.chart["y"])
        st.dataframe(frame, hide_index=True, width="stretch")
    if a.sql:
        with st.expander("SQL", expanded=True):
            st.code(a.sql, language="sql")
    st.caption(f"{a.attempts} attempt(s) · {a.seconds}s · {a.input_tokens:,} input and {a.output_tokens:,} output tokens")
