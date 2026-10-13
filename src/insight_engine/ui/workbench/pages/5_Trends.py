"""Basic explainable trend metrics."""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[4]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import pandas as pd
import streamlit as st

from insight_engine.db.connection import get_connection, initialize_database
from insight_engine.trends.metrics import compute_trend_metrics

st.set_page_config(page_title="趋势分析 · Insight Engine", layout="wide")
initialize_database()

st.title("趋势分析")
st.caption(
    "指标可解释、可拆解。若样本量不足或来源集中，系统会警告�?
    "不会把结果表述为已确认的市场趋势�?
)

window = st.selectbox("时间窗口（日�?, [7, 30, 90], index=1)
persist = st.checkbox("保存快照�?trend_snapshots", value=False)

with get_connection() as conn:
    report = compute_trend_metrics(conn, window_days=int(window), persist=persist)

    if report.warnings:
        for w in report.warnings:
            st.warning(w)
    else:
        st.success("未触发样本量/来源集中警告（仍请人工判断）�?)

    st.subheader("核心计数")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("去重文档", report.unique_documents)
    c2.metric("独立事件�?, report.independent_events)
    c3.metric("独立来源", report.independent_sources)
    growth_label = (
        f"{report.growth_rate:.0%}" if report.growth_rate is not None else "N/A"
    )
    c4.metric("相对前窗增长�?, growth_label)

    st.write(
        {
            "confirmed_market_trend": report.confirmed_market_trend,
            "prior_window_unique_docs": report.prior_window_unique_docs,
            "duplicate_documents_in_window": report.duplicate_documents,
        }
    )

    st.subheader("主题占比")
    if report.topic_counts:
        st.bar_chart(pd.Series(report.topic_counts, name="count"))
    else:
        st.info("无主题主张，请先在「事件与主张」页运行分析�?)

    st.subheader("行为意向分布")
    if report.intent_counts:
        st.bar_chart(pd.Series(report.intent_counts, name="count"))
    else:
        st.info("无意向主张�?)

    st.subheader("正反证据（立场）")
    if report.stance_counts:
        st.bar_chart(pd.Series(report.stance_counts, name="count"))
    else:
        st.info("无立场主张�?)

    st.subheader("价格区间")
    if report.price_buckets:
        st.bar_chart(pd.Series(report.price_buckets, name="count"))
        st.caption(f"抽取到的价格样本：{report.price_values}")
    else:
        st.info("无价格主张�?)

    st.subheader("按日去重内容�?)
    if report.daily_unique_docs:
        st.line_chart(pd.Series(report.daily_unique_docs, name="unique_docs"))
    else:
        st.info("窗口内无带时间戳的文档�?)

    with st.expander("趋势组成说明（非黑盒分数�?):
        st.json(report.composition)
