"""DAG structure test; runs in the `airflow` CI job (Airflow is kept out of the project's own virtualenv)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from load_dag import load_dag  # noqa: E402

ORDER = ["load_raw", "dbt_build", "build_sop_index", "retrieval_regression_check"]


def test_dag_structure():
    dag = load_dag()
    assert dag.dag_id == "erp_pipeline"
    assert {t.task_id for t in dag.tasks} == set(ORDER)
    for upstream, downstream in zip(ORDER, ORDER[1:]):
        assert downstream in dag.get_task(upstream).downstream_task_ids
    assert all(t.retries == 2 for t in dag.tasks)
