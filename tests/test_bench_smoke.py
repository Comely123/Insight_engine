from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_bench_local_smoke(tmp_path, monkeypatch):
    # Run bench script; it creates its own isolated DB under data/benchmarks
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "bench_local.py")],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "import_csv_ms" in proc.stdout
    # latest result file
    bench_dir = ROOT / "data" / "benchmarks"
    results = sorted(bench_dir.glob("bench_result_*.json"))
    assert results
    payload = json.loads(results[-1].read_text(encoding="utf-8"))
    assert "metrics_ms" in payload
    assert payload["metrics_ms"]["import_csv_ms"] >= 0
