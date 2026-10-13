"""统一研究工作台：项目配置、检索、趋势、预警、报告。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[3]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import pandas as pd
import streamlit as st

from insight_engine.db.connection import get_connection, initialize_database
from insight_engine.db.research_repository import ResearchRepository
from insight_engine.research.service import ResearchWorkbenchService

st.set_page_config(page_title="研究工作台 · Insight Engine", layout="wide")
initialize_database()

st.title("研究工作台")
st.caption(
    "研究项目 · 关键词版本 · 统一检索 · 可解释趋势 · 规则预警 · 引用式报告。"
    "预警含义是「值得进一步研究」，不是市场爆发断言。"
)

tab_proj, tab_run, tab_alerts = st.tabs(["项目与关键词", "运行分析/报告", "预警核验"])

with tab_proj:
    st.subheader("创建研究项目")
    name = st.text_input("研究名称", value="中国宠物毛发祈福/纪念物探索")
    question = st.text_area(
        "研究问题",
        value="活体祈福编织需求与离世纪念需求分别如何分布？价格与意向证据是否可追溯？",
    )
    market = st.text_input("目标市场", value="中国消费市场")
    geo = st.text_input("地理范围", value="中国")
    c1, c2 = st.columns(2)
    time_start = c1.text_input("时间起 (ISO)", value="2025-01-01")
    time_end = c2.text_input("时间止 (ISO)", value="2026-12-31")
    keywords = st.text_input("关键词（逗号分隔）", value="祈福,编织,手绳,毛发,纪念")
    synonyms = st.text_input("同义词（逗号分隔）", value="平安结,纪念品")
    excludes = st.text_input("排除词（逗号分隔）", value="")

    if st.button("创建项目并保存关键词 v1", type="primary"):
        with get_connection() as conn:
            result = ResearchWorkbenchService(conn).create_project(
                name=name,
                research_question=question,
                target_market=market,
                geo_scope=geo,
                time_start=time_start or None,
                time_end=time_end or None,
                keywords=[x.strip() for x in keywords.split(",") if x.strip()],
                synonyms=[x.strip() for x in synonyms.split(",") if x.strip()],
                exclude_keywords=[x.strip() for x in excludes.split(",") if x.strip()],
                change_note="initial via UI",
            )
        st.success(f"已创建 project_id={result['project_id']}")

    with get_connection() as conn:
        projects = ResearchRepository(conn).list_projects()
    st.subheader("已有项目")
    st.dataframe(projects, width="stretch")

    if projects:
        pid = st.selectbox("选择项目以新增关键词版本", [p["project_id"] for p in projects])
        with get_connection() as conn:
            versions = ResearchRepository(conn).list_keyword_versions(pid)
        st.write("关键词版本历史（不可静默覆盖）")
        st.dataframe(versions, width="stretch")
        nk = st.text_input("新关键词", value=keywords, key="nk")
        ns = st.text_input("新同义词", value=synonyms, key="ns")
        ne = st.text_input("新排除词", value=excludes, key="ne")
        note = st.text_input("变更说明（必填建议）", value="调整筛选范围")
        if st.button("提交新关键词版本"):
            with get_connection() as conn:
                v = ResearchWorkbenchService(conn).add_keyword_version(
                    pid,
                    keywords=[x.strip() for x in nk.split(",") if x.strip()],
                    synonyms=[x.strip() for x in ns.split(",") if x.strip()],
                    exclude_keywords=[x.strip() for x in ne.split(",") if x.strip()],
                    change_note=note,
                )
            st.success(f"已保存 v{v['version_number']}")
            st.rerun()

with tab_run:
    with get_connection() as conn:
        projects = ResearchRepository(conn).list_projects()
    if not projects:
        st.info("请先创建研究项目。")
    else:
        pid = st.selectbox(
            "运行项目",
            [p["project_id"] for p in projects],
            format_func=lambda x: next(
                (p["name"] + " / " + p["project_id"][:8] for p in projects if p["project_id"] == x),
                x,
            ),
        )
        window = st.selectbox("窗口（日）", [7, 30, 90], index=1)
        with get_connection() as conn:
            docs = ResearchWorkbenchService(conn).search_project_documents(pid)
        st.write(f"当前关键词版本匹配文档：{len(docs)}")
        if docs:
            st.dataframe(pd.DataFrame(docs)[
                [c for c in ["document_id", "title", "source_name", "published_at", "content_type"] if c in pd.DataFrame(docs).columns]
            ], width="stretch")

        if st.button("运行趋势 + 预警 + 导出报告", type="primary"):
            with get_connection() as conn:
                result = ResearchWorkbenchService(conn).run_project(
                    pid, window_days=int(window), export=True
                )
            st.success(
                f"完成 run_id={result['run_id']} docs={result['document_count']} "
                f"alerts={len(result['alerts'])}"
            )
            trend = result["trend"]
            st.subheader("趋势（绝对数量）")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("原始文档", trend["raw_documents"])
            m2.metric("去重文档", trend["unique_documents"])
            m3.metric("独立来源", trend["independent_sources"])
            m4.metric("独立事件", trend["independent_events"])
            st.write(
                {
                    "growth_rate": trend.get("growth_rate"),
                    "behavior_stage_counts": trend.get("behavior_stage_counts"),
                    "demand_subtype_counts": trend.get("demand_subtype_counts"),
                    "confirmed_market_trend": trend.get("confirmed_market_trend"),
                }
            )
            for w in trend.get("warnings") or []:
                st.warning(w)
            if trend.get("behavior_stage_counts"):
                st.bar_chart(pd.Series(trend["behavior_stage_counts"], name="count"))
            if trend.get("demand_subtype_counts"):
                st.bar_chart(pd.Series(trend["demand_subtype_counts"], name="subtype"))

            st.subheader("正反证据（报告摘录）")
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**正向**")
                st.json(result["report"].get("positive_evidence") or [])
            with c2:
                st.markdown("**反向**")
                st.json(result["report"].get("negative_evidence") or [])

            cite = result["report"].get("citation_validation") or {}
            if cite.get("ok"):
                st.success("引用校验通过")
            else:
                st.error("引用校验失败")
                st.write(cite.get("errors"))
            if result.get("report_path"):
                st.info(f"Markdown 报告：{result['report_path']}")
                md = Path(result["report_path"])
                if md.exists():
                    st.download_button("下载 Markdown", md.read_text(encoding="utf-8"), file_name=md.name)
                    jp = md.with_suffix(".json")
                    if jp.exists():
                        st.download_button("下载 JSON", jp.read_text(encoding="utf-8"), file_name=jp.name)

            with st.expander("指标定义"):
                st.json(trend.get("definitions") or {})
            with st.expander("完整报告 JSON"):
                st.json(result["report"])

with tab_alerts:
    with get_connection() as conn:
        projects = ResearchRepository(conn).list_projects()
        pid = None
        if projects:
            pid = st.selectbox(
                "项目",
                [p["project_id"] for p in projects],
                key="alert_pid",
            )
            alerts = ResearchRepository(conn).list_alerts(pid)
        else:
            alerts = []
    if not alerts:
        st.info("暂无预警。请先运行项目分析。")
    for alert in alerts:
        with st.expander(f"[{alert['review_status']}] {alert['severity']} · {alert['title']}"):
            st.write(
                {
                    "trigger_reason": alert["trigger_reason"],
                    "metric_values": alert["metric_values"],
                    "compare_window_days": alert["compare_window_days"],
                    "sample_size": alert["sample_size"],
                    "quality_notes": alert["quality_notes"],
                    "review_suggestion": alert["review_suggestion"],
                }
            )
            st.markdown("**支持证据**")
            st.json(alert.get("supporting_evidence") or [])
            st.markdown("**反向证据**")
            st.json(alert.get("opposing_evidence") or [])
            act = st.selectbox(
                "核验",
                ["confirmed", "dismissed", "unreviewed"],
                key=f"al_{alert['alert_id']}",
            )
            note = st.text_input("备注", key=f"aln_{alert['alert_id']}")
            if st.button("提交预警核验", key=f"alb_{alert['alert_id']}"):
                with get_connection() as conn:
                    ResearchWorkbenchService(conn).review_alert(
                        alert["alert_id"], act, note=note or None
                    )
                st.success("已记录")
                st.rerun()
