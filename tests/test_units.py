from steward_kit import sqlgen
from steward_kit.catalog import Column, DatabricksCatalog
from steward_kit.classify import mask, score_column
from steward_kit.quality import build_sql
from steward_kit.sources import infer_date_order, normalize_recalls, parse_date
from steward_kit.synthetic import is_valid_vin, make_vin, vin_check_digit
import random


def col(name, dtype="VARCHAR"):
    return Column("s", "t", name, dtype)


def test_vin_check_digit_matches_known_example():
    # Textbook example VIN 1M8GDM9AXKP042788 has check digit X
    assert vin_check_digit("1M8GDM9A0KP042788") == "X"
    assert is_valid_vin("1M8GDM9AXKP042788")
    assert not is_valid_vin("1M8GDM9A1KP042788")


def test_generated_vins_are_valid():
    rng = random.Random(1)
    assert all(is_valid_vin(make_vin(rng)) for _ in range(200))


def test_email_column_scores_high_and_examples_are_masked():
    s = score_column(col("email"), ["ana.ruiz@example.com", "j.lee@example.net"])
    assert s.pii_type == "email" and s.confidence == 1.0
    assert all("ana.ruiz" not in e for e in s.examples)


def test_value_evidence_without_name_hint():
    s = score_column(col("contact"), ["a@example.com", "b@example.org", "c@example.net"])
    assert s.pii_type == "email" and 0.6 <= s.confidence < 0.7


def test_name_alone_is_not_enough():
    s = score_column(col("vin_prefix"), ["1GNAXUEV0L", "1GCUYDED5M"])
    assert s is None or s.confidence < 0.5


def test_free_text_with_embedded_phone_is_flagged():
    vals = ["Loaner ready."] * 9 + ["Call the owner at (313) 555-0142 tomorrow."]
    s = score_column(col("customer_notes"), vals)
    assert s.pii_type == "free_text" and s.confidence >= 0.8
    assert "555-0142" not in " ".join(s.examples[0].split("-")[:-1])


def test_mask_hides_most_of_value():
    assert mask("fatima.young@example.net") == "f***@example.net"
    assert mask("(317) 555-0175") == "(***) ***-0175"


def test_date_order_inference():
    assert infer_date_order(["25/03/2021", "04/11/2020"]) == "dmy"
    assert infer_date_order(["03/25/2021"]) == "mdy"
    assert parse_date("25/03/2021", "dmy") == "2021-03-25"
    assert parse_date("2021-03-25T00:00:00") == "2021-03-25"
    assert parse_date("not a date") == ""


def test_recalls_are_deduplicated_per_vehicle():
    r = {"NHTSACampaignNumber": "24V001000", "ReportReceivedDate": "25/03/2024", "Make": "CHEVROLET",
         "Model": "EQUINOX", "ModelYear": "2024", "Remedy": "Fix"}
    rows = normalize_recalls([("CHEVROLET", "EQUINOX", 2024, {"results": [r, dict(r)]})])
    assert len(rows) == 1 and rows[0]["report_received_date"] == "2024-03-25"


def test_sql_literals_escape_quotes_and_backslashes():
    assert sqlgen.literal("O'Brien\\x") == "'O\\'Brien\\\\x'"
    assert sqlgen.ident("my col") == "`my col`"
    sql = sqlgen.set_column_tags("workspace", "customer_care", "owner_contacts", "email",
                                 {"classification": "restricted", "pii_type": "email"})
    assert sql == ("ALTER TABLE workspace.customer_care.owner_contacts ALTER COLUMN email "
                   "SET TAGS ('classification' = 'restricted', 'pii_type' = 'email');")


def test_databricks_quality_sql_uses_rlike_and_three_part_names():
    dbx = DatabricksCatalog("workspace", connection=False)
    count_sql, rows_sql = build_sql(dbx, {"id": "X", "table": "customer_care.owner_contacts", "column": "email",
                                          "check": "pattern", "pattern": "[^@]+@[^@]+"})
    assert "workspace.customer_care.owner_contacts" in count_sql and "RLIKE '^(?:[^@]+@[^@]+)$'" in count_sql
    assert rows_sql.endswith("LIMIT 100")


class _FakeCursor:
    def __init__(self, log):
        self.log, self.rows = log, []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.log.append(sql)
        if "information_schema.table_tags" in sql:
            self.rows = [("customer_care", "owner_contacts", "steward", "priya.shah@example.com")]
        elif "information_schema.tables" in sql:
            self.rows = [("customer_care", "owner_contacts", None), ("information_schema", "tables", None)]
        elif "information_schema.column_tags" in sql:
            self.rows = [("customer_care", "owner_contacts", "customer_id", "classification", "internal")]
        elif "information_schema.columns" in sql:
            self.rows = [("customer_care", "owner_contacts", "customer_id", "STRING", "Internal id", 1),
                         ("customer_care", "owner_contacts", "email", "STRING", None, 2)]
        elif sql.startswith("SELECT COUNT(*)"):
            self.rows = [(1206,)]
        else:
            self.rows = [("a@example.com",), ("b@example.com",)]

    def fetchall(self):
        return self.rows


class _FakeConnection:
    def __init__(self):
        self.log = []

    def cursor(self):
        return _FakeCursor(self.log)


def test_databricks_adapter_reads_unity_catalog_information_schema():
    con = _FakeConnection()
    cat = DatabricksCatalog("workspace", connection=con)
    tables = cat.tables()
    assert [t.key for t in tables] == ["customer_care.owner_contacts"]
    assert tables[0].tags == {"steward": "priya.shah@example.com"} and tables[0].row_count == 1206
    cols = {c.name: c for c in cat.columns()}
    assert cols["customer_id"].tags == {"classification": "internal"} and cols["email"].comment is None
    assert cat.sample("customer_care", "owner_contacts", "email", 5) == ["a@example.com", "b@example.com"]
    assert any("workspace.information_schema.tables" in s for s in con.log)
    assert any("CAST(email AS STRING) FROM workspace.customer_care.owner_contacts" in s for s in con.log)


def test_fetch_skips_vehicles_nhtsa_has_no_data_for(tmp_path):
    import shutil
    from fixture_http import fixture_get
    from steward_kit.config import ROOT
    from steward_kit.sources import NoData, fetch_all

    def get(url):
        if "SILVERADO" in url and "2025" in url:
            raise NoData("HTTP Error 400: Bad Request")
        if "TAHOE" in url and "complaints" in url:
            raise ConnectionError("reset")
        return fixture_get(url)

    shutil.copy(ROOT / "data" / "raw" / "epa_vehicles_gm.csv", tmp_path / "epa_vehicles_gm.csv")
    prov = fetch_all(tmp_path, get=get, pause=0)
    assert "2025 CHEVROLET SILVERADO 1500" in prov["nhtsa_recalls"]["vehicles_without_data"]
    assert len(prov["nhtsa_recalls"]["failed_requests"]) == 5
    assert (tmp_path / "nhtsa_recalls.csv").exists()


def test_toll_free_hotlines_in_recall_notes_are_not_personal_data():
    notes = ["Owners may also contact the NHTSA Vehicle Safety Hotline at 1-888-327-4236 (TTY 1-800-424-9153)."] * 20
    s = score_column(col("notes"), notes)
    assert s is None or s.confidence < 0.5
    s = score_column(col("customer_notes"), notes[:19] + ["Call me at (313) 555-0142."])
    assert s.pii_type == "free_text"
