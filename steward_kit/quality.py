"""Run the quality rules in governance.yml as SQL against the catalog.

Each rule becomes one query that counts failing rows, plus a query a steward can run to see them.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from . import sqlgen
from .catalog import Catalog


def _cols(rule: Dict[str, Any]) -> List[str]:
    return rule.get("columns") or [rule["column"]]


def build_sql(cat: Catalog, rule: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """Return (count_sql, failing_rows_sql). freshness returns a MAX() query instead of a count."""
    schema, table = rule["table"].split(".")
    ref = cat.table_ref(schema, table)
    check = rule["check"]
    col = sqlgen.ident(rule["column"]) if rule.get("column") else None

    if check == "not_null":
        where = f"{col} IS NULL"
    elif check == "accepted_values":
        values = ", ".join(cat.lit(v) for v in rule["values"])
        where = f"{col} IS NOT NULL AND {col} NOT IN ({values})"
    elif check == "range":
        conds = []
        if "min" in rule:
            conds.append(f"{col} < {float(rule['min'])}")
        if "max" in rule:
            conds.append(f"{col} > {float(rule['max'])}")
        where = f"{col} IS NOT NULL AND ({' OR '.join(conds)})"
    elif check == "pattern":
        where = f"{col} IS NOT NULL AND {cat.regex_mismatch_sql(col, rule['pattern'])}"
    elif check == "condition":
        where = f"NOT ({rule['condition']})"
    elif check == "relationship":
        p_schema, p_table, p_col = rule["references"].split(".")
        pref = cat.table_ref(p_schema, p_table)
        where = (f"{col} IS NOT NULL AND NOT EXISTS (SELECT 1 FROM {pref} p "
                 f"WHERE p.{sqlgen.ident(p_col)} = t.{col})")
        return (f"SELECT COUNT(*) FROM {ref} t WHERE {where}",
                f"SELECT t.* FROM {ref} t WHERE {where} LIMIT 100")
    elif check == "unique":
        keys = ", ".join(sqlgen.ident(c) for c in _cols(rule))
        not_null = " AND ".join(f"{sqlgen.ident(c)} IS NOT NULL" for c in _cols(rule))
        dup = f"SELECT {keys}, COUNT(*) AS n FROM {ref} WHERE {not_null} GROUP BY {keys} HAVING COUNT(*) > 1"
        return (f"SELECT COALESCE(SUM(n - 1), 0) FROM ({dup}) d", dup + " ORDER BY n DESC LIMIT 100")
    elif check == "freshness":
        return (f"SELECT MAX({col}) FROM {ref}", None)
    else:
        raise ValueError(f"Unknown check '{check}' in rule {rule['id']}")
    return f"SELECT COUNT(*) FROM {ref} WHERE {where}", f"SELECT * FROM {ref} WHERE {where} LIMIT 100"


def _as_date(v: Any) -> Optional[date]:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def run_rules(cat: Catalog, rules: List[Dict[str, Any]], today: Optional[date] = None) -> List[Dict[str, Any]]:
    today = today or datetime.now(timezone.utc).date()
    results = []
    for rule in rules:
        schema, table = rule["table"].split(".")
        base = {"id": rule["id"], "table": rule["table"], "column": ", ".join(_cols(rule)) if rule["check"] != "condition" else "",
                "check": rule["check"], "severity": rule.get("severity", "medium"),
                "description": rule.get("description", "")}
        try:
            count_sql, rows_sql = build_sql(cat, rule)
            total = cat.query(f"SELECT COUNT(*) FROM {cat.table_ref(schema, table)}")[0][0]
            if rule["check"] == "freshness":
                latest = _as_date(cat.query(count_sql)[0][0])
                age = (today - latest).days if latest else None
                ok = age is not None and age <= int(rule["max_age_days"])
                detail = (f"Latest value {latest.isoformat()} is {age} days old (limit {rule['max_age_days']})"
                          if latest else "No dates found")
                results.append({**base, "status": "pass" if ok else "fail", "failing_rows": 0 if ok else None,
                                "total_rows": total, "detail": detail, "sql": count_sql})
                continue
            failing = int(cat.query(count_sql)[0][0] or 0)
            pct = (failing / total * 100) if total else 0
            detail = f"{failing:,} of {total:,} rows fail ({pct:.2f}%)" if failing else f"All {total:,} rows pass"
            results.append({**base, "status": "fail" if failing else "pass", "failing_rows": failing,
                            "total_rows": total, "detail": detail, "sql": rows_sql})
        except Exception as exc:  # a broken rule should not stop the scan
            results.append({**base, "status": "error", "failing_rows": None, "total_rows": None,
                            "detail": f"Rule could not run: {str(exc).splitlines()[0][:200]}", "sql": None})
    return results
