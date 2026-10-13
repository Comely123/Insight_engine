"""Macaron Altair charts with Chinese labels for the public report page."""

from __future__ import annotations

from typing import Any

import altair as alt
import pandas as pd
import streamlit as st

from insight_engine.ui.theme import MACARON

LABEL_ZH: dict[str, str] = {
    "unknown": "未知",
    "interest": "兴趣表达",
    "inquiry": "咨询了解",
    "price_inquiry": "价格咨询",
    "purchase_intent": "购买意向",
    "payment": "实际付款",
    "fulfillment": "服务完成",
    "participation": "实际参与",
    "signup": "预约报名",
    "cancel_refund": "取消退款",
    "personal_experience": "个人经历",
    "discussion": "一般讨论",
    "living_blessing": "活体祈福",
    "memorial": "离世纪念",
    "positive": "正面",
    "negative": "负面",
    "neutral": "中性",
    "<50": "50元以下",
    "50-99": "50–99元",
    "100-149": "100–149元",
    "150-199": "150–199元",
    "200+": "200元以上",
    "200-": "200元以上",
}


def _zh(key: Any) -> str:
    s = str(key)
    return LABEL_ZH.get(s, s)


def counts_to_frame(counts: dict[str, Any] | None) -> pd.DataFrame:
    if not counts:
        return pd.DataFrame(columns=["类别", "数量"])
    rows = [{"类别": _zh(k), "数量": int(v)} for k, v in counts.items() if int(v) > 0]
    if not rows:
        return pd.DataFrame(columns=["类别", "数量"])
    return pd.DataFrame(rows).sort_values("数量", ascending=False)


def macaron_bar(counts: dict[str, Any] | None, *, title: str, alt_text: str) -> None:
    df = counts_to_frame(counts)
    if df.empty:
        st.caption("暂无数据")
        return
    colors = MACARON * ((len(df) // len(MACARON)) + 1)
    chart = (
        alt.Chart(df)
        .mark_bar(cornerRadiusTopLeft=6, cornerRadiusTopRight=6, size=28)
        .encode(
            x=alt.X(
                "类别:N",
                sort="-y",
                title=None,
                axis=alt.Axis(labelAngle=0, labelFontSize=12, labelColor="#444"),
            ),
            y=alt.Y(
                "数量:Q",
                title=None,
                axis=alt.Axis(grid=True, gridColor="#eee", tickCount=4, labelFontSize=11),
            ),
            color=alt.Color(
                "类别:N",
                scale=alt.Scale(range=colors[: len(df)]),
                legend=None,
            ),
            tooltip=[
                alt.Tooltip("类别:N", title="类别"),
                alt.Tooltip("数量:Q", title="数量"),
            ],
        )
        .properties(height=220, title=alt.TitleParams(text=title, fontSize=14, color="#222", anchor="start"))
        .configure_view(strokeWidth=0)
        .configure_axis(domainColor="#ddd")
    )
    st.altair_chart(chart, width="stretch", alt=alt_text)
