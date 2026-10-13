"""Content search and export page."""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[3]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import pandas as pd
import streamlit as st

from insight_engine.config import get_settings
from insight_engine.db.connection import get_connection, initialize_database
from insight_engine.export.writers import export_documents_csv, export_documents_json
from insight_engine.search.fts import (
    SearchFilters,
    list_content_types,
    list_source_names,
    search_documents,
)

st.set_page_config(page_title="内容检索 · Insight Engine", layout="wide")
initialize_database()
settings = get_settings()

st.title("内容检索")
st.caption("SQLite FTS5 全文检索。重复文档默认隐藏。模型输出未接入前，结果均为原始/规范化文本。")

with get_connection() as conn:
    sources = list_source_names(conn)
    types = list_content_types(conn)

query = st.text_input("关键词", placeholder="例如：宠物 毛发 编织 价格")
c1, c2, c3, c4 = st.columns(4)
source_name = c1.selectbox("来源", ["（全部）"] + sources)
content_type = c2.selectbox("内容类型", ["（全部）"] + types)
published_from = c3.text_input("发布时间起 (ISO)", placeholder="2024-01-01")
published_to = c4.text_input("发布时间止 (ISO)", placeholder="2026-12-31")
include_dupes = st.checkbox("包含重复文档", value=False)
limit = st.slider("返回条数", 10, settings.search_max_limit, settings.search_default_limit)

if st.button("搜索", type="primary") or query:
    filters = SearchFilters(
        query=query or "",
        source_name=None if source_name == "（全部）" else source_name,
        content_type=None if content_type == "（全部）" else content_type,
        published_from=published_from.strip() or None,
        published_to=published_to.strip() or None,
        include_duplicates=include_dupes,
        limit=limit,
    )
    with get_connection() as conn:
        rows = search_documents(conn, filters)

    st.write(f"命中 {len(rows)} 条")
    if rows:
        df = pd.DataFrame(rows)
        # Preview shorter content
        if "normalized_content" in df.columns:
            df["preview"] = df["normalized_content"].astype(str).str.slice(0, 160)
        show_cols = [
            c
            for c in [
                "document_id",
                "title",
                "preview",
                "source_name",
                "content_type",
                "published_at",
                "is_duplicate",
                "original_url",
            ]
            if c in df.columns
        ]
        st.dataframe(df[show_cols], use_container_width=True)

        with st.expander("完整结果 JSON"):
            st.json(rows)

        export_dir = settings.data_dir / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        col_a, col_b = st.columns(2)
        if col_a.button("导出 CSV"):
            out = export_documents_csv(export_dir / "search_export.csv", rows)
            st.success(f"已写入 {out}")
            st.download_button(
                "下载 CSV",
                data=out.read_bytes(),
                file_name="search_export.csv",
                mime="text/csv",
            )
        if col_b.button("导出 JSON"):
            out = export_documents_json(export_dir / "search_export.json", rows)
            st.success(f"已写入 {out}")
            st.download_button(
                "下载 JSON",
                data=out.read_bytes(),
                file_name="search_export.json",
                mime="application/json",
            )
    else:
        st.info("无匹配结果。可尝试更短关键词，或先导入示例数据。")
