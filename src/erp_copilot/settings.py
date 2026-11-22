"""Paths and runtime configuration (overridable with environment variables)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(os.environ.get("ERP_COPILOT_HOME", Path(__file__).resolve().parents[2]))


@dataclass(frozen=True)
class Settings:
    raw_dir: Path
    duckdb_path: Path
    dbt_dir: Path
    sop_dir: Path
    index_path: Path
    llm_provider: str      # "ollama" | "openai" (any OpenAI-compatible server, e.g. vLLM) | "none"
    llm_model: str
    llm_base_url: str
    embed_model: str        # "" disables dense retrieval (BM25 only)


def get_settings() -> Settings:
    env = os.environ.get
    return Settings(
        raw_dir=Path(env("ERP_RAW_DIR", PROJECT_ROOT / "data" / "raw")),
        duckdb_path=Path(env("ERP_DUCKDB_PATH", PROJECT_ROOT / "warehouse" / "erp.duckdb")),
        dbt_dir=Path(env("ERP_DBT_DIR", PROJECT_ROOT / "dbt")),
        sop_dir=Path(env("ERP_SOP_DIR", PROJECT_ROOT / "docs" / "sop")),
        index_path=Path(env("ERP_INDEX_PATH", PROJECT_ROOT / "warehouse" / "sop_index.json")),
        llm_provider=env("LLM_PROVIDER", "ollama"),
        llm_model=env("LLM_MODEL", "qwen2.5-coder:3b"),
        llm_base_url=env("LLM_BASE_URL", "http://127.0.0.1:11434"),
        embed_model=env("EMBED_MODEL", ""),
    )
