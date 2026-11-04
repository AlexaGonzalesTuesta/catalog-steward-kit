"""Build the demo catalog: real NHTSA and EPA tables plus two synthetic customer tables.

The same table definitions produce the local DuckDB catalog and the Databricks SQL scripts,
so the demo and your Databricks workspace hold identical data and starting metadata.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Dict, List, Tuple

import yaml

from . import sqlgen, synthetic
from .catalog import DuckDBCatalog
from .config import ROOT

SEED = ROOT / "demo" / "seed_metadata.yml"
VOLUME = "/Volumes/{catalog}/steward_kit/raw"

# table -> (source file, [(column, type, source column)])
TABLES: Dict[str, Tuple[str, List[Tuple[str, str, str]]]] = {
    "vehicle_safety.recalls": ("raw/nhtsa_recalls.csv", [
        ("campaign_number", "string", "campaign_number"), ("manufacturer", "string", "manufacturer"),
        ("make", "string", "make"), ("model", "string", "model"), ("model_year", "int", "model_year"),
        ("component", "string", "component"), ("summary", "string", "summary"),
        ("consequence", "string", "consequence"), ("remedy", "string", "remedy"), ("notes", "string", "notes"),
        ("report_received_date", "date", "report_received_date"), ("park_it", "boolean", "park_it"),
        ("park_outside", "boolean", "park_outside"), ("over_the_air_update", "boolean", "over_the_air_update")]),
    "vehicle_safety.complaints": ("raw/nhtsa_complaints.csv", [
        ("odi_number", "string", "odi_number"), ("manufacturer", "string", "manufacturer"),
        ("make", "string", "make"), ("model", "string", "model"), ("model_year", "int", "model_year"),
        ("crash", "boolean", "crash"), ("fire", "boolean", "fire"), ("injuries", "int", "injuries"),
        ("deaths", "int", "deaths"), ("incident_date", "date", "incident_date"),
        ("filed_date", "date", "filed_date"), ("vin_prefix", "string", "vin_prefix"),
        ("components", "string", "components"), ("summary", "string", "summary")]),
    "fuel_economy.vehicles": ("raw/epa_vehicles_gm.csv", [
        ("vehicle_id", "int", "id"), ("model_year", "int", "year"), ("make", "string", "make"),
        ("model", "string", "model"), ("vehicle_class", "string", "VClass"), ("drive", "string", "drive"),
        ("transmission", "string", "trany"), ("cylinders", "int", "cylinders"),
        ("displacement_l", "double", "displ"), ("fuel_type", "string", "fuelType"),
        ("alt_fuel_type", "string", "atvType"), ("city_mpg", "int", "city08"),
        ("highway_mpg", "int", "highway08"), ("combined_mpg", "int", "comb08"),
        ("co2_grams_per_mile", "double", "co2TailpipeGpm"), ("annual_fuel_cost_usd", "int", "fuelCost08"),
        ("ev_range_miles", "int", "range")]),
    "customer_care.owner_contacts": ("synthetic/owner_contacts.csv", [
        ("customer_id", "string", "customer_id"), ("first_name", "string", "first_name"),
        ("last_name", "string", "last_name"), ("email", "string", "email"), ("phone", "string", "phone"),
        ("street_address", "string", "street_address"), ("city", "string", "city"),
        ("state", "string", "state"), ("zip", "string", "zip"), ("vin", "string", "vin"),
        ("preferred_dealer", "string", "preferred_dealer"), ("marketing_opt_in", "boolean", "marketing_opt_in"),
        ("created_at", "date", "created_at")]),
    "dealer_service.service_appointments": ("synthetic/service_appointments.csv", [
        ("appointment_id", "string", "appointment_id"), ("vin", "string", "vin"),
        ("dealer_code", "string", "dealer_code"), ("appointment_date", "date", "appointment_date"),
        ("service_type", "string", "service_type"), ("recall_campaign_number", "string", "recall_campaign_number"),
        ("status", "string", "status"), ("completed_at", "date", "completed_at"),
        ("customer_notes", "string", "customer_notes")]),
}

DUCK_TYPES = {"string": "VARCHAR", "int": "INTEGER", "date": "DATE", "boolean": "BOOLEAN", "double": "DOUBLE"}
DBX_TYPES = {"string": "STRING", "int": "INT", "date": "DATE", "boolean": "BOOLEAN", "double": "DOUBLE"}


def _select(cols: List[Tuple[str, str, str]], types: Dict[str, str], quote) -> str:
    parts = []
    for name, typ, src in cols:
        s = quote(src)
        if typ == "string":
            parts.append(f"NULLIF(TRIM({s}), '') AS {name}")
        else:
            parts.append(f"TRY_CAST(NULLIF(TRIM({s}), '') AS {types[typ]}) AS {name}")
    return ",\n    ".join(parts)


def write_synthetic(data_dir: Path = ROOT / "data") -> Dict[str, int]:
    with open(data_dir / "raw" / "nhtsa_recalls.csv", encoding="utf-8") as f:
        campaigns = [r["campaign_number"] for r in csv.DictReader(f)]
    owners, appts = synthetic.build(campaigns)
    syn = data_dir / "synthetic"
    syn.mkdir(parents=True, exist_ok=True)
    for name, rows in (("owner_contacts", owners), ("service_appointments", appts)):
        with open(syn / f"{name}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    (syn / "defects.json").write_text(json.dumps(synthetic.DEFECTS, indent=2))
    return {"owner_contacts": len(owners), "service_appointments": len(appts)}


def load_seed() -> dict:
    with open(SEED, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def build_duckdb(path: str = str(ROOT / "demo" / "catalog.duckdb"), catalog_name: str = "workspace",
                 data_dir: Path = ROOT / "data") -> DuckDBCatalog:
    missing = [p for p, _ in TABLES.values() if p.startswith("raw/") and not (data_dir / p).exists()]
    if missing:
        raise FileNotFoundError("Missing " + ", ".join("data/" + m for m in missing) + ". Run: python -m steward_kit fetch")
    write_synthetic(data_dir)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    if Path(path).exists():
        Path(path).unlink()
    cat = DuckDBCatalog(path, catalog_name)
    for key, (src, cols) in TABLES.items():
        schema, table = key.split(".")
        cat.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
        file = str(data_dir / src).replace("\\", "/")
        cat.execute(f"CREATE TABLE {schema}.{table} AS SELECT\n    {_select(cols, DUCK_TYPES, lambda c: chr(34) + c + chr(34))}\n"
                    f"FROM read_csv('{file}', header = true, all_varchar = true, quote = '\"', escape = '\"')")
    seed = load_seed()
    for key, meta in (seed.get("tables") or {}).items():
        schema, table = key.split(".")
        meta = meta or {}
        if meta.get("comment"):
            cat.comment_table(schema, table, meta["comment"])
        if meta.get("tags"):
            cat.set_table_tags(schema, table, meta["tags"])
        for col, text in (meta.get("columns") or {}).items():
            cat.comment_column(schema, table, col, text)
        for col, tags in (meta.get("column_tags") or {}).items():
            cat.set_column_tags(schema, table, col, tags)
    return cat


def databricks_sql(catalog_name: str = "workspace") -> Dict[str, str]:
    """SQL scripts to recreate the demo catalog in a Databricks workspace."""
    vol = VOLUME.format(catalog=catalog_name)
    schemas = sorted({k.split(".")[0] for k in TABLES})
    setup = ["-- 1. Run once. Creates the schemas and the volume you upload the CSV files to.",
             f"USE CATALOG {sqlgen.ident(catalog_name)};",
             "CREATE SCHEMA IF NOT EXISTS steward_kit COMMENT 'Landing area for the Catalog Steward Kit demo files';",
             "CREATE VOLUME IF NOT EXISTS steward_kit.raw COMMENT 'Raw CSV files from NHTSA, EPA and the synthetic generator';"]
    setup += [f"CREATE SCHEMA IF NOT EXISTS {s};" for s in schemas]
    load = ["-- 2. Run after uploading the five CSV files to " + vol,
            f"USE CATALOG {sqlgen.ident(catalog_name)};"]
    for key, (src, cols) in TABLES.items():
        fname = src.split("/")[-1]
        load.append(f"\nCREATE OR REPLACE TABLE {key} AS SELECT\n    {_select(cols, DBX_TYPES, lambda c: '`' + c + '`')}\n"
                    f"FROM read_files('{vol}/{fname}', format => 'csv', header => true, inferSchema => false,\n"
                    f"                escape => '\"', multiLine => true);")
    seed = ["-- 3. Recreates the starting metadata (comments and tags) the demo begins with."]
    for key, meta in (load_seed().get("tables") or {}).items():
        schema, table = key.split(".")
        meta = meta or {}
        if meta.get("comment"):
            seed.append(sqlgen.comment_table(catalog_name, schema, table, meta["comment"]))
        if meta.get("tags"):
            seed.append(sqlgen.set_table_tags(catalog_name, schema, table, meta["tags"]))
        for col, text in (meta.get("columns") or {}).items():
            seed.append(sqlgen.comment_column(catalog_name, schema, table, col, text))
        for col, tags in (meta.get("column_tags") or {}).items():
            seed.append(sqlgen.set_column_tags(catalog_name, schema, table, col, tags))
    return {"01_setup.sql": "\n".join(setup) + "\n", "02_load_tables.sql": "\n".join(load) + "\n",
            "03_starting_metadata.sql": "\n".join(seed) + "\n"}
