"""Daily ERP pipeline: land raw CSVs -> dbt build (models + data tests) -> SOP index -> retrieval regression check.

The DAG only orchestrates; each task shells out to the project's own virtualenv
(ERP_COPILOT_PYTHON) so Airflow's dependency pins never clash with dbt / DuckDB.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta

try:  # Airflow 3
    from airflow.providers.standard.operators.bash import BashOperator
    from airflow.sdk import DAG
except ImportError:  # Airflow 2.x
    from airflow import DAG
    from airflow.operators.bash import BashOperator

PROJECT = os.environ.get("ERP_COPILOT_HOME", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
PYTHON = os.environ.get("ERP_COPILOT_PYTHON", "python")
ENV = {"ERP_COPILOT_HOME": PROJECT, "PATH": os.environ.get("PATH", ""), "LLM_PROVIDER": "none",
       "EMBED_MODEL": os.environ.get("EMBED_MODEL", "")}

default_args = {"owner": "data-platform", "retries": 2, "retry_delay": timedelta(minutes=5)}

with DAG(
    dag_id="erp_pipeline",
    description="ERP raw -> dbt marts -> SOP index -> retrieval regression check",
    start_date=datetime(2026, 1, 1),
    schedule="0 6 * * *",
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    tags=["erp", "dbt", "rag"],
) as dag:
    load_raw = BashOperator(
        task_id="load_raw",
        bash_command=f"cd {PROJECT} && {PYTHON} -m erp_copilot.pipeline load",
        env=ENV,
    )
    dbt_build = BashOperator(
        task_id="dbt_build",
        bash_command=f"cd {PROJECT} && {PYTHON} -m erp_copilot.pipeline dbt-build",
        env=ENV,
    )
    build_sop_index = BashOperator(
        task_id="build_sop_index",
        bash_command=f"cd {PROJECT} && {PYTHON} -m erp_copilot.pipeline index",
        env=ENV,
    )
    retrieval_check = BashOperator(
        task_id="retrieval_regression_check",
        bash_command=(f"cd {PROJECT} && {PYTHON} -m erp_copilot.evaluation retrieval --modes bm25 "
                      "--min-hit-at-3 0.8 --no-write"),
        env=ENV,
    )

    load_raw >> dbt_build >> build_sop_index >> retrieval_check
