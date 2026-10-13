"""Read-only audit helper: recompute metrics from local DB. Do not modify data."""

from __future__ import annotations

import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from insight_engine.config import get_settings  # noqa: E402


def main() -> None:
    settings = get_settings()
    db = settings.db_path
    print("DB:", db, "exists=", db.exists())
    if not db.exists():
        return
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row

    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    print("tables:", tables)

    if "search_sessions" in tables:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(search_sessions)")]
        print("search_sessions cols:", cols)
        metric_col = "metrics_json" if "metrics_json" in cols else ("metrics" if "metrics" in cols else None)
        select_cols = [
            "session_id",
            "mode",
            "document_count",
            "unique_document_count",
            "report_summary",
            "created_at",
        ]
        if metric_col:
            select_cols.append(metric_col)
        sessions = conn.execute(
            f"SELECT {', '.join(select_cols)} FROM search_sessions ORDER BY created_at DESC LIMIT 10"
        ).fetchall()
        print("\n=== latest sessions ===")
        for s in sessions:
            print(
                s["created_at"],
                s["session_id"][:8],
                "mode=",
                s["mode"],
                "raw=",
                s["document_count"],
                "unique=",
                s["unique_document_count"],
                "|",
                (s["report_summary"] or "")[:80],
            )

        target = None
        for s in sessions:
            if s["document_count"] == 162 or s["unique_document_count"] == 159:
                target = s
                break
        if target is None and sessions:
            target = sessions[0]
        if target and metric_col:
            print("\n=== audit target session ===")
            print("session_id=", target["session_id"])
            metrics = {}
            try:
                metrics = json.loads(target[metric_col] or "{}")
            except json.JSONDecodeError:
                pass
            trend = metrics.get("trend") or {}
            print("stored trend keys:", sorted(trend.keys())[:40])
            for k in (
                "raw_documents",
                "unique_documents",
                "duplicate_documents",
                "independent_sources",
                "independent_events",
                "topic_counts",
                "intent_counts",
                "behavior_stage_counts",
                "demand_subtype_counts",
                "stance_counts",
                "price_values",
                "price_buckets",
                "top_source_share",
                "warnings",
            ):
                print(f"  {k}:", trend.get(k))
            doc_ids = trend.get("document_ids") or []
            print("document_ids in trend:", len(doc_ids))
            if doc_ids:
                audit_docs(conn, doc_ids)
                audit_claims(conn, doc_ids)
                audit_prices(conn, doc_ids)
                audit_sources(conn, doc_ids)

    # Also scan recent public report folders
    export_root = settings.data_dir / "exports" / "public_reports"
    if export_root.exists():
        print("\n=== public_reports dirs ===")
        dirs = sorted(export_root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)[:5]
        for d in dirs:
            print(d.name, "mtime", d.stat().st_mtime)
            for name in ("report.json", "public_narrative.md", "literature_breakdown.csv"):
                p = d / name
                if p.exists():
                    print(" ", name, "bytes", p.stat().st_size)
            jp = d / "report.json"
            if jp.exists():
                try:
                    payload = json.loads(jp.read_text(encoding="utf-8"))
                except Exception as exc:  # noqa: BLE001
                    print("  json err", exc)
                    continue
                m = (payload.get("metrics") or {})
                print(
                    "  metrics raw/unique/src/evt:",
                    m.get("raw_documents"),
                    m.get("unique_documents"),
                    m.get("independent_sources"),
                    m.get("independent_events"),
                )
                print("  topic:", m.get("topic_counts"))
                print("  demand:", m.get("demand_subtype_counts"))
                print("  intent:", m.get("intent_counts"))
                print("  behavior:", m.get("behavior_stage_counts"))
                print("  prices sample:", (m.get("price_values") or [])[:20], "n=", len(m.get("price_values") or []))
                narr = payload.get("public_narrative") or {}
                print("  findings0:", (narr.get("findings") or [None])[0])
                print("  innov[:3]:", (narr.get("literature_innovations") or [])[:3])
                ids = m.get("document_ids") or []
                if ids and (m.get("raw_documents") == 162 or m.get("unique_documents") == 159):
                    print("\n=== recomputing from report.json document_ids ===")
                    audit_docs(conn, ids)
                    audit_claims(conn, ids)
                    audit_prices(conn, ids)
                    audit_sources(conn, ids)
                    break
        else:
            # fall back: largest recent report
            for d in dirs:
                jp = d / "report.json"
                if not jp.exists():
                    continue
                payload = json.loads(jp.read_text(encoding="utf-8"))
                m = payload.get("metrics") or {}
                ids = m.get("document_ids") or []
                if ids:
                    print("\n=== recomputing from latest report with ids ===", d.name)
                    audit_docs(conn, ids)
                    audit_claims(conn, ids)
                    audit_prices(conn, ids)
                    audit_sources(conn, ids)
                    break


def audit_docs(conn: sqlite3.Connection, doc_ids: list[str]) -> None:
    ph = ",".join("?" for _ in doc_ids)
    rows = conn.execute(
        f"""
        SELECT document_id, source_id, source_name, original_url, title, content_type,
               is_duplicate, duplicate_of, content_hash, published_at,
               COALESCE(raw_content, '') AS raw,
               COALESCE(normalized_content, '') AS norm,
               processing_status
        FROM documents WHERE document_id IN ({ph})
        """,
        doc_ids,
    ).fetchall()
    print("rows fetched:", len(rows), "of", len(doc_ids))
    raw_n = len(rows)
    unique = [r for r in rows if int(r["is_duplicate"] or 0) == 0]
    dups = [r for r in rows if int(r["is_duplicate"] or 0) == 1]
    print("raw=", raw_n, "unique=", len(unique), "exact_dup_flag=", len(dups))
    if raw_n:
        print("retention=", round(len(unique) / raw_n, 4), "dedup_delete_rate=", round(len(dups) / raw_n, 4))
    # hash collisions among unique
    hash_c = Counter(r["content_hash"] for r in unique)
    multi = {h: c for h, c in hash_c.items() if c > 1}
    print("unique docs sharing same hash (should be 0):", len(multi))
    cleared = sum(1 for r in rows if "[ephemeral:cleared]" in (r["norm"] or "") or (r["raw"] == "" and r["norm"] == "[ephemeral:cleared]"))
    print("ephemeral cleared bodies:", cleared)
    # approximate near-dup not implemented — report N/A
    print("near_duplicate: NOT IMPLEMENTED in codebase (exact hash only)")


def audit_claims(conn: sqlite3.Connection, doc_ids: list[str]) -> None:
    ph = ",".join("?" for _ in doc_ids)
    rows = conn.execute(
        f"""
        SELECT c.claim_type, c.claim_value, c.polarity, c.confidence, c.is_inference, c.document_id,
               d.is_duplicate, e.excerpt
        FROM claims c
        JOIN documents d ON d.document_id = c.document_id
        LEFT JOIN evidence_links e ON e.claim_id = c.claim_id
        WHERE c.document_id IN ({ph}) AND d.is_duplicate = 0
        """,
        doc_ids,
    ).fetchall()
    by_type: dict[str, Counter] = {}
    for r in rows:
        by_type.setdefault(r["claim_type"], Counter())[r["claim_value"] or r["polarity"] or ""] += 1
    print("\n=== claim distributions (unique docs only) ===")
    for t, ctr in sorted(by_type.items()):
        print(t, dict(ctr.most_common(20)))

    # conflicts: memorial_craft topic vs memorial subtype
    topics = {r["document_id"]: r["claim_value"] for r in rows if r["claim_type"] == "topic"}
    subtypes = {r["document_id"]: r["claim_value"] for r in rows if r["claim_type"] == "demand_subtype"}
    craft_not_memorial = [
        did
        for did, t in topics.items()
        if t == "memorial_craft" and subtypes.get(did) not in {"memorial", None}
        and subtypes.get(did) != "memorial"
    ]
    craft_and_living = [
        did
        for did, t in topics.items()
        if t == "memorial_craft" and subtypes.get(did) == "living_blessing"
    ]
    craft_and_unknown = [
        did for did, t in topics.items() if t == "memorial_craft" and subtypes.get(did) == "unknown"
    ]
    print("memorial_craft docs:", sum(1 for t in topics.values() if t == "memorial_craft"))
    print("subtype memorial:", sum(1 for v in subtypes.values() if v == "memorial"))
    print("craft & living_blessing:", len(craft_and_living))
    print("craft & unknown subtype:", len(craft_and_unknown))
    print("craft & non-memorial subtype:", len(craft_not_memorial))


def audit_prices(conn: sqlite3.Connection, doc_ids: list[str]) -> None:
    ph = ",".join("?" for _ in doc_ids)
    rows = conn.execute(
        f"""
        SELECT c.claim_id, c.claim_value, c.document_id, d.title, d.source_name, e.excerpt,
               e.char_start, e.char_end
        FROM claims c
        JOIN documents d ON d.document_id = c.document_id
        LEFT JOIN evidence_links e ON e.claim_id = c.claim_id
        WHERE c.document_id IN ({ph}) AND c.claim_type = 'price' AND d.is_duplicate = 0
        ORDER BY CAST(c.claim_value AS REAL)
        """,
        doc_ids,
    ).fetchall()
    print("\n=== price claims (unique docs) n=", len(rows), "===")
    suspicious = []
    for r in rows[:80]:
        amt = r["claim_value"]
        ex = (r["excerpt"] or "")[:120]
        title = (r["title"] or "")[:60]
        flag = ""
        try:
            v = float(amt)
            if v >= 1900 and v <= 2035 and "元" not in ex and "¥" not in ex and "￥" not in ex:
                flag = "SUSPECT_YEAR"
            elif v in {1, 2, 3, 4, 5, 10, 100, 1000} and "元" not in (ex or ""):
                flag = "WEAK"
        except ValueError:
            flag = "NAN"
        if flag:
            suspicious.append((amt, flag, ex, title))
        print(f"  {amt:>10} {flag:14} | {ex!r} | {title!r}")
    print("suspicious flagged:", len(suspicious), "of", len(rows))


def audit_sources(conn: sqlite3.Connection, doc_ids: list[str]) -> None:
    ph = ",".join("?" for _ in doc_ids)
    rows = conn.execute(
        f"""
        SELECT source_id, source_name, original_url, is_duplicate
        FROM documents WHERE document_id IN ({ph}) AND is_duplicate = 0
        """,
        doc_ids,
    ).fetchall()
    by_name = Counter((r["source_name"] or r["source_id"] or "?") for r in rows)
    by_sid = Counter(r["source_id"] for r in rows)
    domains = []
    for r in rows:
        u = r["original_url"] or ""
        try:
            domains.append(urlparse(u).netloc.lower() or "(no-url)")
        except Exception:  # noqa: BLE001
            domains.append("(bad-url)")
    by_dom = Counter(domains)
    print("\n=== source definitions ===")
    print("distinct source_name|source_id (current independent_sources formula):", len(by_name))
    print("distinct source_id:", len(by_sid))
    print("distinct domains:", len(by_dom))
    print("top source_name:", by_name.most_common(15))
    print("top domains:", by_dom.most_common(15))
    print("top source_id:", by_sid.most_common(10))


if __name__ == "__main__":
    main()
