"""Read catalog metadata from Unity Catalog (Databricks) or a local DuckDB copy.

Both adapters return the same shapes, so scanning, classification and quality checks
run the same way against a real workspace or the local demo catalog.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import sqlgen

SYSTEM_SCHEMAS = {"information_schema", "_uc", "default", "pg_catalog", "main"}


@dataclass
class Table:
    schema: str
    name: str
    comment: Optional[str] = None
    tags: Dict[str, str] = field(default_factory=dict)
    row_count: Optional[int] = None

    @property
    def key(self) -> str:
        return f"{self.schema}.{self.name}"


@dataclass
class Column:
    schema: str
    table: str
    name: str
    data_type: str
    comment: Optional[str] = None
    tags: Dict[str, str] = field(default_factory=dict)
    position: int = 0

    @property
    def key(self) -> str:
        return f"{self.schema}.{self.table}.{self.name}"

    @property
    def table_key(self) -> str:
        return f"{self.schema}.{self.table}"


class Catalog:
    dialect = "generic"
    name = ""

    def query(self, sql: str, params: Sequence[Any] = ()) -> List[Tuple]:
        raise NotImplementedError

    def execute(self, sql: str, params: Sequence[Any] = ()) -> None:
        raise NotImplementedError

    def tables(self) -> List[Table]:
        raise NotImplementedError

    def columns(self) -> List[Column]:
        raise NotImplementedError

    def table_ref(self, schema: str, table: str) -> str:
        raise NotImplementedError

    def sample(self, schema: str, table: str, column: str, limit: int = 300) -> List[str]:
        ref = self.table_ref(schema, table)
        col = sqlgen.ident(column)
        rows = self.query(f"SELECT CAST({col} AS VARCHAR(4000)) FROM {ref} "
                          f"WHERE {col} IS NOT NULL LIMIT {int(limit)}")
        return [r[0] for r in rows if r[0] is not None]

    def lit(self, value: Any) -> str:
        raise NotImplementedError

    def regex_mismatch_sql(self, column_sql: str, pattern: str) -> str:
        raise NotImplementedError


class DuckDBCatalog(Catalog):
    """Local catalog. Comments are native DuckDB comments; tags live in the _uc schema,
    mirroring Unity Catalog's information_schema.table_tags and column_tags."""

    dialect = "duckdb"

    def __init__(self, path: str, catalog_name: str = "workspace", read_only: bool = False):
        import duckdb
        self.path = path
        self.name = catalog_name
        self.con = duckdb.connect(path, read_only=read_only)
        if not read_only:
            self.con.execute("CREATE SCHEMA IF NOT EXISTS _uc")
            self.con.execute("CREATE TABLE IF NOT EXISTS _uc.table_tags (schema_name VARCHAR, table_name VARCHAR,"
                             " tag_name VARCHAR, tag_value VARCHAR, PRIMARY KEY (schema_name, table_name, tag_name))")
            self.con.execute("CREATE TABLE IF NOT EXISTS _uc.column_tags (schema_name VARCHAR, table_name VARCHAR,"
                             " column_name VARCHAR, tag_name VARCHAR, tag_value VARCHAR,"
                             " PRIMARY KEY (schema_name, table_name, column_name, tag_name))")

    def close(self) -> None:
        self.con.close()

    def query(self, sql: str, params: Sequence[Any] = ()) -> List[Tuple]:
        return self.con.execute(sql, list(params)).fetchall()

    def execute(self, sql: str, params: Sequence[Any] = ()) -> None:
        self.con.execute(sql, list(params))

    def table_ref(self, schema: str, table: str) -> str:
        return f"{sqlgen.ident(schema)}.{sqlgen.ident(table)}"

    def lit(self, value: Any) -> str:
        return "'" + str(value).replace("'", "''") + "'"

    def regex_mismatch_sql(self, column_sql: str, pattern: str) -> str:
        return f"NOT regexp_full_match({column_sql}, {self.lit(pattern)})"

    def _tags(self) -> Tuple[Dict[Tuple[str, str], Dict[str, str]], Dict[Tuple[str, str, str], Dict[str, str]]]:
        tt: Dict[Tuple[str, str], Dict[str, str]] = {}
        for s, t, k, v in self.query("SELECT schema_name, table_name, tag_name, tag_value FROM _uc.table_tags"):
            tt.setdefault((s, t), {})[k] = v
        ct: Dict[Tuple[str, str, str], Dict[str, str]] = {}
        for s, t, c, k, v in self.query(
                "SELECT schema_name, table_name, column_name, tag_name, tag_value FROM _uc.column_tags"):
            ct.setdefault((s, t, c), {})[k] = v
        return tt, ct

    def tables(self) -> List[Table]:
        tt, _ = self._tags()
        out = []
        for s, t, comment in self.query(
                "SELECT schema_name, table_name, comment FROM duckdb_tables() "
                "WHERE database_name = current_database() ORDER BY schema_name, table_name"):
            if s in SYSTEM_SCHEMAS:
                continue
            n = self.query(f"SELECT COUNT(*) FROM {self.table_ref(s, t)}")[0][0]
            out.append(Table(s, t, comment or None, tt.get((s, t), {}), n))
        return out

    def columns(self) -> List[Column]:
        _, ct = self._tags()
        out = []
        for s, t, c, dt, comment, pos in self.query(
                "SELECT schema_name, table_name, column_name, data_type, comment, column_index FROM duckdb_columns() "
                "WHERE database_name = current_database() ORDER BY schema_name, table_name, column_index"):
            if s in SYSTEM_SCHEMAS:
                continue
            out.append(Column(s, t, c, dt, comment or None, ct.get((s, t, c), {}), pos))
        return out

    # Writes used by the demo loader to recreate a catalog's existing metadata.
    def set_table_tags(self, schema: str, table: str, tags: Dict[str, str]) -> None:
        for k, v in tags.items():
            self.execute("INSERT OR REPLACE INTO _uc.table_tags VALUES (?, ?, ?, ?)", (schema, table, k, v))

    def set_column_tags(self, schema: str, table: str, column: str, tags: Dict[str, str]) -> None:
        for k, v in tags.items():
            self.execute("INSERT OR REPLACE INTO _uc.column_tags VALUES (?, ?, ?, ?, ?)", (schema, table, column, k, v))

    def comment_table(self, schema: str, table: str, text: str) -> None:
        lit = "'" + text.replace("'", "''") + "'"
        self.execute(f"COMMENT ON TABLE {self.table_ref(schema, table)} IS {lit}")

    def comment_column(self, schema: str, table: str, column: str, text: str) -> None:
        lit = "'" + text.replace("'", "''") + "'"
        self.execute(f"COMMENT ON COLUMN {self.table_ref(schema, table)}.{sqlgen.ident(column)} IS {lit}")


class DatabricksCatalog(Catalog):
    """Unity Catalog through a Databricks SQL warehouse.

    Needs: pip install databricks-sql-connector, and the environment variables
    DATABRICKS_HOST, DATABRICKS_HTTP_PATH and DATABRICKS_TOKEN.
    """

    dialect = "databricks"

    def __init__(self, catalog_name: str, connection: Any = None):
        self.name = catalog_name
        if connection is None:
            from databricks import sql  # type: ignore
            host = os.environ["DATABRICKS_HOST"].replace("https://", "").rstrip("/")
            connection = sql.connect(server_hostname=host,
                                     http_path=os.environ["DATABRICKS_HTTP_PATH"],
                                     access_token=os.environ["DATABRICKS_TOKEN"])
        self.con = connection

    def close(self) -> None:
        self.con.close()

    def query(self, sql: str, params: Sequence[Any] = ()) -> List[Tuple]:
        with self.con.cursor() as cur:
            cur.execute(sql, list(params) if params else None)
            return [tuple(r) for r in cur.fetchall()]

    def execute(self, sql: str, params: Sequence[Any] = ()) -> None:
        with self.con.cursor() as cur:
            cur.execute(sql, list(params) if params else None)

    def table_ref(self, schema: str, table: str) -> str:
        return sqlgen.fqn(self.name, schema, table)

    def lit(self, value: Any) -> str:
        return sqlgen.literal(value)

    def regex_mismatch_sql(self, column_sql: str, pattern: str) -> str:
        return f"NOT ({column_sql} RLIKE {sqlgen.literal('^(?:' + pattern + ')$')})"

    def sample(self, schema: str, table: str, column: str, limit: int = 300) -> List[str]:
        ref = self.table_ref(schema, table)
        col = sqlgen.ident(column)
        rows = self.query(f"SELECT CAST({col} AS STRING) FROM {ref} WHERE {col} IS NOT NULL LIMIT {int(limit)}")
        return [r[0] for r in rows if r[0] is not None]

    def _is(self) -> str:
        return f"{sqlgen.ident(self.name)}.information_schema"

    def tables(self) -> List[Table]:
        tt: Dict[Tuple[str, str], Dict[str, str]] = {}
        for s, t, k, v in self.query(f"SELECT schema_name, table_name, tag_name, tag_value FROM {self._is()}.table_tags"):
            tt.setdefault((s, t), {})[k] = v
        out = []
        for s, t, comment in self.query(
                f"SELECT table_schema, table_name, comment FROM {self._is()}.tables "
                f"WHERE table_type IN ('MANAGED', 'EXTERNAL') ORDER BY table_schema, table_name"):
            if s in SYSTEM_SCHEMAS:
                continue
            n = self.query(f"SELECT COUNT(*) FROM {self.table_ref(s, t)}")[0][0]
            out.append(Table(s, t, comment or None, tt.get((s, t), {}), n))
        return out

    def columns(self) -> List[Column]:
        ct: Dict[Tuple[str, str, str], Dict[str, str]] = {}
        for s, t, c, k, v in self.query(
                f"SELECT schema_name, table_name, column_name, tag_name, tag_value FROM {self._is()}.column_tags"):
            ct.setdefault((s, t, c), {})[k] = v
        out = []
        for s, t, c, dt, comment, pos in self.query(
                f"SELECT table_schema, table_name, column_name, data_type, comment, ordinal_position "
                f"FROM {self._is()}.columns ORDER BY table_schema, table_name, ordinal_position"):
            if s in SYSTEM_SCHEMAS:
                continue
            out.append(Column(s, t, c, dt, comment or None, ct.get((s, t, c), {}), pos))
        return out


def open_catalog(target: str, catalog_name: str, db_path: str = "demo/catalog.duckdb") -> Catalog:
    if target == "duckdb":
        if not os.path.exists(db_path):
            raise FileNotFoundError(f"{db_path} not found. Run: python -m steward_kit build-demo")
        return DuckDBCatalog(db_path, catalog_name, read_only=True)
    if target == "databricks":
        missing = [v for v in ("DATABRICKS_HOST", "DATABRICKS_HTTP_PATH", "DATABRICKS_TOKEN") if not os.environ.get(v)]
        if missing:
            raise EnvironmentError("Set these environment variables first: " + ", ".join(missing))
        return DatabricksCatalog(catalog_name)
    raise ValueError("target must be duckdb or databricks")
