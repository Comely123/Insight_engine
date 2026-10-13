"""Data import page."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_SRC = Path(__file__).resolve().parents[3]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import streamlit as st

from insight_engine.config import get_settings
from insight_engine.db.connection import get_connection, initialize_database
from insight_engine.ingest.service import ImportService
from insight_engine.models.documents import PermissionStatus

st.set_page_config(page_title="数据导入 · Insight Engine", layout="wide")
initialize_database()
settings = get_settings()

st.title("数据导入")
st.caption("支持 CSV / JSON / TXT / Markdown。导入失败会显示可读错误，不会静默丢弃整批。")

permission = st.selectbox(
    "许可 / 授权状态",
    options=[
        PermissionStatus.USER_OWNED.value,
        PermissionStatus.ALLOWED.value,
        PermissionStatus.UNCLEAR.value,
        PermissionStatus.DENIED.value,
    ],
    index=0,
    help="授权不明时请勿用于自动采集；本页仅处理你主动上传的本地文件。",
)
if permission == PermissionStatus.UNCLEAR.value:
    st.warning("授权状态不明确：仅允许你确认已合法持有的本地文件导入；不会启用自动采集。")
if permission == PermissionStatus.DENIED.value:
    st.error("许可状态为 denied：不建议导入。若仍继续，系统会记录该状态。")

source_name = st.text_input("来源名称（可选）", placeholder="例如：手工整理样本")
license_note = st.text_input("许可说明（可选）", value="User-provided research sample")

uploaded = st.file_uploader("选择文件", type=["csv", "json", "txt", "md", "markdown"])

sample_files = sorted(settings.samples_dir.glob("*")) if settings.samples_dir.exists() else []
sample_choice = None
if sample_files:
    st.markdown("或选择仓库示例数据：")
    labels = ["（不使用示例）"] + [p.name for p in sample_files]
    pick = st.selectbox("示例文件", labels)
    if pick != "（不使用示例）":
        sample_choice = settings.samples_dir / pick

if st.button("开始导入", type="primary"):
    target_path: Path | None = None
    tmp_path: Path | None = None
    try:
        if uploaded is not None:
            suffix = Path(uploaded.name).suffix
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(uploaded.getvalue())
                tmp_path = Path(tmp.name)
            target_path = tmp_path
            display_name = uploaded.name
        elif sample_choice is not None:
            target_path = sample_choice
            display_name = sample_choice.name
        else:
            st.error("请上传文件或选择示例数据。")
            st.stop()

        # Preserve original filename for batch metadata via copy name trick:
        # write into a named temp under imports after service copy — pass path with real name
        named = settings.imports_dir / f"_upload_{display_name}"
        settings.ensure_directories()
        named.write_bytes(target_path.read_bytes())

        with get_connection() as conn:
            service = ImportService(conn, settings)
            result = service.import_file(
                named,
                source_name=source_name or Path(display_name).stem,
                permission_status=PermissionStatus(permission),
                license_note=license_note or None,
                save_copy=True,
            )

        st.success(
            f"导入完成：status={result.status}, "
            f"input={result.row_count_input}, imported={result.row_count_imported}, "
            f"dupes={result.row_count_dupes}, errors={len(result.errors)}"
        )
        st.json(result.model_dump(mode="json"))
        if result.errors:
            st.subheader("错误明细")
            st.dataframe([e.model_dump() for e in result.errors], use_container_width=True)
    finally:
        if tmp_path and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
