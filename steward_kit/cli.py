"""Command line: python -m steward_kit <command>"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import ROOT, load_config

SYNTHETIC = ["customer_care.owner_contacts", "dealer_service.service_appointments"]
DB = str(ROOT / "demo" / "catalog.duckdb")


def _sources() -> dict:
    p = ROOT / "data" / "raw" / "sources.json"
    return json.loads(p.read_text()) if p.exists() else {}


def cmd_fetch(args) -> int:
    from .sources import fetch_all
    prov = fetch_all()
    for k, v in prov.items():
        print(f"{k:18} {v.get('rows', '-'):>6} rows  {v.get('note', v.get('fetched_at', ''))}")
    skipped = prov.get("nhtsa_recalls", {}).get("vehicles_without_data", [])
    failed = prov.get("nhtsa_recalls", {}).get("failed_requests", [])
    if skipped:
        print(f"NHTSA has no data yet for {len(skipped)} make, model and year combinations (normal for new models).")
    if failed:
        print(f"{len(failed)} requests failed and were skipped. Run fetch again later to fill them in.")
    return 0


def cmd_build(args) -> int:
    from .demo import build_duckdb
    cfg = load_config(args.config)
    cat = build_duckdb(args.db, cfg["catalog"])
    for t in cat.tables():
        print(f"{t.key:40} {t.row_count:>7,} rows")
    cat.close()
    return 0


def cmd_scan(args) -> int:
    from .catalog import open_catalog
    from .scan import scan, write_snapshot
    cfg = load_config(args.config)
    cat = open_catalog(args.target, cfg["catalog"], args.db)
    demo = args.target == "duckdb"
    snap = scan(cat, cfg, _sources() if demo else {}, SYNTHETIC if demo else [])
    path = write_snapshot(snap, Path(args.out))
    m = snap["metrics"]
    print(f"Scanned {m['tables']} tables, {m['columns']} columns in {snap['catalog']['scan_seconds']}s")
    print(f"  Governance-ready tables: {m['tables_ready']} of {m['tables']}")
    print(f"  Columns waiting for PII review: {m['open_pii']}")
    print(f"  Failing quality checks: {m['quality_failing']} of {m['quality_rules']}")
    print(f"  Open work items: {m['open_items']}")
    print(f"Wrote {path}")
    return 0


def cmd_eval(args) -> int:
    from . import evals
    from .catalog import open_catalog
    cfg = load_config(args.config)
    res = evals.run(open_catalog("duckdb", cfg["catalog"], args.db), cfg)
    c, q = res["classifier"], res["quality"]
    print(f"PII classifier: precision {c['precision']:.2f}, recall {c['recall']:.2f}, "
          f"type accuracy {c['type_accuracy']}, {c['pii_columns']} PII columns of {c['columns']}")
    for e in c["errors"]:
        print("   ", e)
    h = res["hard_cases"]
    print(f"PII hard cases: precision {h['precision']:.2f}, recall {h['recall']:.2f} on {h['cases']} tricky columns")
    for e in h["errors"]:
        print("   ", e)
    print(f"Quality rules: {q['exact_matches']} of {q['total']} found exactly the injected defects")
    for r in q["rules"]:
        print(f"    {r['rule']} {r['defect']:30} injected {r['injected']:>3}  found {r['found']}")
    ok = (c["precision"] >= 0.9 and c["recall"] >= 0.9 and h["recall"] >= 0.8
          and q["exact_matches"] == q["total"])
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


def cmd_dbx_sql(args) -> int:
    from .demo import databricks_sql
    cfg = load_config(args.config)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, sql in databricks_sql(cfg["catalog"]).items():
        (out / name).write_text(sql)
        print(f"Wrote {out / name}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m steward_kit",
                                description="Find and fix governance gaps in a Unity Catalog.")
    p.add_argument("--config", default=str(ROOT / "governance.yml"))
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("fetch", help="Download NHTSA and EPA data into data/raw")
    b = sub.add_parser("build-demo", help="Build the local demo catalog from data/raw")
    b.add_argument("--db", default=DB)
    s = sub.add_parser("scan", help="Scan a catalog and write the steward snapshot")
    s.add_argument("--target", choices=["duckdb", "databricks"], default="duckdb")
    s.add_argument("--db", default=DB)
    s.add_argument("--out", default=str(ROOT / "site" / "data" / "snapshot.json"))
    e = sub.add_parser("eval", help="Score the classifier and quality rules against ground truth")
    e.add_argument("--db", default=DB)
    d = sub.add_parser("databricks-sql", help="Write the SQL that recreates the demo catalog in Databricks")
    d.add_argument("--out", default=str(ROOT / "databricks"))
    args = p.parse_args(argv)
    handlers = {"fetch": cmd_fetch, "build-demo": cmd_build, "scan": cmd_scan, "eval": cmd_eval,
                "databricks-sql": cmd_dbx_sql}
    try:
        return handlers[args.cmd](args)
    except (FileNotFoundError, EnvironmentError, ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
