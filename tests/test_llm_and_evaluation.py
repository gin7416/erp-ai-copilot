import json

import httpx
import pytest

from erp_copilot.evaluation import evaluate_retrieval, evaluate_sql, oracle_factory
from erp_copilot.evaluation.compare import lenient_match, strict_match
from erp_copilot.llm import OllamaChat, OllamaEmbedder, OpenAICompatibleChat, make_chat
from erp_copilot.rag import SopIndex


def mock_client(base_url, handler):
    return httpx.Client(base_url=base_url, transport=httpx.MockTransport(handler))


def test_ollama_chat_payload():
    seen = {}

    def handler(req):
        seen.update(json.loads(req.content))
        assert req.url.path == "/api/chat"
        return httpx.Response(200, json={"message": {"content": "SELECT 1"}})

    chat = OllamaChat("qwen2.5-coder:3b", client=mock_client("http://ollama", handler))
    assert chat.chat([{"role": "user", "content": "hi"}]) == "SELECT 1"
    assert seen["stream"] is False and seen["options"]["temperature"] == 0


def test_openai_compatible_chat_payload():
    def handler(req):
        assert req.url.path == "/v1/chat/completions"
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    assert OpenAICompatibleChat("m", "http://vllm", client=mock_client("http://vllm", handler)).chat([]) == "ok"


def test_embedder_and_factory():
    def handler(req):
        return httpx.Response(200, json={"embeddings": [[0.1, 0.2]] * len(json.loads(req.content)["input"])})

    assert OllamaEmbedder(client=mock_client("http://o", handler)).embed(["a", "b"]) == [[0.1, 0.2]] * 2
    assert make_chat("none", "", "") is None
    with pytest.raises(ValueError):
        make_chat("bogus", "", "")


@pytest.mark.parametrize("cand,ref,strict,lenient", [
    ([[1, "a"], [2, "b"]], [[2, "b"], [1, "a"]], True, True),          # order ignored
    ([[0.333333]], [[0.33]], True, True),                               # rounding
    ([["P001", "x"]], [["x"]], False, True),                            # extra helper column
    ([["a", 1]], [[1, "a"]], False, True),                              # column order
    ([[1]], [[2]], False, False),
    ([[1], [1]], [[1]], False, False),                                  # row count differs
])
def test_result_comparison(cand, ref, strict, lenient):
    assert strict_match(cand, ref) is strict
    assert lenient_match(cand, ref) is lenient


def test_oracle_scores_100_percent(settings):
    result = evaluate_sql(settings, oracle_factory, ["schema_only", "semantic_retry"])
    for cfg in result["configs"].values():
        assert cfg["summary"]["lenient_acc"] == 1.0 and cfg["summary"]["strict_acc"] == 1.0


def test_bm25_retrieval_regression_gate(settings):
    result = evaluate_retrieval(SopIndex.from_directory(settings.sop_dir), ["bm25"])
    assert result["modes"]["bm25"]["hit@3"] >= 0.8


def test_report_renders_committed_results():
    from erp_copilot.evaluation.report import render
    text = render()
    assert "In-house Text-to-SQL" in text and "In-house SOP retrieval" in text
