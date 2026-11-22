from pathlib import Path

import pytest

from erp_copilot.pipeline import dbt_build, load_raw
from erp_copilot.settings import PROJECT_ROOT, Settings
from erp_copilot.warehouse import Warehouse


def make_settings(tmp: Path) -> Settings:
    return Settings(raw_dir=PROJECT_ROOT / "data" / "raw", duckdb_path=tmp / "erp.duckdb", dbt_dir=PROJECT_ROOT / "dbt",
                    sop_dir=PROJECT_ROOT / "docs" / "sop", index_path=tmp / "sop_index.json",
                    llm_provider="none", llm_model="", llm_base_url="", embed_model="")


@pytest.fixture(scope="session")
def settings(tmp_path_factory) -> Settings:
    """Build the warehouse once per test session: raw load + full dbt build (models and data tests)."""
    s = make_settings(tmp_path_factory.mktemp("warehouse"))
    load_raw(s)
    dbt_build(s)
    return s


@pytest.fixture(scope="session")
def warehouse(settings) -> Warehouse:
    return Warehouse(settings.duckdb_path)
