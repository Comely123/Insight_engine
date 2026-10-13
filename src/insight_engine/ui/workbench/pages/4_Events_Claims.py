"""Events, claims, evidence, and human review."""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[4]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import streamlit as st

from insight_engine.analysis.pipeline import AnalysisService
from insight_engine.db.analysis_repository import AnalysisRepository
from insight_engine.db.connection import get_connection, initialize_database
from insight_engine.llm.factory import get_llm_provider

st.set_page_config(page_title="事件与主�?· Insight Engine", layout="wide")
initialize_database()

st.title("事件与主�?)
st.caption(
    "结构化结论必须带来源摘录。未核验内容默认显示�?unreviewed�?
    "请勿将模�?规则输出直接当作已确认事实�?
)

llm = get_llm_provider()
st.write(
    {
        "llm_provider": llm.name,
        "llm_available": llm.available(),
    }
)

col_a, col_b = st.columns(2)
use_llm = col_a.checkbox("尝试 LLM 增强（需 API Key�?, value=False)
include_dupes = col_b.checkbox("包含重复文档", value=False)

if st.button("对库内文档运行分�?, type="primary"):
    with get_connection() as conn:
        summary = AnalysisService(conn).analyze_documents(
            use_llm=use_llm,
            include_duplicates=include_dupes,
        )
    st.success(
        f"完成：status={summary.status}, events={summary.events_created}, "
        f"claims={summary.claims_created}, errors={len(summary.errors)}"
    )
    if summary.errors:
        st.warning("\n".join(summary.errors[:10]))

status_filter = st.selectbox(
    "主张核验状态过�?,
    ["全部", "unreviewed", "confirmed", "corrected", "rejected"],
)

with get_connection() as conn:
    repo = AnalysisRepository(conn)
    stats = repo.overview_analysis_stats()
    events = repo.list_events(limit=100)
    review = None if status_filter == "全部" else status_filter
    claims = repo.list_claims_with_evidence(review_status=review, limit=200)

st.subheader("分析规模")
c1, c2, c3, c4 = st.columns(4)
c1.metric("分析运行", stats["analysis_runs"])
c2.metric("事件", stats["events"])
c3.metric("主张", stats["claims"])
c4.metric("未核验主�?, stats["unreviewed_claims"])

st.subheader("事件列表")
st.dataframe(events, width="stretch")

st.subheader("主张与证�?)
if not claims:
    st.info("暂无主张。请先导入数据并点击「运行分析」�?)
else:
    for claim in claims:
        badge = claim["review_status"]
        header = (
            f"[{badge}] {claim['claim_type']} = {claim['claim_value']} "
            f"| doc={claim['document_title'] or claim['document_id'][:8]}"
        )
        with st.expander(header):
            st.write(
                {
                    "claim_id": claim["claim_id"],
                    "document_id": claim["document_id"],
                    "source_name": claim["source_name"],
                    "original_url": claim["original_url"],
                    "published_at": claim["published_at"],
                    "confidence": claim["confidence"],
                    "is_inference": bool(claim["is_inference"]),
                    "created_by": claim["created_by"],
                    "polarity": claim["polarity"],
                }
            )
            st.markdown("**证据摘录**")
            for ev in claim.get("evidence") or []:
                st.code(ev["excerpt"])
                st.caption(
                    f"document_id={ev['document_id']} "
                    f"span=({ev.get('char_start')}, {ev.get('char_end')})"
                )

            action = st.selectbox(
                "人工核验动作",
                ["confirm", "correct", "reject"],
                key=f"action_{claim['claim_id']}",
            )
            new_value = st.text_input(
                "纠正后的主张值（correct 时填写）",
                value=claim["claim_value"],
                key=f"val_{claim['claim_id']}",
            )
            note = st.text_input("备注", key=f"note_{claim['claim_id']}")
            if st.button("提交核验", key=f"btn_{claim['claim_id']}"):
                with get_connection() as conn:
                    AnalysisRepository(conn).apply_review(
                        target_type="claim",
                        target_id=claim["claim_id"],
                        action=action,
                        new_value=new_value if action == "correct" else None,
                        note=note or None,
                    )
                    conn.commit()
                st.success("已记录人工核�?)
                st.rerun()
