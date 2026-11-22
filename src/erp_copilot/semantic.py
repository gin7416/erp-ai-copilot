"""Semantic layer for Text-to-SQL: table/column descriptions taken from the dbt marts YAML."""
from __future__ import annotations

from pathlib import Path

import yaml

from .warehouse import Warehouse


def load_dbt_docs(dbt_dir: Path) -> dict[str, dict]:
    """{table: {"description": str, "columns": {col: description}}} from dbt model YAML files."""
    docs: dict[str, dict] = {}
    for path in sorted((Path(dbt_dir) / "models" / "marts").glob("*.yml")):
        for model in (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("models", []):
            docs[model["name"]] = {
                "description": " ".join(str(model.get("description", "")).split()),
                "columns": {c["name"]: " ".join(str(c.get("description", "")).split()) for c in model.get("columns", [])},
            }
    return docs


def schema_context(warehouse: Warehouse, dbt_dir: Path, with_descriptions: bool = True) -> str:
    """Render the marts schema for the prompt; optionally include business-rule descriptions."""
    docs = load_dbt_docs(dbt_dir) if with_descriptions else {}
    blocks = []
    for table, cols in sorted(warehouse.columns().items()):
        info = docs.get(table, {})
        head = f"TABLE marts.{table}"
        if info.get("description"):
            head += f"  -- {info['description']}"
        lines = [head]
        for name, dtype in cols:
            desc = info.get("columns", {}).get(name, "")
            lines.append(f"  {name} {dtype}" + (f"  -- {desc}" if desc else ""))
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def describe_tables(warehouse: Warehouse, dbt_dir: Path) -> list[dict]:
    docs = load_dbt_docs(dbt_dir)
    return [
        {
            "table": f"marts.{table}",
            "description": docs.get(table, {}).get("description", ""),
            "columns": [{"name": n, "type": t, "description": docs.get(table, {}).get("columns", {}).get(n, "")}
                        for n, t in cols],
        }
        for table, cols in sorted(warehouse.columns().items())
    ]
