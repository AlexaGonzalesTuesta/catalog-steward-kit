import json

import pytest

from steward_kit import evals
from steward_kit.demo import databricks_sql
from steward_kit.quality import run_rules
from steward_kit.scan import scan
from steward_kit.synthetic import DEFECTS


def test_demo_catalog_has_all_tables(demo_catalog):
    keys = {t.key for t in demo_catalog.tables()}
    assert keys == {"vehicle_safety.recalls", "vehicle_safety.complaints", "fuel_economy.vehicles",
                    "customer_care.owner_contacts", "dealer_service.service_appointments"}


def test_starting_metadata_is_loaded(demo_catalog):
    t = {t.key: t for t in demo_catalog.tables()}
    assert t["vehicle_safety.recalls"].tags["classification"] == "public"
    assert t["dealer_service.service_appointments"].comment is None


def test_scan_finds_expected_work(demo_catalog, cfg):
    snap = scan(demo_catalog, cfg)
    pii = {i["object"] for i in snap["items"] if i["type"] == "pii"}
    assert "customer_care.owner_contacts.email" in pii
    assert "dealer_service.service_appointments.customer_notes" in pii
    assert "customer_care.owner_contacts.customer_id" not in pii  # already tagged internal
    assert not any(o.startswith("vehicle_safety") or o.startswith("fuel_economy") for o in pii)
    owners = {i["object"] for i in snap["items"] if i["type"] == "owner"}
    assert "vehicle_safety.recalls" not in owners and "vehicle_safety.complaints" in owners
    assert snap["metrics"]["tables_ready"] == 1
    json.dumps(snap)  # snapshot must be serializable


def test_work_items_have_runnable_sql_templates(demo_catalog, cfg):
    snap = scan(demo_catalog, cfg)
    for i in snap["items"]:
        if i["type"] in ("owner", "describe", "classify"):
            assert "{value}" in i["sql"] and i["sql"].startswith(("ALTER TABLE workspace.", "COMMENT ON TABLE workspace."))
        if i["type"] == "pii":
            assert i["sql_confirm"].startswith("ALTER TABLE workspace.") and "'restricted'" in i["sql_confirm"]


def test_quality_rules_find_injected_defects(demo_catalog, cfg):
    res = {r["id"]: r for r in run_rules(demo_catalog, cfg["quality_rules"])}
    assert res["CC-01"]["failing_rows"] == DEFECTS["duplicate_customer_id"]
    assert res["DS-01"]["failing_rows"] == DEFECTS["orphan_recall_campaign"]
    assert res["FE-02"]["status"] == "pass"
    assert res["VS-03"]["failing_rows"] == 1  # the fixture has one recall without a remedy


def test_broken_rule_reports_error_instead_of_crashing(demo_catalog):
    res = run_rules(demo_catalog, [{"id": "BAD", "table": "fuel_economy.vehicles", "column": "nope", "check": "not_null"}])
    assert res[0]["status"] == "error"


def test_evals_meet_thresholds(demo_catalog, cfg):
    out = evals.run(demo_catalog, cfg, write=False)
    assert out["classifier"]["precision"] >= 0.9 and out["classifier"]["recall"] >= 0.9
    assert out["hard_cases"]["recall"] >= 0.8
    assert out["quality"]["exact_matches"] == out["quality"]["total"]


def test_databricks_scripts_cover_every_table(cfg):
    sql = databricks_sql(cfg["catalog"])
    assert sql["02_load_tables.sql"].count("CREATE OR REPLACE TABLE") == 5
    assert "read_files('/Volumes/workspace/steward_kit/raw/nhtsa_recalls.csv'" in sql["02_load_tables.sql"]
    assert "SET TAGS" in sql["03_starting_metadata.sql"]


def test_config_rejects_unknown_steward(tmp_path):
    from steward_kit.config import load_config
    p = tmp_path / "g.yml"
    p.write_text("catalog: c\ntags: {}\nclassification_levels: [internal, restricted]\n"
                 "domains: {a: {name: A, steward: x@example.com, default_owner: o}}\nstewards: []\nquality_rules: []\n")
    with pytest.raises(ValueError):
        load_config(p)
