"""Public product: upload or collect → keywords → report only."""

from __future__ import annotations

import sys
import tempfile
import uuid
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import pandas as pd
import streamlit as st

from insight_engine.collectors.registry import list_collector_cards
from insight_engine.db.connection import initialize_database
from insight_engine.product.pipeline import DEFAULT_BRIEF, PublicAnalysisService
from insight_engine.ui.theme import PUBLIC_CSS

st.set_page_config(
    page_title="宠物祈福活动洞察",
    page_icon="◆",
    layout="centered",
    initial_sidebar_state="collapsed",
)

initialize_database()
st.markdown(PUBLIC_CSS, unsafe_allow_html=True)

if "anonymous_id" not in st.session_state:
    st.session_state.anonymous_id = str(uuid.uuid4())

st.markdown("## 活动洞察报告")
st.markdown(
    '<p class="muted">面向非专业人士的极简分析：选择数据来源 → 填写关键词 → 阅读完整报告。'
    "中间技术过程已隐藏。分析完成后原文会立即清除，仅保留结构化成果。</p>",
    unsafe_allow_html=True,
)

with st.container():
    st.markdown('<div class="hero-card">', unsafe_allow_html=True)
    mode = st.radio(
        "数据来源",
        options=["upload", "collect"],
        format_func=lambda x: "批量上传文件" if x == "upload" else "合规网络采集（RSS / 预留平台）",
        horizontal=True,
    )

    uploaded = None
    collector_ids: list[str] = []
    if mode == "upload":
        uploaded = st.file_uploader(
            "上传 CSV / JSON / TXT（可多选）",
            type=["csv", "json", "txt", "md"],
            accept_multiple_files=True,
        )
    else:
        cards = list_collector_cards()
        available = [c for c in cards if c["available"]]
        stubs = [c for c in cards if not c["available"]]
        default_ids = [c["id"] for c in available if c["enabled_by_default"]]
        collector_ids = st.multiselect(
            "选择采集源",
            options=[c["id"] for c in cards],
            default=default_ids,
            format_func=lambda i: next(c["name"] for c in cards if c["id"] == i),
        )
        if stubs:
            st.caption(
                "以下平台适配器已预留，需官方/授权 API 后启用："
                + "、".join(c["name"] for c in stubs)
            )

    keywords_raw = st.text_input(
        "检索关键词（多个用逗号或空格分隔）",
        value="宠物毛发,祈福,编织,福袋,纪念",
    )
    brief = st.text_area("研究说明（可改）", value=DEFAULT_BRIEF, height=140)

    with st.expander("高级：模型设置（可选）"):
        use_llm = st.checkbox("启用大模型增强分析（默认尝试本机/自部署接口）", value=False)
        llm_base = st.text_input("模型 Base URL", value="http://127.0.0.1:11434/v1")
        llm_model = st.text_input("模型名", value="qwen2.5:7b")
        llm_key = st.text_input(
            "可选：自有 API Key（仅本次会话使用，不写入代码仓库）",
            type="password",
            value="",
        )
        st.caption("不填 Key 时默认走自部署地址；关闭开关则仅用规则统计分析。")

    run = st.button("生成分析报告", type="primary", use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)


def _split_keywords(text: str) -> list[str]:
    parts = []
    for chunk in text.replace("，", ",").replace(" ", ",").split(","):
        c = chunk.strip()
        if c:
            parts.append(c)
    return parts


if run:
    keywords = _split_keywords(keywords_raw)
    paths: list[Path] = []
    tmp_dir = None
    try:
        if mode == "upload":
            if not uploaded:
                st.error("请先上传文件")
                st.stop()
            tmp_dir = Path(tempfile.mkdtemp(prefix="insight_up_"))
            for f in uploaded:
                p = tmp_dir / f.name
                p.write_bytes(f.getvalue())
                paths.append(p)

        with st.spinner("正在分析，请稍候…"):
            result = PublicAnalysisService().run(
                mode=mode,
                keywords=keywords,
                research_brief=brief,
                upload_paths=paths or None,
                collector_ids=collector_ids or None,
                anonymous_id=st.session_state.anonymous_id,
                llm_api_key=llm_key or None,
                llm_base_url=llm_base or None,
                llm_model=llm_model or None,
                use_llm=use_llm,
            )
        st.session_state["last_report"] = result
    except Exception as exc:  # noqa: BLE001
        st.error(str(exc))
        st.stop()
    finally:
        if tmp_dir and tmp_dir.exists():
            for p in tmp_dir.glob("*"):
                p.unlink(missing_ok=True)
            tmp_dir.rmdir()

result = st.session_state.get("last_report")
if result:
    if result.get("status") == "empty":
        st.warning(result.get("message"))
        with st.expander("采集说明"):
            for n in result.get("ingest_notes") or []:
                st.write(n)
    elif result.get("report"):
        narrative = result["report"].get("public_narrative") or {}
        st.success("报告已生成（原文已按策略清除）")
        st.markdown(f"### {narrative.get('one_liner', '分析结果')}")
        st.caption(narrative.get("disclaimer", ""))

        stats = narrative.get("stats") or {}
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("原始样本", stats.get("raw_documents") or 0)
        c2.metric("去重后", stats.get("unique_documents") or 0)
        c3.metric("独立来源", stats.get("independent_sources") or 0)
        c4.metric("独立事件", stats.get("independent_events") or 0)

        st.markdown("#### 程度定位（数据档位）")
        st.info(narrative.get("degree_positioning", ""))

        left, right = st.columns(2)
        with left:
            st.markdown("#### 行为阶段分布")
            behavior = stats.get("behavior_stage_counts") or {}
            if behavior:
                st.bar_chart(pd.Series(behavior, name="数量"))
            else:
                st.caption("暂无行为阶段数据")
            st.markdown("#### 需求类型")
            subtype = stats.get("demand_subtype_counts") or {}
            if subtype:
                st.bar_chart(pd.Series(subtype, name="数量"))
        with right:
            st.markdown("#### 正反声音")
            stance = stats.get("stance_counts") or {}
            if stance:
                st.bar_chart(pd.Series(stance, name="数量"))
            st.markdown("#### 价格区间")
            buckets = stats.get("price_buckets") or {}
            if buckets:
                st.bar_chart(pd.Series(buckets, name="数量"))
            elif stats.get("price_values"):
                st.write("价格样本：", stats.get("price_values"))
            else:
                st.caption("样本中未抽取到明确价格")

        st.markdown("#### 关注点提示")
        for a in narrative.get("alerts") or []:
            st.markdown(f"- **{a.get('title')}** — {a.get('reason')}")

        for w in narrative.get("warnings") or []:
            st.caption(f"注意：{w}")

        md_path = (result.get("report_paths") or {}).get("markdown")
        if md_path and Path(md_path).exists():
            st.download_button(
                "下载完整 Markdown 报告",
                data=Path(md_path).read_text(encoding="utf-8"),
                file_name="insight_report.md",
                use_container_width=True,
            )

st.markdown("---")
st.caption("管理归档请使用管理端：streamlit run src/insight_engine/ui/admin_app.py")
