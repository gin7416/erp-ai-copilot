"""Retrieval over SOP documents: Chinese-aware BM25, optional dense embeddings, hybrid RRF, grounded answers."""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, Protocol

from .llm import ChatModel

Mode = Literal["bm25", "dense", "hybrid"]
_CJK = re.compile(r"[㐀-鿿豈-﫿]+")
_WORD = re.compile(r"[a-z0-9][a-z0-9_.\-]*")


class Embedder(Protocol):
    name: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...


def tokenize(text: str) -> list[str]:
    """ASCII words + overlapping character bigrams for CJK runs (no external segmenter needed)."""
    text = text.lower()
    tokens = _WORD.findall(text)
    for run in _CJK.findall(text):
        tokens.extend([run] if len(run) == 1 else [run[i:i + 2] for i in range(len(run) - 1)])
    return tokens


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    doc_title: str
    section: str
    text: str


def chunk_markdown(doc_id: str, markdown: str, max_chars: int = 450) -> list[Chunk]:
    """One chunk per `##` section (split further on paragraphs if a section is long)."""
    title_match = re.search(r"^#\s+(.+)$", markdown, re.M)
    title = title_match.group(1).strip() if title_match else doc_id
    chunks: list[Chunk] = []
    for n, part in enumerate(re.split(r"^##\s+", markdown, flags=re.M)[1:], start=1):
        heading, _, body = part.partition("\n")
        paras = [p.strip() for p in body.strip().split("\n\n") if p.strip()]
        buf: list[str] = []
        pieces: list[str] = []
        for para in paras:
            if buf and len("\n".join(buf)) + len(para) > max_chars:
                pieces.append("\n".join(buf))
                buf = []
            buf.append(para)
        if buf:
            pieces.append("\n".join(buf))
        for k, piece in enumerate(pieces, start=1):
            suffix = f"-{k}" if len(pieces) > 1 else ""
            chunks.append(Chunk(f"{doc_id}#{n}{suffix}", doc_id, title, heading.strip(), piece))
    return chunks


class SopIndex:
    def __init__(self, chunks: list[Chunk], embeddings: list[list[float]] | None = None, embed_model: str = ""):
        self.chunks = chunks
        self.embeddings = embeddings
        self.embed_model = embed_model
        self._docs = [tokenize(f"{c.doc_title} {c.section} {c.text}") for c in chunks]
        self._tf = [Counter(d) for d in self._docs]
        self._avgdl = sum(map(len, self._docs)) / max(len(self._docs), 1)
        df = Counter(t for d in self._docs for t in set(d))
        n = len(self._docs)
        self._idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    @classmethod
    def from_directory(cls, sop_dir: Path) -> SopIndex:
        chunks: list[Chunk] = []
        for path in sorted(Path(sop_dir).glob("*.md")):
            chunks += chunk_markdown(path.stem, path.read_text(encoding="utf-8"))
        return cls(chunks)

    def add_embeddings(self, embedder: Embedder, batch: int = 16) -> None:
        texts = [f"{c.doc_title} / {c.section}\n{c.text}" for c in self.chunks]
        vectors: list[list[float]] = []
        for i in range(0, len(texts), batch):
            vectors += embedder.embed(texts[i:i + batch])
        self.embeddings, self.embed_model = vectors, embedder.name

    def save(self, path: Path) -> None:
        Path(path).write_text(json.dumps({"embed_model": self.embed_model, "chunks": [asdict(c) for c in self.chunks],
                                          "embeddings": self.embeddings}, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> SopIndex:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls([Chunk(**c) for c in data["chunks"]], data.get("embeddings"), data.get("embed_model", ""))

    # --- scoring -----------------------------------------------------------
    def _bm25(self, query: str, k1: float = 1.5, b: float = 0.75) -> list[float]:
        q = tokenize(query)
        scores = []
        for tf, doc in zip(self._tf, self._docs):
            s = 0.0
            for t in q:
                if t in tf:
                    f = tf[t]
                    s += self._idf[t] * f * (k1 + 1) / (f + k1 * (1 - b + b * len(doc) / self._avgdl))
            scores.append(s)
        return scores

    def _dense(self, query: str, embedder: Embedder) -> list[float]:
        if not self.embeddings:
            raise ValueError("index has no embeddings; build it with EMBED_MODEL set")
        qv = embedder.embed([query])[0]
        qn = math.sqrt(sum(x * x for x in qv)) or 1.0
        out = []
        for v in self.embeddings:
            vn = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append(sum(a * b for a, b in zip(qv, v)) / (qn * vn))
        return out

    def search(self, query: str, k: int = 3, mode: Mode = "bm25", embedder: Embedder | None = None) -> list[dict]:
        def ranked(scores: list[float]) -> list[int]:
            return sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)

        if mode == "bm25":
            scores = self._bm25(query)
        elif mode == "dense":
            if embedder is None:
                raise ValueError("dense search needs an embedder")
            scores = self._dense(query, embedder)
        elif mode == "hybrid":
            if embedder is None:
                raise ValueError("hybrid search needs an embedder")
            fused = [0.0] * len(self.chunks)
            for order in (ranked(self._bm25(query)), ranked(self._dense(query, embedder))):
                for rank, i in enumerate(order, start=1):
                    fused[i] += 1.0 / (60 + rank)   # reciprocal rank fusion
            scores = fused
        else:
            raise ValueError(f"unknown mode {mode}")
        return [{**asdict(self.chunks[i]), "score": round(scores[i], 6)} for i in ranked(scores)[:k]]


ANSWER_PROMPT = """你是公司內部 SOP 問答助理。只能根據下列 SOP 段落回答，使用繁體中文，回答要簡潔。
每個重點後面用 [編號] 標註來源段落。如果段落中沒有答案，請回答「SOP 中沒有相關規定」，不要自行推測。

SOP 段落：
{context}"""


class SopQA:
    def __init__(self, chat: ChatModel, index: SopIndex, embedder: Embedder | None = None, mode: Mode = "bm25", k: int = 3):
        self.chat, self.index, self.embedder, self.mode, self.k = chat, index, embedder, mode, k

    def ask(self, question: str) -> dict:
        hits = self.index.search(question, k=self.k, mode=self.mode, embedder=self.embedder)
        context = "\n\n".join(f"[{n}] 《{h['doc_title']}》{h['section']}\n{h['text']}" for n, h in enumerate(hits, start=1))
        answer = self.chat.chat([{"role": "system", "content": ANSWER_PROMPT.format(context=context)},
                                 {"role": "user", "content": question}])
        cited = sorted({int(n) for n in re.findall(r"\[(\d+)\]", answer) if 1 <= int(n) <= len(hits)})
        return {"question": question, "answer": answer.strip(),
                "sources": [{"ref": n, "chunk_id": hits[n - 1]["chunk_id"], "doc_title": hits[n - 1]["doc_title"],
                             "section": hits[n - 1]["section"]} for n in cited] or
                           [{"ref": n, "chunk_id": h["chunk_id"], "doc_title": h["doc_title"], "section": h["section"]}
                            for n, h in enumerate(hits, start=1)],
                "model": self.chat.name}
