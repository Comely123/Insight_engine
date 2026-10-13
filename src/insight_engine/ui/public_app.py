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
from insight_engine.llm.presets import PRESETS, preset_by_id
from insight_engine.ops.secrets_store import SecretsStore
from insight_engine.product.narrative import narrative_to_markdown
from insight_engine.product.pipeline import PublicAnalysisService
from insight_engine.ui.charts import render_distribution
from insight_engine.ui.theme import PUBLIC_CSS

st.set_page_config(
    page_title="活动洞察",
    page_icon=":material/insights:",
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
    narrative = report.get("public_narrative") or {}
    public_path = (result.get("report_paths") or {}).get("public_markdown")
    if public_path and Path(public_path).exists():
        return Path(public_path).read_text(encoding="utf-8")
    if narrative:
        return narrative_to_markdown(narrative)
    return "# 分析报告\n"


def page_collect() -> None:
    st.markdown("## 数据采集")

    mode = st.radio(
        "数据来源",
        options=["upload", "collect"],
        format_func=lambda x: "批量上传文件" if x == "upload" else "公开网络采集",
        horizontal=True,
        label_visibility="collapsed",
    )

    uploaded = None
    collector_ids: list[str] = []
    if mode == "upload":
        uploaded = st.file_uploader(
            "上传文件（文字 / PDF 文献 / 音频 / 视频，可多选）",
            type=[
                "csv",
                "json",
                "txt",
                "md",
                "log",
                "pdf",
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
        "检索关键词（多个用逗号分隔；上传文献可留空）",
        value="",
        placeholder="例如：宠物毛发, 祈福",
    )
    brief = st.text_area(
        "研究说明",
        value="",
        height=100,
        placeholder="可选：说明你想关注的问题、市场范围或文献分析目标",
    )

    store = SecretsStore()
    saved_provider = store.get_pref("llm.provider", "rules") or "rules"
    provider_ids = [p.id for p in PRESETS]
    try:
        default_idx = provider_ids.index(saved_provider)
    except ValueError:
        default_idx = 0

    with st.expander("模型设置", expanded=False):
        provider = st.selectbox(
            "分析模型",
            options=provider_ids,
            format_func=lambda i: next(p.label for p in PRESETS if p.id == i),
            index=default_idx,
        )
        preset = preset_by_id(provider)
        assert preset is not None
        saved = store.load_llm_settings(provider)
        use_llm = provider != "rules"
        llm_base = saved.get("base_url") or preset.base_url
        llm_model = saved.get("model") or (preset.models[0] if preset.models else "")
        llm_key_input = ""
        clear_key = False

        if use_llm:
            if provider in {"custom", "local", "doubao"}:
                llm_base = st.text_input("Base URL", value=llm_base or "")
            if provider == "custom":
                llm_model = st.text_input("模型名", value=llm_model or "")
            elif provider == "doubao":
                llm_model = st.text_input(
                    "方舟推理接入点 / 模型 ID",
                    value=llm_model or "",
                    placeholder="ep-xxxxxxxx 或控制台给出的模型名",
                )
            elif preset.models:
                choices = list(preset.models) + ["（手动输入）"]
                if llm_model in choices:
                    m_idx = choices.index(llm_model)
                else:
                    m_idx = len(choices) - 1
                picked = st.selectbox("模型", choices, index=m_idx)
                if picked == "（手动输入）":
                    llm_model = st.text_input(
                        "自定义模型名",
                        value=llm_model if llm_model not in preset.models else preset.models[0],
                    )
                else:
                    llm_model = picked
            if preset.note:
                st.caption(preset.note)
            if preset.needs_key or provider == "local":
                if saved.get("has_api_key"):
                    st.caption("已保存加密 API Key（数据库密文存储）。留空沿用；填写则更新。")
                default_key = "local" if provider == "local" and not saved.get("has_api_key") else ""
                llm_key_input = st.text_input(
                    "API Key",
                    type="password",
                    value=default_key,
                    placeholder="已保存则留空" if saved.get("has_api_key") else "粘贴后分析时自动加密保存",
                )
                clear_key = st.checkbox("清除该模型已保存的 API Key", value=False)

    if st.button("开始分析", type="primary", width="stretch"):
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
            elif not keywords:
                st.error("网络采集请填写关键词")
                st.stop()

            if clear_key and use_llm:
                store.delete_secret(store.llm_secret_key(provider))

            resolved_key = (llm_key_input or "").strip()
            if use_llm and not resolved_key:
                resolved_key = store.get_secret(store.llm_secret_key(provider)) or ""
            if use_llm and (preset.needs_key) and not resolved_key:
                st.error("请填写 API Key（或先成功保存过一次）")
                st.stop()

            # Persist provider / model / key (encrypted) on submit
            store.save_llm_settings(
                provider=provider,
                api_key=llm_key_input if (llm_key_input or "").strip() else None,
                model=llm_model,
                base_url=llm_base,
                replace_key=bool((llm_key_input or "").strip()),
            )

            with st.spinner("正在分析…"):
                result = PublicAnalysisService().run(
                    mode=mode,
                    keywords=keywords,
                    research_brief=brief,
                    upload_paths=paths or None,
                    collector_ids=collector_ids or None,
                    anonymous_id=st.session_state.anonymous_id,
                    llm_api_key=resolved_key or None,
                    llm_base_url=llm_base or None,
                    llm_model=llm_model or None,
                    use_llm=use_llm,
                )
            st.session_state["last_report"] = result
            if result.get("status") == "empty":
                st.warning(result.get("message"))
            else:
                st.success("完成。请打开左侧「分析报告」。")
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
        return

    if not result.get("report"):
        st.warning("报告数据不完整，请重新生成。")
        return

    narrative = result["report"].get("public_narrative") or {}
    st.markdown(f"### {narrative.get('one_liner', '分析结果')}")

    stats = narrative.get("stats") or {}
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("原始样本", stats.get("raw_documents") or 0)
    c2.metric("去重后", stats.get("unique_documents") or 0)
    c3.metric("独立来源", stats.get("independent_sources") or 0)
    c4.metric("独立事件", stats.get("independent_events") or 0)

    st.markdown("#### 程度定位")
    st.info(narrative.get("degree_positioning", ""))

    st.markdown("#### 主要发现")
    for x in narrative.get("findings") or []:
        st.markdown(f"- {x}")

    st.markdown("#### 参考建议")
    for x in narrative.get("recommendations") or []:
        st.markdown(f"- {x}")

    lit = narrative.get("literature_commonality") or []
    if lit:
        st.markdown("#### 文献 / 样本共性")
        for x in lit:
            st.markdown(f"- {x}")

    left, right = st.columns(2)
    with left:
        render_distribution(
            stats.get("behavior_stage_counts"),
            title="行为阶段",
            kind="hbar",
            alt_text="行为阶段分布",
        )
        render_distribution(
            stats.get("demand_subtype_counts"),
            title="需求类型",
            kind="donut",
            alt_text="需求类型分布",
        )
    with right:
        render_distribution(
            stats.get("stance_counts"),
            title="正反声音",
            kind="donut",
            alt_text="正反声音分布",
        )
        render_distribution(
            stats.get("price_buckets"),
            title="价格区间",
            kind="area",
            alt_text="价格区间分布",
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
            pdf_bytes = markdown_to_pdf_bytes(md_text, title="分析报告")
            st.download_button(
                "导出 PDF",
                data=pdf_bytes,
                file_name="insight_report.pdf",
                mime="application/pdf",
                width="stretch",
            )
        except Exception as exc:  # noqa: BLE001
            st.error(f"PDF 导出失败：{exc}")


nav = st.navigation(
    [
        st.Page(page_collect, title="数据采集", icon=":material/upload_file:", default=True),
        st.Page(page_report, title="分析报告", icon=":material/description:"),
    ],
    position="sidebar",
)
nav.run()
