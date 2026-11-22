import duckdb
import pytest

from erp_copilot.sql_guard import SqlGuardError, validate_sql

TABLES = {"fct_sales", "dim_customers"}


@pytest.mark.parametrize("sql", [
    "DROP TABLE marts.fct_sales",
    "DELETE FROM marts.fct_sales",
    "UPDATE marts.fct_sales SET quantity = 0",
    "INSERT INTO marts.fct_sales VALUES (1)",
    "CREATE TABLE x AS SELECT 1",
    "SELECT 1; SELECT 2",
    "SELECT * FROM raw.customers",
    "SELECT * FROM staging.stg_products",
    "SELECT * FROM information_schema.tables",
    "SELECT * FROM read_csv('/etc/passwd')",
    "SELECT * FROM read_parquet('s3://bucket/x.parquet')",
    "SELECT * FROM glob('*')",
    "ATTACH 'other.db'",
    "PRAGMA version",
    "COPY marts.fct_sales TO 'out.csv'",
    "SELECT * FROM marts.secret_table",
    "SELECT * FROM other_db.marts.fct_sales",
    "",
    "this is not sql",
])
def test_rejects_unsafe_sql(sql):
    with pytest.raises(SqlGuardError):
        validate_sql(sql, TABLES)


def test_allows_select_with_cte_and_join_and_adds_limit():
    sql = validate_sql("WITH t AS (SELECT * FROM marts.fct_sales) SELECT c.region, count(*) FROM t "
                       "JOIN dim_customers c USING (customer_id) GROUP BY 1", TABLES, max_rows=50)
    assert sql.endswith("LIMIT 50")


def test_keeps_existing_limit():
    assert validate_sql("SELECT * FROM marts.fct_sales LIMIT 5", TABLES).endswith("LIMIT 5")


def test_connection_is_read_only_even_without_guard(warehouse):
    """Defense in depth: the DuckDB connection itself rejects writes and file access."""
    con = warehouse._connect()
    try:
        with pytest.raises(duckdb.Error):
            con.execute("CREATE TABLE marts.hacked AS SELECT 1")
        with pytest.raises(duckdb.Error):
            con.execute("SELECT * FROM read_csv('pyproject.toml')")
    finally:
        con.close()


def test_warehouse_run_returns_jsonable_rows(warehouse):
    d = warehouse.run("SELECT order_date, revenue FROM marts.fct_sales LIMIT 1").to_dict()
    assert isinstance(d["rows"][0][0], str) and isinstance(d["rows"][0][1], float)
