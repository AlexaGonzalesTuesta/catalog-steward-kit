"""Databricks SQL for the changes a steward approves. Pure functions so they are easy to test."""
from __future__ import annotations

import re
from typing import Dict

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def ident(name: str) -> str:
    """Quote an identifier with backticks unless it is a plain name."""
    if _IDENT.match(name):
        return name
    return "`" + name.replace("`", "``") + "`"


def literal(value: str) -> str:
    return "'" + str(value).replace("\\", "\\\\").replace("'", "\\'") + "'"


def fqn(catalog: str, schema: str, table: str) -> str:
    return ".".join(ident(p) for p in (catalog, schema, table))


def _tag_list(tags: Dict[str, str]) -> str:
    return ", ".join(f"{literal(k)} = {literal(v)}" for k, v in tags.items())


def set_table_tags(catalog: str, schema: str, table: str, tags: Dict[str, str]) -> str:
    return f"ALTER TABLE {fqn(catalog, schema, table)} SET TAGS ({_tag_list(tags)});"


def set_column_tags(catalog: str, schema: str, table: str, column: str, tags: Dict[str, str]) -> str:
    return (f"ALTER TABLE {fqn(catalog, schema, table)} ALTER COLUMN {ident(column)} "
            f"SET TAGS ({_tag_list(tags)});")


def comment_table(catalog: str, schema: str, table: str, text: str) -> str:
    return f"COMMENT ON TABLE {fqn(catalog, schema, table)} IS {literal(text)};"


def comment_column(catalog: str, schema: str, table: str, column: str, text: str) -> str:
    return (f"ALTER TABLE {fqn(catalog, schema, table)} ALTER COLUMN {ident(column)} "
            f"COMMENT {literal(text)};")
