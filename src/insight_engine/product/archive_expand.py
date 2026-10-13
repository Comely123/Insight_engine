"""Safely expand zip/tar uploads into a temp directory for analysis."""

from __future__ import annotations

import tarfile
import tempfile
import zipfile
from pathlib import Path

ARCHIVE_EXTENSIONS = {".zip", ".tar", ".tgz"}

_MAX_MEMBERS = 200
_MAX_TOTAL_BYTES = 80 * 1024 * 1024  # 80 MB uncompressed budget
_SKIP_DIR_NAMES = {
    "__macosx",
    ".git",
    "node_modules",
    ".svn",
    ".hg",
    "__pycache__",
}


def is_archive(path: Path) -> bool:
    name = path.name.lower()
    if name.endswith(".tar.gz") or name.endswith(".tar.bz2") or name.endswith(".tgz"):
        return True
    return path.suffix.lower() in {".zip", ".tar"}


def _safe_join(root: Path, member: str) -> Path | None:
    # Block path traversal
    target = (root / member).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError:
        return None
    parts_lower = {p.lower() for p in Path(member).parts}
    if parts_lower & _SKIP_DIR_NAMES:
        return None
    return target


def expand_archives(
    paths: list[Path],
    *,
    work_root: Path | None = None,
) -> tuple[list[Path], list[str], list[Path]]:
    """
    Returns:
      flat_files (non-archive files + extracted members),
      notes,
      temp_dirs_to_cleanup
    """
    out: list[Path] = []
    notes: list[str] = []
    temps: list[Path] = []

    for path in paths:
        if not is_archive(path):
            out.append(path)
            continue
        dest = Path(tempfile.mkdtemp(prefix="insight_unpacked_", dir=work_root))
        temps.append(dest)
        try:
            extracted, note = _extract_one(path, dest)
            out.extend(extracted)
            notes.append(note)
        except Exception as exc:  # noqa: BLE001
            notes.append(f"{path.name}: 解压失败 {exc}")
    return out, notes, temps


def _extract_one(path: Path, dest: Path) -> tuple[list[Path], str]:
    name = path.name.lower()
    files: list[Path] = []
    total = 0
    count = 0

    if name.endswith(".zip") or path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                if count >= _MAX_MEMBERS:
                    break
                target = _safe_join(dest, info.filename)
                if target is None:
                    continue
                if info.file_size > _MAX_TOTAL_BYTES:
                    continue
                if total + info.file_size > _MAX_TOTAL_BYTES:
                    break
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, target.open("wb") as dst:
                    data = src.read()
                    dst.write(data)
                total += len(data)
                count += 1
                files.append(target)
        return files, f"{path.name}: 解压 {count} 个文件（zip，约 {total} 字节）"

    # tar / tgz / tar.gz
    mode = "r:*"
    with tarfile.open(path, mode) as tf:
        for member in tf.getmembers():
            if not member.isfile():
                continue
            if count >= _MAX_MEMBERS:
                break
            target = _safe_join(dest, member.name)
            if target is None:
                continue
            if member.size > _MAX_TOTAL_BYTES:
                continue
            if total + member.size > _MAX_TOTAL_BYTES:
                break
            extracted = tf.extractfile(member)
            if extracted is None:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            data = extracted.read()
            target.write_bytes(data)
            total += len(data)
            count += 1
            files.append(target)
    return files, f"{path.name}: 解压 {count} 个文件（tar，约 {total} 字节）"
