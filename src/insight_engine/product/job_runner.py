"""Background analysis jobs that keep running across Streamlit page switches."""

from __future__ import annotations

import shutil
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from insight_engine.config import Settings, get_settings
from insight_engine.ops.logging_util import get_logger
from insight_engine.ops.secrets_store import SecretsStore
from insight_engine.product.job_store import JobStore
from insight_engine.product.pipeline import PublicAnalysisService

log = get_logger("insight_engine.jobs")

_executor: ThreadPoolExecutor | None = None
_executor_lock = threading.Lock()


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    with _executor_lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="insight-job")
        return _executor


def job_workdir(settings: Settings, job_id: str) -> Path:
    path = settings.data_dir / "jobs" / job_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def submit_public_analysis(
    *,
    mode: str,
    keywords: list[str],
    research_brief: str,
    collector_ids: list[str] | None,
    anonymous_id: str | None,
    upload_files: list[tuple[str, bytes]] | None,
    use_llm: bool,
    llm_provider: str,
    llm_base_url: str | None,
    llm_model: str | None,
    settings: Settings | None = None,
) -> str:
    """
    Persist job + copy uploads, then run PublicAnalysisService in a background thread.
    Returns job_id immediately.
    """
    settings = settings or get_settings()
    settings.ensure_directories()
    store = JobStore(settings)
    job_id = str(uuid.uuid4())
    work = job_workdir(settings, job_id)
    upload_dir = work / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    saved_names: list[str] = []
    if upload_files:
        for name, data in upload_files:
            safe = Path(name).name
            (upload_dir / safe).write_bytes(data)
            saved_names.append(safe)

    params = {
        "mode": mode,
        "keywords": keywords,
        "research_brief": research_brief,
        "collector_ids": collector_ids or [],
        "use_llm": use_llm,
        "llm_provider": llm_provider,
        "llm_base_url": llm_base_url,
        "llm_model": llm_model,
        "upload_names": saved_names,
    }
    store.create(
        job_id=job_id,
        anonymous_id=anonymous_id,
        mode=mode,
        params=params,
        message="已提交，后台排队中",
    )
    _get_executor().submit(_execute_job, job_id)
    log.info("submitted job_id=%s mode=%s uploads=%s", job_id, mode, len(saved_names))
    return job_id


def _execute_job(job_id: str) -> None:
    settings = get_settings()
    store = JobStore(settings)
    job = store.get(job_id)
    if job is None:
        return

    store.update(job_id, status="running", message="正在采集与分析…")
    params = job["params"]
    work = job_workdir(settings, job_id)
    upload_dir = work / "uploads"
    upload_paths = [upload_dir / n for n in (params.get("upload_names") or [])]

    provider = params.get("llm_provider") or "rules"
    use_llm = bool(params.get("use_llm"))
    llm_key = None
    if use_llm:
        llm_key = SecretsStore(settings).get_secret(f"llm.api_key.{provider}")

    try:
        result = PublicAnalysisService(settings).run(
            mode=params["mode"],
            keywords=params.get("keywords") or [],
            research_brief=params.get("research_brief") or "",
            upload_paths=upload_paths or None,
            collector_ids=params.get("collector_ids") or None,
            anonymous_id=job.get("anonymous_id"),
            llm_api_key=llm_key,
            llm_base_url=params.get("llm_base_url"),
            llm_model=params.get("llm_model"),
            use_llm=use_llm,
        )
        status = result.get("status") or "succeeded"
        if status == "empty":
            store.update(
                job_id,
                status="empty",
                message=result.get("message") or "未得到可用样本",
                result=result,
                finished=True,
            )
        else:
            store.update(
                job_id,
                status="succeeded",
                message="分析完成",
                result=result,
                finished=True,
            )
        log.info("job finished job_id=%s status=%s", job_id, status)
    except Exception as exc:  # noqa: BLE001
        log.exception("job failed job_id=%s", job_id)
        store.update(
            job_id,
            status="failed",
            message="分析失败",
            error_message=str(exc),
            finished=True,
        )
    finally:
        try:
            if upload_dir.exists():
                shutil.rmtree(upload_dir, ignore_errors=True)
        except OSError:
            pass


def get_job(job_id: str, settings: Settings | None = None) -> dict[str, Any] | None:
    return JobStore(settings).get(job_id)


def latest_job(anonymous_id: str | None, settings: Settings | None = None) -> dict[str, Any] | None:
    return JobStore(settings).latest_for_anonymous(anonymous_id)
