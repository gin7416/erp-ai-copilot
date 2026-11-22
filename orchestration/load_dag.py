"""Import the DAG file directly (no scheduler / DagBag needed)."""
import importlib.util
from pathlib import Path

DAG_FILE = Path(__file__).parent / "dags" / "erp_pipeline.py"


def load_dag():
    spec = importlib.util.spec_from_file_location("erp_pipeline", DAG_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.dag
