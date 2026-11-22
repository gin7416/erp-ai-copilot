import math

import pytest

from erp_copilot.llm import ScriptedChat
from erp_copilot.rag import SopIndex, SopQA, chunk_markdown, tokenize
from erp_copilot.settings import PROJECT_ROOT

SOP = PROJECT_ROOT / "docs" / "sop"


def test_tokenize_uses_cjk_bigrams_and_ascii_words():
    assert tokenize("SSD 保固年限") == ["ssd", "保固", "固年", "年限"]
    assert tokenize("料") == ["料"]


def test_chunking_one_chunk_per_section():
    md = "# 標題\n\n## 第一節\n內容一\n\n## 第二節\n內容二\n"
    chunks = chunk_markdown("doc", md)
    assert [c.chunk_id for c in chunks] == ["doc#1", "doc#2"]
    assert chunks[1].section == "第二節" and chunks[1].doc_title == "標題"


@pytest.fixture(scope="module")
def index():
    return SopIndex.from_directory(SOP)


@pytest.mark.parametrize("q,expected", [
    ("企業級 SSD 保固幾年", "rma#1"),
    ("採購金額 150 萬要誰核准", "purchasing#1"),
    ("延遲交貨罰款上限", "supplier_delay#4"),
])
def test_bm25_finds_expected_section(index, q, expected):
    assert index.search(q, k=1)[0]["chunk_id"] == expected


class CharEmbedder:
    """Deterministic toy embedder: bag of characters (enough to exercise dense/hybrid code paths)."""
    name = "toy"

    def embed(self, texts):
        vocab = "採購庫存供應商延遲退貨保固訂單取消資料權限盤點"
        return [[float(t.count(ch)) for ch in vocab] for t in texts]


def test_dense_and_hybrid_search(index, tmp_path):
    index.add_embeddings(CharEmbedder())
    for mode in ("dense", "hybrid"):
        hits = index.search("退貨保固", k=3, mode=mode, embedder=CharEmbedder())
        assert len(hits) == 3 and hits[0]["score"] >= hits[1]["score"]
    path = tmp_path / "idx.json"
    index.save(path)
    loaded = SopIndex.load(path)
    assert len(loaded.chunks) == len(index.chunks) and loaded.embed_model == "toy"
    assert math.isclose(loaded.embeddings[0][0], index.embeddings[0][0])


def test_dense_requires_embedder(index):
    with pytest.raises(ValueError):
        index.search("x", mode="dense")


def test_sop_qa_returns_cited_sources(index):
    qa = SopQA(ScriptedChat(["企業級 SSD 保固 5 年 [1]。"]), index)
    out = qa.ask("企業級 SSD 保固幾年？")
    assert out["sources"][0]["chunk_id"] == "rma#1"
    assert "SOP 段落" in qa.chat.calls[0][0]["content"]
