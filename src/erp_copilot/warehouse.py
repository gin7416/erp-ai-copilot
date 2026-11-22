"""Read-only access to the DuckDB warehouse built by dbt."""
from __future__ import annotations

import datetime as dt
import decimal
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb

from .sql_guard import ALLOWED_SCHEMA, validate_sql


@dataclass
class QueryResult:
    sql: str
    columns: list[str]
    rows: list[list[Any]]

    def to_dict(self, max_rows: int | None = None) -> dict[str, Any]:
        rows = self.rows if max_rows is None else self.rows[:max_rows]
        return {"sql": self.sql, "columns": self.columns, "rows": [[_jsonable(v) for v in r] for r in rows],
                "row_count": len(self.rows)}


def _jsonable(value: Any) -> Any:
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    return value


class Warehouse:
    def __init__(self, path: Path, timeout_s: float = 15.0):
        self.path = Path(path)
        self.timeout_s = timeout_s
        self._tables: set[str] | None = None

    def _connect(self) -> duckdb.DuckDBPyConnection:
        if not self.path.exists():
            raise FileNotFoundError(f"warehouse not built yet: {self.path} (run `python -m erp_copilot.pipeline all`)")
        con = duckdb.connect(str(self.path), read_only=True)
        con.execute(f"SET search_path = '{ALLOWED_SCHEMA}'")
        con.execute("SET enable_external_access = false")  # no read_csv/httpfs/attach of other files
        con.execute("SET lock_configuration = true")
        return con

    def mart_tables(self) -> set[str]:
        if self._tables is None:
            with self._connect() as con:
                rows = con.execute(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema = ?", [ALLOWED_SCHEMA]
                ).fetchall()
            self._tables = {r[0].lower() for r in rows}
        return self._tables

    def columns(self) -> dict[str, list[tuple[str, str]]]:
        with self._connect() as con:
            rows = con.execute(
                "SELECT table_name, column_name, data_type FROM information_schema.columns "
                "WHERE table_schema = ? ORDER BY table_name, ordinal_position", [ALLOWED_SCHEMA]
            ).fetchall()
        out: dict[str, list[tuple[str, str]]] = {}
        for table, col, dtype in rows:
            out.setdefault(table, []).append((col, dtype))
        return out

    def run(self, sql: str, max_rows: int = 200) -> QueryResult:
        """Validate with the SQL guard, then execute on a read-only connection with a timeout."""
        safe_sql = validate_sql(sql, self.mart_tables(), max_rows=max_rows)
        with self._connect() as con:
            timer = threading.Timer(self.timeout_s, con.interrupt)
            timer.start()
            try:
                cur = con.execute(safe_sql)
                columns = [d[0] for d in cur.description]
                rows = [list(r) for r in cur.fetchall()]
            finally:
                timer.cancel()
        return QueryResult(safe_sql, columns, rows)
