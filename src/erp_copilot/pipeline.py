"""Pipeline steps shared by the CLI and the Airflow DAG.

    python -m erp_copilot.pipeline load        # CSV -> DuckDB raw schema (all VARCHAR)
    python -m erp_copilot.pipeline dbt-build   # dbt run + dbt test (staging -> marts)
    python -m erp_copilot.pipeline index       # build the SOP retrieval index
    python -m erp_copilot.pipeline all
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from .settings import Settings, get_settings

RAW_TABLES = ["products", "suppliers", "warehouses", "customers", "sales_orders",
              "sales_order_lines", "purchase_orders", "inventory_snapshots"]


def load_raw(settings: Settings | None = None) -> dict[str, int]:
    """Land each CSV unchanged (as strings) in the `raw` schema; typing happens in dbt staging."""
    s = settings or get_settings()
    s.duckdb_path.parent.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    with duckdb.connect(str(s.duckdb_path)) as con:
        con.execute("CREATE SCHEMA IF NOT EXISTS raw")
        con.execute("CREATE TABLE IF NOT EXISTS raw._load_audit (table_name VARCHAR, row_count BIGINT, source_file VARCHAR, loaded_at TIMESTAMP)")
        for table in RAW_TABLES:
            path = s.raw_dir / f"{table}.csv"
            if not path.exists():
                raise FileNotFoundError(path)
            con.execute(
                f"CREATE OR REPLACE TABLE raw.{table} AS "
                "SELECT * FROM read_csv(?, header = true, all_varchar = true)",
                [str(path)],
            )
            n = con.execute(f"SELECT count(*) FROM raw.{table}").fetchone()[0]
            con.execute("INSERT INTO raw._load_audit VALUES (?, ?, ?, ?)",
                        [table, n, path.name, datetime.now(timezone.utc).replace(tzinfo=None)])
            counts[table] = n
    return counts


def _dbt_executable() -> str:
    candidate = Path(sys.executable).parent / "dbt"
    return str(candidate) if candidate.exists() else (shutil.which("dbt") or "dbt")


def dbt_build(settings: Settings | None = None) -> str:
    """Run `dbt build` (models + data tests) in a subprocess; raise with dbt's output if anything fails.

    A subprocess (rather than dbtRunner in-process) guarantees dbt's DuckDB connection is closed
    before the API or tests open the warehouse read-only.
    """
    s = settings or get_settings()
    env = {**os.environ, "ERP_DUCKDB_PATH": str(s.duckdb_path.resolve()), "DBT_SEND_ANONYMOUS_USAGE_STATS": "false",
           "DBT_USE_COLORS": "false"}
    cmd = [_dbt_executable(), "build", "--project-dir", str(s.dbt_dir), "--profiles-dir", str(s.dbt_dir)]
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"dbt build failed:\n{proc.stdout[-4000:]}\n{proc.stderr[-2000:]}")
    return next((line.strip() for line in reversed(proc.stdout.splitlines()) if "PASS=" in line), "")


def build_index(settings: Settings | None = None) -> Path:
    from .rag import SopIndex

    s = settings or get_settings()
    index = SopIndex.from_directory(s.sop_dir)
    if s.embed_model:
        from .llm import OllamaEmbedder
        index.add_embeddings(OllamaEmbedder(s.embed_model, s.llm_base_url))
    s.index_path.parent.mkdir(parents=True, exist_ok=True)
    index.save(s.index_path)
    return s.index_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("step", choices=["load", "dbt-build", "index", "all"])
    step = parser.parse_args().step
    if step in ("load", "all"):
        print("loaded:", load_raw())
    if step in ("dbt-build", "all"):
        print("dbt build:", dbt_build())
    if step in ("index", "all"):
        print("index written:", build_index())


if __name__ == "__main__":
    main()
