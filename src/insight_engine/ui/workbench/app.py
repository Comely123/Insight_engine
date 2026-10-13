"""Streamlit entrypoint for Insight Engine."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Allow `streamlit run src/insight_engine/ui/app.py` without installing the package.
_SRC = Path(__file__).resolve().parents[3]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import streamlit as st

from insight_engine.config import get_settings
from insight_engine.db.analysis_repository import AnalysisRepository
from insight_engine.db.connection import get_connection, initialize_database
from insight_engine.db.media_repository import MediaRepository
from insight_engine.db.repository import DocumentRepository
from insight_engine.llm.factory import get_llm_provider

st.set_page_config(
    page_title="Insight Engine",
    page_icon="🔎",
    layout="wide",
)


def ensure_db() -> None:
    settings = get_settings()
    initialize_database(settings)


def main() -> None:
    ensure_db()
    settings = get_settings()
    st.title("Insight Engine")
    st.caption("本地优先 · 多源趋势研究引擎 · Phase 4")

    with get_connection() as conn:
        stats = DocumentRepository(conn).overview_stats()
        analysis = AnalysisRepository(conn).overview_analysis_stats()
        media = MediaRepository(conn).overview_stats()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("文档总数", stats["document_count"])
    c2.metric("去重后文�?, stats["unique_document_count"])
    c3.metric("重复标记", stats["duplicate_count"])
    c4.metric("数据�?, stats["source_count"])

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("主张", analysis["claims"])
    c6.metric("未核验主�?, analysis["unreviewed_claims"])
    c7.metric("媒体", media["media_count"])
    c8.metric("媒体片段", media["segment_count"])

    st.subheader("最近导�?)
    if stats["recent_batches"]:
        st.dataframe(stats["recent_batches"], width="stretch")
    else:
        st.info("尚无导入记录。请打开左侧「数据导入」页面，或使用公开站上传自有数据�?)

    with get_connection() as conn:
        errors = DocumentRepository(conn).list_import_errors(limit=50)

    st.subheader("最近导入错�?/ 警告")
    if errors:
        st.dataframe(errors, width="stretch")
        st.caption("日期解析失败等不会静默丢弃整行；内容缺失的行会被跳过并记录错误�?)
    else:
        st.success("暂无导入错误记录�?)

    st.info(
        "研究闭环请用「研究工作台」。另有事件主�?/ 趋势 / 视频证据页面�?
        "未核验结论与预警不得当作已确认市场事实�?
    )

    with st.expander("运行环境"):
        llm = get_llm_provider()
        st.write(
            {
                "db_path": str(settings.db_path),
                "data_dir": str(settings.data_dir),
                "samples_dir": str(settings.samples_dir),
                "llm_provider": llm.name,
                "llm_available": llm.available(),
                "llm_env_set": bool(os.environ.get("INSIGHT_LLM_API_KEY")),
            }
        )
        st.caption("�?API Key 时可完成导入、规则分析、检索、趋势统计与导出�?)


if __name__ == "__main__":
    main()
