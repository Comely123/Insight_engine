"""Public product: two pages only — 数据采集 / 分析报告."""

from __future__ import annotations

import sys
import tempfile
import uuid
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import streamlit as st

from insight_engine.collectors.registry import list_collector_cards
from insight_engine.db.connection import initialize_database
from insight_engine.export.pdf_report import markdown_to_pdf_bytes
from insight_engine.product.pipeline import DEFAULT_BRIEF, PublicAnalysisService
from insight_engine.reports.builder import render_markdown
from insight_engine.ui.charts import macaron_bar
from insight_engine.ui.theme import PUBLIC_CSS

st.set_page_config(
    page_title="活动洞察",
    page_icon="◆",
    layout="centered",
    initial_sidebar_state="expanded",
)

initialize_database()
st.markdown(PUBLIC_CSS, unsafe_allow_html=True)

if "anonymous_id" not in st.session_state:
    st.session_state.anonymous_id = str(uuid.uuid4())


def _split_keywords(text: str) -> list[str]:
    parts = []
    for chunk in text.replace("，", ",").replace(" ", ",").split(","):
        c = chunk.strip()
        if c:
            parts.append(c)
    return parts


def _report_markdown(result: dict) -> str:
    report = result.get("report") or {}
    md_path = (result.get("report_paths") or {}).get("markdown")
    if md_path and Path(md_path).exists():
        return Path(md_path).read_text(encoding="utf-8")
    if report:
        try:
            return render_markdown(report)
        except Exception:  # noqa: BLE001
            pass
    narrative = report.get("public_narrative") or {}
    return "\n".join(
        [
            f"# {narrative.get('one_liner', '分析报告')}",
            "",
            narrative.get("degree_positioning", ""),
            "",
            narrative.get("disclaimer", ""),
        ]
    )


def page_collect() -> None:
    st.markdown("## 数据采集")
    st.markdown(
        '<p class="muted">上传文件，或使用当前已开放的公开资讯源按关键词采集。'
        "分析完成后原文会立即清除。</p>",
        unsafe_allow_html=True,
    )

    mode = st.radio(
        "数据来源",
        options=["upload", "collect"],
        format_func=lambda x: "批量上传文件" if x == "upload" else "公开网络采集",
        horizontal=True,
    )

    uploaded = None
    collector_ids: list[str] = []
    if mode == "upload":
        uploaded = st.file_uploader(
            "上传文件（可多选：文字 / 音频 / 视频）",
            type=[
                "csv",
                "json",
                "txt",
                "md",
                "log",
                "srt",
                "vtt",
                "mp4",
                "mov",
                "mkv",
                "webm",
                "mp3",
                "wav",
                "m4a",
                "aac",
                "flac",
                "ogg",
            ],
            accept_multiple_files=True,
        )
    else:
        cards = list_collector_cards(available_only=True)
        if not cards:
            st.error("当前没有可用的采集源")
            return
        default_ids = [c["id"] for c in cards if c["enabled_by_default"]] or [cards[0]["id"]]
        collector_ids = st.multiselect(
            "采集源",
            options=[c["id"] for c in cards],
            default=default_ids,
            format_func=lambda i: next(c["name"] for c in cards if c["id"] == i),
        )

    keywords_raw = st.text_input(
        "检索关键词（多个用逗号分隔）",
        value="宠物毛发,祈福,编织,福袋,纪念",
    )
    brief = st.text_area("研究说明（可改）", value=DEFAULT_BRIEF, height=120)

    with st.expander("模型设置（可选）"):
        provider = st.selectbox(
            "分析模型",
            options=["rules", "deepseek", "local", "custom"],
            format_func=lambda x: {
                "rules": "仅规则统计（不调用大模型）",
                "deepseek": "DeepSeek API",
                "local": "本机/自部署 OpenAI 兼容接口",
                "custom": "自定义 OpenAI 兼容接口",
            }[x],
            index=0,
        )
        use_llm = provider != "rules"
        llm_base = "https://api.deepseek.com/v1"
        llm_model = "deepseek-chat"
        if provider == "local":
            llm_base = st.text_input("Base URL", value="http://127.0.0.1:11434/v1")
            llm_model = st.text_input("模型名", value="qwen2.5:7b")
        elif provider == "custom":
            llm_base = st.text_input("Base URL", value="https://api.deepseek.com/v1")
            llm_model = st.text_input("模型名", value="deepseek-chat")
        elif provider == "deepseek":
            llm_base = "https://api.deepseek.com/v1"
            llm_model = "deepseek-chat"
        llm_key = ""
        if use_llm and provider != "local":
            llm_key = st.text_input("API Key（仅本次会话）", type="password", value="")
        elif provider == "local":
            llm_key = st.text_input("可选本地 Key", type="password", value="local")

    if st.button("采集并生成报告", type="primary", width="stretch"):
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
            elif not collector_ids:
                st.error("请至少选择一个采集源")
                st.stop()

            with st.spinner("正在采集与分析…"):
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
            if result.get("status") == "empty":
                st.warning(result.get("message"))
                for n in result.get("ingest_notes") or []:
                    st.caption(n)
            else:
                st.success("完成。请打开左侧「分析报告」查看与导出。")
        except Exception as exc:  # noqa: BLE001
            st.error(str(exc))
        finally:
            if tmp_dir and tmp_dir.exists():
                for p in tmp_dir.glob("*"):
                    p.unlink(missing_ok=True)
                try:
                    tmp_dir.rmdir()
                except OSError:
                    pass


def page_report() -> None:
    st.markdown("## 分析报告")
    result = st.session_state.get("last_report")
    if not result:
        st.info("还没有报告。请先到「数据采集」上传或采集后生成。")
        return

    if result.get("status") == "empty":
        st.warning(result.get("message") or "未采集到数据")
        for n in result.get("ingest_notes") or []:
            st.caption(n)
        return

    if not result.get("report"):
        st.warning("报告数据不完整，请重新生成。")
        return

    narrative = result["report"].get("public_narrative") or {}
    st.markdown(f"### {narrative.get('one_liner', '分析结果')}")
    st.caption(narrative.get("disclaimer", ""))

    stats = narrative.get("stats") or {}
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("原始样本", stats.get("raw_documents") or 0)
    c2.metric("去重后", stats.get("unique_documents") or 0)
    c3.metric("独立来源", stats.get("independent_sources") or 0)
    c4.metric("独立事件", stats.get("independent_events") or 0)

    st.markdown("#### 程度定位")
    st.info(narrative.get("degree_positioning", ""))

    left, right = st.columns(2)
    with left:
        macaron_bar(
            stats.get("behavior_stage_counts"),
            title="行为阶段",
            alt_text="行为阶段分布柱状图",
        )
        macaron_bar(
            stats.get("demand_subtype_counts"),
            title="需求类型",
            alt_text="需求类型分布柱状图",
        )
    with right:
        macaron_bar(
            stats.get("stance_counts"),
            title="正反声音",
            alt_text="正反声音分布柱状图",
        )
        macaron_bar(
            stats.get("price_buckets"),
            title="价格区间",
            alt_text="价格区间分布柱状图",
        )

    for a in narrative.get("alerts") or []:
        st.markdown(f"- **{a.get('title')}** — {a.get('reason')}")

    md_text = _report_markdown(result)
    d1, d2 = st.columns(2)
    with d1:
        st.download_button(
            "导出 Markdown",
            data=md_text,
            file_name="insight_report.md",
            mime="text/markdown",
            width="stretch",
        )
    with d2:
        try:
            pdf_bytes = markdown_to_pdf_bytes(md_text, title="活动洞察报告")
            st.download_button(
                "导出 PDF",
                data=pdf_bytes,
                file_name="insight_report.pdf",
                mime="application/pdf",
                width="stretch",
            )
        except Exception as exc:  # noqa: BLE001
            st.error(f"PDF 导出失败：{exc}")


# Two-page nav only (workbench multipage lives under ui/workbench/)
nav = st.navigation(
    [
        st.Page(page_collect, title="数据采集", icon=":material/upload_file:", default=True),
        st.Page(page_report, title="分析报告", icon=":material/description:"),
    ],
    position="sidebar",
)
nav.run()
