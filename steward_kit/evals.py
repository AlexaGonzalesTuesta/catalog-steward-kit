"""Measure the kit against ground truth.

1. PII classifier: every column in the demo catalog is labeled in evals/pii_ground_truth.csv.
2. Quality rules: the synthetic generator injects a known number of defects (data/synthetic/defects.json);
   each rule must find exactly that many failing rows.
"""
from __future__ import annotations

import csv
import json
from typing import Any, Dict

from .catalog import Catalog, Column
from .classify import score_column
from .config import ROOT
from .quality import run_rules
from .synthetic import DEFECTS

RULE_TO_DEFECT = {"CC-01": "duplicate_customer_id", "CC-02": "invalid_email", "CC-03": "invalid_vin",
                  "DS-01": "orphan_recall_campaign", "DS-02": "completed_before_appointment",
                  "DS-03": "invalid_status"}


def eval_classifier(cat: Catalog, cfg: Dict[str, Any]) -> Dict[str, Any]:
    with open(ROOT / "evals" / "pii_ground_truth.csv", encoding="utf-8") as f:
        truth = {r["column"]: r for r in csv.DictReader(f)}
    threshold = float(cfg["pii_suggestion_threshold"])
    tp = fp = fn = tn = type_ok = 0
    errors = []
    columns = [c for c in cat.columns() if c.schema in cfg["domains"]]
    unlabeled = [c.key for c in columns if c.key not in truth]
    if unlabeled:
        raise ValueError("Label these columns in evals/pii_ground_truth.csv: " + ", ".join(unlabeled))
    for c in columns:
        is_text = any(t in c.data_type.upper() for t in ("CHAR", "STRING", "TEXT"))
        s = score_column(c, cat.sample(c.schema, c.table, c.name)) if is_text else None
        predicted = bool(s and s.confidence >= threshold)
        actual = truth[c.key]["is_pii"] == "yes"
        if predicted and actual:
            tp += 1
            type_ok += s.pii_type == truth[c.key]["pii_type"]
        elif predicted:
            fp += 1
            errors.append(f"false positive: {c.key} ({s.pii_type}, {s.confidence:.2f})")
        elif actual:
            fn += 1
            errors.append(f"missed: {c.key}")
        else:
            tn += 1
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    return {"columns": len(columns), "pii_columns": tp + fn, "true_positives": tp, "false_positives": fp,
            "missed": fn, "precision": round(precision, 3), "recall": round(recall, 3),
            "type_accuracy": round(type_ok / tp, 3) if tp else None, "errors": errors}


def eval_hard_cases(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Tricky columns that are not in the demo catalog: no name hints, business contacts, near-miss formats."""
    threshold = float(cfg["pii_suggestion_threshold"])
    tp = fp = fn = tn = 0
    errors = []
    with open(ROOT / "evals" / "pii_hard_cases.csv", encoding="utf-8") as f:
        cases = list(csv.DictReader(f))
    for r in cases:
        s = score_column(Column("eval", "hard_cases", r["column"], "VARCHAR"), r["values"].split("|"))
        predicted = bool(s and s.confidence >= threshold and (r["is_pii"] != "yes" or s.pii_type == r["pii_type"]))
        flagged = bool(s and s.confidence >= threshold)
        if r["is_pii"] == "yes":
            if predicted:
                tp += 1
            else:
                fn += 1
                errors.append(f"missed: {r['column']} ({r['why_it_is_hard']})")
        elif flagged:
            fp += 1
            errors.append(f"false positive: {r['column']} ({r['why_it_is_hard']})")
        else:
            tn += 1
    return {"cases": len(cases), "precision": round(tp / (tp + fp), 3) if tp + fp else 1.0,
            "recall": round(tp / (tp + fn), 3) if tp + fn else 1.0, "true_positives": tp,
            "false_positives": fp, "missed": fn, "errors": errors}


def eval_quality(cat: Catalog, cfg: Dict[str, Any]) -> Dict[str, Any]:
    expected = DEFECTS
    rules = [r for r in cfg["quality_rules"] if r["id"] in RULE_TO_DEFECT]
    results = {r["id"]: r for r in run_rules(cat, rules)}
    rows = []
    for rid, defect in RULE_TO_DEFECT.items():
        found = results[rid]["failing_rows"]
        rows.append({"rule": rid, "defect": defect, "injected": expected[defect], "found": found,
                     "exact": found == expected[defect]})
    return {"rules": rows, "exact_matches": sum(r["exact"] for r in rows), "total": len(rows)}


def run(cat: Catalog, cfg: Dict[str, Any], write: bool = True) -> Dict[str, Any]:
    out = {"classifier": eval_classifier(cat, cfg), "hard_cases": eval_hard_cases(cfg),
           "quality": eval_quality(cat, cfg)}
    if write:
        (ROOT / "evals" / "results.json").write_text(json.dumps(out, indent=2))
    return out
