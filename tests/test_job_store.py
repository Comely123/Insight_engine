from insight_engine.product.job_store import JobStore


def test_job_store_lifecycle(tmp_settings) -> None:
    store = JobStore(tmp_settings)
    store.create(
        job_id="job-1",
        anonymous_id="anon",
        mode="upload",
        params={"keywords": ["a"]},
        message="queued",
    )
    row = store.get("job-1")
    assert row is not None
    assert row["status"] == "queued"
    store.update("job-1", status="running", message="go")
    store.update(
        "job-1",
        status="succeeded",
        message="done",
        result={"status": "succeeded", "report": {}},
        finished=True,
    )
    latest = store.latest_for_anonymous("anon")
    assert latest is not None
    assert latest["status"] == "succeeded"
    assert latest["result"]["status"] == "succeeded"
