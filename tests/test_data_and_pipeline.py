import filecmp

import duckdb

from erp_copilot.generate_data import INJECTED_ISSUES, generate
from erp_copilot.pipeline import RAW_TABLES
from erp_copilot.settings import PROJECT_ROOT


def test_generator_is_deterministic_and_matches_committed_data(tmp_path):
    generate(tmp_path / "a")
    generate(tmp_path / "b")
    committed = PROJECT_ROOT / "data" / "raw"
    for table in RAW_TABLES:
        assert filecmp.cmp(tmp_path / "a" / f"{table}.csv", tmp_path / "b" / f"{table}.csv", shallow=False)
        assert filecmp.cmp(tmp_path / "a" / f"{table}.csv", committed / f"{table}.csv", shallow=False), table


def test_raw_load_is_audited(settings):
    with duckdb.connect(str(settings.duckdb_path), read_only=True) as con:
        audited = {r[0] for r in con.execute("select table_name from raw._load_audit").fetchall()}
        types = {r[0] for r in con.execute(
            "select distinct data_type from information_schema.columns where table_schema = 'raw' "
            "and table_name <> '_load_audit'").fetchall()}
    assert audited == set(RAW_TABLES)
    assert types == {"VARCHAR"}  # raw layer is untyped; dbt staging does the casting


def test_marts_built(warehouse):
    assert warehouse.mart_tables() == {"dim_customers", "dim_products", "dim_suppliers", "dim_warehouses",
                                       "fct_inventory", "fct_purchase_orders", "fct_sales"}


def test_injected_quality_issues_are_caught_and_explained(warehouse, settings):
    with duckdb.connect(str(settings.duckdb_path), read_only=True) as con:
        issues = dict(con.execute("select issue, count(*) from audit.dq_order_line_issues group by 1").fetchall())
        raw_n = con.execute("select count(*) from raw.sales_order_lines").fetchone()[0]
        kept_n = con.execute("select count(*) from marts.fct_sales").fetchone()[0]
    assert issues == {"duplicate_row": INJECTED_ISSUES["duplicate_order_lines"],
                      "non_positive_quantity": INJECTED_ISSUES["non_positive_quantity_lines"]}
    assert raw_n == kept_n + sum(issues.values())


def test_staging_cleans_dirty_values(warehouse):
    skus = warehouse.run("select sku from marts.dim_products").rows
    assert all(s[0] == s[0].strip().upper() for s in skus)
    regions = {r[0] for r in warehouse.run("select distinct region from marts.dim_customers").rows}
    assert regions <= {"台灣", "中國", "日本", "美國", "歐洲"}
