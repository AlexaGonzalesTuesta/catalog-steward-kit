"""Scan a catalog and produce the steward snapshot (site/data/snapshot.json)."""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import sqlgen
from .catalog import Catalog, DatabricksCatalog
from .classify import suggest
from .config import ROOT
from .quality import build_sql, run_rules

PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}
VALUE = "{value}"  # placeholder the UI fills with the steward's input


def _id(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:10]


def _template(sql: str, placeholder_literal: str) -> str:
    return sql.replace(placeholder_literal, VALUE)


def scan(cat: Catalog, cfg: Dict[str, Any], sources: Optional[Dict[str, Any]] = None,
         synthetic_tables: Optional[List[str]] = None) -> Dict[str, Any]:
    started = time.perf_counter()
    tags = cfg["tags"]
    domains = cfg["domains"]
    stewards = {s["email"]: s for s in cfg["stewards"]}
    tables = [t for t in cat.tables() if t.schema in domains]
    columns = [c for c in cat.columns() if c.schema in domains]
    suggestions = suggest(cat, columns, cfg)
    quality = run_rules(cat, cfg["quality_rules"])
    # Stewards run the failing-rows query in Databricks, so show it in Databricks SQL
    # even when the scan itself ran against the local DuckDB copy.
    dbx = DatabricksCatalog(cat.name, connection=False)
    rules = {r["id"]: r for r in cfg["quality_rules"]}
    for q in quality:
        if q["status"] != "error":
            count_sql, rows_sql = build_sql(dbx, rules[q["id"]])
            q["sql"] = rows_sql or count_sql
    open_pii = {}
    for s in suggestions:
        open_pii.setdefault(f"{s.schema}.{s.table}", []).append(s)
    pii_tagged = {c.table_key for c in columns if c.tags.get(tags["classification"]) == cfg["pii_level"]}

    items: List[Dict[str, Any]] = []
    table_rows = []
    for t in tables:
        d = domains[t.schema]
        steward = t.tags.get(tags["steward"]) or d["steward"]
        cols = [c for c in columns if c.table_key == t.key]
        described = sum(1 for c in cols if c.comment)
        classified_cols = sum(1 for c in cols if tags["classification"] in c.tags)
        owner = t.tags.get(tags["data_owner"])
        level = t.tags.get(tags["classification"])
        quality_t = [q for q in quality if q["table"] == t.key]
        row = {
            "table": t.key, "domain": t.schema, "domain_name": d["name"], "steward": steward,
            "rows": t.row_count, "description": t.comment, "data_owner": owner, "classification": level,
            "columns": len(cols), "columns_described": described, "columns_classified": classified_cols,
            "open_pii": len(open_pii.get(t.key, [])), "contains_pii": t.key in pii_tagged,
            "quality_failing": sum(1 for q in quality_t if q["status"] == "fail"),
            "quality_rules": len(quality_t), "synthetic": t.key in (synthetic_tables or []),
        }
        row["ready"] = bool(t.comment and owner and level and row["open_pii"] == 0)
        table_rows.append(row)

        base = {"domain": t.schema, "steward": steward, "table": t.key}
        if not owner:
            items.append({**base, "id": _id("owner", t.key), "type": "owner", "priority": "medium",
                          "object": t.key, "title": "No data owner",
                          "evidence": f"Nobody is accountable for {t.row_count:,} rows. The {d['name']} default owner is "
                                      f"{d['default_owner']}.",
                          "suggested": d["default_owner"],
                          "sql": _template(sqlgen.set_table_tags(cat.name, t.schema, t.name,
                                                                 {tags["data_owner"]: "__V__"}), "'__V__'")})
        if not t.comment:
            items.append({**base, "id": _id("describe", t.key), "type": "describe", "priority": "low",
                          "object": t.key, "title": "No table description",
                          "evidence": f"Users searching the catalog cannot tell what this table holds. "
                                      f"{described} of {len(cols)} columns are described.",
                          "suggested": "",
                          "sql": _template(sqlgen.comment_table(cat.name, t.schema, t.name, "__V__"), "'__V__'")})
        if not level:
            pii = t.key in pii_tagged or t.key in open_pii
            items.append({**base, "id": _id("classify", t.key), "type": "classify",
                          "priority": "high" if pii else "medium", "object": t.key, "title": "No classification",
                          "evidence": ("Columns in this table hold or may hold personal data."
                                       if pii else "No columns look like personal data. Confirm the level the data needs."),
                          "suggested": cfg["pii_level"] if pii else cfg["not_pii_level"],
                          "levels": cfg["classification_levels"],
                          "sql": _template(sqlgen.set_table_tags(cat.name, t.schema, t.name,
                                                                 {tags["classification"]: "__V__"}), "'__V__'")})

    for s in suggestions:
        d = domains[s.schema]
        table_key = f"{s.schema}.{s.table}"
        steward = next((r["steward"] for r in table_rows if r["table"] == table_key), d["steward"])
        items.append({"id": _id("pii", s.key), "type": "pii", "priority": "high" if s.confidence >= 0.8 else "medium",
                      "domain": s.schema, "steward": steward, "table": table_key, "object": s.key,
                      "title": f"Possible {s.to_dict()['label']}", "evidence": s.evidence,
                      "confidence": round(s.confidence, 2), "pii_type": s.pii_type, "examples": s.examples,
                      "sql_confirm": sqlgen.set_column_tags(cat.name, s.schema, s.table, s.column,
                                                            {tags["classification"]: cfg["pii_level"],
                                                             tags["pii_type"]: s.pii_type}),
                      "sql_reject": sqlgen.set_column_tags(cat.name, s.schema, s.table, s.column,
                                                           {tags["classification"]: cfg["not_pii_level"]})})

    for q in quality:
        if q["status"] == "pass":
            continue
        schema = q["table"].split(".")[0]
        steward = next((r["steward"] for r in table_rows if r["table"] == q["table"]), domains[schema]["steward"])
        items.append({"id": _id("dq", q["id"]), "type": "quality", "priority": q["severity"],
                      "domain": schema, "steward": steward, "table": q["table"],
                      "object": q["table"] + (f".{q['column']}" if q["column"] and "," not in q["column"] else ""),
                      "title": f"{q['id']}: {q['description']}", "evidence": q["detail"], "rule": q["id"],
                      "query": q["sql"]})

    type_order = {"pii": 0, "quality": 1, "classify": 2, "owner": 3, "describe": 4}
    items.sort(key=lambda i: (PRIORITY_ORDER[i["priority"]], type_order[i["type"]], i["object"]))

    open_by_steward: Dict[str, int] = {}
    for i in items:
        open_by_steward[i["steward"]] = open_by_steward.get(i["steward"], 0) + 1
    steward_rows = []
    for email, s in stewards.items():
        ob = s.get("onboarding", {})
        steward_rows.append({"email": email, "name": s["name"], "domain": s["domain"],
                             "domain_name": domains.get(s["domain"], {}).get("name", s["domain"]),
                             "required_learning": bool(ob.get("required_learning")),
                             "catalog_access": bool(ob.get("catalog_access")),
                             "first_review": bool(ob.get("first_review")),
                             "ready": all(ob.get(k) for k in ("required_learning", "catalog_access", "first_review")),
                             "open_items": open_by_steward.get(email, 0)})

    total_cols = len(columns)
    snapshot = {
        "catalog": {"name": cat.name, "display_name": cfg.get("display_name", cat.name), "target": cat.dialect,
                    "scanned_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "scan_seconds": round(time.perf_counter() - started, 2)},
        "policy": {"levels": cfg["classification_levels"], "pii_level": cfg["pii_level"],
                   "not_pii_level": cfg["not_pii_level"], "tags": tags},
        "metrics": {
            "tables": len(table_rows), "tables_ready": sum(r["ready"] for r in table_rows),
            "open_pii": len(suggestions), "quality_rules": len(quality),
            "quality_failing": sum(1 for q in quality if q["status"] == "fail"),
            "quality_errors": sum(1 for q in quality if q["status"] == "error"),
            "stewards": len(steward_rows), "stewards_ready": sum(s["ready"] for s in steward_rows),
            "columns": total_cols, "columns_described": sum(1 for c in columns if c.comment),
            "open_items": len(items),
        },
        "tables": table_rows, "items": items, "quality": quality, "stewards": steward_rows,
        "sources": sources or {}, "synthetic_tables": synthetic_tables or [],
    }
    return snapshot


def write_snapshot(snapshot: Dict[str, Any], path: Path = ROOT / "site" / "data" / "snapshot.json") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, indent=1, default=str))
    return path
