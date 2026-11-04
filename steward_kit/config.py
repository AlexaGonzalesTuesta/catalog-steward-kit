from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml

ROOT = Path(__file__).resolve().parent.parent

REQUIRED = ["catalog", "tags", "classification_levels", "domains", "stewards", "quality_rules"]


def load_config(path: str | Path = ROOT / "governance.yml") -> Dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    missing = [k for k in REQUIRED if k not in cfg]
    if missing:
        raise ValueError(f"governance.yml is missing: {', '.join(missing)}")
    for level in (cfg.get("pii_level", "restricted"), cfg.get("not_pii_level", "internal")):
        if level not in cfg["classification_levels"]:
            raise ValueError(f"'{level}' is not in classification_levels")
    stewards = {s["email"] for s in cfg["stewards"]}
    for key, d in cfg["domains"].items():
        if d["steward"] not in stewards:
            raise ValueError(f"Domain {key} names steward {d['steward']} who is not in stewards")
    ids = [r["id"] for r in cfg["quality_rules"]]
    if len(ids) != len(set(ids)):
        raise ValueError("Quality rule ids must be unique")
    cfg.setdefault("pii_level", "restricted")
    cfg.setdefault("not_pii_level", "internal")
    cfg.setdefault("pii_suggestion_threshold", 0.5)
    cfg.setdefault("display_name", cfg["catalog"])
    return cfg
