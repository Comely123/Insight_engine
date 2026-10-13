"""Admin: export anonymous search archives (not for end users)."""

from __future__ import annotations

import csv
import io
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import streamlit as st

from insight_engine.db.connection import get_connection, initialize_database
from insight_engine.db.session_repository import SessionRepository

st.set_page_config(page_title="Insight 管理归档", layout="wide")
initialize_database()

st.title("检索归档（管理端）")
st.caption("记录用户使用网站产生的关键词与报告摘要，便于二次分析。不对公众展示。")

with get_connection() as conn:
    rows = SessionRepository(conn).list_sessions(limit=500)

st.metric("归档条数", len(rows))
st.dataframe(rows, use_container_width=True)

if rows:
    buf = io.StringIO()
    writer = csv.DictWriter(
        buf,
        fieldnames=list(rows[0].keys()),
        extrasaction="ignore",
    )
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    st.download_button(
        "导出 CSV",
        data=buf.getvalue(),
        file_name="search_sessions.csv",
        mime="text/csv",
    )
