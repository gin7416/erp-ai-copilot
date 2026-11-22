"""Wires settings, warehouse, LLM and SOP index together; shared by the API, MCP server and evaluation."""
from __future__ import annotations

from functools import cached_property

from .llm import ChatModel, OllamaEmbedder, make_chat
from .rag import Embedder, SopIndex, SopQA
from .semantic import describe_tables, schema_context
from .settings import Settings, get_settings
from .text_to_sql import TextToSQL
from .warehouse import Warehouse


class LLMNotConfigured(RuntimeError):
    pass


class Copilot:
    def __init__(self, settings: Settings | None = None, chat: ChatModel | None = None,
                 embedder: Embedder | None = None):
        self.settings = s = settings or get_settings()
        self.warehouse = Warehouse(s.duckdb_path)
        self.chat = chat if chat is not None else make_chat(s.llm_provider, s.llm_model, s.llm_base_url)
        self.embedder = embedder if embedder is not None else (
            OllamaEmbedder(s.embed_model, s.llm_base_url) if s.embed_model else None)

    @cached_property
    def index(self) -> SopIndex:
        if self.settings.index_path.exists():
            return SopIndex.load(self.settings.index_path)
        return SopIndex.from_directory(self.settings.sop_dir)

    @property
    def retrieval_mode(self) -> str:
        return "hybrid" if self.embedder is not None and self.index.embeddings else "bm25"

    def _require_chat(self) -> ChatModel:
        if self.chat is None:
            raise LLMNotConfigured("LLM_PROVIDER=none; set LLM_PROVIDER=ollama or openai to enable this endpoint")
        return self.chat

    @cached_property
    def text_to_sql(self) -> TextToSQL:
        return TextToSQL(self._require_chat(), self.warehouse, schema_context(self.warehouse, self.settings.dbt_dir))

    @cached_property
    def sop_qa(self) -> SopQA:
        return SopQA(self._require_chat(), self.index, self.embedder, mode=self.retrieval_mode)  # type: ignore[arg-type]

    def tables(self) -> list[dict]:
        return describe_tables(self.warehouse, self.settings.dbt_dir)

    def search_sop(self, query: str, k: int = 3) -> list[dict]:
        return self.index.search(query, k=k, mode=self.retrieval_mode, embedder=self.embedder)  # type: ignore[arg-type]
