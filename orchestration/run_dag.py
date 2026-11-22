"""Execute the whole DAG once in-process (`dag.test()`) and exit non-zero unless every task succeeded."""
import sys

from load_dag import load_dag

run = load_dag().test()
states = {ti.task_id: str(ti.state) for ti in run.get_task_instances()}
print("dag run:", run.state, states)
sys.exit(0 if str(run.state) == "success" and all(s == "success" for s in states.values()) else 1)
