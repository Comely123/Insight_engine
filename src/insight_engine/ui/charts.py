"""Richer macaron Altair charts (no clipped titles; mixed mark types)."""

from __future__ import annotations

from typing import Any, Literal

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

ChartKind = Literal["hbar", "donut", "area"]


def _zh(key: Any) -> str:
    return LABEL_ZH.get(str(key), str(key))


def counts_to_frame(counts: dict[str, Any] | None) -> pd.DataFrame:
    if not counts:
        return pd.DataFrame(columns=["类别", "数量"])
    rows = [{"类别": _zh(k), "数量": int(v)} for k, v in counts.items() if int(v) > 0]
    if not rows:
        return pd.DataFrame(columns=["类别", "数量"])
    return pd.DataFrame(rows).sort_values("数量", ascending=True)


def _colors(n: int) -> list[str]:
    return (MACARON * ((n // len(MACARON)) + 1))[:n]


def render_distribution(
    counts: dict[str, Any] | None,
    *,
    title: str,
    kind: ChartKind = "hbar",
    alt_text: str | None = None,
) -> None:
    st.markdown(f"**{title}**")
    df = counts_to_frame(counts)
    if df.empty:
        st.caption("暂无数据")
        return

    colors = _colors(len(df))
    height = max(180, 36 * len(df) + 40)

    if kind == "donut":
        chart = (
            alt.Chart(df)
            .mark_arc(innerRadius=48, outerRadius=84, stroke="#fff", strokeWidth=2)
            .encode(
                theta=alt.Theta("数量:Q", stack=True),
                color=alt.Color(
                    "类别:N",
                    scale=alt.Scale(range=colors),
                    legend=alt.Legend(orient="bottom", title=None, labelFontSize=11),
                ),
                tooltip=["类别:N", "数量:Q"],
            )
            .properties(height=260, padding={"left": 8, "right": 8, "top": 8, "bottom": 8})
            .configure_view(strokeWidth=0)
        )
    elif kind == "area":
        # Ranked soft points + area for visual variety on ordered buckets
        ordered = df.sort_values("数量", ascending=False)
        chart = (
            alt.Chart(ordered)
            .mark_area(
                interpolate="monotone",
                opacity=0.55,
                color=MACARON[2],
                line={"color": MACARON[3]},
            )
            .encode(
                x=alt.X("类别:N", sort="-y", title=None, axis=alt.Axis(labelAngle=-25, labelLimit=120)),
                y=alt.Y("数量:Q", title=None, axis=alt.Axis(grid=True, gridColor="#eee")),
                tooltip=["类别:N", "数量:Q"],
            )
            .properties(height=240, padding={"left": 12, "right": 12, "top": 10, "bottom": 30})
            .configure_view(strokeWidth=0)
        )
    else:
        chart = (
            alt.Chart(df)
            .mark_bar(cornerRadiusEnd=8, height=18)
            .encode(
                y=alt.Y(
                    "类别:N",
                    sort="-x",
                    title=None,
                    axis=alt.Axis(labelFontSize=12, labelColor="#333", labelLimit=160, domain=False),
                ),
                x=alt.X(
                    "数量:Q",
                    title=None,
                    axis=alt.Axis(grid=True, gridColor="#f0f0f0", tickCount=4, domainColor="#ddd"),
                ),
                color=alt.Color("类别:N", scale=alt.Scale(range=colors), legend=None),
                tooltip=["类别:N", "数量:Q"],
            )
            .properties(height=height, padding={"left": 4, "right": 16, "top": 8, "bottom": 8})
            .configure_view(strokeWidth=0)
        )

    st.altair_chart(chart, width="stretch", alt=alt_text or title)


# Back-compat alias
def macaron_bar(counts: dict[str, Any] | None, *, title: str, alt_text: str) -> None:
    render_distribution(counts, title=title, kind="hbar", alt_text=alt_text)
