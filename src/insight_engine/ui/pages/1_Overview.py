"""Overview page (also available as multipage entry)."""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[3]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import streamlit as st

from insight_engine.db.connection import get_connection, initialize_database
from insight_engine.db.repository import DocumentRepository

st.set_page_config(page_title="总览 · Insight Engine", layout="wide")
initialize_database()

st.title("总览")
st.caption("数据库规模、导入记录与异常")

with get_connection() as conn:
    stats = DocumentRepository(conn).overview_stats()
    errors = DocumentRepository(conn).list_import_errors(50)

cols = st.columns(4)
cols[0].metric("文档总数", stats["document_count"])
cols[1].metric("去重后", stats["unique_document_count"])
cols[2].metric("重复", stats["duplicate_count"])
cols[3].metric("错误", stats["error_count"])

st.subheader("最近导入批次")
st.dataframe(stats["recent_batches"] or [], use_container_width=True)

st.subheader("导入错误")
st.dataframe(errors or [], use_container_width=True)
