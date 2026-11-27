"""Checks every query before it runs. The model is treated as untrusted: nothing it writes reaches the database unless it is
a single read-only SELECT over the published tables, with no access to files or the network. Personal data is protected one
level lower: it is never copied into the database the agent opens (see publish.py)."""
from __future__ import annotations

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

from analyst.config import ROW_LIMIT, SCHEMA
from analyst.semantic import allowed_tables, pii_columns

WRITES = (exp.Insert, exp.Update, exp.Delete, exp.Create, exp.Drop, exp.Alter, exp.Merge, exp.Command, exp.Copy, exp.Pragma,
          exp.Set, exp.Use, exp.Transaction, exp.Commit, exp.Rollback, exp.Attach, exp.Detach, exp.TruncateTable, exp.Into)
BLOCKED_FUNCTIONS = ("read_", "glob", "getenv", "current_setting", "query", "which_secret", "duckdb_", "pragma_", "sniff_csv",
                     "parquet_", "iceberg_", "delta_", "sqlite_", "postgres_", "mysql_", "http", "load_", "install_")


class Blocked(ValueError):
    """The query broke a safety rule. It is refused, never repaired."""


class Invalid(ValueError):
    """The query is not usable SQL or names something that does not exist. The model may try again."""


def check(sql: str) -> str:
    """Return the query to run (with a row limit), or raise Blocked / Invalid."""
    try:
        statements = [s for s in sqlglot.parse(sql, read="duckdb") if s is not None]
    except SqlglotError as exc:
        raise Invalid(f"The SQL could not be parsed: {str(exc).splitlines()[0]}") from exc
    if len(statements) != 1:
        raise Blocked("Exactly one statement is allowed")
    tree = statements[0]
    if not isinstance(tree, (exp.Select, exp.SetOperation)):
        raise Blocked("Only SELECT queries are allowed")
    if any(isinstance(node, WRITES) for node in tree.walk()):
        raise Blocked("The query tries to change data or settings")

    ctes = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
    used = set()
    for table in tree.find_all(exp.Table):
        name, schema = table.name.lower(), table.db.lower()
        if not isinstance(table.this, exp.Identifier):
            raise Blocked("Table functions are not allowed")
        if not schema and name in ctes:
            continue
        if table.catalog or schema != SCHEMA or name not in allowed_tables():
            if schema in ("", SCHEMA) and name.isidentifier() and not table.this.quoted:
                raise Invalid(f"Unknown table '{table.sql()}'. Use {SCHEMA}.<table> with one of: {', '.join(sorted(allowed_tables()))}")
            raise Blocked(f"Access to '{table.sql()}' is not allowed")
        used.add(name)

    for func in tree.find_all(exp.Func):
        fname = (func.name if isinstance(func, exp.Anonymous) else func.sql_name()).lower()
        if fname.startswith(BLOCKED_FUNCTIONS):
            raise Blocked(f"The function '{fname}' is not allowed")

    pii = pii_columns()
    for node in tree.find_all(exp.Column, exp.Identifier):
        if node.name.lower() in pii:
            raise Blocked(f"'{node.name}' is personal data")
    return f"SELECT * FROM (\n{tree.sql(dialect='duckdb')}\n) AS answer LIMIT {ROW_LIMIT}"
