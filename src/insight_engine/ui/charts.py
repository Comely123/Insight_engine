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
    "price_inquiry": "询价",
    "purchase_intent": "明确意向",
    "payment": "付款",
    "fulfillment": "履约/交付",
    "participation": "参与活动",
    "signup": "报名",
    "cancel_refund": "取消或退款",
    "personal_experience": "个人经历",
    "discussion": "一般讨论",
    "living_blessing": "活体祈福",
    "memorial": "离世纪念",
    "pet_funeral": "宠物殡葬",
    "souvenir": "纪念品/手工",
    "religious_ritual": "宗教仪式",
    "unrelated": "无关内容",
    "academic": "学术论文",
    "market_report": "市场/行业报告",
    "survey_report": "调查/问卷报告",
    "inspection_report": "检验/检测报告",
    "news": "新闻报道",
    "video_meta": "视频元数据",
    "activity_page": "活动页面",
    "product_page": "商品页面",
    "consumer_comment": "消费者评论",
    "image_ocr": "图片OCR",
    "source_code": "源代码",
    "document": "文档",
    "text": "文本",
    "csv": "表格",
    "json": "JSON",
    "subtitle": "字幕",
    "media_stub": "媒体占位",
    "direct": "直接相关",
    "edge": "边缘相关",
    "pending_review": "待复核",
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


def build_distribution_chart(
    counts: dict[str, Any] | None,
    *,
    kind: ChartKind = "hbar",
) -> alt.Chart | None:
    """Build Altair chart object (for UI or export)."""
    df = counts_to_frame(counts)
    if df.empty:
        return None

    colors = _colors(len(df))
    height = max(200, 36 * len(df) + 48)

    if kind == "donut":
        return (
            alt.Chart(df)
            .mark_arc(innerRadius=48, outerRadius=84, stroke="#fff", strokeWidth=2)
            .encode(
                theta=alt.Theta("数量:Q", stack=True),
                color=alt.Color(
                    "类别:N",
                    scale=alt.Scale(range=colors),
                    legend=alt.Legend(
                        orient="bottom",
                        title=None,
                        labelFontSize=12,
                        labelLimit=200,
                        columns=2,
                        symbolLimit=400,
                    ),
                ),
                tooltip=["类别:N", "数量:Q"],
            )
            .properties(
                height=260,
                padding={"left": 12, "right": 12, "top": 12, "bottom": 20},
            )
            .configure_view(strokeWidth=0)
        )
    if kind == "area":
        ordered = df.sort_values("数量", ascending=False)
        return (
            alt.Chart(ordered)
            .mark_area(
                interpolate="monotone",
                opacity=0.55,
                color=MACARON[2],
                line={"color": MACARON[3]},
            )
            .encode(
                x=alt.X(
                    "类别:N",
                    sort="-y",
                    title=None,
                    axis=alt.Axis(labelAngle=-20, labelLimit=160, labelFontSize=11),
                ),
                y=alt.Y("数量:Q", title=None, axis=alt.Axis(grid=True, gridColor="#eee")),
                tooltip=["类别:N", "数量:Q"],
            )
            .properties(height=240, padding={"left": 16, "right": 16, "top": 12, "bottom": 36})
            .configure_view(strokeWidth=0)
        )

    left_pad = 12 + min(120, max(len(str(x)) for x in df["类别"]) * 14)
    return (
        alt.Chart(df)
        .mark_bar(cornerRadiusEnd=8, height=18)
        .encode(
            y=alt.Y(
                "类别:N",
                sort="-x",
                title=None,
                axis=alt.Axis(
                    labelFontSize=12,
                    labelColor="#333",
                    labelLimit=220,
                    labelOverlap=False,
                    domain=False,
                ),
            ),
            x=alt.X(
                "数量:Q",
                title=None,
                axis=alt.Axis(grid=True, gridColor="#f0f0f0", tickCount=4, domainColor="#ddd"),
            ),
            color=alt.Color("类别:N", scale=alt.Scale(range=colors), legend=None),
            tooltip=["类别:N", "数量:Q"],
        )
        .properties(
            height=height,
            padding={"left": left_pad, "right": 20, "top": 12, "bottom": 8},
        )
        .configure_view(strokeWidth=0)
    )


def render_distribution(
    counts: dict[str, Any] | None,
    *,
    title: str,
    kind: ChartKind = "hbar",
    alt_text: str | None = None,
) -> None:
    st.markdown(f"**{title}**")
    chart = build_distribution_chart(counts, kind=kind)
    if chart is None:
        st.caption("暂无数据")
    else:
        st.altair_chart(chart, width="stretch", alt=alt_text or title)


def pick_report_chart_slots(
    stats: dict[str, Any],
    *,
    profile: str,
) -> list[tuple[str, dict[str, Any] | None, ChartKind]]:
    """
    Always return 4 slots for a 2×2 square:
      TL 内容类型 | TR 研究相关度
      BL 研究主题 | BR 行为/立场/创新（随画像）
    """
    fourth_title = "行为 / 意向阶段"
    fourth_counts = stats.get("behavior_stage_counts")
    fourth_kind: ChartKind = "hbar"
    if profile == "literature":
        if stats.get("innovation_counts"):
            fourth_title, fourth_counts, fourth_kind = (
                "创新主张（已门控）",
                stats.get("innovation_counts"),
                "hbar",
            )
        elif stats.get("stance_counts"):
            fourth_title, fourth_counts, fourth_kind = (
                "立场（≠意向）",
                stats.get("stance_counts"),
                "donut",
            )
    elif stats.get("stance_counts") and not fourth_counts:
        fourth_title, fourth_counts, fourth_kind = (
            "立场（≠意向）",
            stats.get("stance_counts"),
            "donut",
        )
    elif stats.get("price_buckets") and profile in {"market", "mixed"}:
        if not fourth_counts:
            fourth_title, fourth_counts, fourth_kind = (
                "已确认价格区间",
                stats.get("price_buckets"),
                "area",
            )

    return [
        ("内容类型", stats.get("content_kind_counts"), "donut"),
        ("研究相关度", stats.get("relevance_counts"), "donut"),
        (
            "研究主题",
            stats.get("research_topic_counts") or stats.get("demand_subtype_counts"),
            "hbar",
        ),
        (fourth_title, fourth_counts, fourth_kind),
    ]


# Back-compat alias
def macaron_bar(counts: dict[str, Any] | None, *, title: str, alt_text: str) -> None:
    render_distribution(counts, title=title, kind="hbar", alt_text=alt_text)
