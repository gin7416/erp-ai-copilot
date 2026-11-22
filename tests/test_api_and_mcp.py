import json

import anyio
import pytest
from fastapi.testclient import TestClient
from mcp import Client

from erp_copilot.api import app, get_copilot
from erp_copilot.copilot import Copilot
from erp_copilot.llm import ScriptedChat
from erp_copilot.mcp_server import build_server


@pytest.fixture
def client_factory(settings):
    def make(replies=None):
        chat = ScriptedChat(replies) if replies is not None else None
        copilot = Copilot(settings, chat=chat)
        app.dependency_overrides[get_copilot] = lambda: copilot
        return TestClient(app)
    yield make
    app.dependency_overrides.clear()


def test_health_and_tables(client_factory):
    c = client_factory()
    h = c.get("/health").json()
    assert h["status"] == "ok" and h["warehouse_ready"] and h["llm"] is None and h["retrieval"] == "bm25"
    tables = {t["table"]: t for t in c.get("/tables").json()}
    assert "marts.fct_sales" in tables and "cancelled" in tables["marts.fct_sales"]["description"]


def test_sql_endpoint_runs_and_rejects(client_factory):
    c = client_factory()
    ok = c.post("/sql", json={"sql": "select count(*) as n from marts.dim_warehouses"})
    assert ok.status_code == 200 and ok.json()["rows"] == [[3]]
    assert c.post("/sql", json={"sql": "drop table marts.fct_sales"}).status_code == 400
    assert c.post("/sql", json={"sql": "select nope from marts.fct_sales"}).status_code == 400
    assert c.post("/sql", json={"sql": "select 1", "extra": True}).status_code == 422


def test_ask_data_with_llm(client_factory):
    c = client_factory(["```sql\nSELECT region, count(*) AS n FROM marts.dim_customers GROUP BY 1\n```"])
    body = c.post("/ask/data", json={"question": "各地區有幾位客戶？"}).json()
    assert body["ok"] and body["row_count"] == 5 and body["columns"] == ["region", "n"]


def test_llm_endpoints_return_503_without_llm(client_factory):
    c = client_factory()
    assert c.post("/ask/data", json={"question": "各地區有幾位客戶？"}).status_code == 503
    assert c.post("/ask/sop", json={"question": "保固幾年？"}).status_code == 503


def test_sop_search_and_answer(client_factory):
    c = client_factory(["保固 5 年 [1]"])
    hits = c.get("/search/sop", params={"q": "企業級 SSD 保固", "k": 2}).json()["hits"]
    assert hits[0]["chunk_id"] == "rma#1"
    ans = c.post("/ask/sop", json={"question": "企業級 SSD 保固幾年？"}).json()
    assert ans["sources"][0]["chunk_id"] == "rma#1"


def _text(result) -> object:
    return json.loads(result.content[0].text)


def test_mcp_tools(settings):
    copilot = Copilot(settings, chat=ScriptedChat(["```sql\nSELECT count(*) AS n FROM marts.dim_products\n```"]))

    async def scenario():
        async with Client(build_server(copilot)) as mcp:
            names = {t.name for t in (await mcp.list_tools()).tools}
            assert names == {"list_tables", "run_sql", "search_sop", "ask_data"}
            ok = _text(await mcp.call_tool("run_sql", {"sql": "select count(*) as n from marts.dim_suppliers"}))
            assert ok["rows"] == [[8]]
            blocked = _text(await mcp.call_tool("run_sql", {"sql": "delete from marts.dim_suppliers"}))
            assert "only SELECT" in blocked["error"]
            hit = _text(await mcp.call_tool("search_sop", {"query": "急單加急費", "k": 1}))
            assert hit["chunk_id"] == "order_change#4"
            answer = _text(await mcp.call_tool("ask_data", {"question": "有幾個產品？"}))
            assert answer["ok"] and answer["rows"] == [[20]]

    anyio.run(scenario)
