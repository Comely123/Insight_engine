from __future__ import annotations

from insight_engine.product.narrative_guards import finding_is_blocked, sanitize_narrative_lists


def test_block_dedup_rate_and_repost_claims():
    assert finding_is_blocked("去重后159条，原始162条，去重率约98.1%。")
    assert finding_is_blocked("说明同源重复报道或同事件多篇转载占比较高。")
    assert not finding_is_blocked("样本保留率 98.1%，去重删除率 1.85%。")


def test_sanitize_strips_bad_findings():
    narr = {
        "findings": [
            "去重率约98.1%，转载占比较高。",
            "最终保留 159 条，精确重复 3 条。",
        ],
        "one_liner": "去重率很高",
    }
    sanitize_narrative_lists(narr)
    assert narr["findings"] == ["最终保留 159 条，精确重复 3 条。"]
    assert "去重率" not in narr["one_liner"]
