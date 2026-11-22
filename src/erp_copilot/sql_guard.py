"""Static checks that LLM-generated SQL is a single read-only query over the marts schema.

This is the first of two layers; the warehouse connection itself is also read-only with
external file access disabled (see warehouse.py).
"""
from __future__ import annotations

import sqlglot
from sqlglot import exp

ALLOWED_SCHEMA = "marts"
FORBIDDEN_FUNCTION_PREFIXES = ("read_", "glob", "query", "duckdb_", "pragma_", "sniff_", "parquet_")
FORBIDDEN_NODES = (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Alter,
                   exp.Command, exp.Copy, exp.Merge, exp.Set, exp.Use, exp.Pragma)


class SqlGuardError(ValueError):
    """The SQL is not allowed; the message is safe to show to the user or the LLM."""


def _function_name(node: exp.Func) -> str:
    return (node.name if isinstance(node, exp.Anonymous) else node.sql_name()).lower()


def validate_sql(sql: str, allowed_tables: set[str], max_rows: int = 200) -> str:
    """Return a normalized, row-limited SQL string, or raise SqlGuardError."""
    if not sql or not sql.strip():
        raise SqlGuardError("empty SQL")
    try:
        statements = [s for s in sqlglot.parse(sql, read="duckdb") if s is not None]
    except sqlglot.errors.ParseError as exc:
        raise SqlGuardError(f"SQL parse error: {str(exc).splitlines()[0]}") from None
    if len(statements) != 1:
        raise SqlGuardError(f"exactly one statement is allowed, got {len(statements)}")
    stmt = statements[0]
    if not isinstance(stmt, exp.Query):
        raise SqlGuardError(f"only SELECT queries are allowed, got {stmt.key.upper()}")

    for node in stmt.walk():
        if isinstance(node, FORBIDDEN_NODES):
            raise SqlGuardError(f"statement type not allowed: {node.key.upper()}")
        if isinstance(node, exp.Func) and _function_name(node).startswith(FORBIDDEN_FUNCTION_PREFIXES):
            raise SqlGuardError(f"function not allowed: {_function_name(node)}")

    cte_names = {cte.alias_or_name.lower() for cte in stmt.find_all(exp.CTE)}
    for table in stmt.find_all(exp.Table):
        if isinstance(table.this, exp.Func):
            continue  # table functions were checked above
        name, schema = table.name.lower(), table.db.lower()
        if not schema and name in cte_names:
            continue
        if schema and schema != ALLOWED_SCHEMA:
            raise SqlGuardError(f"schema not allowed: {schema} (use {ALLOWED_SCHEMA}.<table>)")
        if table.catalog:
            raise SqlGuardError("catalog-qualified table names are not allowed")
        if name not in allowed_tables:
            raise SqlGuardError(f"unknown table: {name}; allowed: {', '.join(sorted(allowed_tables))}")

    if stmt.args.get("limit") is None:
        stmt = stmt.limit(max_rows)
    return stmt.sql(dialect="duckdb")
