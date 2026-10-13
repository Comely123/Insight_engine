"""Public product: two pages — 数据采集 / 分析报告 (async jobs)."""

from __future__ import annotations

import math
import sys
import time
import uuid
from datetime import timedelta
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import streamlit as st

from insight_engine.collectors.registry import list_collector_cards
from insight_engine.collectors.source_credentials import (
    CONTACT_EMAIL_PREF,
    SOURCE_CREDENTIALS,
)
from insight_engine.db.connection import initialize_database
from insight_engine.export.pdf_report import report_to_pdf_bytes
from insight_engine.llm.presets import PRESETS, preset_by_id
from insight_engine.ops.secrets_store import SecretsStore
from insight_engine.product.job_runner import latest_job, submit_public_analysis
from insight_engine.product.narrative import narrative_to_markdown
from insight_engine.product.uploads import UPLOADER_TYPES
from insight_engine.ui.charts import pick_report_chart_slots, render_distribution
from insight_engine.ui.theme import PUBLIC_CSS

st.set_page_config(
    page_title="活动洞察",
    page_icon=":material/insights:",
    layout="centered",
    initial_sidebar_state="collapsed",
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


def _job_progress_value(job: dict) -> float:
    """
    Display progress that never goes backwards.

    Backend stage progress is the floor. While a stage is slow (e.g. ASR),
    creep a little forward only — no sine pulse (that used to make the bar retreat).
    """
    base = float(job.get("progress") or 0.0)
    status = job.get("status")
    job_id = str(job.get("job_id") or "")
    if status == "queued":
        base = max(base, 0.03)
    elif status == "running":
        base = max(base, 0.06)
    elif status in {"succeeded", "empty"}:
        if job_id:
            st.session_state.pop(f"_prog_hw_{job_id}", None)
            st.session_state.pop(f"_prog_base_{job_id}", None)
            st.session_state.pop(f"_prog_creep_{job_id}", None)
        return 1.0

    hw_key = f"_prog_hw_{job_id}"
    base_key = f"_prog_base_{job_id}"
    creep_key = f"_prog_creep_{job_id}"
    hw = float(st.session_state.get(hw_key) or 0.0)

    if status in {"queued", "running"} and base < 0.97:
        # Reset creep when backend stage advances; ease forward up to +3% of stage.
        rounded = round(base, 4)
        if st.session_state.get(base_key) != rounded:
            st.session_state[base_key] = rounded
            st.session_state[creep_key] = time.time()
        started = float(st.session_state.get(creep_key) or time.time())
        elapsed = max(0.0, time.time() - started)
        creep = min(0.03, 0.03 * (1.0 - math.exp(-elapsed / 14.0)))
        shown = max(hw, min(0.98, base + creep))
    else:
        shown = max(hw, base)

    st.session_state[hw_key] = shown
    return shown


def _sync_finished_job_once(job: dict) -> bool:
    """
    Persist finished job into session_state at most once per job_id.
    Returns True only on the first sync (caller may trigger one full-app rerun).
    """
    jid = str(job.get("job_id") or "")
    if not jid:
        return False
    if st.session_state.get("synced_job_id") == jid:
        return False
    st.session_state["synced_job_id"] = jid
    st.session_state["job_id"] = jid
    st.session_state.pop("awaiting_job", None)
    if job.get("result") is not None:
        st.session_state["last_report"] = job["result"]
    return True


def _live_job_panel_impl(anonymous_id: str, *, compact: bool) -> None:
    """Progress UI. Never loop full-app reruns — that blanked pages on navigation."""
    job = latest_job(anonymous_id)
    if not job:
        return
    status = job["status"]
    if status in {"queued", "running"}:
        msg = job.get("message") or ("排队中…" if status == "queued" else "处理中…")
        pct = _job_progress_value(job)
        if not compact:
            st.caption(f"任务 {job['job_id'][:8]}… · {status} · {pct:.0%}")
        st.progress(pct, text=msg)
        if compact:
            st.caption("可随时切换到「分析报告」查看进度；完成后结果会自动出现。")
        return
    if status == "failed":
        if st.session_state.get("job_id") == job["job_id"] or st.session_state.get(
            "awaiting_job"
        ):
            st.error(job.get("error_message") or job.get("message") or "任务失败")
            st.session_state.pop("awaiting_job", None)
        return
    if status in {"succeeded", "empty"}:
        first_sync = _sync_finished_job_once(job)
        if compact:
            # Collect page: update session only — do NOT st.rerun() (keeps form widgets alive)
            st.success("分析已完成。打开「分析报告」查看结果；本页可继续提交新任务。")
            return
        # Report page: one full-app rerun so results render outside this fragment
        if first_sync:
            st.rerun()
        return


@st.fragment(run_every=timedelta(milliseconds=500), key="collect_job_panel")
def _live_job_panel_collect(anonymous_id: str) -> None:
    _live_job_panel_impl(anonymous_id, compact=True)


@st.fragment(run_every=timedelta(milliseconds=500), key="report_job_panel")
def _live_job_panel_report(anonymous_id: str) -> None:
    _live_job_panel_impl(anonymous_id, compact=False)


def page_collect() -> None:
    # Page title comes from top nav only (no duplicate in-body heading)
    _live_job_panel_collect(st.session_state.anonymous_id)

    mode = st.radio(
        "数据来源",
        options=["upload", "collect"],
        format_func=lambda x: "批量上传文件" if x == "upload" else "公开网络采集",
        horizontal=True,
        label_visibility="collapsed",
        key="collect_mode",
    )

    uploaded = None
    collector_ids: list[str] = []
    key_inputs: dict[str, str] = {}
    clear_source: dict[str, bool] = {}
    contact_email_input = ""
    if mode == "upload":
        uploaded = st.file_uploader(
            "上传文件（文本 / PDF / 代码 / 图片OCR / 压缩包 / 音视频，可多选）",
            type=UPLOADER_TYPES,
            accept_multiple_files=True,
            key="collect_uploads",
            help=(
                "支持 JPG/PNG/SVG 等图片（OCR 提取文字）、zip/tar 解压后分析、"
                "常见源代码，以及文档与音视频。图片 OCR 需本机安装 Tesseract。"
            ),
        )
    else:
        store_early = SecretsStore()
        with st.expander("开放数据源 API Key（免费/自助申请）", expanded=False):
            st.caption(
                "已接入 OpenAlex / Semantic Scholar / Crossref / arXiv / Europe PMC / "
                "PubMed / OpenAIRE；CORE 与 YouTube 需自行申请 Key 后启用。"
                "Key 加密保存在本地库，用法与模型 API Key 相同。"
            )
            contact_email_input = st.text_input(
                "联系邮箱（Crossref / OpenAlex / NCBI 礼仪字段）",
                value=store_early.get_pref(CONTACT_EMAIL_PREF, "") or "",
                placeholder="you@example.com",
                key="collect_contact_email",
            )
            for spec in SOURCE_CREDENTIALS:
                st.markdown(f"**{spec.label}**")
                st.caption(spec.note)
                status = store_early.load_source_key_status(spec.id)
                if status["has_api_key"]:
                    st.caption("已保存加密 Key。留空沿用；填写则更新。")
                key_inputs[spec.id] = st.text_input(
                    f"{spec.label} API Key",
                    type="password",
                    value="",
                    key=f"src_key_{spec.id}",
                    placeholder="已保存则留空" if status["has_api_key"] else "可选/必填见说明",
                    label_visibility="collapsed",
                )
                clear_source[spec.id] = st.checkbox(
                    f"清除 {spec.label} Key",
                    value=False,
                    key=f"src_clear_{spec.id}",
                )
            if st.button("保存数据源凭证", width="stretch"):
                if contact_email_input.strip():
                    store_early.set_pref(CONTACT_EMAIL_PREF, contact_email_input.strip())
                for spec in SOURCE_CREDENTIALS:
                    if clear_source.get(spec.id):
                        store_early.delete_secret(store_early.source_secret_key(spec.id))
                    elif (key_inputs.get(spec.id) or "").strip():
                        store_early.save_source_api_key(spec.id, key_inputs[spec.id])
                st.success("已保存。若刚填写 CORE / YouTube Key，采集源列表会立即刷新。")
                st.rerun()

        cards = list_collector_cards(available_only=False)
        locked = [c for c in cards if not c["available"]]
        cards = [c for c in cards if c["available"]]
        if locked:
            st.caption(
                "待填写 Key 后可用："
                + "、".join(c["name"] for c in locked)
            )
        if not cards:
            st.error("当前没有可用的采集源")
            return
        default_ids = [c["id"] for c in cards if c["enabled_by_default"]] or [cards[0]["id"]]
        # Keep defaults that still exist after filtering
        default_ids = [i for i in default_ids if i in {c["id"] for c in cards}] or [cards[0]["id"]]
        collector_ids = st.multiselect(
            "采集源",
            options=[c["id"] for c in cards],
            default=default_ids,
            format_func=lambda i: next(c["name"] for c in cards if c["id"] == i),
            key="collect_sources",
        )

    keywords_raw = st.text_input(
        "检索关键词（多个用逗号分隔；上传文献可留空）",
        value="",
        placeholder="例如：宠物毛发, 祈福",
        key="collect_keywords",
    )
    brief = st.text_area(
        "研究说明（分析议程）",
        value="",
        height=120,
        placeholder=(
            "写清你想知道的每一件事（可分条）。"
            "例如：价格区间？付费顾虑？与竞品差异？文献创新点？"
            "引擎会逐条对照样本作答；证据不足会标明缺口。"
            "主题词负责扩大检索范围，研究说明不收缩范围。"
        ),
        key="collect_brief",
        help="研究说明 = 要分析什么；关键词 = 去哪里找。说明越具体，报告覆盖越全。",
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
                    st.caption("已保存加密 API Key。留空沿用；填写则更新。")
                default_key = "local" if provider == "local" and not saved.get("has_api_key") else ""
                llm_key_input = st.text_input(
                    "API Key",
                    type="password",
                    value=default_key,
                    placeholder="已保存则留空" if saved.get("has_api_key") else "粘贴后自动加密保存",
                )
                clear_key = st.checkbox("清除该模型已保存的 API Key", value=False)

    if st.button("开始分析", type="primary", width="stretch"):
        keywords = _split_keywords(keywords_raw)
        try:
            if mode == "upload":
                if not uploaded:
                    st.error("请先上传文件")
                    st.stop()
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
            if use_llm and preset.needs_key and not resolved_key:
                st.error("请填写 API Key（或先成功保存过一次）")
                st.stop()

            store.save_llm_settings(
                provider=provider,
                api_key=llm_key_input if (llm_key_input or "").strip() else None,
                model=llm_model,
                base_url=llm_base,
                replace_key=bool((llm_key_input or "").strip()),
            )

            if mode == "collect":
                if contact_email_input.strip():
                    store.set_pref(CONTACT_EMAIL_PREF, contact_email_input.strip())
                for spec in SOURCE_CREDENTIALS:
                    if clear_source.get(spec.id):
                        store.delete_secret(store.source_secret_key(spec.id))
                    elif (key_inputs.get(spec.id) or "").strip():
                        store.save_source_api_key(spec.id, key_inputs[spec.id])

            upload_files = None
            if mode == "upload" and uploaded:
                upload_files = [(f.name, f.getvalue()) for f in uploaded]

            job_id = submit_public_analysis(
                mode=mode,
                keywords=keywords,
                research_brief=brief,
                collector_ids=collector_ids or None,
                anonymous_id=st.session_state.anonymous_id,
                upload_files=upload_files,
                use_llm=use_llm,
                llm_provider=provider,
                llm_base_url=llm_base or None,
                llm_model=llm_model or None,
            )
            st.session_state["job_id"] = job_id
            st.session_state["awaiting_job"] = True
            st.session_state.pop("last_report", None)
            st.session_state.pop("synced_job_id", None)
            st.success("任务已提交，正在后台运行。可切换到「分析报告」查看进度，离开本页不会中断。")
            st.rerun()
        except Exception as exc:  # noqa: BLE001
            st.error(str(exc))


def _render_result(result: dict) -> None:
    if result.get("status") == "empty":
        st.warning(result.get("message") or "未采集到数据")
        return
    if not result.get("report"):
        st.warning("报告数据不完整，请重新生成。")
        return

    narrative = result["report"].get("public_narrative") or {}
    stats = narrative.get("stats") or {}
    profile = str(
        narrative.get("analysis_profile")
        or stats.get("analysis_profile")
        or "market"
    )
    labels = narrative.get("section_labels") or {}
    profile_zh = {
        "literature": "文献分析",
        "market": "市场趋势",
        "video": "视频分析",
        "mixed": "混合样本",
    }.get(profile, profile)

    st.markdown(f"### {narrative.get('one_liner', '分析结果')}")
    st.caption(f"报告画像：{profile_zh}（随上传/采集内容自动切换，不是固定文献模板）")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("原始样本", stats.get("raw_documents") or 0)
    c2.metric("最终保留", stats.get("unique_documents") or 0)
    c3.metric("采集平台", stats.get("platform_count") or stats.get("independent_sources") or 0)
    c4.metric("域名数", stats.get("domain_count") or 0)
    r_rate = stats.get("retention_rate")
    d_rate = stats.get("dedup_deletion_rate")
    if r_rate is not None or d_rate is not None:
        st.caption(
            f"样本保留率 {float(r_rate or 0):.1%} · 去重删除率 {float(d_rate or 0):.1%}"
            f"（精确重复 {stats.get('duplicate_documents') or 0} 条；保留率≠去重率）"
        )
    pending = stats.get("price_pending_review") or []
    if pending and profile in {"market", "mixed", "video"}:
        with st.expander(f"价格待审核（{len(pending)}，未计入分布）", expanded=False):
            st.dataframe(pending, width="stretch", hide_index=True)

    st.markdown("#### 程度定位")
    st.info(narrative.get("degree_positioning", ""))

    st.markdown("#### 主要发现")
    for x in narrative.get("findings") or []:
        st.markdown(f"- {x}")

    st.markdown("#### 参考建议")
    for x in narrative.get("recommendations") or []:
        st.markdown(f"- {x}")

    brief_cov = narrative.get("brief_coverage") or {}
    if brief_cov.get("coverage_lines"):
        st.markdown("#### 研究说明覆盖")
        st.caption("研究说明决定「要回答什么」；关键词决定「去哪里找」。不会用说明收缩检索。")
        for x in brief_cov["coverage_lines"]:
            st.markdown(f"- {x}")

    if narrative.get("video_summaries") and profile in {"video", "mixed"}:
        st.markdown("#### 视频要点摘要")
        for x in narrative["video_summaries"]:
            st.markdown(f"- {x}")

    if narrative.get("show_batch_sections", True):
        lit = narrative.get("literature_commonality") or []
        if lit:
            st.markdown(f"#### {labels.get('commonality', '样本共性')}")
            for x in lit:
                st.markdown(f"- {x}")
        diffs = narrative.get("literature_differences") or []
        if diffs:
            st.markdown(f"#### {labels.get('differences', '样本差异')}")
            for x in diffs:
                st.markdown(f"- {x}")
        innov = narrative.get("literature_innovations") or []
        if innov and narrative.get("show_innovation_section", profile == "literature"):
            st.markdown(f"#### {labels.get('innovations', '亮点线索')}")
            for x in innov:
                st.markdown(f"- {x}")

        table = narrative.get("literature_table") or []
        st.markdown(f"#### {labels.get('table', '样本对照表')}")
        st.caption(
            "表头随报告画像动态变化（文献 / 市场 / 视频 / 混合）；"
            "含创新点、现状、趋势、可发展方向等深度字段。"
        )
        if table:
            st.dataframe(table, width="stretch", hide_index=True)
        else:
            st.info("本批暂无逐条样本行，仍可下载带表头的空模板 CSV。")
        csv_path = narrative.get("literature_csv") or (
            (result.get("report_paths") or {}).get("literature_csv")
        )
        csv_name = labels.get("csv_name") or "sample_breakdown.csv"
        csv_label = labels.get("csv") or "导出样本对照 CSV"
        if csv_path and Path(str(csv_path)).exists():
            st.download_button(
                csv_label,
                data=Path(str(csv_path)).read_bytes(),
                file_name=csv_name,
                mime="text/csv",
                width="stretch",
            )
        else:
            from insight_engine.product.literature import literature_rows_to_csv

            raw = narrative.get("literature_table_raw") or table
            st.download_button(
                csv_label,
                data=literature_rows_to_csv(raw, profile=profile),
                file_name=csv_name,
                mime="text/csv",
                width="stretch",
            )

    st.caption(
        "报告画像随内容切换：文献→共性/差异/创新；采集/资讯→市场趋势；视频→主题与摘要。"
        "分类三维相互独立；未知/待复核可保留。"
    )
    # 2×2 square: TL 内容类型 | TR 研究相关度 / BL 研究主题 | BR 随画像
    slots = pick_report_chart_slots(stats, profile=profile)
    row1 = st.columns(2, gap="medium")
    row2 = st.columns(2, gap="medium")
    for cell, (title, counts, kind) in zip([*row1, *row2], slots):
        with cell:
            with st.container(border=True):
                render_distribution(
                    counts, title=title, kind=kind, alt_text=title
                )
    conflicts = stats.get("taxonomy_conflict_notes") or []
    if conflicts:
        with st.expander("分类冲突提示（未自动改标）", expanded=False):
            for c in conflicts:
                st.markdown(f"- {c}")

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
            pdf_bytes = report_to_pdf_bytes(
                narrative, title="分析报告", include_charts=True
            )
            st.download_button(
                "导出 PDF（含图，不含 CSV 表）",
                data=pdf_bytes,
                file_name="insight_report.pdf",
                mime="application/pdf",
                width="stretch",
            )
        except Exception as exc:  # noqa: BLE001
            st.error(f"PDF 导出失败：{exc}")


def page_report() -> None:
    # Page title comes from top nav only (no duplicate in-body heading)
    job = latest_job(st.session_state.anonymous_id)
    if not job:
        st.info("还没有报告。请先到「数据采集」提交分析任务。")
        return

    if job["status"] in {"queued", "running"}:
        _live_job_panel_report(st.session_state.anonymous_id)
        st.caption("处理中可返回「数据采集」继续操作，不会中断任务。")
        return

    # Ensure session has latest finished payload without depending on fragment loops
    _sync_finished_job_once(job)

    st.caption(f"任务 {job['job_id'][:8]}… · 状态：{job['status']}")
    if job["status"] == "failed":
        st.error(job.get("error_message") or job.get("message") or "任务失败")
        return

    result = job.get("result") or st.session_state.get("last_report")
    if not result:
        st.warning("任务已结束但没有报告数据。")
        return
    st.session_state["last_report"] = result
    st.session_state["job_id"] = job["job_id"]
    if job["status"] == "empty":
        st.warning(result.get("message") or job.get("message") or "未采集到数据")
        return
    st.success(job.get("message") or "分析完成")
    _render_result(result)


_page_collect = st.Page(
    page_collect, title="数据采集", icon=":material/upload_file:", default=True
)
_page_report = st.Page(
    page_report, title="分析报告", icon=":material/description:"
)

# Native top header: circular icon switches (no in-body brand / pills)
nav = st.navigation([_page_collect, _page_report], position="top")
# Push page body below sticky frosted header so nothing is clipped
st.markdown('<div class="ie-below-header" aria-hidden="true"></div>', unsafe_allow_html=True)
nav.run()
